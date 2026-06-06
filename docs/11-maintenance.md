# 11 — Upgrade & maintenance

## Routine

| Cadence | Task |
|---|---|
| Daily | Verify `scripts\backup-native.ps1` ran (size sanity check on the latest .dump in `backups\`) |
| Weekly | `cd .odoo && git pull origin 19.0 && cd .. && .venv\Scripts\pip install -r .odoo\requirements.txt --upgrade` then `scripts\start-native.ps1` to pick up Odoo CE security patches |
| Weekly (Sunday 03:00) | Restore drill — verify latest backup is recoverable: `scripts\restore-drill.ps1` (see `docs/18-restore-drill.md`) |
| Monthly | Restore-drill from a recent backup into a scratch DB (`pg_restore` into `wms_drill` and start Odoo against it briefly) |
| Quarterly | Review `wms.forecast` accuracy report; retune safety stock |
| Yearly | Major Odoo CE upgrade (see below) |

## Odoo CE major upgrade (e.g. 19 → 20)

1. Read upstream migration notes for any deprecated API we use:
   - `stock.quant` field changes
   - `stock.location` removal-strategy hooks
   - `mail.thread` decoration
2. Clone the new Odoo version alongside (`git clone -b 20.0 https://github.com/odoo/odoo .odoo-v20`), create a parallel venv, install deps. Restore a copy of the DB into `wms_v20_test` via `pg_restore`.
3. Run each module's tests: `.venv\Scripts\python .odoo-v20\odoo-bin -d wms_v20_test -i wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports --test-enable --stop-after-init`.
4. Fix what breaks in a feature branch, never on prod.
5. Cut over: `scripts\stop-native.ps1`, point `config\odoo.native.conf`'s `addons_path` at the new `.odoo-v20`, `scripts\start-native.ps1`.

## Tuning the FIFO query

If `stock.quant` grows large (> 1M rows), add a partial index:

```sql
CREATE INDEX CONCURRENTLY idx_quant_fifo
  ON stock_quant (product_id, in_date)
  WHERE quantity > 0;
```

We ship this index in `addons/wms_fifo/hooks.py:20-26` (created by the
`post_init_hook` on first install). The same script is idempotent on
re-runs, so re-installing `wms_fifo` will never duplicate the index.

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

## Optional safety toggles (System Parameters)

Both are off/conservative by default. Set them under **Settings → Technical →
System Parameters** (Manager only).

| Key | Default | Effect |
|---|---|---|
| `wms_reports.undo_minutes` | `15` | How long after a Scan Issue the orange **Undo this transfer** button stays available. The undo posts a compensating internal transfer (it never deletes anything) and is blocked once the stock has moved on. Set to `0` to switch Undo off entirely. |
| `wms_location.enforce_capacity` | `0` (off) | When `1`, a putaway that would push an internal location's on-hand over its **Capacity (units)** is refused with a clear error and rolled back — nothing is forced. With it off, capacity stays a soft hint shown only in the occupancy report. Set capacities per slot on the location form before turning this on. |
| `wms_reports.alert_email` | `0` (off) | The daily **low-stock alert** always reaches managers in-app (Discuss Inbox / systray). Set this to `1` to ALSO email them (best-effort — needs an outgoing mail server; a missing one never breaks the alert). |

Changing any of these takes effect immediately — no restart needed.

### Automatic alerts (no setup needed)

Three crons quietly watch the warehouse and notify WMS managers **in-app** only
when something needs attention (all use `message_notify`, so they land in the
manager's Discuss Inbox):

- **Daily low-stock alert** — products at or below their reorder level.
- **Daily backup-freshness check** — a stale backup or restore drill.
- **Weekly expiry digest** — perishables expired or expiring within 30 days.

Photos: Scan Receipt, Scan Issue, and Damage all accept an optional photo
(the camera opens on a phone) that is attached to the record for the audit trail.

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
