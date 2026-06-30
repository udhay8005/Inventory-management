# Production Release Report — v20.0.0

**Released:** 2026-06-28 · **Tag:** `v20.0.0` · **Release:**
<https://github.com/udhay8005/Inventory-management/releases/tag/v20.0.0>
**Authorised by:** owner (explicit "full cutover now", 2026-06-28).

This records the completed production cutover of the v20 program (Wave 1 +
Wave 2 + Wave 3) to `main`. It is the post-release record requested by the
engineering program; the pre-release analysis is in
[`release-readiness.md`](release-readiness.md).

---

## 1. What shipped

| Wave | Addon | Version |
|------|-------|---------|
| Wave 1 — Universal Perishable Engine | `wms_perishable` | 19.0.1.20.0 |
| Wave 2 — Warehouse Intelligence (15 features) | `wms_analytics` | 19.0.2.0.0 |
| Wave 3 — Pharmacy Packaging Engine | `wms_pharmacy` | 19.0.3.0.0 |

Plus the Wave 1 completion ticket **V20-022** (per-kind shelf-life policy +
short-dated-at-issue guard) in `wms_perishable`.

## 2. Cutover steps performed (with evidence)

| # | Action | Evidence |
|---|--------|----------|
| 1 | Push feature branch | `origin/v20-wave2-3` |
| 2 | Integration PR `v20-wave2-3 → v20` | [PR #84](https://github.com/udhay8005/Inventory-management/pull/84), merged `538cf9f` (2026-06-28T05:07:05Z) |
| 3 | CI on PR #84 | green — lint, security, module tests (10 addons), v19→HEAD upgrade, native smoke, aggregate |
| 4 | Production PR `v20 → main` | [PR #85](https://github.com/udhay8005/Inventory-management/pull/85), merged `310f4e2` (2026-06-28T05:18:50Z) |
| 5 | CI on PR #85 | green (all 6 jobs) |
| 6 | Annotated tag `v20.0.0` → `310f4e2` | tag object `9af5cb7`, pushed |
| 7 | GitHub Release published (Latest) | <https://github.com/udhay8005/Inventory-management/releases/tag/v20.0.0> (2026-06-28T05:19:36Z) |
| 8 | Fresh-clone clean install from the tag | clone HEAD `310f4e2` (`describe` = v20.0.0); fresh `-i` of all 10 addons on a new DB → exit 0, no CRITICAL/ERROR |

`main` was a clean ancestor of `v20` (48 commits), so the cutover advanced the
production line without conflicts.

## 3. Quality gates at release

- **Tests:** full 10-addon suite **619 tests, 0 failed / 0 error / 0 skipped**
  (local), re-run green by CI's `odoo_tests` job on `main`.
- **CI:** green on `main` after the PR #85 merge run (lint + pylint-odoo,
  security/bandit + pip-audit, Odoo module tests, v19→HEAD upgrade, native smoke).
- **Independent audit (7 read-only teams):** architecture / security /
  performance / QA / documentation / devops / repository — **all GREEN** after
  remediating 1 high (heat-map N+1) and the substantive medium findings;
  Performance re-audited PASS.
- **Static analysis:** black / isort / flake8 / pylint-odoo (10.00/10) / bandit
  all clean.
- **One CI-only defect was caught and fixed during cutover:** pylint-odoo
  `no-raise-unlink` on the dispense-log deletion guard → replaced with the
  sanctioned `@api.ondelete(at_uninstall=False)` pattern; CI green thereafter.

## 4. Known limitations (low severity, non-blocking)

- "Frozen Wave 1" = behaviour-compatible and retested, not byte-identical (the
  V20 lot-tracking change + a security-hardening pass touched some Wave 1 source
  and test fixtures; all retested green).
- A few additional edge-case tests and docstrings are worth adding over time.
- Real warehouse-scale throughput benchmarking, browser-automation, and
  multi-user concurrency at scale remain **pilot-time / human** activities; CI's
  native-smoke is the automated fresh-install-and-boot proxy.

## 5. Post-release notes

- The production code line (`main`) now carries the full v20 program; `v20`
  remains the ongoing development line (this report lands there).
- `v19.0.46.0.0` remains the prior production tag; the upgrade hop from it to
  HEAD is exercised by CI's upgrade job (the v20 addons are fresh-installed, as
  they did not exist at that tag).
- The production database (`wms` on :8069) was **not** touched by this cutover —
  it is a code/release action only. Deploying v20.0.0 to the live box is a
  separate operational step (backup-first, per the pilot/runbook).
