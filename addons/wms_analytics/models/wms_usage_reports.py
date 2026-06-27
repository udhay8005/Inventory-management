"""Wave 2 Wave-2-3 — Department / Animal / Medicine usage reporting.

Three read-only ``_auto = False`` SQL views that answer "WHO consumed WHAT,
and how much did it cost?" off the Scan Issue audit trail:

* ``wms.department.usage``     — consumption qty / value per department.
* ``wms.animal.usage``         — consumption qty / value per animal (cow).
* ``wms.medicine.consumption`` — consumption of medicine products per product
  per month bucket (only ``wms_product_kind = 'medicine'``).

Data source & costing
----------------------
Consumption = done Scan Issue ``stock.move.line`` rows, identified by the
immutable ``stock_picking.wms_is_scan_issue`` flag and excluding pickings that
were Undone (``wms_reversed_by_id IS NOT NULL`` nets to zero consumption) —
exactly the filter the Consumption Value report (wms_reports) uses.

Value reads the per-line snapshot ``wms_unit_cost_at_done`` frozen at
validate-time, falling back to the live company-keyed ``standard_price`` JSONB
(``->> company_id::text``) only for legacy rows where the snapshot is NULL — so
a later cost change never rewrites historical value.

The issue dimensions (``wms_department_id``, ``wms_animal_id``,
``wms_purpose_id``) are stamped on the picking by the Scan Issue wizard
(``addons/wms_barcode/wizards/scan_issue.py``). There is no separate "vaccine"
WMS kind in ``WMS_KIND_SELECTION`` — veterinary injections/vaccines are all the
``medicine`` kind, so the medicine view filters on ``('medicine')`` only.

Mirrors the structure of ``wms_lot_expiry_risk.py`` /
``wms_reports/models/wms_value_reports.py`` (the project's other reporting
views): ``_name`` / ``_description`` / ``_auto = False`` / ``_order`` /
``_rec_name``, an ``init()`` that drops + (re)creates the view, and a
``staticmethod _query()`` holding the SQL.
"""

from odoo import fields, models, tools

# Done Scan Issue move lines, excluding undone (reversed) pickings — the same
# definition of "real consumption" the Consumption Value report uses.
_CONSUMPTION_FROM = """
            FROM stock_move_line sml
            JOIN stock_picking sp ON sp.id = sml.picking_id
            JOIN product_product pp ON pp.id = sml.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
           WHERE sp.wms_is_scan_issue = TRUE
             AND sml.state = 'done'
             AND sp.wms_reversed_by_id IS NULL
"""

# Per-line value: frozen snapshot first, live company cost only as a legacy
# fallback. Reused verbatim in the SELECT and the value SUM of every view.
_LINE_VALUE = """COALESCE(
                       sml.wms_unit_cost_at_done,
                       (pp.standard_price ->> sml.company_id::text)::numeric,
                       0
                   )"""


