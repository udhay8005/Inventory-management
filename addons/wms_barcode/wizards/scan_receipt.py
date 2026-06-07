from markupsafe import Markup
from odoo import fields, models
from odoo.exceptions import UserError


class WmsScanReceipt(models.TransientModel):
    """Scan-based receipt: build a list of (product, qty, slot) lines
    by repeatedly scanning, then validate to create a stock.picking
    of type 'incoming' against the warehouse stock location.

    Inherits `barcodes.barcode_events_mixin` so any wireless/USB HID scanner
    fires `on_barcode_scanned` automatically — no button click needed.
    """

    _name = "wms.scan.receipt"
    _description = "Scan-based receipt"
    _inherit = ["barcodes.barcode_events_mixin"]

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda s: s.env["stock.warehouse"].search([], limit=1),
    )
    last_scan = fields.Char(
        string="Scan here",
        help="Keep the cursor here and scan away — each barcode is processed automatically.",
    )
    feedback = fields.Char(readonly=True)
    line_ids = fields.One2many("wms.scan.receipt.line", "wizard_id")
    picking_id = fields.Many2one(
        "stock.picking",
        readonly=True,
        copy=False,
        help="The receipt this scan created. Set once validated so a "
        "double-click or a refreshed re-submit cannot receive the same "
        "delivery twice — the second attempt just re-opens the receipt "
        "that was already made.",
    )

    # ---- Return-entry mode ----------------------------------------------
    is_return = fields.Boolean(
        string="Return entry",
        default=lambda s: bool(s.env.context.get("default_is_return")),
        help="Tick this when receiving stock that's coming back into the "
        "warehouse — e.g. a tool returned from production, a spare "
        "borrowed and brought back. Products whose WMS Kind is NOT "
        "returnable (Fluids, Consumables) will be refused at validate.",
    )

    # ---- Quality check ---------------------------------------------------
    # This trust runs internal stock — products aren't sold, no invoices
    # are issued, no money changes hands. So there's no price-based
    # approval gate. The QC checkbox stays: the Receiver still confirms
    # the physical count and condition before the receipt is filed, which
    # is the whole point of responsible tracking.
    qc_passed = fields.Boolean(
        string="Quality check passed",
        help="Receiver confirms physical count and condition match what was expected.",
    )
    qc_notes = fields.Text(string="QC notes")

    # ---- Photo capture (parity with Scan Issue / Damage) ----------------
    # Binary + widget="image" gives mobile browsers a camera input. Optional
    # on receipts; attached to the resulting picking for the audit trail.
    photo = fields.Binary(
        string="Delivery photo",
        attachment=True,
        help="Optional: snap a photo of the goods received (carton, batch "
        "label, condition). On a phone this opens the camera. Attached to "
        "the receipt for the audit trail.",
    )

    # ---- Audit trail (matches Scan Issue / damage / repair) -------------
    storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        required=True,
        domain=[("active", "=", True)],
        help="The on-duty Store Keeper who took the delivery. Picked from "
        "the roster the Admin maintains under Configuration → Store Keepers.",
    )
    delivered_by = fields.Char(
        string="Delivered by",
        help="Name of the person / vendor who handed the goods over "
        "(driver, vendor representative, internal courier). Optional but "
        "helpful for the audit trail.",
    )

    def on_barcode_scanned(self, barcode):
        """Called automatically by the JS barcode listener when a scan
        is detected. Drops into the same code path as the manual
        'Process scan' button.
        """
        self.last_scan = barcode
        return self.action_process_scan()

    def action_process_scan(self):
        self.ensure_one()
        if not self.last_scan:
            return self._reopen()
        info = self.env["wms.barcode.alias"].resolve(self.last_scan)
        kind = info.get("kind")

        if kind in ("product", "alias", "lot"):
            self.env["wms.scan.receipt.line"].create(
                {
                    "wizard_id": self.id,
                    "product_id": info["product"].id,
                    "quantity": info.get("units", 1.0),
                    "lot_id": info["lot"].id if kind == "lot" else False,
                }
            )
            self.feedback = "Added %s × %s" % (
                info.get("units", 1.0),
                info["product"].display_name,
            )
        elif kind == "location":
            # Apply this slot to the most recent line that has no destination yet.
            target = self.line_ids.filtered(lambda ln: not ln.location_dest_id)[-1:]
            if not target:
                self.feedback = "No pending line for slot %s" % info["location"].display_name
            else:
                target.location_dest_id = info["location"].id
                self.feedback = "Slot %s assigned" % info["location"].display_name
        else:
            self.feedback = "Unknown barcode: %s" % self.last_scan

        self.last_scan = False
        return self._reopen()

    def action_validate(self):
        self.ensure_one()
        # FPAT High: under real concurrency (two parallel RPC submits of the
        # same wizard id) the pre-lock Python check let both pass. We now
        # SELECT FOR UPDATE the wizard row so the second caller blocks on
        # the first, then sees the now-populated picking_id and short-
        # circuits. Receipts don't reserve stock so no per-product lock is
        # needed - the wizard-row lock is sufficient.
        self.env.cr.execute(
            "SELECT picking_id FROM wms_scan_receipt WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        row = self.env.cr.fetchone()
        if row and row[0]:
            self.invalidate_recordset(["picking_id"])
            return self._open_picking()
        if self.picking_id:
            return self._open_picking()
        if not self.line_ids:
            raise UserError("No lines to receive.")

        # Return-entry gate — reject products whose kind isn't returnable.
        if self.is_return:
            non_returnable = self.line_ids.filtered(
                lambda ln: ln.product_id and not ln.product_id.wms_is_returnable
            )
            if non_returnable:
                # Translate the Selection key to its human label via
                # fields_get() — `_fields[...].selection` can be a callable
                # in some Odoo flavours, so going through fields_get is
                # the safe path.
                kind_labels = dict(
                    self.env["product.product"]
                    .fields_get(["wms_product_kind"])
                    .get("wms_product_kind", {})
                    .get("selection", [])
                )
                rows = []
                for ln in non_returnable:
                    kind_key = ln.product_id.wms_product_kind
                    rows.append(
                        "  • %s (kind: %s)"
                        % (
                            ln.product_id.display_name,
                            kind_labels.get(kind_key, "unclassified"),
                        )
                    )
                raise UserError(
                    "These products cannot be received as a return — they "
                    "are flagged not-returnable on the product form "
                    "(fluids, consumables, single-use items):\n%s\n\n"
                    "Ask the Admin to either change the product's WMS Kind / "
                    "Returnable flag, or scrap these items via the Damages "
                    "workflow instead." % "\n".join(rows)
                )

        # QC gate — receiver must tick the box.
        if not self.qc_passed:
            raise UserError(
                "Mark 'Quality check passed' first. This confirms you've "
                "physically counted and inspected the delivery."
            )

        # Auto-assign slot if operator didn't.
        for line in self.line_ids:
            if not line.location_dest_id:
                line.location_dest_id = self._auto_assign_slot(line.product_id, line.quantity)

        # Use the warehouse-level m2o so we don't hit Odoo 19's archived
        # picking type problem for 1-step warehouses.
        picking_type = self.warehouse_id.in_type_id
        if not picking_type:
            raise UserError(
                "Warehouse %s isn't configured to receive incoming stock. "
                "Ask an Administrator to enable Receipts in the Inventory settings."
                % self.warehouse_id.display_name
            )
        if not picking_type.active:
            picking_type.sudo().active = True

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": self.warehouse_id.lot_stock_id.id,
                "origin": "Barcode scan" + (" (return)" if self.is_return else ""),
                # Audit-trail fields — same shape as Scan Issue so reports
                # can read both incoming and outgoing flows the same way.
                "wms_taken_by": (self.delivered_by or "").strip(),
                "wms_storekeeper_id": self.storekeeper_id.id,
            }
        )
        for line in self.line_ids:
            # Odoo 19: stock.move.name was retired in favour of
            # description_picking (free text shown on the picking).
            # stock.move.line.reserved_uom_qty is gone too — moves are
            # assigned and we just set `quantity` on the lines.
            self.env["stock.move"].create(
                {
                    "description_picking": line.product_id.display_name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.quantity,
                    "product_uom": line.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": line.location_dest_id.id,
                }
            )
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            for ml in move.move_line_ids:
                if not ml.quantity:
                    ml.quantity = ml.quantity_product_uom or move.product_uom_qty
        picking.button_validate()

        # Audit-trail message — matches the Scan Issue chatter pattern.
        # Markup() so Odoo 19 renders the HTML instead of escaping it.
        audit_body = Markup(
            "<p><b>%(kind)s.</b> "
            "Delivered by <b>%(delivered)s</b>; "
            "Store Keeper on duty: <b>%(keeper)s</b>; "
            "logged in as: <b>%(login)s</b>.</p>"
        ) % {
            "kind": "Return received" if self.is_return else "Receipt received",
            "delivered": picking.wms_taken_by or "(unspecified)",
            "keeper": self.storekeeper_id.name or "(unknown)",
            "login": self.env.user.display_name or "(system)",
        }
        picking.message_post(
            body=audit_body,
            subject="Receipt audit",
            message_type="notification",
        )
        # Attach the delivery photo (if any) for the audit trail.
        if self.photo:
            self.env["ir.attachment"].create(
                {
                    "name": "receipt-photo-%s.jpg" % picking.name,
                    "datas": self.photo,
                    "res_model": "stock.picking",
                    "res_id": picking.id,
                    "mimetype": "image/jpeg",
                }
            )
            picking.message_post(body="Delivery photo attached at receipt.")

        # Record the picking so a re-submit is a no-op (idempotency guard).
        self.picking_id = picking.id

        return self._open_picking()

    def _open_picking(self):
        """Open the receipt this scan created (also the no-op target a
        double-submit lands on)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
        }

    def _auto_assign_slot(self, product, qty):
        """Pick a stocking location.

        Priority order (resolved via stock.quant because compute fields
        can't appear in a search domain):

          1. Rack slot or floor zone already holding this product (cluster).
          2. Any empty rack slot.
          3. Any empty floor zone.
          4. Any rack slot (warning — will mix products).
          5. Any floor zone.

        Floor zones (`wms_location_type='floor'`) are open-area storage
        outside the rack hierarchy. They behave the same as slots for
        receiving / FIFO / reports.
        """
        Loc = self.env["stock.location"]
        Quant = self.env["stock.quant"]
        stock_loc = self.warehouse_id.lot_stock_id
        STOCK_TYPES = ("slot", "floor")

        # 1. Cluster: a slot/floor that already holds this product
        quant_here = Quant.search(
            [
                ("product_id", "=", product.id),
                ("location_id", "child_of", stock_loc.id),
                ("location_id.wms_location_type", "in", STOCK_TYPES),
                ("quantity", ">", 0),
            ],
            limit=1,
        )
        if quant_here:
            return quant_here.location_id.id

        # Slots+floors with live quants
        occupied_ids = Quant.search(
            [
                ("location_id", "child_of", stock_loc.id),
                ("location_id.wms_location_type", "in", STOCK_TYPES),
                ("quantity", ">", 0),
            ]
        ).location_id.ids
        not_in = occupied_ids or [0]

        # 2. Empty rack slot
        empty_slot = Loc.search(
            [
                ("id", "child_of", stock_loc.id),
                ("wms_location_type", "=", "slot"),
                ("id", "not in", not_in),
            ],
            limit=1,
        )
        if empty_slot:
            return empty_slot.id

        # 3. Empty floor zone
        empty_floor = Loc.search(
            [
                ("id", "child_of", stock_loc.id),
                ("wms_location_type", "=", "floor"),
                ("id", "not in", not_in),
            ],
            limit=1,
        )
        if empty_floor:
            return empty_floor.id

        # 4. Any rack slot
        any_slot = Loc.search(
            [
                ("id", "child_of", stock_loc.id),
                ("wms_location_type", "=", "slot"),
            ],
            limit=1,
        )
        if any_slot:
            return any_slot.id

        # 5. Any floor zone
        any_floor = Loc.search(
            [
                ("id", "child_of", stock_loc.id),
                ("wms_location_type", "=", "floor"),
            ],
            limit=1,
        )
        if any_floor:
            return any_floor.id

        raise UserError(
            "No slots or floor zones are set up in warehouse %s yet. "
            "Use Create Rack or Generate Floor Zones in the WMS Configuration "
            "menu first." % self.warehouse_id.display_name
        )

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Scan Receipt",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class WmsScanReceiptLine(models.TransientModel):
    _name = "wms.scan.receipt.line"
    _description = "Receipt scan line"

    wizard_id = fields.Many2one("wms.scan.receipt", ondelete="cascade", required=True)
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(default=1.0, required=True)
    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "Receipt quantity must be greater than zero.",
    )
    lot_id = fields.Many2one("stock.lot")
    location_dest_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "in", ("slot", "floor"))],
        help="Leave empty to let auto-assign pick a slot or floor zone at validate.",
    )
