"""V20-007 — extend stock.lot with the perishable lifecycle + supplier/expiry
metadata (data model only; the UI surfacing lives with the lot views/timeline,
V20-017). Additive _inherit — no v19 file edited, no flow changed.

Field contract is the frozen spec, docs/v20-perishable-engine/03-database-and-migration.md
(`stock.lot` table). `expiration_date` / `use_date` already come from the
product_expiry dependency; this adds the lifecycle state, supplier traceability,
manufacture date, and a computed expired flag.
"""

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

# V20-019 — stable extension-hook API version. Future modules that override
# _wms_lifecycle_hook should check this if they depend on the event vocabulary.
WMS_HOOK_API_VERSION = "1.0"

# The lifecycle events passed to _wms_lifecycle_hook (the stable vocabulary).
WMS_LIFECYCLE_EVENTS = (
    "received",  # a batch was received onto the shelf
    "issued",  # a batch was issued out
    "recalled",  # a lot was recalled (frozen)
    "quarantined",  # a lot was put on QC hold
    "released",  # a recall/quarantine was released back to available
    "rejected",  # a QC hold was rejected
    "destroyed",  # a lot was marked destroyed
)


class StockLot(models.Model):
    _inherit = "stock.lot"

    wms_lot_state = fields.Selection(
        [
            ("available", "Available"),
            ("quarantine", "Quarantine"),
            ("recalled", "Recalled"),
            ("destroyed", "Destroyed"),
        ],
        string="Lot state",
        default="available",
        required=True,
        index=True,
        help="Lifecycle state of this lot. 'available' is normal; quarantine / "
        "recalled / destroyed lots are excluded from FEFO issuing (wired in the "
        "recall/quarantine tickets, V20-013/014). Distinct from native "
        "reservation and from the computed expired flag.",
    )
    wms_supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        help="Supplier this batch was received from — for recall and traceability.",
    )
    wms_supplier_batch = fields.Char(
        string="Supplier batch",
        help="The supplier's own batch / lot code, when it differs from our lot name.",
    )
    wms_supplier_invoice = fields.Char(
        string="Supplier invoice",
        help="Inbound invoice / delivery reference, for traceability.",
    )
    wms_manufacture_date = fields.Date(
        string="Manufacture date",
        help="Optional manufacture date of this batch.",
    )
    wms_is_expired = fields.Boolean(
        string="Expired",
        compute="_compute_wms_is_expired",
        help="True when this lot's expiration date is in the past. Computed from "
        "product_expiry's expiration_date; not stored.",
    )

    wms_movement_count = fields.Integer(
        string="Movements",
        compute="_compute_wms_movement_count",
        help="Number of completed stock movements this lot has been through — "
        "its full receive/move/issue/return/damage/repair history.",
    )

    @api.depends("expiration_date")
    def _compute_wms_is_expired(self):
        now = fields.Datetime.now()
        for lot in self:
            lot.wms_is_expired = bool(lot.expiration_date and lot.expiration_date < now)

    def _compute_wms_movement_count(self):
        # Per-lot is fine here (the form computes one lot at a time); a done
        # move line is an immutable record of one physical movement.
        for lot in self:
            lot.wms_movement_count = self.env["stock.move.line"].search_count(
                [("lot_id", "=", lot.id), ("state", "=", "done")]
            )

    def action_wms_lot_timeline(self):
        """V20-017 — open this lot's immutable movement timeline: every
        completed move line (receive -> move -> issue -> return -> damage ->
        repair), newest first. Move lines are immutable once done, so the
        timeline can never be rewritten. Recall / quarantine / destroy events
        are lifecycle states shown on the lot form (wms_lot_state) alongside."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Movement timeline — %s" % (self.name or ""),
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            "domain": [("lot_id", "=", self.id), ("state", "=", "done")],
            "context": {"create": False, "edit": False},
        }

    def _wms_lifecycle_hook(self, event, payload=None):
        """V20-019 — stable extension point (v20 Hook API %s).

        A NO-OP by default. Fired on ``self`` (the affected lots) at each
        perishable lifecycle event in WMS_LIFECYCLE_EVENTS. Future modules
        extend behaviour by overriding this method — e.g. to notify a
        supplier-quality engine on 'recalled', or feed an analytics model on
        'received' — WITHOUT touching the FEFO / recall / quarantine internals.

        :param event: one of WMS_LIFECYCLE_EVENTS.
        :param payload: the originating record (e.g. the wms.lot.recall /
            wms.lot.quarantine, or the receipt line), for context.
        """ % (
            WMS_HOOK_API_VERSION,
        )
        return None

    def _wms_lot_label_vals(self):
        """V20-016 — printable lot-label content. The barcode is the lot name,
        so scanning the printed label resolves straight back to this lot
        (wms.barcode.alias.resolve -> kind 'lot'). Batch / expiry / supplier
        are on the human-readable sub-line."""
        self.ensure_one()
        bits = ["Batch %s" % (self.name or "")]
        if self.expiration_date:
            bits.append("Exp %s" % self.expiration_date.date())
        if self.wms_supplier_id:
            bits.append(self.wms_supplier_id.name)
        return {
            "title": self.product_id.display_name,
            "subtitle": " | ".join(bits),
            "barcode": self.name or "",
        }

    def action_wms_print_lot_label(self):
        """V20-016 — print this lot's label on the default WMS label printer."""
        self.ensure_one()
        printer = self.env["wms.label.printer"].get_default_printer()
        if not printer:
            raise UserError(
                "No label printer is configured. An administrator can add one "
                "under WMS settings before printing lot labels."
            )
        printer.print_labels([self._wms_lot_label_vals()])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Lot label sent",
                "message": "Label for %s sent to %s." % (self.name, printer.name),
                "sticky": False,
            },
        }


class StockLotExpiryDefault(models.Model):
    """UAT R3 — never stamp a batch as 'expired the moment it is created'.

    Odoo's product_expiry computes ``expiration_date = now + expiration_time
    days`` for every lot of an expiry-tracked product. The trust does not
    configure a per-product shelf life (``expiration_time`` stays 0), so that
    formula produced **now** — every new batch was born already expired:

      * its ``removal_date`` was in the past, so the batch could not be
        reserved for ANY move (a fuel draw failed with a misleading "the tank
        level changed" error — the finding that opened this ticket), and
      * medicine received without typing an expiry was silently unusable too.

    An unknown expiry must be EMPTY, not "now". Operators enter the real
    expiry per batch at Scan Receipt (the trust's actual workflow), and
    products that do carry a configured shelf life are unaffected.
    """

    _inherit = "stock.lot"

    @api.depends("product_id")
    def _compute_expiration_date(self):
        # Mirrors product_expiry's compute, minus the zero-duration stamp.
        self.expiration_date = False
        for lot in self:
            if lot.product_id.use_expiration_date and not lot.expiration_date:
                duration = lot.product_id.product_tmpl_id.expiration_time
                if duration:
                    lot.expiration_date = fields.Datetime.now() + timedelta(days=duration)
