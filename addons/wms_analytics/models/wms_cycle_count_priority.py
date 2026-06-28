"""Wave 2 #14 — Cycle Count Intelligence.

Wave 1's *Cycle Count Due* (wms.cycle.count.due) is a flat age list: any slot
not counted in > 30 days shows up, ordered by age alone. That treats a quiet,
always-accurate floor bay the same as a fast-moving medicine slot that drifted
on the last three audits. The keeper has finite hours; this view tells them
*which slot to count first*.

It scores every storage location (slot / floor) on three independent signals
and folds them into a single composite ``priority_score`` (higher = count
sooner):

  * **age** — days since the slot was last counted (wms_last_counted). Older =
    more drift has had time to accumulate.
  * **accuracy history** — how many past audit lines at this slot came back with
    a non-zero variance (counted != expected). A slot that has been wrong before
    is more likely to be wrong again.
  * **velocity / throughput** — the fastest AI velocity_class among the products
    currently stored in the slot (wms.forecast). Fast-moving stock turns over
    between counts, so book vs shelf drifts quicker and is worth re-counting
    sooner than dead stock.

Each signal becomes bounded points; the sum is the score, and the score is
bucketed into a LOW / MEDIUM / HIGH ``priority_band``.

Implemented as an ``_auto=False`` SQL view (read-only, always fresh, no
storage), mirroring wms.lot.expiry.risk and wms.cycle.count.due.
"""

from odoo import fields, models, tools


