"""Wave 2 — Disposal / loss analytics.

A single read-only report unioning every way stock physically leaves the trust
as a *loss* (not an issue/consumption):

  (a) confirmed ``wms.damage`` events — the explicit "this got broken / expired /
      contaminated" record, carrying its frozen ``damage_value`` snapshot; and
  (b) destroyed lots — ``stock.lot`` rows whose lifecycle reached
      ``wms_lot_state = 'destroyed'`` (see wms_perishable/models/stock_lot.py),
      valued at the lot's current on-hand quantity x the product's unit cost as a
      proxy for what was lost when it was destroyed.

Implemented as an ``_auto=False`` SQL view (read-only, always fresh, no storage),
mirroring wms.lot.expiry.risk and the project's other reporting views. The two
branches are UNIONed; ids are kept globally unique by offsetting the destroyed
branch (damage ids stay as-is; lot ids are negated) so each report row has a
stable, collision-free primary key.
"""

from odoo import fields, models, tools


class WmsDisposalReport(models.Model):
    _name = "wms.disposal.report"
    _description = "Disposal / loss analytics (damage + destroyed lots)"
    _auto = False
    _order = "disposal_date desc, id desc"
    _rec_name = "product_id"

    source = fields.Selection(
        [
            ("damage", "Damage event"),
            ("destroyed", "Destroyed lot"),
        ],
        readonly=True,
        help="Where the loss originated: a confirmed damage event, or a lot "
        "whose lifecycle reached the 'destroyed' state.",
    )
    reason = fields.Char(
        readonly=True,
        help="Damage reason for damage events; 'Destroyed lot' for destroyed lots.",
    )
    product_id = fields.Many2one("product.product", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    quantity = fields.Float(
        readonly=True,
        help="Units lost: the damage quantity, or the destroyed lot's on-hand "
        "quantity at the time of reporting (a proxy for qty-at-destroy).",
    )
    disposal_value = fields.Float(
        readonly=True,
        help="Monetary value of the loss. For damage this is the frozen "
        "damage_value snapshot taken at confirm; for destroyed lots it is "
        "on-hand quantity x the product's unit cost.",
    )
    disposal_date = fields.Datetime(
        readonly=True, help="When the loss was recorded (damage create date / lot write date)."
    )
    month = fields.Date(readonly=True, help="Disposal month (first day) for trend grouping.")

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # Branch (a): confirmed damage events. damage_value is the frozen
        # loss-at-confirm snapshot. Positive ids = damage primary key.
        #
        # Branch (b): destroyed lots. There is no historical "qty at destroy",
        # so use the lot's CURRENT live on-hand (internal storage, excluding the
        # damage/repair sinks — same exclusion the expiry-risk view uses) as a
        # proxy, valued at the product's per-company unit cost. Negated lot id
        # keeps the union's primary key globally unique and collision-free.
        # NOTE: wms.damage defines no company_id field, so the wms_damage table
        # has no such column. Derive the company from the source slot's location
        # (native stock_location.company_id), falling back to the damage's stored
        # warehouse company.
        return """
            SELECT d.id AS id,
                   'damage'::varchar AS source,
                   CASE d.reason
                        WHEN 'broken' THEN 'Broken'
                        WHEN 'expired' THEN 'Expired'
                        WHEN 'contaminated' THEN 'Contaminated'
                        WHEN 'other' THEN 'Other'
                        ELSE d.reason
                   END AS reason,
                   d.product_id AS product_id,
                   COALESCE(sl.company_id, wh.company_id) AS company_id,
                   d.quantity AS quantity,
                   COALESCE(d.damage_value, 0.0) AS disposal_value,
                   d.create_date AS disposal_date,
                   date_trunc('month', d.create_date)::date AS month
              FROM wms_damage d
              LEFT JOIN stock_location sl ON sl.id = d.source_slot_id
              LEFT JOIN stock_warehouse wh ON wh.id = d.warehouse_id
             WHERE d.state = 'confirmed'

            UNION ALL

            SELECT (-lot.id) AS id,
                   'destroyed'::varchar AS source,
                   'Destroyed lot'::varchar AS reason,
                   lot.product_id AS product_id,
                   lot.company_id AS company_id,
                   COALESCE(oh.on_hand, 0.0) AS quantity,
                   COALESCE(oh.on_hand, 0.0)
                       * COALESCE(
                           (pp.standard_price ->> COALESCE(lot.company_id, oh.company_id)::text)
                               ::numeric,
                           0)
                       AS disposal_value,
                   lot.write_date AS disposal_date,
                   date_trunc('month', lot.write_date)::date AS month
              FROM stock_lot lot
              JOIN product_product pp ON pp.id = lot.product_id
              LEFT JOIN (
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
              ) oh ON oh.lot_id = lot.id
             WHERE lot.wms_lot_state = 'destroyed'
        """
