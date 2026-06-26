# v20.0.0-beta1 — Pilot Release (Wave 1 Universal Perishable Engine)

**Pilot build only — not a production release.** Tagged on the `v20` branch; NOT
merged to `main`. v19 (`v19.0.46.0.0`) remains the production line. The 2–4 week
warehouse pilot and any production cutover are human-run and require owner
approval (see "After the pilot").

## What's in it

The complete Wave-1 perishable engine — per-lot expiry, FEFO, expired
block + disposal carve-out + manager override, lot-aware reversal, recall,
quarantine, per-lot expiry reporting, lot labels, lot timeline, near-expiry
receiving guard, and the extension hook API. Full ticket list and per-ticket
notes are in [`../../addons/wms_perishable/CHANGELOG.md`](../../addons/wms_perishable/CHANGELOG.md).

## Engineering gates (all met, with evidence)

- **Tests:** full WMS suite 519 tests, 0 failed / 0 skipped / 0 error;
  `wms_perishable` alone = 106 tests.
- **CI:** green on every commit — lint & static checks, security scan, Odoo
  module tests, v19→HEAD upgrade path, native fresh-install smoke, CI status.
- **Independent read-only audit (6 teams):** architecture / security /
  performance / QA / docs / devops all GREEN, zero blocking defects.
- **Fresh install:** every suite run installs all 8 addons from scratch on a new
  database; CI's native-smoke re-verifies install + boot on each push.
- **Additive:** no v19 file edited — only `_inherit` extensions + new models.

## Pilot guide — what to validate on the floor (2–4 weeks)

Run real gaushala operations on the beta1 build and watch for:

1. **Receipt** — capture batch + expiry + supplier; confirm short-dated stock is
   blocked and a manager can accept it.
2. **FEFO issue** — confirm the soonest-expiring batch is issued first across
   multiple lots; confirm expired stock is blocked with a clear reason and a
   manager can override (audited).
3. **Recall** — recall a batch; confirm it freezes, cancels open reservations,
   and is excluded from issue until released.
4. **Quarantine** — hold a batch; confirm release / reject / destroy behave; held
   stock is un-issuable.
5. **Lot label + scan** — print a lot label; confirm scanning it pulls up the
   batch (product / expiry / supplier / location / remaining / timeline).
6. **Reports** — confirm the per-lot expiry report buckets batches correctly.
7. **Disposal** — confirm expired stock can be moved to Damage (not stuck).

## Operator checklist (before go-live on the pilot build)

- [ ] Verified backup taken (the project's `backup-native.ps1`).
- [ ] Decide the migration path: fresh v20 line (no live-stock migration) is the
      default; for an in-place upgrade use the Perishable Lot Migration wizard.
- [ ] Configure `wms_perishable.min_receive_shelf_life_days` if 60 is not right.
- [ ] Confirm a default WMS label printer is set (for lot labels).
- [ ] Confirm storekeeper vs manager roles are assigned (overrides are
      manager-only).

## Rollback

- The perishable engine is additive; uninstalling `wms_perishable` removes the
  new behaviour (the legacy lots remain harmless).
- **The lot-tracking migration is reversible only by RESTORE** — once
  `tracking='lot'` is set with stock on hand, Odoo cannot cleanly downgrade.
  Therefore migrate only after a verified backup; rollback = restore that backup
  with `restore-native.ps1`. Record the exact backup file in the run log.

## After the pilot

Collect verified pilot feedback → implement only verified fixes → re-run the
full suite + CI → tag `v20.0.0-rc1`. Then, on owner approval: merge `v20 → main`,
tag `v20.0.0`, publish the GitHub release. Wave 2 (analytics, dashboards, expiry
risk engine, forecasting, supplier analytics, cold-chain) follows production.
