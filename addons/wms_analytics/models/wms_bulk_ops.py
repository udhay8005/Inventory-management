"""Wave 2 #13 — Bulk Operations on lots.

Lets a manager multi-select many stock.lot records from a list and act on them
in one go: recall, quarantine, or destroy the whole selection. Each bulk action
reads context ``active_ids`` and creates a SINGLE wms.lot.recall /
wms.lot.quarantine spanning all selected lots (reusing the Wave 1 perishable
models and their manager-gated action_* methods — no flow re-implemented here).

The methods are bound to stock.lot via ``_inherit`` and invoked by the
ir.actions.server records in views/wms_bulk_ops_views.xml (binding_model_id =
stock.model_stock_lot). Odoo 19's ir.actions.server has no groups_id, so each
method gates on env.user.has_group("wms_location.group_wms_manager") in code;
the underlying recall/quarantine action_* methods are manager-gated too, so this
is belt-and-braces with a clearer error.
"""

from odoo import _, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = "stock.lot"

    def _wms_bulk_selected_lots(self):
        """Resolve the lots to act on from the server-action context.

        The list-view server action passes the ticked rows as ``active_ids``;
        fall back to ``self`` when called directly (e.g. from a test).
        """
        ctx_ids = self.env.context.get("active_ids")
        lots = self.browse(ctx_ids) if ctx_ids else self
        lots = lots.exists()
        if not lots:
            raise UserError(_("Select at least one lot to act on."))
        return lots

    def _wms_bulk_check_manager(self):
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise UserError(_("Only a Manager can run bulk lot operations."))

    @staticmethod
    def _wms_bulk_notify(title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": title,
                "message": message,
                "sticky": False,
            },
        }

    def action_wms_bulk_recall(self):
        """Recall every selected lot under one wms.lot.recall notice."""
        self._wms_bulk_check_manager()
        lots = self._wms_bulk_selected_lots()
        recall = self.env["wms.lot.recall"].create(
            {
                "mode": "manual",
                "reason": _("Bulk recall of %d selected lot(s).") % len(lots),
                "lot_ids": [(6, 0, lots.ids)],
            }
        )
        recall.action_recall()
        return self._wms_bulk_notify(
            _("Lots recalled"),
            _("%(n)d lot(s) recalled under %(ref)s.") % {"n": len(lots), "ref": recall.name},
        )

    def action_wms_bulk_quarantine(self):
        """Put every selected lot on QC hold under one wms.lot.quarantine."""
        self._wms_bulk_check_manager()
        lots = self._wms_bulk_selected_lots()
        # wms.lot.quarantine applies the hold on create (the record IS the hold).
        quarantine = self.env["wms.lot.quarantine"].create(
            {
                "reason": _("Bulk quarantine of %d selected lot(s).") % len(lots),
                "lot_ids": [(6, 0, lots.ids)],
            }
        )
        return self._wms_bulk_notify(
            _("Lots quarantined"),
            _("%(n)d lot(s) put on QC hold under %(ref)s.")
            % {"n": len(lots), "ref": quarantine.name},
        )

    def action_wms_bulk_destroy(self):
        """Destroy every selected lot via a quarantine hold + destroy decision.

        Reuses wms.lot.quarantine: creating it holds the lots, then action_destroy
        flips them to the 'destroyed' lifecycle state in one decision over the
        whole selection.
        """
        self._wms_bulk_check_manager()
        lots = self._wms_bulk_selected_lots()
        quarantine = self.env["wms.lot.quarantine"].create(
            {
                "reason": _("Bulk destroy of %d selected lot(s).") % len(lots),
                "lot_ids": [(6, 0, lots.ids)],
            }
        )
        quarantine.action_destroy()
        return self._wms_bulk_notify(
            _("Lots destroyed"),
            _("%(n)d lot(s) marked destroyed under %(ref)s.")
            % {"n": len(lots), "ref": quarantine.name},
        )
