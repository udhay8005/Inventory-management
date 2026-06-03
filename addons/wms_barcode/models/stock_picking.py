from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    """Audit trail fields populated by the Scan Issue wizard.

    Trust workflow:
      • The Store Keeper roster (wms.storekeeper) holds the names of
        the actual humans who rotate on the store desk. They typically
        share one Odoo login, so the on-duty name is picked from the
        roster each time — not auto-detected from env.user.
      • Taken by — the person physically receiving the items. Plain
        text because not every taker has a system record.
      • Ordered by — whoever authorised the issue (the cow-care lead,
        the Manager, etc.). Plain text for the same reason.

    These fields stay editable after validate so an Admin can fix a
    typo without re-issuing the stock move. They're shown on the
    picking's form view by an inherited view defined in
    `views/stock_picking_views.xml`.
    """

    _inherit = ["stock.picking", "wms.keeper.warning.mixin"]

    wms_taken_by = fields.Char(
        string="Handled by",
        index=True,
        help="Name of the person who physically handled this stock at the "
        "warehouse door — the receiver on an incoming delivery, or the "
        "person who took the goods on an issue. Neutral so the same "
        "column reads naturally on both directions of the transfer.",
    )
    wms_ordered_by = fields.Char(
        string="Ordered by",
        index=True,
        help="Name of the person who authorised this issue "
        "(the Manager / cow-care lead / project owner).",
    )
    wms_storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        index=True,
        help="The actual human Store Keeper running the desk at the time of "
        "this issue. Picked from the roster the Admin maintains under "
        "Configuration → Store Keepers.",
    )
    wms_audit_legacy = fields.Boolean(
        default=False,
        copy=False,
        readonly=True,
        index=False,
        help="Internal: set True by the 19.0.1.7.0 migration on pre-existing "
        "WMS-originated pickings that pre-date the audit-trail CHECK "
        "constraint. Allows the CHECK to grandfather historical rows "
        "while enforcing the invariant on every new row. Admin-readable "
        "filter target: search for wms_audit_legacy=True to review.",
    )

    # Declarative DB constraint (Odoo 19 idiom — the old list-of-tuples
    # `_sql_constraints` is silently ignored on inherited models in 19).
    # The CHECK string is applied directly as a DDL fragment (NOT through
    # psycopg2 %-formatting), so the LIKE wildcard is a single '%'.
    _wms_audit_triplet_on_done = models.Constraint(
        # COALESCE on wms_audit_legacy is essential: a raw SQL INSERT that
        # omits the column leaves it NULL (Odoo applies default=False only
        # via the ORM, not at the DB level). Without COALESCE the whole OR
        # evaluates to NULL when legacy is NULL + storekeeper is NULL, and
        # PostgreSQL PASSES a CHECK that is NULL — silently defeating the
        # SQL-bypass protection. COALESCE(..., FALSE) forces that operand
        # to FALSE so the OR resolves to FALSE and the CHECK fires.
        "CHECK ("
        "state != 'done' "
        "OR origin IS NULL "
        "OR origin NOT LIKE 'Barcode%' "
        "OR wms_storekeeper_id IS NOT NULL "
        "OR COALESCE(wms_audit_legacy, FALSE) = TRUE"
        ")",
        "WMS-originated pickings must record the storekeeper before being marked done.",
    )

    @api.constrains("state", "origin", "wms_storekeeper_id", "wms_audit_legacy")
    def _check_wms_audit_trail_on_done(self):
        """Refuse to mark a WMS-originated picking 'done' unless the
        storekeeper anchor is set. The DB CHECK catches SQL / XML-RPC
        bypasses; this @api.constrains gives operators a friendly error
        through the normal write/button-validate path.
        """
        for rec in self:
            if rec.state != "done":
                continue
            if not (rec.origin or "").startswith("Barcode"):
                continue
            if rec.wms_audit_legacy:
                continue
            if not rec.wms_storekeeper_id:
                raise ValidationError(
                    _(
                        "Picking %(name)s is WMS-originated but has no storekeeper "
                        "recorded. Re-run the scan wizard to record who handled "
                        "this transfer before marking it done."
                    )
                    % {"name": rec.name}
                )
