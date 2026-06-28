# File: wizards/wms_dispense_wizard.py
# Module: wms_pharmacy
# Description: Pharmacy dispensing wizard (wms.dispense.wizard).
#              Implements strip-level FEFO lot selection, open-package
#              optimisation, tablet-level stock deduction via a real DONE
#              stock.move, and pharmaceutical genealogy logging.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: wms_perishable (stock.lot.wms_lot_state), wms_location (wms.animal)

from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Far-future sentinel used when a lot has no expiration_date set (treat as
# last to expire in FEFO ordering — effectively infinite shelf life).
_FAR_FUTURE = datetime(9999, 12, 31, 23, 59, 59)


class WmsDispenseWizard(models.TransientModel):
    """Pharmacy dispensing wizard — strip-level FEFO, open-package optimisation.

    The operator selects a packaged medicine, an optional target animal, the
    storage location to draw from, and the number of tablets to dispense.
    ``action_dispense()`` then:

    1. Selects the best lot via strip-level FEFO (earliest-expiry first) with
       open-package optimisation (prefer a lot that already has an open strip
       when its expiry is not worse than the FEFO winner).
    2. Draws the requested tablets first from any existing open strip, then by
       opening new sealed strips as needed. The leftover from the last opened
       strip is registered in ``wms.open.strip``.
    3. Deducts the quantity from stock via the Odoo 19 done-move recipe:
       ``_action_confirm → unlink move_line_ids → create move.line with lot_id
       → picked=True → _action_done()``.
    4. Creates an immutable ``wms.dispense.log`` row (box→strip→tablet genealogy
       + animal medication history).

    Guards:
    * Only 'available' (wms_lot_state) and non-expired lots are eligible.
    * Raises ``UserError`` if available stock is insufficient.
    * Manager-only: a non-manager user cannot override an expired or quarantined lot.

    Usage example::

        wiz = env['wms.dispense.wizard'].create({
            'product_id': oxy_variant.id,
            'location_id': shelf_a.id,
            'quantity': 6,
            'animal_id': gauri.id,
        })
        wiz.action_dispense()
    """

    _name = "wms.dispense.wizard"
    _description = "Pharmacy dispense wizard"

    # ------------------------------------------------------------------
    # Wizard fields
    # ------------------------------------------------------------------

    product_id = fields.Many2one(
        "product.product",
        string="Medicine",
        required=True,
        domain="[('product_tmpl_id.wms_is_packaged', '=', True)]",
        help="The packaged medicine to dispense. Only products with the "
        "Box→Strip→Tablet flag are shown.",
    )
    animal_id = fields.Many2one(
        "wms.animal",
        string="Animal",
        help="Optional — the animal receiving the dose. When set, the "
        "dispense event is linked to the animal's Medication History.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Storage location",
        required=True,
        domain="[('usage', '=', 'internal')]",
        help="The internal storage location to draw stock from (the shelf / "
        "rack / slot where the medicine is physically stored).",
    )
    quantity = fields.Integer(
        string="Tablets to dispense",
        required=True,
        default=1,
        help="Number of individual tablets to dispense. Must be at least 1.",
    )
    note = fields.Text(
        string="Note",
        help="Optional treatment note (reason, dosage instructions, etc.). "
        "Stored on the genealogy log for the medication record.",
    )

    # ------------------------------------------------------------------
    # Python constraints on wizard fields
    # ------------------------------------------------------------------

    @api.constrains("quantity")
    def _check_quantity_positive(self):
        """Quantity must be at least 1 tablet.

        :raises UserError: when quantity <= 0.
        """
        for wiz in self:
            if wiz.quantity <= 0:
                raise UserError(
                    _("Tablets to dispense must be at least 1. Got: %d.") % wiz.quantity
                )

    # ------------------------------------------------------------------
    # FEFO lot selection
    # ------------------------------------------------------------------

    def _select_fefo_lot(self, product, location, qty_needed):
        """Select the best lot via strip-level FEFO + open-package optimisation.

        Algorithm:
        1. Search all ``stock.quant`` rows for this product at or below the
           given location (child_of) with ``quantity > 0`` and a lot_id.
        2. Exclude lots whose ``wms_lot_state != 'available'`` or that are
           expired (``wms_is_expired``).
        3. Aggregate available quantity per lot (quants can be spread across
           child locations).
        4. Sort the eligible lots by ``(expiration_date ASC, not_has_open_strip)``:
           earliest-expiry first (FEFO), breaking ties by preferring a lot that
           already has an open strip at this location (open-package optimisation).
        5. Return the first lot in the sorted list that has >= ``qty_needed``
           tablets available.

        :param product: ``product.product`` record — the packaged medicine.
        :param location: ``stock.location`` record — the source storage location.
        :param qty_needed: int — number of tablets to dispense.
        :returns: ``stock.lot`` singleton.
        :raises UserError: when no available lot has sufficient stock.
        """
        now = fields.Datetime.now()

        # Fetch all live quants for this product at this location (child-of
        # covers sub-slots within a rack). We read lot_id + quantity in one
        # read() to avoid individual field access in a loop (N+1 guard).
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id", "child_of", location.id),
                ("quantity", ">", 0),
                ("lot_id", "!=", False),
            ]
        )

        if not quants:
            raise UserError(
                _(
                    "No stock found for '%(prod)s' at '%(loc)s'. "
                    "Receive stock first before dispensing."
                )
                % {"prod": product.display_name, "loc": location.display_name}
            )

        # Filter to available, non-expired lots. wms_lot_state and
        # expiration_date are already loaded via _prefetch_ids after the
        # search, so this filtered() is pure-Python with no extra queries.
        available_quants = quants.filtered(
            lambda q: (
                q.lot_id.wms_lot_state == "available"
                and (not q.lot_id.expiration_date or q.lot_id.expiration_date > now)
            )
        )

        if not available_quants:
            raise UserError(
                _(
                    "No available (non-quarantined, non-recalled, non-expired) "
                    "stock of '%(prod)s' found at '%(loc)s'."
                )
                % {"prod": product.display_name, "loc": location.display_name}
            )

        # Aggregate quantity per lot (product may span multiple child slots).
        lot_qty: dict = {}
        for q in available_quants:
            lot = q.lot_id
            if lot.id not in lot_qty:
                lot_qty[lot.id] = {"lot": lot, "qty": 0.0}
            lot_qty[lot.id]["qty"] += q.quantity

        # Find lots that have an open strip at this location (open-package
        # optimisation). We check tablets_remaining > 0 even though the
        # CHECK constraint on wms.open.strip already enforces it.
        open_strip_lot_ids = set(
            self.env["wms.open.strip"]
            .sudo()
            .search(
                [
                    ("product_id", "=", product.id),
                    ("location_id", "=", location.id),
                    ("tablets_remaining", ">", 0),
                ]
            )
            .mapped("lot_id")
            .ids
        )

        def _sort_key(entry):
            """Sort key: (expiry ASC, has_open_strip DESC).

            Lots with an open strip are preferred ONLY when their expiry is
            not worse than the FEFO leader (i.e. when expiries are equal the
            open-strip lot wins). The tuple sort achieves this naturally:
            (same_expiry, 0) < (same_expiry, 1), so open-strip lot sorts first.
            """
            lot = entry["lot"]
            exp = lot.expiration_date or _FAR_FUTURE
            # 0 = has open strip (preferred), 1 = no open strip
            has_open = 0 if lot.id in open_strip_lot_ids else 1
            return (exp, has_open)

        sorted_entries = sorted(lot_qty.values(), key=_sort_key)

        # Return the first lot that can cover the full dispense.
        for entry in sorted_entries:
            if entry["qty"] >= qty_needed:
                return entry["lot"]

        # No single lot has enough; report total available for clarity.
        total_available = int(sum(e["qty"] for e in sorted_entries))
        raise UserError(
            _(
                "Insufficient available stock for '%(prod)s' at '%(loc)s'.\n"
                "Requested: %(needed)d tablets — "
                "Total available across all eligible lots: %(avail)d tablets.\n\n"
                "No single lot has enough to cover the full dispense. "
                "Reduce the quantity or receive more stock."
            )
            % {
                "prod": product.display_name,
                "loc": location.display_name,
                "needed": qty_needed,
                "avail": total_available,
            }
        )

    # ------------------------------------------------------------------
    # Done-move recipe (Odoo 19 MANDATORY)
    # ------------------------------------------------------------------

    def _create_done_move(self, product, lot, location, qty):
        """Deduct ``qty`` product units from stock using the Odoo 19 done-move recipe.

        Recipe (per spec and Odoo 19 codebase):
        1. Create ``stock.move`` (description_picking, no 'name' field).
        2. ``move._action_confirm()`` — transitions to 'confirmed'.
        3. ``move.move_line_ids.unlink()`` — remove the auto-created draft ML.
        4. Create ONE ``stock.move.line`` with lot_id and explicit quantity.
           picking_id is NOT set (standalone move without a picking).
        5. ``move.picked = True`` — mark as physically done.
        6. ``move._action_done()`` — commit the stock deduction.

        :param product: ``product.product`` record.
        :param lot: ``stock.lot`` record.
        :param location: ``stock.location`` source location.
        :param qty: int — tablets to deduct (= product units, UoM=Units).
        :returns: the completed ``stock.move`` record.
        """
        customers_loc = self.env.ref("stock.stock_location_customers", raise_if_not_found=False)
        if not customers_loc:
            raise UserError(
                _(
                    "Cannot find the Customers stock location "
                    "(stock.stock_location_customers). "
                    "Ensure the 'stock' module is installed and configured."
                )
            )

        move = self.env["stock.move"].create(
            {
                "description_picking": "Pharmacy dispense: %s" % product.display_name,
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": location.id,
                "location_dest_id": customers_loc.id,
            }
        )
        move._action_confirm()
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": product.id,
                "lot_id": lot.id,
                "quantity": qty,
                "location_id": location.id,
                "location_dest_id": customers_loc.id,
            }
        )
        move.picked = True
        move._action_done()
        return move

    # ------------------------------------------------------------------
    # Main dispense action
    # ------------------------------------------------------------------

    def action_dispense(self):
        """Execute the pharmacy dispense.

        Orchestration:
        1. Validate product is packaged (wms_is_packaged guard).
        2. Select the best lot via strip-level FEFO + open-package optimisation.
        3. Compute strip usage: draw first from the open strip, then open sealed
           strips for the remainder. Track ``strips_opened`` and the leftover.
        4. Persist the open-strip state (create or update ``wms.open.strip``).
        5. Deduct ``quantity`` tablets from stock via done-move recipe.
        6. Create an immutable ``wms.dispense.log`` row.
        7. Return a success notification.

        :returns: dict — ``ir.actions.client`` display_notification with
            a summary of what was dispensed.
        :raises UserError: on insufficient stock, no available lot, non-packaged
            product, or quantity <= 0.
        """
        self.ensure_one()

        product = self.product_id
        location = self.location_id
        qty_needed = self.quantity

        # Guard: product must be packaged
        if not product.product_tmpl_id.wms_is_packaged:
            raise UserError(
                _(
                    "Product '%(prod)s' is not flagged as packaged "
                    "(Box→Strip→Tablet). Configure the Pharmacy packaging "
                    "counts on the product form first."
                )
                % {"prod": product.display_name}
            )

        tablets_per_strip = product.product_tmpl_id.wms_tablets_per_strip
        tablets_per_box = product.product_tmpl_id.wms_tablets_per_box

        if tablets_per_strip <= 0:
            raise UserError(
                _(
                    "Product '%(prod)s' has no 'Tablets per strip' configured. "
                    "Set it on the WMS Classification tab before dispensing."
                )
                % {"prod": product.display_name}
            )

        # 1. FEFO lot selection
        lot = self._select_fefo_lot(product, location, qty_needed)

        # 2. Open-strip and sealed-strip accounting
        OpenStrip = self.env["wms.open.strip"].sudo()
        strips_opened = 0
        qty_remaining = qty_needed

        # 2a. Draw from any existing open strip first
        open_strip = OpenStrip.find_for(product, lot, location)
        if open_strip:
            from_open = min(open_strip.tablets_remaining, qty_remaining)
            new_remaining = open_strip.tablets_remaining - from_open
            qty_remaining -= from_open
            if new_remaining <= 0:
                open_strip.unlink()
            else:
                open_strip.tablets_remaining = new_remaining

        # 2b. Open sealed strips for the remainder
        while qty_remaining > 0:
            strips_opened += 1
            qty_remaining -= tablets_per_strip

        # qty_remaining is now <= 0.
        # If negative: abs(qty_remaining) tablets remain from the last strip.
        leftover = -qty_remaining  # 0 when strip was exactly consumed

        # 2c. Update/create open-strip record for leftover tablets
        if leftover > 0:
            OpenStrip.open_new(product, lot, location, leftover)

        # 3. Deduct stock via Odoo 19 done-move recipe
        self._create_done_move(product, lot, location, qty_needed)

        # 4. Create genealogy log (sudo so users don't need write on log model)
        log = (
            self.env["wms.dispense.log"]
            .sudo()
            .create(
                {
                    "product_id": product.id,
                    "lot_id": lot.id,
                    "animal_id": self.animal_id.id or False,
                    "quantity": qty_needed,
                    "dispense_date": fields.Datetime.now(),
                    "strips_opened": strips_opened,
                    "tablets_per_strip": tablets_per_strip,
                    "tablets_per_box": tablets_per_box,
                    "dispensed_by": self.env.user.id,
                    "note": (self.note or "").strip() or False,
                    "picking_id": False,
                }
            )
        )

        # 5. Success notification
        animal_part = " for %s" % self.animal_id.name if self.animal_id else ""
        strips_part = " (%d sealed strip(s) opened)" % strips_opened if strips_opened else ""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Dispensed",
                "message": (
                    "%(qty)d tablet(s) of %(prod)s [Lot: %(lot)s]"
                    "%(animal)s.%(strips)s  Log #%(log)d."
                )
                % {
                    "qty": qty_needed,
                    "prod": product.display_name,
                    "lot": lot.name,
                    "animal": animal_part,
                    "strips": strips_part,
                    "log": log.id,
                },
                "sticky": False,
            },
        }
