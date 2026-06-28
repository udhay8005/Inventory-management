"""Wave 2 — Supplier Analytics: quality scorecard + receipt ledger.

Two read-only ``_auto=False`` SQL views, one per supplier-quality question:

* ``wms.supplier.scorecard`` — one row per res.partner that has ever supplied
  stock (i.e. is named on a lot's wms_supplier_id). It rolls up every quality
  signal the trust records against that partner: how many lots were received,
  how many were recalled, how many QC holds ended in rejection, how much stock
  was damaged (qty + value), and how many of their lots expired on the shelf.
  From those counts it derives an acceptance / rejection rate and a 0-100
  quality score (100 minus weighted penalties).

* ``wms.supplier.ledger`` — one row per received lot, the chronological receipt
  history per supplier (product / batch / expiry / live on-hand), so a buyer can
  drill from a poor scorecard straight into the individual batches behind it.

Both mirror the project's other reporting views (wms.lot.expiry.risk,
wms.expiry.alert, wms.occupancy): drop_view_if_exists + CREATE OR REPLACE VIEW
in init(), a _table_query property, and a staticmethod _query().

Supplier attribution: Wave 1 stores the supplier on the lot
(stock.lot.wms_supplier_id) and on the recall (wms.lot.recall.supplier_id). The
addon's wms_links.py adds a stored wms_supplier_id to wms.damage and
wms.lot.quarantine, so every quality event is attributable to a partner and the
SQL below can aggregate them directly.
"""

from odoo import fields, models, tools

# Quality-score penalty weights (points subtracted from a starting 100). Tuned
# so a supplier with a handful of recalls/rejections lands in the 60-80 band and
# a chronically bad one floors at 0 (the score is clamped to >= 0).
PENALTY_PER_RECALL = 15
PENALTY_PER_REJECTION = 10
PENALTY_PER_DAMAGE = 5
PENALTY_PER_EXPIRY = 3


