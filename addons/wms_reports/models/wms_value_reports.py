"""Cost / value reporting (Batch 5).

Two read-only SQL views (``_auto = False``) that put a money figure on the
warehouse. The trust BUYS and CONSUMES stock (it never sells), so the questions
that matter are "how much capital is sitting on the shelves right now?" and
"what did we consume, by value, this month?".

Cost source
-----------
``product.product.standard_price`` is a company-dependent field, stored as a
JSONB column keyed by company id (e.g. ``{"1": 42.5}``). We read the right
company's cost in SQL with ``standard_price ->> company_id::text`` so the value
is computed in the database and stays aggregatable in pivot / graph views.
"""

from odoo import api, fields, models, tools
from odoo.addons.wms_barcode.models.stock_picking import WMS_ISSUED_FOR_SELECTION


class WmsStockValueReport(models.Model):
    """Current on-hand value per product = unit cost x quantity on internal
    locations. One row per (product, company)."""

    _name = "wms.stock.value.report"
    _description = "Current stock value (cost x on-hand)"
    _auto = False
    _order = "stock_value desc"

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    qty_on_hand = fields.Float(string="On hand", readonly=True)
    unit_cost = fields.Float(string="Unit cost", readonly=True)
    stock_value = fields.Float(string="Stock value", readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_stock_value_report AS
            SELECT
                row_number() OVER (ORDER BY sq.product_id, sq.company_id)::int AS id,
                sq.product_id AS product_id,
                pt.categ_id   AS categ_id,
                sq.company_id AS company_id,
                SUM(sq.quantity) AS qty_on_hand,
                COALESCE((pp.standard_price ->> sq.company_id::text)::numeric, 0)
                    AS unit_cost,
                SUM(sq.quantity)
                    * COALESCE((pp.standard_price ->> sq.company_id::text)::numeric, 0)
                    AS stock_value
            FROM stock_quant sq
            JOIN product_product pp ON pp.id = sq.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN stock_location loc ON loc.id = sq.location_id
            WHERE loc.usage = 'internal' AND sq.quantity > 0
                  -- Count only WAREHOUSE STORAGE (slots / floor / lot-stock and
                  -- its children). The 'Trust internal use' sink is internal but
                  -- holds already-consumed goods, so it must NOT inflate on-hand
                  -- value. parent_path LIKE <lot_stock>% is the SQL child_of.
                  AND EXISTS (
                      SELECT 1
                      FROM stock_warehouse w
                      JOIN stock_location ls ON ls.id = w.lot_stock_id
                      WHERE loc.parent_path LIKE ls.parent_path || '%'
                  )
            GROUP BY sq.product_id, pt.categ_id, sq.company_id, pp.standard_price
            """
        )


class WmsConsumptionValueReport(models.Model):
    """Consumed value per product per month = unit cost x issued quantity.
    Counts only done Scan Issue move lines (the immutable wms_is_scan_issue
    flag), so returns and manual adjustments don't inflate consumption."""

    _name = "wms.consumption.value.report"
    _description = "Consumption value (issued qty x cost)"
    _auto = False
    _order = "period desc, consumption_value desc"

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    department_id = fields.Many2one("wms.department", string="Department", readonly=True)
    issued_for = fields.Selection(WMS_ISSUED_FOR_SELECTION, string="Issued for", readonly=True)
    period = fields.Date(string="Month", readonly=True)
    qty_out = fields.Float(string="Issued qty", readonly=True)
    unit_cost = fields.Float(string="Unit cost", readonly=True)
    consumption_value = fields.Float(string="Consumption value", readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_consumption_value_report AS
            SELECT
                row_number() OVER (
                    ORDER BY date_trunc('month', sml.date), sml.product_id
                )::int AS id,
                sml.product_id AS product_id,
                pt.categ_id    AS categ_id,
                sml.company_id AS company_id,
                sp.wms_department_id AS department_id,
                sp.wms_issued_for AS issued_for,
                date_trunc('month', sml.date)::date AS period,
                SUM(sml.quantity) AS qty_out,
                -- FPAT High: read the snapshot cost frozen at validate-time
                -- (wms_unit_cost_at_done) so a later standard_price change
                -- does not rewrite past months. Fall back to current cost
                -- ONLY for legacy rows where the snapshot is NULL (pre-v16).
                COALESCE(
                    sml.wms_unit_cost_at_done,
                    (pp.standard_price ->> sml.company_id::text)::numeric,
                    0
                ) AS unit_cost,
                SUM(
                    sml.quantity * COALESCE(
                        sml.wms_unit_cost_at_done,
                        (pp.standard_price ->> sml.company_id::text)::numeric,
                        0
                    )
                ) AS consumption_value
            FROM stock_move_line sml
            JOIN stock_picking sp ON sp.id = sml.picking_id
            JOIN product_product pp ON pp.id = sml.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sp.wms_is_scan_issue = TRUE AND sml.state = 'done'
                  -- an issue that was Undone within the window nets to zero
                  -- consumption: the stock came straight back, so exclude it.
                  AND sp.wms_reversed_by_id IS NULL
            GROUP BY date_trunc('month', sml.date), sml.product_id,
                     pt.categ_id, sml.company_id, sp.wms_department_id,
                     sp.wms_issued_for,
                     sml.wms_unit_cost_at_done, pp.standard_price
            """
        )
