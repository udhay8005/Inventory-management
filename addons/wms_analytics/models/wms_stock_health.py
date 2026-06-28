"""Wave 2 — Stock Health Score.

A single read-only, one-row-per-company scorecard that classifies all on-hand
storage quantity into five mutually-exclusive health buckets and rolls them up
into an overall health score (the % of stock that is healthy).

Every live storage quant (``stock.quant`` in an ``internal`` location, excluding
the damage/repair sinks — the same exclusion the expiry-risk and disposal views
use) is placed in exactly ONE bucket, by strict precedence:

    Recall  >  Quarantine  >  Expired  >  NearExpiry  >  Healthy

  * Recall / Quarantine come from the lot lifecycle state
    (``stock.lot.wms_lot_state`` = 'recalled' / 'quarantine').
  * Expired / NearExpiry come from the per-quant stored effective expiry
    (``stock.quant.wms_effective_expiry``): expired = date < today;
    near = within the next 30 days.
  * Everything else is Healthy.

A quant with no lot (``lot_id IS NULL``) can never be recalled/quarantined
(those are lot states), so it falls through to the expiry checks on its own
``wms_effective_expiry`` (product-template fallback), then Healthy.

Implemented as an ``_auto=False`` SQL view (read-only, always fresh, no storage),
mirroring wms.lot.expiry.risk / wms.disposal.report. The five bucket quantities
are aggregated in SQL per company; the percentage fields and the overall score
are NON-STORED Python computes derived from those quantities.
"""

from odoo import api, fields, models, tools


class WmsStockHealth(models.Model):
    _name = "wms.stock.health"
    _description = "Stock health score (one row per company)"
    _auto = False
    # overall_score is a non-stored compute, so it cannot drive _order (no SQL
    # column). Order by the stored company_id column instead.
    _order = "company_id"
    _rec_name = "company_id"

    company_id = fields.Many2one("res.company", readonly=True)
    total_qty = fields.Float(
        readonly=True, help="Total on-hand units in live internal storage for this company."
    )
    healthy_qty = fields.Float(
        readonly=True, help="Units that are available, not expired and not near expiry."
    )
    near_qty = fields.Float(
        readonly=True,
        help="Available units whose effective expiry is within the next 30 days "
        "(and not already expired).",
    )
    expired_qty = fields.Float(
        readonly=True, help="Available units whose effective expiry is already in the past."
    )
    quarantine_qty = fields.Float(
        readonly=True, help="Units on lots whose lifecycle state is 'quarantine'."
    )
    recall_qty = fields.Float(
        readonly=True, help="Units on lots whose lifecycle state is 'recalled'."
    )

    # --- Non-stored derived percentages + overall score -------------------
    healthy_pct = fields.Float(
        string="Healthy %",
        compute="_compute_pct",
        help="Healthy units as a percentage of total on-hand units.",
    )
    near_pct = fields.Float(
        string="Near expiry %",
        compute="_compute_pct",
        help="Near-expiry units as a percentage of total on-hand units.",
    )
    expired_pct = fields.Float(
        string="Expired %",
        compute="_compute_pct",
        help="Expired units as a percentage of total on-hand units.",
    )
    quarantine_pct = fields.Float(
        string="Quarantine %",
        compute="_compute_pct",
        help="Quarantined units as a percentage of total on-hand units.",
    )
    recall_pct = fields.Float(
        string="Recall %",
        compute="_compute_pct",
        help="Recalled units as a percentage of total on-hand units.",
    )
    overall_score = fields.Float(
        string="Health score",
        compute="_compute_pct",
        help="Overall stock-health score (0-100): the percentage of on-hand "
        "stock that is healthy. Equal to Healthy %. Higher is better.",
    )

    @api.depends(
        "total_qty",
        "healthy_qty",
        "near_qty",
        "expired_qty",
        "quarantine_qty",
        "recall_qty",
    )
    def _compute_pct(self):
        for rec in self:
            total = rec.total_qty or 0.0
            if total > 0:
                rec.healthy_pct = 100.0 * rec.healthy_qty / total
                rec.near_pct = 100.0 * rec.near_qty / total
                rec.expired_pct = 100.0 * rec.expired_qty / total
                rec.quarantine_pct = 100.0 * rec.quarantine_qty / total
                rec.recall_pct = 100.0 * rec.recall_qty / total
            else:
                rec.healthy_pct = 0.0
                rec.near_pct = 0.0
                rec.expired_pct = 0.0
                rec.quarantine_pct = 0.0
                rec.recall_pct = 0.0
            rec.overall_score = rec.healthy_pct

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # Each live storage quant is classified into ONE bucket by strict
        # precedence (Recall > Quarantine > Expired > NearExpiry > Healthy) in a
        # single CASE, then summed per company. id is company_id (one row per
        # company, so it is a stable unique primary key).
        return """
            WITH classified AS (
                SELECT sq.company_id AS company_id,
                       sq.quantity AS qty,
                       CASE
                         WHEN lot.wms_lot_state = 'recalled' THEN 'recall'
                         WHEN lot.wms_lot_state = 'quarantine' THEN 'quarantine'
                         WHEN sq.wms_effective_expiry IS NOT NULL
                              AND sq.wms_effective_expiry < CURRENT_DATE THEN 'expired'
                         WHEN sq.wms_effective_expiry IS NOT NULL
                              AND sq.wms_effective_expiry <= CURRENT_DATE + INTEGER '30'
                              THEN 'near'
                         ELSE 'healthy'
                       END AS bucket
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                  LEFT JOIN stock_lot lot ON lot.id = sq.lot_id
                 WHERE sl.usage = 'internal'
                   AND COALESCE(sl.wms_is_damage, FALSE) = FALSE
                   AND COALESCE(sl.wms_is_repair, FALSE) = FALSE
                   AND sq.quantity > 0
                   AND sq.company_id IS NOT NULL
            )
            SELECT company_id AS id,
                   company_id AS company_id,
                   COALESCE(SUM(qty), 0.0) AS total_qty,
                   COALESCE(SUM(qty) FILTER (WHERE bucket = 'healthy'), 0.0) AS healthy_qty,
                   COALESCE(SUM(qty) FILTER (WHERE bucket = 'near'), 0.0) AS near_qty,
                   COALESCE(SUM(qty) FILTER (WHERE bucket = 'expired'), 0.0) AS expired_qty,
                   COALESCE(SUM(qty) FILTER (WHERE bucket = 'quarantine'), 0.0) AS quarantine_qty,
                   COALESCE(SUM(qty) FILTER (WHERE bucket = 'recall'), 0.0) AS recall_qty
              FROM classified
             GROUP BY company_id
        """
