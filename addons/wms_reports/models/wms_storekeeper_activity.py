import pytz
from odoo import api, fields, models, tools


class WmsStorekeeperActivity(models.Model):
    """One-row-per-event timeline of everything a Store Keeper has done.

    Why
    ---
    The trust runs the warehouse on a shared Odoo login (the
    `storekeeper` user). The actual humans rotate on the desk and pick
    "Store Keeper on duty" from the roster on every action. The Admin
    needs a single screen to ask:

      * What did Suresh / Ramesh / Lakshmi each do today?
      * How many issues vs receipts on Tuesday vs Wednesday?
      * Who was on the desk when DMG/00005 was filed?

    Method
    ------
    Build a SQL view by UNION-ing three sources:

      1. `stock.picking` — Scan Receipt / Scan Issue / Scan Return /
         internal damage moves all carry `wms_storekeeper_id`. The
         picking-type code (incoming / outgoing / internal) becomes the
         `activity_type` so the pivot lets the Admin slice by direction
         of stock.
      2. `wms.damage` — every damage event records the keeper who took
         the report.
      3. `wms.repair.order` — every repair order records who created /
         drove it.

    Each event becomes one row, with `activity_date` = the day-bucket
    used in the pivot view. The model is `_auto = False` so there's no
    table to migrate; just refresh the SQL view at module upgrade.

    Audience
    --------
    Read access is granted to WMS / Manager only — Store Keepers do
    not need to audit each other. The Admin opens this from WMS →
    Reports → Store Keeper Activity.
    """

    _name = "wms.storekeeper.activity"
    _description = "Store Keeper activity log"
    _auto = False
    _order = "activity_datetime desc"

    storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper",
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Odoo user",
        readonly=True,
        help="The Odoo login used to record this event. Usually the "
        "shared `storekeeper` user — the real human is in the "
        "Store Keeper column above.",
    )
    activity_type = fields.Selection(
        [
            ("receipt", "Scan Receipt"),
            ("return", "Scan Return"),
            ("issue", "Scan Issue"),
            ("internal", "Internal move"),
            ("damage", "Damage filed"),
            ("repair", "Repair order"),
        ],
        string="Activity",
        readonly=True,
    )
    reference = fields.Char(string="Reference", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    quantity = fields.Float(readonly=True)
    partner_name = fields.Char(
        string="Counterparty",
        readonly=True,
        help="Whichever audit-trail name applies to this event — the "
        "Delivered-by on a receipt, the Taken-by on an issue, the "
        "Reported-by on a damage.",
    )
    picking_id = fields.Many2one("stock.picking", readonly=True)
    damage_id = fields.Many2one("wms.damage", readonly=True)
    repair_id = fields.Many2one("wms.repair.order", readonly=True)
    activity_date = fields.Date(string="Day", readonly=True)
    activity_datetime = fields.Datetime(string="When", readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Bucket each event by the COMPANY-LOCAL calendar day, not the raw UTC
        # date. Odoo stores datetimes as naive UTC, so casting date_done /
        # create_date straight to ::date lands a late-evening IST event on the
        # *next* UTC day — "what did Suresh do Tuesday?" then shows it under
        # Wednesday. An event's local date is historical and never changes, so
        # resolving the company tz once and baking it into the view is correct
        # here (unlike wms_returns_due's live "today", which must join for the
        # tz). The tz is passed as a query PARAMETER (psycopg2 quotes it — no
        # injection); pytz still validates it so a malformed value falls back to
        # UTC instead of erroring the view DDL.
        tz_local = self.env.company.partner_id.tz or "UTC"
        if tz_local not in pytz.all_timezones_set:
            tz_local = "UTC"
        # ROW_NUMBER over the UNION gives a unique, stable-per-snapshot
        # primary key — needed because Odoo's ORM requires `id` even on
        # synthetic views. We can't just (picking_id * 3 + 0) because
        # pickings can produce multiple product-rows.
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_storekeeper_activity AS
            WITH picking_events AS (
                SELECT
                    p.wms_storekeeper_id AS storekeeper_id,
                    p.create_uid         AS user_id,
                    CASE pt.code
                        WHEN 'incoming' THEN
                            CASE WHEN p.name LIKE 'IN/RET%%' THEN 'return'
                                 ELSE 'receipt' END
                        WHEN 'outgoing' THEN 'issue'
                        WHEN 'internal' THEN 'internal'
                        ELSE 'internal'
                    END AS activity_type,
                    p.name AS reference,
                    sm.product_id AS product_id,
                    sm.product_uom_qty AS quantity,
                    p.wms_taken_by AS partner_name,
                    p.id AS picking_id,
                    NULL::int AS damage_id,
                    NULL::int AS repair_id,
                    (COALESCE(p.date_done, p.scheduled_date)
                        AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date AS activity_date,
                    COALESCE(p.date_done, p.scheduled_date)       AS activity_datetime
                FROM stock_picking p
                JOIN stock_picking_type pt ON pt.id = p.picking_type_id
                JOIN stock_move sm
                       ON sm.picking_id = p.id
                      AND sm.state = 'done'
                WHERE p.wms_storekeeper_id IS NOT NULL
            ),
            damage_events AS (
                SELECT
                    d.wms_storekeeper_id AS storekeeper_id,
                    d.create_uid         AS user_id,
                    'damage'::varchar    AS activity_type,
                    d.name               AS reference,
                    d.product_id         AS product_id,
                    d.quantity           AS quantity,
                    d.wms_reported_by    AS partner_name,
                    NULL::int            AS picking_id,
                    d.id                 AS damage_id,
                    NULL::int            AS repair_id,
                    (d.create_date
                        AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date AS activity_date,
                    d.create_date        AS activity_datetime
                FROM wms_damage d
                WHERE d.wms_storekeeper_id IS NOT NULL
            ),
            repair_events AS (
                SELECT
                    r.wms_storekeeper_id AS storekeeper_id,
                    r.create_uid         AS user_id,
                    'repair'::varchar    AS activity_type,
                    r.name               AS reference,
                    r.product_id         AS product_id,
                    r.quantity           AS quantity,
                    NULL::varchar        AS partner_name,
                    NULL::int            AS picking_id,
                    NULL::int            AS damage_id,
                    r.id                 AS repair_id,
                    (r.create_date
                        AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date AS activity_date,
                    r.create_date        AS activity_datetime
                FROM wms_repair_order r
                WHERE r.wms_storekeeper_id IS NOT NULL
            ),
            all_events AS (
                SELECT * FROM picking_events
                UNION ALL
                SELECT * FROM damage_events
                UNION ALL
                SELECT * FROM repair_events
            )
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY activity_datetime DESC NULLS LAST,
                             reference,
                             product_id
                )::int AS id,
                storekeeper_id,
                user_id,
                activity_type,
                reference,
                product_id,
                quantity,
                partner_name,
                picking_id,
                damage_id,
                repair_id,
                activity_date,
                activity_datetime
            FROM all_events
        """,
            {"tz": tz_local},
        )
