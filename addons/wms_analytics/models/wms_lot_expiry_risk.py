"""Wave 2 #2 — Expiry Risk Engine.

The Wave 1 expiry report bands a lot purely by calendar distance to expiry. This
engine answers a sharper question: *will this lot be consumed before it expires?*
It joins each lot's on-hand quantity to the product's AI consumption velocity
(wms.forecast.daily_avg) to estimate days-of-cover, compares that to the lot's
remaining shelf life, and assigns a LOW / MEDIUM / HIGH / CRITICAL risk band.

Implemented as an ``_auto=False`` SQL view (read-only, always fresh, no storage),
mirroring the project's other reporting views (wms.expiry.alert, wms.occupancy).
"""

from odoo import fields, models, tools


class WmsLotExpiryRisk(models.Model):
    _name = "wms.lot.expiry.risk"
    _description = "Lot expiry risk (consume-before-expiry prediction)"
    _auto = False
    _order = "risk_rank desc, days_to_expiry"
    _rec_name = "lot_id"

    lot_id = fields.Many2one("stock.lot", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    expiration_date = fields.Datetime(readonly=True)
    days_to_expiry = fields.Integer(
        readonly=True, help="Calendar days until this lot expires (negative = expired)."
    )
    on_hand = fields.Float(readonly=True, help="On-hand units of this lot in storage.")
    daily_avg = fields.Float(
        readonly=True, help="Forecast average daily consumption for the product."
    )
    days_of_cover = fields.Float(
        readonly=True,
        help="How many days the on-hand lot quantity will last at the current "
        "consumption rate (on-hand / daily average). Blank when there is no "
        "measured consumption.",
    )
    risk_band = fields.Selection(
        [
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        readonly=True,
        help="LOW = will be consumed comfortably before expiry. MEDIUM = tight. "
        "HIGH = will likely expire before it is used up. CRITICAL = already "
        "expired, or large unconsumable surplus.",
    )
    risk_rank = fields.Integer(readonly=True, help="Numeric risk for ordering (3=critical).")
    value_at_risk = fields.Float(
        readonly=True, help="On-hand quantity x unit cost — money exposed if the lot is lost."
    )

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # on_hand per lot, restricted to live internal storage (excludes the
        # damage/repair sinks so only issuable stock counts toward risk).
        return """
            WITH oh AS (
                SELECT sq.lot_id,
                       SUM(sq.quantity) AS on_hand,
                       MAX(sq.company_id) AS company_id
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                 WHERE sl.usage = 'internal'
                   AND COALESCE(sl.wms_is_damage, FALSE) = FALSE
                   AND COALESCE(sl.wms_is_repair, FALSE) = FALSE
                   AND sq.lot_id IS NOT NULL
                   AND sq.quantity > 0
                 GROUP BY sq.lot_id
            )
            SELECT lot.id AS id,
                   lot.id AS lot_id,
                   lot.product_id AS product_id,
                   oh.company_id AS company_id,
                   lot.expiration_date AS expiration_date,
                   (lot.expiration_date::date - CURRENT_DATE) AS days_to_expiry,
                   oh.on_hand AS on_hand,
                   COALESCE(f.daily_avg, 0.0) AS daily_avg,
                   CASE WHEN COALESCE(f.daily_avg, 0) > 0
                        THEN oh.on_hand / f.daily_avg
                        ELSE NULL END AS days_of_cover,
                   oh.on_hand
                       * COALESCE((pp.standard_price ->> oh.company_id::text)::numeric, 0)
                       AS value_at_risk,
                   CASE
                     WHEN (lot.expiration_date::date - CURRENT_DATE) < 0 THEN 'critical'
                     WHEN COALESCE(f.daily_avg, 0) <= 0 THEN
                          CASE WHEN (lot.expiration_date::date - CURRENT_DATE) <= 30 THEN 'high'
                               WHEN (lot.expiration_date::date - CURRENT_DATE) <= 90 THEN 'medium'
                               ELSE 'low' END
                     ELSE
                          CASE
                            WHEN oh.on_hand / f.daily_avg
                                 >= 2 * GREATEST(lot.expiration_date::date - CURRENT_DATE, 1)
                                 THEN 'critical'
                            WHEN oh.on_hand / f.daily_avg
                                 > (lot.expiration_date::date - CURRENT_DATE) THEN 'high'
                            WHEN oh.on_hand / f.daily_avg
                                 > 0.75 * (lot.expiration_date::date - CURRENT_DATE) THEN 'medium'
                            ELSE 'low'
                          END
                   END AS risk_band,
                   CASE
                     WHEN (lot.expiration_date::date - CURRENT_DATE) < 0 THEN 3
                     WHEN COALESCE(f.daily_avg, 0) <= 0 THEN
                          CASE WHEN (lot.expiration_date::date - CURRENT_DATE) <= 30 THEN 2
                               WHEN (lot.expiration_date::date - CURRENT_DATE) <= 90 THEN 1
                               ELSE 0 END
                     ELSE
                          CASE
                            WHEN oh.on_hand / f.daily_avg
                                 >= 2 * GREATEST(lot.expiration_date::date - CURRENT_DATE, 1)
                                 THEN 3
                            WHEN oh.on_hand / f.daily_avg
                                 > (lot.expiration_date::date - CURRENT_DATE) THEN 2
                            WHEN oh.on_hand / f.daily_avg
                                 > 0.75 * (lot.expiration_date::date - CURRENT_DATE) THEN 1
                            ELSE 0
                          END
                   END AS risk_rank
              FROM stock_lot lot
              JOIN oh ON oh.lot_id = lot.id
              JOIN product_product pp ON pp.id = lot.product_id
              LEFT JOIN wms_forecast f ON f.product_id = lot.product_id
             WHERE lot.expiration_date IS NOT NULL
        """