class WmsCycleCountPriority(models.Model):
    _name = "wms.cycle.count.priority"
    _description = "Cycle-count priority (risk-ranked count order)"
    _auto = False
    # priority_score is a REAL view column (computed in SQL), so it is safe in
    # _order — never order an _auto=False view by a non-stored computed field.
    _order = "priority_score desc, days_since_count desc"
    _rec_name = "location_id"

    location_id = fields.Many2one("stock.location", readonly=True, string="Slot")
    rack_id = fields.Many2one("stock.location", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    last_counted = fields.Datetime(readonly=True)
    days_since_count = fields.Integer(
        readonly=True,
        help="Calendar days since this slot was last counted or had stock "
        "movement. Higher = more time for the books to drift.",
    )
    mismatch_count = fields.Integer(
        readonly=True,
        help="Number of past audit lines at this slot that came back with a "
        "non-zero variance (counted != expected). A history of being wrong "
        "raises the count priority.",
    )
    velocity_class = fields.Selection(
        [("fast", "Fast"), ("normal", "Normal"), ("slow", "Slow"), ("dead", "Dead")],
        readonly=True,
        help="Fastest AI velocity class among the products currently stored "
        "here. Fast-moving stock drifts between counts.",
    )
    on_hand = fields.Float(readonly=True, help="Total on-hand units in this slot.")
    distinct_products = fields.Integer(
        readonly=True, help="Number of distinct products currently in this slot."
    )
    age_points = fields.Integer(readonly=True, help="Score contribution from count age.")
    mismatch_points = fields.Integer(
        readonly=True, help="Score contribution from past audit variances."
    )
    velocity_points = fields.Integer(
        readonly=True, help="Score contribution from product velocity."
    )
    priority_score = fields.Integer(
        readonly=True,
        help="Composite priority (age + accuracy history + velocity). Higher = "
        "count this slot sooner.",
    )
    priority_band = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        readonly=True,
        help="LOW = leave for the routine cycle. MEDIUM = bring forward. " "HIGH = count next.",
    )

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # One row per storage location (slot / floor). days_since_count is the
        # inline delta from the stored wms_last_counted (never counted => a large
        # sentinel so it sorts to the top). mismatch_count counts non-zero
        # variance audit lines ever recorded at the slot. velocity is the fastest
        # class among products with live on-hand here (fast > normal > slow >
        # dead). The three signals become bounded point buckets and sum into
        # priority_score; the band thresholds key off that score.
        #
        # NOTE: no literal percent sign anywhere in this string (the project's
        # _table_query path inlines it into parameterized search SQL).
        return """
            WITH base AS (
                SELECT s.id AS loc_id,
                       r.id AS rack_id,
                       s.company_id AS company_id,
                       s.wms_last_counted AS last_counted,
                       COALESCE(
                           CURRENT_DATE - s.wms_last_counted::date, 999
                       ) AS days_since_count
                  FROM stock_location s
                  LEFT JOIN stock_location c
                    ON c.id = s.location_id AND c.wms_location_type = 'compartment'
                  LEFT JOIN stock_location r
                    ON r.id = c.location_id AND r.wms_location_type = 'rack'
                 WHERE s.wms_location_type IN ('slot', 'floor')
                   AND s.usage = 'internal'
            ),
            mm AS (
                SELECT al.location_id AS loc_id,
                       COUNT(*) AS mismatch_count
                  FROM wms_audit_line al
                 WHERE al.variance <> 0
                 GROUP BY al.location_id
            ),
            oh AS (
                SELECT q.location_id AS loc_id,
                       SUM(q.quantity) AS on_hand,
                       COUNT(DISTINCT q.product_id) AS distinct_products,
                       MIN(
                           CASE f.velocity_class
                               WHEN 'fast' THEN 1
                               WHEN 'normal' THEN 2
                               WHEN 'slow' THEN 3
                               WHEN 'dead' THEN 4
                               ELSE 5
                           END
                       ) AS velocity_rank
                  FROM stock_quant q
                  LEFT JOIN wms_forecast f ON f.product_id = q.product_id
                 WHERE q.quantity > 0
                 GROUP BY q.location_id
            )
            SELECT b.loc_id AS id,
                   b.loc_id AS location_id,
                   b.rack_id AS rack_id,
                   b.company_id AS company_id,
                   b.last_counted AS last_counted,
                   b.days_since_count AS days_since_count,
                   COALESCE(mm.mismatch_count, 0) AS mismatch_count,
                   COALESCE(oh.on_hand, 0.0) AS on_hand,
                   COALESCE(oh.distinct_products, 0) AS distinct_products,
                   CASE oh.velocity_rank
                       WHEN 1 THEN 'fast'
                       WHEN 2 THEN 'normal'
                       WHEN 3 THEN 'slow'
                       WHEN 4 THEN 'dead'
                       ELSE NULL
                   END AS velocity_class,
                   -- age points: 0 (<=30d) .. 40 (>=180d), stepped
                   CASE
                       WHEN b.days_since_count >= 180 THEN 40
                       WHEN b.days_since_count >= 90 THEN 30
                       WHEN b.days_since_count >= 60 THEN 20
                       WHEN b.days_since_count >= 30 THEN 10
                       ELSE 0
                   END AS age_points,
                   -- mismatch points: capped at 30 (10 per past variance line)
                   LEAST(COALESCE(mm.mismatch_count, 0) * 10, 30) AS mismatch_points,
                   -- velocity points: fast 30, normal 20, slow 10, dead/none 0
                   CASE oh.velocity_rank
                       WHEN 1 THEN 30
                       WHEN 2 THEN 20
                       WHEN 3 THEN 10
                       ELSE 0
                   END AS velocity_points,
                   (
                       CASE
                           WHEN b.days_since_count >= 180 THEN 40
                           WHEN b.days_since_count >= 90 THEN 30
                           WHEN b.days_since_count >= 60 THEN 20
                           WHEN b.days_since_count >= 30 THEN 10
                           ELSE 0
                       END
                       + LEAST(COALESCE(mm.mismatch_count, 0) * 10, 30)
                       + CASE oh.velocity_rank
                             WHEN 1 THEN 30
                             WHEN 2 THEN 20
                             WHEN 3 THEN 10
                             ELSE 0
                         END
                   ) AS priority_score,
                   CASE
                       WHEN (
                           CASE
                               WHEN b.days_since_count >= 180 THEN 40
                               WHEN b.days_since_count >= 90 THEN 30
                               WHEN b.days_since_count >= 60 THEN 20
                               WHEN b.days_since_count >= 30 THEN 10
                               ELSE 0
                           END
                           + LEAST(COALESCE(mm.mismatch_count, 0) * 10, 30)
                           + CASE oh.velocity_rank
                                 WHEN 1 THEN 30
                                 WHEN 2 THEN 20
                                 WHEN 3 THEN 10
                                 ELSE 0
                             END
                       ) >= 50 THEN 'high'
                       WHEN (
                           CASE
                               WHEN b.days_since_count >= 180 THEN 40
                               WHEN b.days_since_count >= 90 THEN 30
                               WHEN b.days_since_count >= 60 THEN 20
                               WHEN b.days_since_count >= 30 THEN 10
                               ELSE 0
                           END
                           + LEAST(COALESCE(mm.mismatch_count, 0) * 10, 30)
                           + CASE oh.velocity_rank
                                 WHEN 1 THEN 30
                                 WHEN 2 THEN 20
                                 WHEN 3 THEN 10
                                 ELSE 0
                             END
                       ) >= 20 THEN 'medium'
                       ELSE 'low'
                   END AS priority_band
              FROM base b
              LEFT JOIN mm ON mm.loc_id = b.loc_id
              LEFT JOIN oh ON oh.loc_id = b.loc_id
        """
