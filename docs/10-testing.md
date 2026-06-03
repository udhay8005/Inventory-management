# 10 — Testing strategy

## Layers

1. **Unit (Odoo)** — `tests/test_*.py` in each module, `TransactionCase`.
2. **Integration** — `HttpCase` for barcode wizards, real picking flow.
3. **Smoke** — Docker compose + `odoo --test-enable -i wms_location,...`.

## What we test, per module

### wms_location
- Creating a rack (default 6 shelves × 3 columns) auto-generates its
  compartments + slots via `wms.rack.generator`.
- Constraint violations: a compartment whose shelf/column range falls
  outside the rack grid is rejected; a slot's parent must be a compartment,
  a compartment's parent a rack.
- `@api.ondelete` blocks deleting a rack/compartment/slot/floor that still
  has children, live quants, or stock-move history (archive instead).
- Slot barcode unique inside warehouse.

### wms_fifo
- Two quants of the same product, in_date differing by 1 day → outbound picks
  oldest first.
- Picker override is allowed and logged.

### wms_barcode
- Scan unknown barcode → wizard offers "create product".
- Carton alias of 24 → +24 to quant on Validate.
- Label PDF is non-empty for product, slot, rack.

### wms_repair_damage
- Damage flow generates exactly one internal picking source→damage.
- Repair done returns to original slot when chosen; lot/serial preserved.

### wms_ai_forecast
- Holt-Winters selected when ≥ 24 weekly observations exist.
- SES used as fallback.
- New product with no history → "monitor only", no PO push.
- Reorder formula: `lead*avg + safety` matches snapshot.

### wms_reports
- Each `_auto=False` view returns the expected rows on demo data.

## CI

GitHub Actions native runner (Ubuntu + Postgres service + venv) — see
`.github/workflows/ci.yml` for the full pipeline. Inner test invocation:

```yaml
- run: |
    git clone --depth 1 -b 19.0 https://github.com/odoo/odoo.git $HOME/odoo
    python -m venv $HOME/venv
    $HOME/venv/bin/pip install -r $HOME/odoo/requirements.txt -r requirements.txt
    $HOME/venv/bin/python $HOME/odoo/odoo-bin --test-enable --stop-after-init \
        -d ci_test --db_host=localhost --db_user=odoo --db_password=odoo_ci_password \
        --addons-path=$HOME/odoo/addons,$GITHUB_WORKSPACE/addons \
        -i wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports \
        --without-demo=all --test-tags wms --log-level=test
```

## Performance benchmarks

- 100k `stock.quant` rows → FIFO query < 50 ms (indexed).
- Daily forecast cron for 5k products → < 10 min on a 2 vCPU box.

If either exceeds budget, see `docs/11-maintenance.md` for tuning.
