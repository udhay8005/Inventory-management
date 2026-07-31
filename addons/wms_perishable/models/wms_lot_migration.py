"""V20-020 — migration framework: bring legacy (v19, non-lot) perishable
products onto lot tracking.

The gaushala's actual path is the FRESH v20 line (path 1 in
docs/v20-perishable-engine/03-database-and-migration.md §5): new perishables
are lot-tracked from creation, so NO live-stock migration is needed. This
wizard implements the other two supported paths for a populated deployment:

  * Path 2 — per-product at zero stock: a clean tracking flip (no lots needed).
  * Path 3 — legacy-lot: assign the on-hand quants of a stock-bearing product
    to a LEGACY-<date>-<id> lot first, THEN flip tracking, so no on-hand stock
    is orphaned without a lot (which would break FEFO / the issue planner).

Dry-run previews exactly what each product would get. ROLLBACK is by RESTORE
of the pre-migration backup (§6): once tracking='lot' is set with stock on
hand, Odoo cannot cleanly downgrade — so this MUST be run only after a verified
backup. Manager-gated.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsLotMigration(models.TransientModel):
    _name = "wms.lot.migration"
    _description = "Perishable lot-tracking migration"

    report = fields.Text(readonly=True)

    @api.model
    def _perishable_kinds(self):
        from odoo.addons.wms_location.models.product_template import EXPIRY_SENSITIVE_KINDS

        return list(EXPIRY_SENSITIVE_KINDS)

    def _products_to_migrate(self):
        return self.env["product.product"].search(
            [
                ("product_tmpl_id.wms_product_kind", "in", self._perishable_kinds()),
                ("tracking", "!=", "lot"),
            ]
        )

    def _on_hand_quants(self, product):
        return self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
                ("lot_id", "=", False),
            ]
        )

    def _check_manager(self):
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise UserError("Only a Manager may run the perishable lot migration.")

    def action_dry_run(self):
        """Preview: list each legacy perishable product and the path it would
        take. Changes NOTHING."""
        self.ensure_one()
        lines = []
        for product in self._products_to_migrate():
            qty = sum(self._on_hand_quants(product).mapped("quantity"))
            path = "legacy-lot (has %g on hand)" % qty if qty else "clean flip (zero stock)"
            lines.append("- %s: %s" % (product.display_name, path))
        body = (
            "DRY RUN — nothing changed.\n\n%d perishable product(s) need migration:\n%s"
            % (len(lines), "\n".join(lines))
            if lines
            else "DRY RUN — nothing to migrate: every perishable product is already lot-tracked."
        )
        self.report = body
        return self._reopen()

    def action_migrate(self):
        """Run the migration. Back up first — rollback is by restore (§6)."""
        self.ensure_one()
        self._check_manager()
        clean, legacy = 0, 0
        today = fields.Date.today()
        for product in self._products_to_migrate():
            quants = self._on_hand_quants(product)
            if quants:
                lot = self.env["stock.lot"].create(
                    {
                        "name": "LEGACY-%s-%s" % (today, product.id),
                        "product_id": product.id,
                        "company_id": self.env.company.id,
                    }
                )
                quants.write({"lot_id": lot.id})
                legacy += 1
            else:
                clean += 1
            product.product_tmpl_id.write({"tracking": "lot", "use_expiration_date": True})
        self.report = (
            "MIGRATION COMPLETE.\n\n%d product(s) clean-flipped (zero stock).\n"
            "%d product(s) migrated via a legacy lot (had on-hand stock).\n\n"
            "Rollback (if needed) is by restoring the pre-migration backup." % (clean, legacy)
        )
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "wms.lot.migration",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