class WmsDepartmentUsage(models.Model):
    """Consumption quantity / value per department per month.

    One row per (department, product, company, month) so the pivot/graph can
    drill department -> product or roll a department up to a single spend line.
    Pickings with no department stamped (legacy) collapse into a NULL
    department group.
    """

    _name = "wms.department.usage"
    _description = "Department usage (consumption qty / value per department)"
    _auto = False
    _order = "period desc, usage_value desc"
    _rec_name = "department_id"

    department_id = fields.Many2one("wms.department", string="Department", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    period = fields.Date(string="Month", readonly=True)
    qty_out = fields.Float(string="Issued qty", readonly=True)
    usage_value = fields.Float(string="Usage value", readonly=True)

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        return (
            """
            SELECT row_number() OVER (
                       ORDER BY date_trunc('month', sml.date),
                                sp.wms_department_id, sml.product_id
                   )::int AS id,
                   sp.wms_department_id AS department_id,
                   sml.product_id AS product_id,
                   pt.categ_id AS categ_id,
                   sml.company_id AS company_id,
                   date_trunc('month', sml.date)::date AS period,
                   SUM(sml.quantity) AS qty_out,
                   SUM(sml.quantity * """
            + _LINE_VALUE
            + """) AS usage_value
            """
            + _CONSUMPTION_FROM
            + """
             GROUP BY date_trunc('month', sml.date), sp.wms_department_id,
                      sml.product_id, pt.categ_id, sml.company_id
            """
        )


class WmsAnimalUsage(models.Model):
    """Consumption quantity / value per animal (cow) per month.

    Only counts issues that named an animal (``wms_animal_id IS NOT NULL``) —
    most issues are department-wide and carry no animal, so including them would
    drown the per-animal signal. One row per (animal, product, company, month).
    """

    _name = "wms.animal.usage"
    _description = "Animal usage (consumption qty / value per animal)"
    _auto = False
    _order = "period desc, usage_value desc"
    _rec_name = "animal_id"

    animal_id = fields.Many2one("wms.animal", string="Animal / cow", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    period = fields.Date(string="Month", readonly=True)
    qty_out = fields.Float(string="Issued qty", readonly=True)
    usage_value = fields.Float(string="Usage value", readonly=True)

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        return (
            """
            SELECT row_number() OVER (
                       ORDER BY date_trunc('month', sml.date),
                                sp.wms_animal_id, sml.product_id
                   )::int AS id,
                   sp.wms_animal_id AS animal_id,
                   sml.product_id AS product_id,
                   pt.categ_id AS categ_id,
                   sml.company_id AS company_id,
                   date_trunc('month', sml.date)::date AS period,
                   SUM(sml.quantity) AS qty_out,
                   SUM(sml.quantity * """
            + _LINE_VALUE
            + """) AS usage_value
            """
            + _CONSUMPTION_FROM
            + """
             AND sp.wms_animal_id IS NOT NULL
             GROUP BY date_trunc('month', sml.date), sp.wms_animal_id,
                      sml.product_id, pt.categ_id, sml.company_id
            """
        )


class WmsMedicineConsumption(models.Model):
    """Medicine consumption per product per month bucket.

    Restricted to products whose ``product.template.wms_product_kind`` is
    ``medicine`` (veterinary injections / ointments / vaccines — the trust has
    no separate 'vaccine' kind). Carries department + animal so a vet can see
    not just how much medicine was used, but for which department / which cow.
    One row per (product, department, animal, company, month).
    """

    _name = "wms.medicine.consumption"
    _description = "Medicine consumption (per product over time)"
    _auto = False
    _order = "period desc, consumption_value desc"
    _rec_name = "product_id"

    product_id = fields.Many2one("product.product", string="Medicine", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    department_id = fields.Many2one("wms.department", string="Department", readonly=True)
    animal_id = fields.Many2one("wms.animal", string="Animal / cow", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    period = fields.Date(string="Month", readonly=True)
    qty_out = fields.Float(string="Issued qty", readonly=True)
    unit_cost = fields.Float(string="Unit cost", readonly=True)
    consumption_value = fields.Float(string="Consumption value", readonly=True)

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        return (
            """
            SELECT row_number() OVER (
                       ORDER BY date_trunc('month', sml.date), sml.product_id
                   )::int AS id,
                   sml.product_id AS product_id,
                   pt.categ_id AS categ_id,
                   sp.wms_department_id AS department_id,
                   sp.wms_animal_id AS animal_id,
                   sml.company_id AS company_id,
                   date_trunc('month', sml.date)::date AS period,
                   SUM(sml.quantity) AS qty_out,
                   """
            + _LINE_VALUE
            + """ AS unit_cost,
                   SUM(sml.quantity * """
            + _LINE_VALUE
            + """) AS consumption_value
            """
            + _CONSUMPTION_FROM
            + """
             AND pt.wms_product_kind = 'medicine'
             GROUP BY date_trunc('month', sml.date), sml.product_id, pt.categ_id,
                      sp.wms_department_id, sp.wms_animal_id, sml.company_id,
                      sml.wms_unit_cost_at_done, pp.standard_price
            """
        )
