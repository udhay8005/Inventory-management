from odoo import api, fields, models, tools


class WmsToolFleetSummary(models.Model):
    """Concurrent-users heuristic for tools and spare parts.

    Why
    ---
    The trust loans out things like a 9 mm spanner, a cordless drill, or
    a specific spare coupling. The same item may be "out" with one
    worker while another worker comes to the desk asking for it. If two
    workers genuinely need the same tool at the same time, owning only
    one is a bottleneck.

    The classical reorder-point math in `wms.forecast` solves the
    *consumption* case — petrol, screws, food — where every unit that
    leaves the store is gone. It DOES NOT model returnable items
    correctly, because the same physical drill that left on Monday and
    came back on Wednesday looks like two events but only one body.

    Method
    ------
    Take the last 90 days of `stock.move` rows with state='done', and
    classify each move by what *kind* of location each endpoint is:

      * `storage`  — an internal slot/rack/shelf the tool calls home.
                     `usage='internal'` AND neither `wms_is_damage` nor
                     `wms_is_repair`.
      * `out`      — anywhere a tool can be without being available for
                     the next request: a customer/production location,
                     plus the WMS's Damage and Repair-Out internal
                     locations. From the perspective of "can another
                     worker grab this drill right now?" these all mean
                     no.
      * `phantom`  — `usage='supplier'` or `usage='inventory'`, used
                     for receipts (buying new stock) and write-offs.
                     Moves touching these aren't real checkouts /
                     returns and are skipped.

    Then for each move:

      * storage → out : +qty (a checkout — drill is now OUT)
      * out → storage : -qty (a return — drill is BACK)
      * everything else: 0

    Sort the per-product timeline by date and compute the running sum.
    The peak of that running sum is the maximum number of physical
    units that were simultaneously out at any one moment. That's the
    concurrent-users count.

    Recommended fleet size = peak + 1 (one in reserve so a sudden
    request isn't blocked while one is being repaired or audited). The
    shortage column highlights products whose current on-hand is below
    the recommendation — these are the candidates to buy more of.

    Scope
    -----
    Only products whose `wms_product_kind` is `tool` or `spare` show
    up. Consumables and raw materials have no return event, so the
    method would always report shortage=0 and waste screen real estate.
    """

    _name = "wms.tool.fleet.summary"
    _description = "Tools & spares — concurrent-users heuristic"
    _auto = False
    _order = "shortage desc, peak_concurrent_out desc"

    # One row per product. Using product_id directly as the primary key
    # so Odoo's view-model has a stable, unique `id` column.
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    wms_product_kind = fields.Selection(
        related="product_id.wms_product_kind",
        string="Kind",
        readonly=True,
    )
    peak_concurrent_out = fields.Integer(
        string="Peak concurrent out (90d)",
        readonly=True,
        help="Largest number of physical units that were simultaneously "
        "checked out of the warehouse at any one moment in the last 90 "
        "days. Computed from stock-move history (internal → non-internal "
        "moves are checkouts, the reverse is a return).",
    )
    event_count = fields.Integer(
        string="Movements (90d)",
        readonly=True,
        help="Number of checkout + return events the peak was computed "
        "from. Below ~5 the peak is statistically unreliable — treat it "
        "as a lower bound, not gospel.",
    )
    current_on_hand = fields.Float(
        string="On hand (now)",
        readonly=True,
        help="Total quantity currently in any internal warehouse "
        "location (Stock, racks, slots — not Damage / Repair / Scrap).",
    )
    recommended_fleet_size = fields.Integer(
        string="Recommended fleet",
        readonly=True,
        help="Suggested total number of units to own: peak + 1 spare. "
        "The +1 covers the case where one is being repaired, audited, "
        "or just lost in the rack at the moment of next request.",
    )
    shortage = fields.Integer(
        string="Shortage",
        readonly=True,
        help="How many more units to buy to reach the recommended "
        "fleet size. Zero means today's fleet covers the peak demand "
        "with one spare; positive means buy more.",
    )

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Three CTEs: events (raw +/- per move), cum (running sum per
        # product), on_hand (current internal qty). The outer SELECT
        # collapses to one row per product and computes the peak +
        # recommendation + shortage.
        #
        # NOTE on the GREATEST(0, MAX(...)) wrapping: if a product had
        # more returns than checkouts at the start of the window (e.g.
        # backlog returns from before day 0), the running sum can go
        # negative. Clamp to 0 so the report doesn't show nonsense
        # negative peaks.
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_tool_fleet_summary AS
            WITH loc_kind AS (
                -- Classify every stock.location into one of three kinds.
                -- COALESCE handles old/inherited rows that pre-date the
                -- wms_is_damage/repair booleans (they're NULL → false).
                SELECT
                    id,
                    CASE
                        WHEN usage = 'internal'
                             AND NOT COALESCE(wms_is_damage, FALSE)
                             AND NOT COALESCE(wms_is_repair, FALSE)
                            THEN 'storage'
                        WHEN usage IN ('supplier', 'inventory')
                            THEN 'phantom'
                        ELSE 'out'
                    END AS kind
                FROM stock_location
            ),
            events AS (
                SELECT
                    sm.product_id,
                    sm.date AS move_date,
                    CASE
                        WHEN lk_src.kind = 'storage'
                             AND lk_dest.kind = 'out'
                            THEN sm.product_uom_qty
                        WHEN lk_src.kind = 'out'
                             AND lk_dest.kind = 'storage'
                            THEN -sm.product_uom_qty
                        ELSE 0
                    END AS delta_out
                FROM stock_move sm
                JOIN loc_kind lk_src
                       ON lk_src.id = sm.location_id
                JOIN loc_kind lk_dest
                       ON lk_dest.id = sm.location_dest_id
                JOIN product_product pp
                       ON pp.id = sm.product_id
                JOIN product_template pt
                       ON pt.id = pp.product_tmpl_id
                WHERE sm.state = 'done'
                  AND sm.date >= NOW() - INTERVAL '90 days'
                  AND pt.wms_product_kind IN ('tool', 'spare')
            ),
            cum AS (
                SELECT
                    product_id,
                    move_date,
                    SUM(delta_out) OVER (
                        PARTITION BY product_id
                        ORDER BY move_date, product_id
                    ) AS running_out
                FROM events
                WHERE delta_out <> 0
            ),
            on_hand AS (
                SELECT
                    sq.product_id,
                    SUM(sq.quantity) AS qty
                FROM stock_quant sq
                JOIN stock_location sl
                       ON sl.id = sq.location_id
                WHERE sl.usage = 'internal'
                GROUP BY sq.product_id
            ),
            agg AS (
                SELECT
                    c.product_id,
                    GREATEST(0, CEIL(MAX(c.running_out)))::int
                        AS peak_concurrent_out,
                    COUNT(*)::int AS event_count
                FROM cum c
                GROUP BY c.product_id
            )
            SELECT
                a.product_id AS id,
                a.product_id,
                a.peak_concurrent_out,
                a.event_count,
                COALESCE(oh.qty, 0) AS current_on_hand,
                (a.peak_concurrent_out + 1) AS recommended_fleet_size,
                GREATEST(
                    0,
                    (a.peak_concurrent_out + 1) - COALESCE(oh.qty, 0)
                )::int AS shortage
            FROM agg a
            LEFT JOIN on_hand oh ON oh.product_id = a.product_id
        """
        )
