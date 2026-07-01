from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class WmsFuelLog(models.Model):
    """Fuel draw log — generator / vehicle / pump refuelling.

    Confirming creates an internal stock.picking that moves the quantity filled
    from the fuel's storage slot to the trust-use (consumed) location, so the
    diesel / petrol stock decrements in real time. It records who filled it,
    when, into which equipment, and the meter reading (odometer km or running
    hours) so consumption-per-km / per-hour and service intervals can be tracked.

    Pattern: mirrors the Damage event (draft -> confirmed, source-slot stock
    guard, keeper-locked once confirmed, audit chatter). The picking build +
    validate reuses the same in-addon flow as Scan Issue (create -> confirm ->
    assign -> abort-if-not-fully-assigned -> button_validate).
    """

    _name = "wms.fuel.log"
    _description = "Fuel log"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "fill_datetime desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft",
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Fuel",
        required=True,
        tracking=True,
        help="The fuel being drawn (e.g. Diesel, Petrol).",
    )
    quantity = fields.Float(
        string="Quantity filled",
        required=True,
        default=0.0,
        tracking=True,
        help="How much fuel went into the equipment, in the product's unit "
        "(usually litres).",
    )
    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "Fuel quantity filled must be greater than zero.",
    )
    source_slot_id = fields.Many2one(
        "stock.location",
        string="Taken from",
        domain=[("wms_location_type", "in", ("slot", "floor"))],
        required=True,
        tracking=True,
        ondelete="restrict",
        help="Where the fuel is stored — the tank / drum slot it was drawn from.",
    )
    asset = fields.Selection(
        [
            ("generator", "Generator"),
            ("vehicle", "Vehicle"),
            ("tractor", "Tractor"),
            ("pump", "Pump"),
            ("other", "Other"),
        ],
        string="Filled into",
        required=True,
        default="generator",
        tracking=True,
    )
    asset_name = fields.Char(
        string="Equipment name / number",
        help="Which one — e.g. 'Generator 1', the vehicle number, 'Borewell pump'.",
    )
    meter_type = fields.Selection(
        [
            ("none", "No meter"),
            ("odometer", "Odometer (km)"),
            ("hours", "Running hours"),
        ],
        string="Meter",
        default="none",
        required=True,
    )
    meter_reading = fields.Float(
        string="Meter reading",
        help="Odometer km or generator running-hours at the time of filling — "
        "lets you track fuel per km / per hour and service intervals.",
    )
    _meter_reading_non_negative = models.Constraint(
        "CHECK(meter_reading >= 0)",
        "Meter reading cannot be negative.",
    )
    filled_by = fields.Char(
        string="Filled by",
        index=True,
        tracking=True,
        help="Name of the person who filled the fuel. Plain text — not every "
        "worker has an Odoo login.",
    )
    wms_storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        index=True,
        tracking=True,
        domain=[("active", "=", True)],
        default=lambda s: s._default_storekeeper_id(),
        help="The on-duty Store Keeper who logged this fuel draw — same roster "
        "as Scan Issue / Receipt.",
    )
    fill_datetime = fields.Datetime(
        string="Filled on",
        default=lambda s: fields.Datetime.now(),
        tracking=True,
    )
    note = fields.Text()
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        compute="_compute_warehouse",
        store=True,
    )
    fuel_value = fields.Float(
        string="Value",
        readonly=True,
        copy=False,
        help="Quantity x the fuel's unit cost, snapshotted when the log was "
        "confirmed. Not recomputed later.",
    )

    @api.model
    def _default_storekeeper_id(self):
        return self.env["wms.storekeeper"].search(
            [("user_id", "=", self.env.uid), ("active", "=", True)], limit=1
        )

    @api.depends("source_slot_id")
    def _compute_warehouse(self):
        # Walk up to a warehouse binding; fall back to the company's primary WH
        # (same out-of-tree fallback as the damage event / FIFO planner).
        Warehouse = self.env["stock.warehouse"]
        for rec in self:
            loc = rec.source_slot_id
            while loc and not loc.warehouse_id:
                loc = loc.location_id
            rec.warehouse_id = (
                loc.warehouse_id
                if (loc and loc.warehouse_id)
                else Warehouse.search([("company_id", "=", rec.env.company.id)], limit=1)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("wms.fuel.log") or "FUEL/0001"
                )
        return super().create(vals_list)

    @api.constrains("product_id", "quantity", "source_slot_id", "state")
    def _check_source_slot_stock(self):
        """Refuse to log more fuel than the tank slot actually has free
        (total - reserved) — same guard as the damage event."""
        Quant = self.env["stock.quant"].sudo()
        for rec in self:
            if rec.state == "confirmed":
                continue
            if not (rec.product_id and rec.source_slot_id and rec.quantity):
                continue
            quants = Quant.search(
                [
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "=", rec.source_slot_id.id),
                ]
            )
            free = max(
                0.0,
                sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity")),
            )
            if rec.quantity > free + 0.0001:
                raise UserError(
                    "You're logging %g of %s taken from %s, but only %g is "
                    "actually there. Re-check the tank level or the quantity."
                    % (
                        rec.quantity,
                        rec.product_id.display_name,
                        rec.source_slot_id.display_name,
                        free,
                    )
                )

    def _issue_destination(self):
        """Consumed fuel goes to the trust's 'used' location (same default as
        Scan Issue), falling back to the customer location if the WMS seed
        hasn't loaded."""
        dest = self.env.ref(
            "wms_location.stock_location_trust_use", raise_if_not_found=False
        )
        return dest or self.env.ref(
            "stock.stock_location_customers", raise_if_not_found=False
        )

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
            missing = []
            if not (rec.filled_by or "").strip():
                missing.append("Filled by")
            if not rec.wms_storekeeper_id:
                missing.append("Store Keeper on duty")
            if rec.meter_type != "none" and not rec.meter_reading:
                missing.append("Meter reading")
            if missing:
                raise UserError(
                    "Fill in %s before confirming this fuel log." % ", ".join(missing)
                )

            destination = rec._issue_destination()
            if not destination:
                raise UserError(
                    "No consumption / usage location is configured to record fuel use."
                )
            picking_type = rec.warehouse_id.int_type_id
            if not picking_type:
                raise UserError(
                    "Warehouse %s isn't set up for internal stock transfers. Ask "
                    "an Administrator to enable them." % rec.warehouse_id.display_name
                )
            if not picking_type.active:
                picking_type.sudo().active = True

            asset_label = dict(rec._fields["asset"].selection).get(rec.asset, rec.asset)
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": rec.source_slot_id.id,
                    "location_dest_id": destination.id,
                    "origin": rec.name,
                }
            )
            move = self.env["stock.move"].create(
                {
                    "description_picking": "Fuel: %s -> %s" % (
                        rec.product_id.display_name,
                        asset_label,
                    ),
                    "product_id": rec.product_id.id,
                    "product_uom_qty": rec.quantity,
                    "product_uom": rec.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": rec.source_slot_id.id,
                    "location_dest_id": destination.id,
                }
            )
            move._action_confirm()
            picking.action_assign()
            # Concurrency safety: only record what we could actually reserve.
            if picking.move_ids.filtered(lambda m: m.state != "assigned"):
                raise UserError(
                    "The fuel couldn't be reserved in full from %s — the tank "
                    "level changed while you were logging. Nothing was recorded; "
                    "re-check and try again." % rec.source_slot_id.display_name
                )
            for ml in move.move_line_ids:
                if not ml.quantity:
                    ml.quantity = ml.quantity_product_uom or move.product_uom_qty
            picking.button_validate()

            rec.write(
                {
                    "state": "confirmed",
                    "picking_id": picking.id,
                    "fuel_value": (rec.quantity or 0.0)
                    * (rec.product_id.standard_price or 0.0),
                }
            )

            body = Markup(
                "<p><b>Fuel logged.</b> %(qty)g of %(fuel)s into <b>%(asset)s</b>, "
                "filled by <b>%(by)s</b>; Store Keeper on duty: <b>%(keeper)s</b>.</p>"
            ) % {
                "qty": rec.quantity,
                "fuel": rec.product_id.display_name,
                "asset": asset_label + ((" " + rec.asset_name) if rec.asset_name else ""),
                "by": rec.filled_by or "(unspecified)",
                "keeper": rec.wms_storekeeper_id.name or "(unknown)",
            }
            if rec.meter_type != "none":
                body += Markup("<p>Meter (%(m)s): <b>%(r)g</b>.</p>") % {
                    "m": dict(rec._fields["meter_type"].selection).get(rec.meter_type),
                    "r": rec.meter_reading,
                }
            rec.message_post(body=body, subject="Fuel log", message_type="notification")

    # Once confirmed the stock has moved and the value is snapshotted, so a
    # keeper must not revise it over RPC. Managers (and internal su paths)
    # bypass; chatter/activity stay writable.
    _KEEPER_ALLOWED_ON_LOCKED = frozenset(
        {
            "message_ids",
            "message_follower_ids",
            "message_partner_ids",
            "message_main_attachment_id",
            "message_is_follower",
            "activity_ids",
        }
    )

    def write(self, vals):
        if (
            not self.env.su
            and set(vals) - self._KEEPER_ALLOWED_ON_LOCKED
            and not self.env.user.has_group("wms_location.group_wms_manager")
        ):
            for rec in self:
                if rec.state == "confirmed":
                    raise AccessError(
                        "Fuel log %s is already confirmed — only a Manager can "
                        "change it. The stock has already moved." % (rec.name or "?")
                    )
        return super().write(vals)

    def action_cancel(self):
        for rec in self:
            if rec.state == "confirmed":
                raise UserError(
                    "Cancel the stock transfer created for this fuel log before "
                    "cancelling the record."
                )
            rec.state = "cancelled"
