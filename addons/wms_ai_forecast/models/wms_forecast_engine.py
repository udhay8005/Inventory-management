import logging
from datetime import timedelta

from odoo import api, fields, models

from . import forecasting

_logger = logging.getLogger(__name__)


class WmsForecastEngine(models.AbstractModel):
    _name = "wms.forecast.engine"
    _description = "Forecast trainer"

    @api.model
    def run_all_forecasts(self):
        """Entry point called by cron and the optional ai_worker.

        In Odoo 19 a "trackable" product has `is_storable=True` (the legacy
        `type='product'` was retired). We forecast every storable product
        and skip services / combos.
        """
        products = self.env["product.product"].search(
            [
                ("active", "=", True),
                ("is_storable", "=", True),
            ]
        )
        _logger.info("wms_ai_forecast: training %d products", len(products))
        signals = self._prefetch_signals(products)
        self.train_for_products(products, signals=signals)
        self._prune_history()

    def _prefetch_signals(self, products):
        """Batch the per-product on-hand / on-order / safety-stock lookups into
        three grouped queries. Previously each was a separate search inside the
        per-product loop (N+1: ~3 extra queries per product), which made the
        nightly cron scale linearly with the catalogue."""
        on_hand, on_order, orderpoints = {}, {}, {}
        pids = products.ids
        if not pids:
            return {"on_hand": on_hand, "on_order": on_order, "orderpoints": orderpoints}
        # On-hand counts only warehouse STORAGE (lot-stock + children), NOT the
        # "Trust internal use" sink — same universe as _on_hand / the value
        # report. Counting the consumed-goods sink here would suppress reorders.
        storage = self._storage_location_ids()
        if storage:
            for product, qty in self.env["stock.quant"]._read_group(
                [("product_id", "in", pids), ("location_id", "child_of", storage)],
                groupby=["product_id"],
                aggregates=["quantity:sum"],
            ):
                on_hand[product.id] = qty or 0.0
        for product, ordered, received in self.env["purchase.order.line"]._read_group(
            [("product_id", "in", pids), ("state", "in", ("purchase", "done"))],
            groupby=["product_id"],
            aggregates=["product_qty:sum", "qty_received:sum"],
        ):
            on_order[product.id] = (ordered or 0.0) - (received or 0.0)
        for op in self.env["stock.warehouse.orderpoint"].search([("product_id", "in", pids)]):
            orderpoints.setdefault(op.product_id.id, op.product_min_qty)
        return {"on_hand": on_hand, "on_order": on_order, "orderpoints": orderpoints}

    def _prune_history(self):
        """Cap forecast-history growth. Each cron run writes one snapshot per
        product; left unbounded the table grows forever. Keep only the most
        recent `wms_ai_forecast.history_retention_days` (default 365) days."""
        param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("wms_ai_forecast.history_retention_days", "365")
        )
        try:
            days = int(param)
        except (TypeError, ValueError):
            days = 365
        if days <= 0:
            return
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old = self.env["wms.forecast.history"].search([("trained_at", "<", cutoff)])
        if old:
            _logger.info(
                "wms_ai_forecast: pruning %d forecast-history rows older than %d days",
                len(old),
                days,
            )
            old.unlink()

    def train_for_products(self, products, signals=None):
        for product in products:
            try:
                self._train_one(product, signals=signals)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("forecast train failed for %s: %s", product.display_name, exc)

    def _gather_outflow(self, product):
        """Return list of (datetime, qty) — daily consumption events.

        For this trust, consumption == Scan Issue: the SAME signal the
        Consumption-Value report keys off (the immutable ``wms_is_scan_issue``
        flag on the picking — see ``wms_value_reports.py``). The previous
        query counted only moves whose DESTINATION usage was
        ``customer``/``production``; but a Scan Issue routes stock into the
        *internal* "Trust internal use" sink, so that filter observed ZERO
        outflow for the only consumption path the shelter actually uses. The
        result was daily_avg=0 -> velocity 'dead' -> reorder_qty=0 for every
        product, silencing both the AI buying recommendations and the daily
        low-stock alert. We now count done Scan-Issue move-lines, excluding
        issues that were later Undone (``wms_reversed_by_id``) since those net
        to zero consumption — exactly the rule the value report uses.
        """
        # The ORM auto-flushes before its OWN queries, but NOT before a raw
        # cr.execute. Flush the two models this query reads so an issue created
        # earlier in the same transaction (a test, or action_retrain right
        # after a Scan Issue) is visible. No-op in the nightly cron, where the
        # data is already committed and nothing on these models is pending.
        self.env["stock.move.line"].flush_model()
        self.env["stock.picking"].flush_model()
        self.env.cr.execute(
            """
            SELECT date_trunc('day', sml.date) AS d,
                   COALESCE(SUM(sml.quantity), 0)
              FROM stock_move_line sml
              JOIN stock_picking sp ON sp.id = sml.picking_id
             WHERE sml.product_id = %s
               AND sml.state = 'done'
               AND sp.wms_is_scan_issue = TRUE
               AND sp.wms_reversed_by_id IS NULL
               AND sml.date >= now() - INTERVAL '2 years'
             GROUP BY d
             ORDER BY d
            """,
            (product.id,),
        )
        return [(row[0], float(row[1])) for row in self.env.cr.fetchall()]

    def _storage_location_ids(self):
        """Warehouse STORAGE locations — each warehouse's lot-stock location
        and all its children (zones / racks / compartments / slots / floor) —
        as the on-hand universe.

        Deliberately EXCLUDES the top-level internal "Trust internal use"
        sink: it is ``usage='internal'`` but holds already-CONSUMED goods, so
        counting it as on-hand would understate reorder need (the engine would
        think issued stock is still available). Mirrors the Stock-Value
        report's ``lot_stock_id`` child_of guard (``wms_value_reports.py``).
        """
        return self.env["stock.warehouse"].search([]).lot_stock_id.ids

    def _on_hand(self, product):
        storage = self._storage_location_ids()
        if not storage:
            return 0.0
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id", "child_of", storage),
            ]
        )
        return sum(q.quantity for q in quants)

    def _on_order(self, product):
        # Confirmed POs not yet received
        lines = self.env["purchase.order.line"].search(
            [
                ("product_id", "=", product.id),
                ("state", "in", ("purchase", "done")),
            ]
        )
        return sum(line.product_qty - line.qty_received for line in lines)

    def _lead_time(self, product):
        seller = product.seller_ids[:1]
        return int(seller.delay) if seller else 7

    def _safety_stock(self, product):
        # If you use stock.warehouse.orderpoint, prefer that; else 0.
        op = self.env["stock.warehouse.orderpoint"].search(
            [
                ("product_id", "=", product.id),
            ],
            limit=1,
        )
        return op.product_min_qty if op else 0.0

    def _train_one(self, product, signals=None):
        observations = self._gather_outflow(product)

        # In Odoo 19 `product.type` is consu/service/combo and EVERY storable
        # product reports type=='consu', so the old `type == 'consu'` test was
        # always true and meaningless. We now key the consumable flag off actual
        # movement history — zero-history products are flagged "monitor only".
        note = ""
        if not observations:
            result = forecasting.ForecastResult(0, 0, 0, "Manual", 0, "dead")
            note = "No usage history yet — monitor only"
        else:
            result = forecasting.forecast(observations, horizon_days=30)

        # Prefer the batched signals from run_all_forecasts; fall back to the
        # per-product lookups when called directly (e.g. action_retrain).
        if signals is not None:
            on_hand = signals["on_hand"].get(product.id, 0.0)
            on_order = signals["on_order"].get(product.id, 0.0)
            safety = signals["orderpoints"].get(product.id, 0.0)
        else:
            on_hand = self._on_hand(product)
            on_order = self._on_order(product)
            safety = self._safety_stock(product)
        lead = self._lead_time(product)
        reorder_qty, reorder_date = forecasting.reorder_recommendation(
            on_hand=on_hand,
            on_order=on_order,
            daily_avg=result.daily_avg,
            lead_time_days=lead,
            safety_stock=safety,
            horizon_days=30,
        )

        # Upsert
        forecast = self.env["wms.forecast"].search(
            [("product_id", "=", product.id)],
            limit=1,
        )
        vals = {
            "product_id": product.id,
            "horizon_days": 30,
            "predicted_qty": result.predicted_qty,
            "daily_avg": result.daily_avg,
            "monthly_avg": result.monthly_avg,
            "reorder_qty": reorder_qty,
            "reorder_date": reorder_date.date() if reorder_date else False,
            "velocity_class": result.velocity_class,
            "is_consumable": bool(observations),
            "last_trained": fields.Datetime.now(),
            "model_name": result.model_name,
            "rmse": result.rmse,
            "on_hand": on_hand,
            "lead_time_days": lead,
            "safety_stock": safety,
            "note": note,
        }
        if forecast:
            forecast.write(vals)
        else:
            forecast = self.env["wms.forecast"].create(vals)

        self.env["wms.forecast.history"].create(
            {
                "product_id": product.id,
                "model_name": result.model_name,
                "predicted_qty": result.predicted_qty,
                "rmse": result.rmse,
                "velocity_class": result.velocity_class,
            }
        )
        return forecast
