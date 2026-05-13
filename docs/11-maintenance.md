# 11 — Upgrade & maintenance

## Routine

| Cadence | Task |
|---|---|
| Daily | Verify `backup.sh` ran (size sanity check) |
| Weekly | `docker compose pull && docker compose build --no-cache && docker compose up -d` for security patches |
| Monthly | Restore-drill from a recent backup into a scratch DB |
| Quarterly | Review `wms.forecast` accuracy report; retune safety stock |
| Yearly | Major Odoo CE upgrade (see below) |

## Odoo CE major upgrade (e.g. 19 → 20)

1. Read upstream migration notes for any deprecated API we use:
   - `stock.quant` field changes
   - `stock.location` removal-strategy hooks
   - `mail.thread` decoration
2. Spin up a parallel stack on a new compose file, attach a copy of the DB
   (`pg_dump | pg_restore`).
3. Run each module's tests: `odoo -i wms_* --test-enable --stop-after-init`.
4. Fix what breaks in a feature branch, never on prod.
5. Cut over: stop old stack, swap volumes, start new stack.

## Tuning the FIFO query

If `stock.quant` grows large (> 1M rows), add a partial index:

```sql
CREATE INDEX CONCURRENTLY idx_quant_fifo
  ON stock_quant (product_id, in_date)
  WHERE quantity > 0;
```

We ship this index in `wms_fifo` migration `0001_initial.py`.

## Forecast retraining

- Default: daily for everything.
- If retrain time becomes painful, split:
  - **Fast/normal velocity** → daily
  - **Slow** → weekly
  - **Dead** → monthly
  Configurable in `wms.forecast.engine` config record.

## Memory pressure on small boxes

- Drop `workers` in `odoo.conf` from 2 → 1.
- Enable the `ai_worker` profile so statsmodels doesn't live in Odoo's RAM.
- Cap `limit_memory_hard` lower; Odoo recycles the worker.

## Common operational issues

| Symptom | First check |
|---|---|
| Scan does nothing | Cursor focus on barcode field? scanner emits ENTER? |
| Slot shows wrong qty | `stock.quant` for that slot; check pending pickings reserving stock |
| Forecast empty | `statsmodels` installed in container? `pip show statsmodels` |
| PO suggestion missing | velocity_class = dead → suppressed by design |
| Damage flow stuck | Confirm Damage location exists for that warehouse |

## Deprecation strategy

We do not support pre-19 versions. Any forwards-compat shim added "just in
case" must be removed before merge — it always rots.