class WmsSupplierScorecard(models.Model):
    _name = "wms.supplier.scorecard"
    _description = "Supplier quality scorecard"
    _auto = False
    _order = "quality_score, partner_id"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", string="Supplier", readonly=True)
    lots_received = fields.Integer(readonly=True, help="Distinct lots received from this supplier.")
    recall_count = fields.Integer(
        readonly=True,
        help="Recalls attributed to this supplier — either named on the recall "
        "notice, or recalls touching one of this supplier's lots.",
    )
    quarantine_total = fields.Integer(
        readonly=True, help="QC holds opened against this supplier's lots."
    )
    quarantine_reject_count = fields.Integer(
        readonly=True,
        help="QC holds against this supplier that ended in rejection or destruction.",
    )
    damaged_qty = fields.Float(
        readonly=True, help="Total units of this supplier's goods filed as damage (confirmed)."
    )
    damaged_value = fields.Float(
        readonly=True, help="Loss value of confirmed damage attributed to this supplier."
    )
    expired_lot_count = fields.Integer(
        readonly=True, help="Lots from this supplier whose expiry date is already in the past."
    )
    acceptance_rate = fields.Float(
        readonly=True,
        help="Share of received lots that were NOT recalled, rejected, or expired "
        "(0-100). Higher is better.",
    )
    rejection_rate = fields.Float(
        readonly=True,
        help="Share of received lots that were recalled, rejected, or expired (0-100).",
    )
    quality_score = fields.Float(
        readonly=True,
        help="0-100 quality score: starts at 100, subtracts weighted penalties for "
        "recalls, QC rejections, damage events, and expired lots. Clamped to 0.",
    )
    quality_band = fields.Selection(
        [("good", "Good"), ("watch", "Watch"), ("poor", "Poor")],
        readonly=True,
        help="GOOD = score >= 80, WATCH = 50-79, POOR = below 50.",
    )

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # One CTE per signal, all keyed on the supplier partner id, then a final
        # LEFT JOIN onto the set of suppliers that appear on any lot. recalls are
        # attributed two ways and de-duplicated: the recall's own supplier_id and
        # any recall whose m2m lot belongs to the supplier (table/columns follow
        # Odoo's auto-generated naming for wms.lot.recall.lot_ids).
        return """
            WITH suppliers AS (
                SELECT DISTINCT wms_supplier_id AS partner_id
                  FROM stock_lot
                 WHERE wms_supplier_id IS NOT NULL
            ),
            lots AS (
                SELECT wms_supplier_id AS partner_id,
                       COUNT(*) AS lots_received,
                       COUNT(*) FILTER (
                           WHERE expiration_date IS NOT NULL
                             AND expiration_date < NOW()
                       ) AS expired_lot_count
                  FROM stock_lot
                 WHERE wms_supplier_id IS NOT NULL
                 GROUP BY wms_supplier_id
            ),
            recalls AS (
                SELECT partner_id, COUNT(DISTINCT recall_id) AS recall_count
                  FROM (
                        SELECT r.id AS recall_id, r.supplier_id AS partner_id
                          FROM wms_lot_recall r
                         WHERE r.supplier_id IS NOT NULL
                        UNION
                        SELECT rel.wms_lot_recall_id AS recall_id,
                               l.wms_supplier_id AS partner_id
                          FROM stock_lot_wms_lot_recall_rel rel
                          JOIN stock_lot l ON l.id = rel.stock_lot_id
                         WHERE l.wms_supplier_id IS NOT NULL
                  ) attributed
                 GROUP BY partner_id
            ),
            quarantines AS (
                SELECT wms_supplier_id AS partner_id,
                       COUNT(*) AS quarantine_total,
                       COUNT(*) FILTER (
                           WHERE state IN ('rejected', 'destroyed')
                       ) AS quarantine_reject_count
                  FROM wms_lot_quarantine
                 WHERE wms_supplier_id IS NOT NULL
                 GROUP BY wms_supplier_id
            ),
            damages AS (
                SELECT wms_supplier_id AS partner_id,
                       COALESCE(SUM(quantity), 0.0) AS damaged_qty,
                       COALESCE(SUM(damage_value), 0.0) AS damaged_value
                  FROM wms_damage
                 WHERE wms_supplier_id IS NOT NULL
                   AND state = 'confirmed'
                 GROUP BY wms_supplier_id
            ),
            agg AS (
                SELECT s.partner_id,
                       COALESCE(l.lots_received, 0) AS lots_received,
                       COALESCE(l.expired_lot_count, 0) AS expired_lot_count,
                       COALESCE(rc.recall_count, 0) AS recall_count,
                       COALESCE(q.quarantine_total, 0) AS quarantine_total,
                       COALESCE(q.quarantine_reject_count, 0) AS quarantine_reject_count,
                       COALESCE(d.damaged_qty, 0.0) AS damaged_qty,
                       COALESCE(d.damaged_value, 0.0) AS damaged_value
                  FROM suppliers s
                  LEFT JOIN lots l ON l.partner_id = s.partner_id
                  LEFT JOIN recalls rc ON rc.partner_id = s.partner_id
                  LEFT JOIN quarantines q ON q.partner_id = s.partner_id
                  LEFT JOIN damages d ON d.partner_id = s.partner_id
            )
            SELECT a.partner_id AS id,
                   a.partner_id AS partner_id,
                   a.lots_received,
                   a.recall_count,
                   a.quarantine_total,
                   a.quarantine_reject_count,
                   a.damaged_qty,
                   a.damaged_value,
                   a.expired_lot_count,
                   -- bad lots = recalled + QC-rejected + expired, capped at the
                   -- number actually received so the rate can never exceed 100 pct.
                   CASE WHEN a.lots_received > 0 THEN
                        ROUND(
                            100.0 * (1 - LEAST(
                                a.recall_count
                                    + a.quarantine_reject_count
                                    + a.expired_lot_count,
                                a.lots_received
                            )::numeric / a.lots_received),
                            1
                        )
                        ELSE 100.0
                   END AS acceptance_rate,
                   CASE WHEN a.lots_received > 0 THEN
                        ROUND(
                            100.0 * LEAST(
                                a.recall_count
                                    + a.quarantine_reject_count
                                    + a.expired_lot_count,
                                a.lots_received
                            )::numeric / a.lots_received,
                            1
                        )
                        ELSE 0.0
                   END AS rejection_rate,
                   GREATEST(
                       0.0,
                       100.0
                           - {recall_w} * a.recall_count
                           - {reject_w} * a.quarantine_reject_count
                           - {damage_w} * (CASE WHEN a.damaged_qty > 0 THEN 1 ELSE 0 END)
                           - {expiry_w} * a.expired_lot_count
                   )::numeric AS quality_score,
                   CASE
                     WHEN GREATEST(
                            0.0,
                            100.0
                                - {recall_w} * a.recall_count
                                - {reject_w} * a.quarantine_reject_count
                                - {damage_w} * (CASE WHEN a.damaged_qty > 0 THEN 1 ELSE 0 END)
                                - {expiry_w} * a.expired_lot_count
                          ) >= 80 THEN 'good'
                     WHEN GREATEST(
                            0.0,
                            100.0
                                - {recall_w} * a.recall_count
                                - {reject_w} * a.quarantine_reject_count
                                - {damage_w} * (CASE WHEN a.damaged_qty > 0 THEN 1 ELSE 0 END)
                                - {expiry_w} * a.expired_lot_count
                          ) >= 50 THEN 'watch'
                     ELSE 'poor'
                   END AS quality_band
              FROM agg a
        """.format(  # nosec B608 — only module-level integer constants are
            # interpolated (the penalty weights below); no user input ever
            # reaches this SQL, so this is not an injection vector.
            recall_w=PENALTY_PER_RECALL,
            reject_w=PENALTY_PER_REJECTION,
            damage_w=PENALTY_PER_DAMAGE,
            expiry_w=PENALTY_PER_EXPIRY,
        )


