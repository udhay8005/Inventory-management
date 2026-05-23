from odoo import fields, models


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
