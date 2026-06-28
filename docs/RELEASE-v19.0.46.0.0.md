# Production Release — v19.0.46.0.0

**Dakshin Vrindavan Gaushala WMS · Odoo 19.0 CE**
**Status: RELEASED (software) · Tagged `v19.0.46.0.0` on `main`.**
**Repository state: Production Certified (software) · Maintenance Mode for v19** — v19 development
is frozen except emergency hotfixes; new work proceeds on `v20`.

Production `wms`:8069 was never touched during this ceremony (all builds/tests on scratch DBs). The
production **tag** is the software release artifact; **go-live deployment to the warehouse machine
remains gated by the Operator Checklist (§9)** — those on-site items are PENDING and were not
fabricated.

## 1. Final Release Report

The release ceremony completed on objective evidence:

| Gate | Result | Evidence |
|---|---|---|
| Working tree clean | ✅ | only untracked docs; no uncommitted code |
| Zero Critical / Zero High | ✅ | hardening + AI cert: 0/0 |
| Regression green | ✅ | 453/453 on a fresh DB (RC commit) |
| CI green (6 jobs) | ✅ | `test`@`7da8b49` + `main`@`b13e928` |
| Migration verified | ✅ | upgrade job `v19.0.45.0.0 → HEAD` green |
| Rollback | ✅ mechanism / ⏸ on-box | `restore-native.ps1` + TOC drill verified; full warehouse-box drill = operator item (§9) |
| Documentation complete | ✅ | guides + cert/hardening/RC reports present |
| Manifests complete | ✅ | §7 |
| Merge `test`→`main` (squash) | ✅ | `main`@`b13e928` |
| Tag `v19.0.46.0.0` pushed | ✅ | annotated tag on `b13e928` |
| Release workflow | ✅ | run completed/success |
| `main`→`test` merge-back | ✅ | `test`@`1678a41` |
| Branches `release/v19`, `v20` | ✅ | both pushed |

## 2. Signed Change Log (v19.0.45.0.0 → v19.0.46.0.0)

Net change on `main` (11 files, +227 / −10), all freeze-safe (no features, no schema redesign):

- **fix(wms):** Scan Issue rejects non-positive quantity with a clear message (was a fake
  "Planned 0" / bogus "STOCK OUT"); carton alias `CHECK(units_per_scan > 0)`; Scan Receipt
  refuses a Damage/Repair location as a destination (good stock was being stranded); clearer
  empty-plan message + a stale docstring fix. **+7 regression tests.**
- **chore(release):** CI upgrade-gate `PREV_TAG` → `v19.0.45.0.0` (tests the real deploy hop);
  guided-create required-field error names the field by its full caption.
- Addon bumps: `wms_barcode` 19.0.1.46.0 → **19.0.1.48.0**; `wms_repair_damage` 19.0.1.16.0 →
  **19.0.1.17.0**.

Release authority: repository owner `udhay8005`. Commits carry no AI attribution (project policy).

## 3–4. Deployment & Rollback Packages

Deployment procedure (verified present, no change this release): `scripts/install-native.ps1`,
`scripts/upgrade-service.ps1`, `docs/07-deployment.md`, `docs/INSTALLATION-GUIDE.md`,
`docs/17-ci-cd.md`. Rollback/DR: `scripts/restore-native.ps1`, `docs/18-restore-drill.md`,
`docs/19-disaster-recovery.md`; backups: `scripts/backup-native.ps1`, `docs/22-gdrive-backup.md`.
**Emergency hotfix:** branch from `release/v19` → minimal fix + regression test → CI green → tag
`v19.0.46.0.1` → deploy; the restore path stays available if a hotfix misbehaves.

## 5. Production Checklist (verify on the live box at deploy)

NSSM service `Odoo-WMS` Running + Automatic · PostgreSQL service running · `odoo.native.conf`
(`list_db=False`, `db_listing=False`, addons path) · scheduled jobs present (daily backup task; the
WMS crons: expiry digest, low-stock 08:10, returns-overdue, health, restore-drill check) · logging
to `.runtime/logs/odoo.log` · wkhtmltopdf on PATH · file permissions on `.runtime/` · health
endpoint OK.

## 6. Risk Register (final)