class WmsSupplierLedger(models.Model):
    _name = "wms.supplier.ledger"
    _description = "Supplier receipt ledger (per-lot)"
    _auto = False
    _order = "received_on desc, id desc"
    _rec_name = "lot_id"

    partner_id = fields.Many2one("res.partner", string="Supplier", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Batch / lot", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    supplier_batch = fields.Char(readonly=True, help="Supplier's own batch code.")
    supplier_invoice = fields.Char(readonly=True, help="Inbound invoice / delivery reference.")
    received_on = fields.Datetime(
        readonly=True, help="When the lot record was created (receipt time)."
    )
    expiration_date = fields.Datetime(readonly=True)
    lot_state = fields.Selection(
        [
            ("available", "Available"),
            ("quarantine", "Quarantine"),
            ("recalled", "Recalled"),
            ("destroyed", "Destroyed"),
        ],
        readonly=True,
        help="Current lifecycle state of the lot.",
    )
    on_hand = fields.Float(readonly=True, help="Units of this lot still in live internal storage.")

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # Live on-hand per lot, restricted to issuable internal storage (the
        # same exclusion the expiry-risk view uses: no damage / repair sinks).
        return """
            WITH oh AS (
                SELECT sq.lot_id,
                       SUM(sq.quantity) AS on_hand
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
                   lot.wms_supplier_id AS partner_id,
                   lot.id AS lot_id,
                   lot.product_id AS product_id,
                   lot.company_id AS company_id,
                   lot.wms_supplier_batch AS supplier_batch,
                   lot.wms_supplier_invoice AS supplier_invoice,
                   lot.create_date AS received_on,
                   lot.expiration_date AS expiration_date,
                   lot.wms_lot_state AS lot_state,
                   COALESCE(oh.on_hand, 0.0) AS on_hand
              FROM stock_lot lot
              LEFT JOIN oh ON oh.lot_id = lot.id
             WHERE lot.wms_supplier_id IS NOT NULL
        """
