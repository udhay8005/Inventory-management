"""In-service asset register — the fans, lights, pumps, motors and fire
extinguishers that were ISSUED OUT and are now installed somewhere.

The gap this closes (owner's question #10): issuing a fan decremented stock
and the trail ended there. Nothing recorded that fan #3 hangs in the
Radharam shed, has done fourteen months, and is due a service. A gaushala
runs on this equipment, so it needs a register of its own:

    what it is  ->  where it is installed  ->  since when  ->  service due

Deliberately NOT a stock model: an installed fan is consumed stock (it left
the shelf via Scan Issue). This is the after-life record, linked back to the
product and, when it breaks, to a Repair order.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WmsAsset(models.Model):
    _name = "wms.asset"
    _description = "In-service asset"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_service_date asc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    product_id = fields.Many2one(
        "product.product",
        string="Item",
        required=True,
        tracking=True,
        help="Which product this is — e.g. the ceiling fan, tube light, "
        "borewell pump or fire extinguisher that was issued out.",
    )
    serial_no = fields.Char(
        string="Serial / tag number",
        index=True,
        tracking=True,
        help="Manufacturer serial, or the tag number you painted on it.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Installed at",
        required=True,
        tracking=True,
        ondelete="restrict",
        help="Where it is physically fitted — a shed, the R&D area, the "
        "office block, the old-plot farm.",
    )
    installed_on = fields.Date(
        string="Installed on",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    installed_by = fields.Char(
        string="Installed by",
        help="Who fitted it. Plain text — not every worker has a login.",
    )
    wms_storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        index=True,
        domain=[("active", "=", True)],
    )
    state = fields.Selection(
        [
            ("in_service", "In service"),
            ("under_repair", "Under repair"),
            ("removed", "Removed"),
            ("scrapped", "Scrapped"),
        ],
        default="in_service",
        required=True,
        index=True,
        tracking=True,
    )

    # ---- servicing ------------------------------------------------------
    service_interval_days = fields.Integer(
        string="Service every (days)",
        default=0,
        help="0 = never needs servicing. A fire extinguisher refilled yearly "
        "is 365; a generator serviced quarterly is 90. Drives the service-due "
        "alert so the trust stops relying on memory.",
    )
    last_service_date = fields.Date(
        string="Last serviced",
        tracking=True,
        help="Leave blank until its first service — the countdown then runs "
        "from the installation date.",
    )
    next_service_date = fields.Date(
        string="Service due",
        compute="_compute_next_service_date",
        store=True,
        index=True,
        help="Last service (or installation) + the interval. Blank when the "
        "item needs no servicing.",
    )
    service_due = fields.Boolean(
        string="Due now",
        compute="_compute_service_due",
        search="_search_service_due",
        help="True once the service date has arrived or passed.",
    )
    repair_order_id = fields.Many2one(
        "wms.repair.order",
        string="Repair order",
        readonly=True,
        copy=False,
        help="Set when the asset was sent for repair from here.",
    )
    note = fields.Text()

    _serial_unique = models.Constraint(
        "UNIQUE(serial_no)",
        "That serial / tag number is already registered against another asset.",
    )
    _service_interval_non_negative = models.Constraint(
        "CHECK(service_interval_days >= 0)",
        "The service interval cannot be negative.",
    )

    @api.depends("installed_on", "last_service_date", "service_interval_days")
    def _compute_next_service_date(self):
        from datetime import timedelta

        for rec in self:
            if rec.service_interval_days and (rec.last_service_date or rec.installed_on):
                base = rec.last_service_date or rec.installed_on
                rec.next_service_date = base + timedelta(days=rec.service_interval_days)
            else:
                rec.next_service_date = False

    @api.depends("next_service_date", "state")
    def _compute_service_due(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.service_due = bool(
                rec.next_service_date
                and rec.next_service_date <= today
                and rec.state in ("in_service", "under_repair")
            )

    def _search_service_due(self, operator, value):
        """Make the "Service due" filter searchable.

        Odoo 19 NORMALISES a boolean search: `('service_due', '=', True)`
        arrives here as operator `in` with an **OrderedSet** — not a list, not
        a tuple. An isinstance(list, tuple) check therefore missed it and the
        method fell through to the negated branch, so the "Service due" filter
        returned exactly the assets that were NOT due. Accept any iterable.
        """
        today = fields.Date.context_today(self)
        due = [
            ("next_service_date", "!=", False),
            ("next_service_date", "<=", today),
            ("state", "in", ("in_service", "under_repair")),
        ]
        if operator in ("in", "not in"):
            try:
                values = list(value)
            except TypeError:  # a bare scalar
                values = [value]
            wants_due = True in values
            if operator == "not in":
                wants_due = not wants_due
        else:
            wants_due = bool(value) if operator == "=" else not bool(value)
        if wants_due:
            return due
        return ["!", ("id", "in", self.search(due).ids)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.asset") or "ASSET/0001"
        return super().create(vals_list)

    # ---- lifecycle ------------------------------------------------------
    def action_service_done(self):
        """Record a service: stamps today and restarts the countdown."""
        for rec in self:
            rec.last_service_date = fields.Date.context_today(rec)
            rec.message_post(
                body=_("Serviced on %s — next due %s.")
                % (rec.last_service_date, rec.next_service_date or _("n/a")),
                subject=_("Asset serviced"),
                message_type="notification",
            )
        return True

    def action_mark_under_repair(self):
        for rec in self:
            if rec.state in ("removed", "scrapped"):
                raise UserError(
                    _("%s is %s — it cannot go for repair.") % (rec.display_name, rec.state)
                )
            rec.state = "under_repair"
        return True

    def action_back_in_service(self):
        for rec in self:
            if rec.state == "scrapped":
                raise UserError(
                    _("%s was scrapped and cannot return to service.") % rec.display_name
                )
            rec.state = "in_service"
        return True

    def action_remove(self):
        self.write({"state": "removed"})
        return True

    def action_scrap(self):
        self.write({"state": "scrapped"})
        return True

    def _compute_display_name(self):
        for rec in self:
            bits = [rec.product_id.display_name or _("Asset")]
            if rec.serial_no:
                bits.append("[%s]" % rec.serial_no)
            if rec.location_id:
                bits.append("@ %s" % rec.location_id.name)
            rec.display_name = " ".join(bits)

    @api.model
    def wms_assets_due_for_service(self):
        """Assets whose service date has arrived — read by the daily
        needs-attention alert."""
        return self.search([("service_due", "=", True)])
