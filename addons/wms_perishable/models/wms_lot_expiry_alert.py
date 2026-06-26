"""V20-015 — per-LOT expiry report.

The v19 wms.expiry.alert keys on the TEMPLATE wms_expiry_date (one row per
product). Now that stock is tracked per lot, this ADDITIVE report surfaces
each BATCH's own expiry, keyed on the stored stock.quant.wms_effective_expiry
(V20-008), with the owner-approved threshold bands (180/90/60/30/15/7/expired)
and the value at risk per lot. The v19 product-level report is left intact, so
nothing that depends on it changes; this is the lot-level companion.

SQL view, read-only, scoped to genuine on-shelf storage (internal, not
damage/repair, under a warehouse's lot_stock_id — the same scoping the v19
report uses, so 'value at risk' is real on-shelf exposure).
"""

from odoo import api, fields, models, tools


class WmsLotExpiryAlert(models.Model):
    _name = "wms.lot.expiry.alert"
    _description = "Lots approaching expiry (per batch)"
    _auto = False
    _order = "days_to_expiry, product_id"

    product_id = fields.Many2one("product.product", readonly=True)
    lot_id = fields.Many2one("stock.lot", readonly=True)
    wms_product_kind = fields.Selection(
        related="product_id.wms_product_kind", string="Kind", readonly=True
    )
    lot_state = fields.Selection(related="lot_id.wms_lot_state", string="Lot state", readonly=True)
    supplier_id = fields.Many2one(
        related="lot_id.wms_supplier_id", string="Supplier", readonly=True
    )
    expiry_date = fields.Date(string="Expiry date", readonly=True)
    days_to_expiry = fields.Integer(
        string="Days to expiry",
        readonly=True,
        help="Negative = already expired. 0 = today.",
    )
    on_hand = fields.Float(string="On hand (units)", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    unit_cost = fields.Float(string="Unit cost", readonly=True)
    value_at_risk = fields.Float(
        string="Value at risk",
        readonly=True,
        help="On-hand quantity of this batch x unit cost.",
    )
    status = fields.Selection(
        [
            ("expired", "Expired"),
            ("d7", "Within 7 days"),
            ("d15", "Within 15 days"),
            ("d30", "Within 30 days"),
            ("d60", "Within 60 days"),
            ("d90", "Within 90 days"),
            ("d180", "Within 180 days"),
            ("ok", "More than 180 days"),
        ],
        string="Status",
        readonly=True,
    )

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_lot_expiry_alert AS
            WITH lot_on_hand AS (
                SELECT sq.product_id,
                       sq.lot_id,
                       sq.wms_effective_expiry AS expiry_date,
                       SUM(sq.quantity)        AS qty,
                       MAX(sq.company_id)      AS company_id
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                 WHERE sl.usage = 'internal'
                   AND COALESCE(sl.wms_is_damage, FALSE) = FALSE
                   AND COALESCE(sl.wms_is_repair, FALSE) = FALSE
                   AND sq.lot_id IS NOT NULL
                   AND sq.wms_effective_expiry IS NOT NULL
                   AND sq.quantity > 0
                   AND EXISTS (
                       SELECT 1
                         FROM stock_warehouse w
                         JOIN stock_location ls ON ls.id = w.lot_stock_id
                        WHERE sl.parent_path LIKE ls.parent_path || '%'
                   )
                 GROUP BY sq.product_id, sq.lot_id, sq.wms_effective_expiry
            )
            SELECT
                loh.lot_id          AS id,
                loh.product_id      AS product_id,
                loh.lot_id          AS lot_id,
                loh.expiry_date     AS expiry_date,
                loh.company_id      AS company_id,
                (loh.expiry_date - CURRENT_DATE)::int AS days_to_expiry,
                loh.qty             AS on_hand,
                COALESCE((pp.standard_price ->> loh.company_id::text)::numeric, 0) AS unit_cost,
                loh.qty * COALESCE((pp.standard_price ->> loh.company_id::text)::numeric, 0)
                    AS value_at_risk,
                CASE
                    WHEN loh.expiry_date < CURRENT_DATE         THEN 'expired'
                    WHEN loh.expiry_date <= CURRENT_DATE + 7    THEN 'd7'
                    WHEN loh.expiry_date <= CURRENT_DATE + 15   THEN 'd15'
                    WHEN loh.expiry_date <= CURRENT_DATE + 30   THEN 'd30'
                    WHEN loh.expiry_date <= CURRENT_DATE + 60   THEN 'd60'
                    WHEN loh.expiry_date <= CURRENT_DATE + 90   THEN 'd90'
                    WHEN loh.expiry_date <= CURRENT_DATE + 180  THEN 'd180'
                    ELSE 'ok'
                END AS status
            FROM lot_on_hand loh
            JOIN product_product pp ON pp.id = loh.product_id
        """
        )
