# 05 — AI / forecasting

## Goals (recap)

- Predict monthly consumption per product.
- Recommend reorder qty + reorder date.
- Classify items: fast / normal / slow / dead.
- Different behavior for **consumables** vs **non-consumables (reusable)**.
- Must run offline, on a small box, in ≤ 200 MB resident.

## Algorithm choice

| Method | Memory | Accuracy on warehouse data | Use case |
|---|---|---|---|
| **Holt-Winters (additive)** | ~30 MB | Good when seasonality present | Default if ≥ 24 weekly observations |
| **Simple Exp. Smoothing (SES)** | ~5 MB | Decent for short, flat series | Fallback < 24 obs |
| **Naïve / 30-day avg** | trivial | Baseline | New products with < 8 obs |

All three are in `statsmodels.tsa`. The engine picks based on data length and
the lower RMSE on a holdout. **No deep learning**, no TensorFlow, no GPU.

For **non-consumables / reusable** items, the signal is *usage events* (issue +
return loop), not consumption. We model `usage_count_per_month` instead of
`net_outflow_per_month`. If a reusable item has zero events in 90 days, we
output "monitor only — no prediction".

## Pipeline

```
1. Build a time series per product (daily outflow from stock.move):
     SELECT date_trunc('day', date) AS d, SUM(product_uom_qty)
     FROM stock_move
     WHERE state='done'
       AND location_dest_id IN (customer/production locations)
       AND product_id = :p
     GROUP BY 1 ORDER BY 1;

2. Resample to weekly buckets, fill missing with 0.

3. Pick model based on len(series) & seasonality test (autocorrelation lag-52).

4. Fit on 80% train, evaluate on 20% holdout → RMSE.

5. Forecast `horizon_days` ahead, sum into `predicted_qty`.

6. Compute reorder:
     reorder_point   = lead_time_days * daily_avg + safety_stock
     suggested_order = max(0, reorder_point + horizon_demand - on_hand - on_order)

7. Velocity class:
     monthly_avg > 100  → fast
            > 10        → normal
            > 0         → slow
            = 0 (90d)   → dead

8. Write to wms.forecast (upsert).
```

## Trigger

- Cron retrains daily (`wms_ai_forecast/data/cron.xml`: interval 1 day, no
  fixed clock time — runs on the scheduler's daily tick).
- Manual "Retrain now" button on `wms.forecast` form for ops.
- Optional native `ai_worker` process (`scripts/start-ai-worker.ps1`) can call
  `run_all_forecasts()` over XML-RPC to offload from the Odoo service.
  Production deployments use `scripts/install-ai-worker-service.ps1`, which
  installs it as the `Odoo-WMS-AIWorker` service (NSSM, DEMAND_START, depends
  on `Odoo-WMS`).

## Determinism

- AI computes **demand**; reorder math is pure deterministic formula.
- Operators see "AI suggests 240 units" — never auto-creates a PO. Confirmation
  is human, with one click to push to `purchase.order`.

## Cold-start

For brand new products with no history we present the buyer with the engine's
default (`30-day avg` of the parent category if any, else "needs manual input").
Never zero-confidently auto-suggest.