| Risk | Sev | Status |
|---|---|---|
| On-site human items not yet evidenced | Medium (ops) | §9; software released, go-live gated |
| Full restore drill on warehouse PC | Medium (ops) | mechanism + TOC verified; on-box drill pending |
| Cross-browser Edge/Firefox | Low | Chrome validated; 10-min manual smoke at go-live |
| Return/expiry gaps (over-return, expired-issue, per-batch) | Medium | by design → v20 Wave 1 (now scaffolded) |
| Single-company (no `ir.rule`) | Low | fine for this deployment; v20 build-condition #5 adds it |

## 7. Production / Version Manifest

```
Release            : v19.0.46.0.0   (RELEASED, tagged on main)
Production commit  : b13e928   (main, squashed release)
Dev/source commit  : 7da8b49 (test, pre-squash) over 81d055c (hardening), on v19.0.45.0.0
Platform           : Odoo 19.0 Community · Python 3.12 · PostgreSQL 16/17 · Windows native (NSSM)
Addon versions:
  wms_location 19.0.3.25.0 · wms_fifo 19.0.1.1.0 · wms_barcode 19.0.1.48.0
  wms_repair_damage 19.0.1.17.0 · wms_ai_forecast 19.0.1.5.0 · wms_reports 19.0.4.14.0
  wms_training 19.0.1.14.0
Runtime deps: numpy<2.0 · pandas<3.0 · statsmodels>=0.14.6 · Pillow>=12.2.0 · reportlab<5.0 · rl-renderPM
Upgrade verified   : v19.0.45.0.0 -> HEAD (CI)
Branches           : main (release) · test (dev) · release/v19 (maintenance) · v20 (next major)
```

## 8. Performance (measured, for the record)

barcode resolve ~1.0 ms · find/where ~0.7 ms · reports 1.3–2.3 ms · Scan Issue ~110 ms · Scan
Receipt ~358 ms (first-op) · warm service restart ~13 s (cold first-install ~115 s). No regression.

## 9. Operator / Human-Validation Checklist (PENDING — gates go-live, NOT fabricated)

Complete on the warehouse machine and record in `docs/GO-LIVE-VALIDATION.md` before declaring the
system live for daily use:

- ☐ **Google Drive backup OAuth** — `scripts/setup-gdrive-auth.ps1`; confirm a test backup uploads.
- ☑ **Label printer (TE244)** — owner-confirmed; for the file, print one label + scan it back.
- ☑ **Barcode scanner** — owner-confirmed (auto-Enter); for the file, one receive→issue→return loop.
- ☐ **Warehouse-PC restore drill** — `scripts/restore-native.ps1` into a throwaway DB on the live box.
- ☐ **Storekeeper session (2–4 h)** — a real keeper runs the floor; capture any issues.
- ☐ **Browser smoke (Edge + Firefox)** — 10 min: login, Scan Receipt, Scan Issue, a report, print.
- ☐ **Production deployment verification** — service Running/Automatic, health OK, first real receipt
  with the scanner, overnight backup ran.

## 10. After the release — v20 initialized

The `v20` branch is cut and the **`wms_perishable`** module is scaffolded (structure only, no
features) as the official Wave 1 starting point: manifest (depends on the v19 addons +
`product_expiry`), `models/ wizards/ views/ security/ data/` layout, `tests/common.py`
`WmsLotTestBase` + a green scaffold smoke test, and CI wiring (module-tests installs it;
`PREV_TAG`=v19.0.46.0.0). Build from the frozen spec in `docs/v20-perishable-engine/` (run
`08-implementation-prompt.md` for Wave 1).

## Final Decision

> ## ✅ PRODUCTION RELEASED
>
> `v19.0.46.0.0` is tagged and released with every objective **software** gate green — 0 Critical,
> 0 High, 453/453 regression, CI 6/6, migration verified, Release workflow success, docs and
> manifests complete. v19 is frozen (Maintenance Mode); `release/v19` and `v20` are cut and v20 is
> scaffolded.
>
> **One honest qualifier:** this is the *software* release. **Daily go-live on the warehouse floor
> remains gated by the Operator Checklist (§9)** — Drive OAuth, the on-box restore drill, the keeper
> session, the Edge/Firefox smoke, and deployment verification are PENDING human evidence and were
> not fabricated. Release ≠ go-live; complete §9 on the live box to flip the warehouse live.
