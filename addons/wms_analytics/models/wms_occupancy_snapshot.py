"""Wave 2 #7 (piece 1) — Occupancy-over-time snapshots.

The Wave 1 ``wms.occupancy.report`` is a live ``_auto=False`` view: it always
shows occupancy *right now* and keeps no history, so it cannot answer "how full
was this slot last Tuesday?" or chart occupancy as a trend.

This model is the historical companion: a STORED table holding one row per
storage location per calendar day, captured by a daily cron. Each snapshot
records the location's capacity, on-hand quantity and occupancy percentage at
capture time, so the graph/pivot views can plot occupancy over the date axis.

The occupancy maths mirror ``wms_reports/models/wms_occupancy_report.py``
exactly (capacity = ``wms_capacity_units``; occupancy_pct =
on_hand / capacity x 100, guarded against a zero capacity), so the trend lines
up with the live report. The cron is idempotent per day: re-running it the same
day refreshes that day's rows in place instead of duplicating them.
"""

from odoo import api, fields, models


class WmsOccupancySnapshot(models.Model):
    _name = "wms.occupancy.snapshot"
    _description = "Location occupancy snapshot (one row per location per day)"
    _order = "snapshot_date desc, occupancy_pct desc"
    _rec_name = "location_id"

    snapshot_date = fields.Date(
        string="Date",
        required=True,
        index=True,
        readonly=True,
        help="The calendar day this occupancy reading was captured for.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    location_kind = fields.Selection(
        [("slot", "Rack slot"), ("floor", "Floor zone")],
        readonly=True,
        help="Whether this storage location is a rack slot or an open floor zone.",
    )
    company_id = fields.Many2one("res.company", readonly=True, index=True)
    capacity = fields.Float(
        readonly=True,
        help="Soft capacity (units) of the location at capture time.",
    )
    on_hand = fields.Float(
        readonly=True,
        help="Total on-hand quantity in the location at capture time.",
    )
    occupancy_pct = fields.Float(
        string="Occupancy %",
        readonly=True,
        help="on-hand / capacity x 100 at capture time (0 when capacity is unset).",
    )
    distinct_products = fields.Integer(
        readonly=True,
        help="How many distinct products occupied the location at capture time.",
    )

    _unique_location_day = models.Constraint(
        "UNIQUE(location_id, snapshot_date)",
        "Only one occupancy snapshot per location per day.",
    )

    @api.model
    def _capture_values(self):
        """Compute today's occupancy rows for every storage location.

        Returns a list of write-ready value dicts (one per slot/floor),
        mirroring the live ``wms.occupancy.report`` maths so the stored trend
        agrees with the live report. Capacity, occupancy_pct and the on-hand
        sum all read from the same fields the live view uses.
        """
        today = fields.Date.context_today(self)
        locations = self.env["stock.location"].search(
            [("wms_location_type", "in", ("slot", "floor"))]
        )
        vals_list = []
        for loc in locations:
            quants = loc.quant_ids.filtered(lambda q: q.quantity > 0)
            on_hand = sum(quants.mapped("quantity"))
            capacity = loc.wms_capacity_units or 0.0
            occupancy_pct = (on_hand / capacity * 100.0) if capacity > 0 else 0.0
            vals_list.append(
                {
                    "snapshot_date": today,
                    "location_id": loc.id,
                    "location_kind": loc.wms_location_type,
                    "company_id": loc.company_id.id or self.env.company.id,
                    "capacity": capacity,
                    "on_hand": on_hand,
                    "occupancy_pct": occupancy_pct,
                    "distinct_products": len(quants.mapped("product_id")),
                }
            )
        return vals_list

    @api.model
    def _cron_capture(self):
        """Daily cron entry point — snapshot every storage location for today.

        Idempotent per day: an existing row for the same (location, day) is
        updated in place rather than duplicated, so a manual re-run or a
        catch-up after a missed day never creates a second reading for the same
        location on the same date. Returns the number of rows touched, which is
        handy when calling the method by hand from a test or the shell.
        """
        vals_list = self._capture_values()
        if not vals_list:
            return 0
        today = fields.Date.context_today(self)
        existing = {rec.location_id.id: rec for rec in self.search([("snapshot_date", "=", today)])}
        to_create = []
        for vals in vals_list:
            rec = existing.get(vals["location_id"])
            if rec:
                rec.write(vals)
            else:
                to_create.append(vals)
        if to_create:
            self.create(to_create)
        return len(vals_list)
