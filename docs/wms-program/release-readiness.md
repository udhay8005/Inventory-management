# WMS v20 — Release Readiness Report (Wave 1 + Wave 2 + Wave 3)

**Date:** 2026-06-27 · **Branch:** `v20-wave2-3` · **Working tree:** clean
**Recommendation:** see [§10 GO / NO-GO](#10-go--no-go-decision).
**Scope of this report:** the v20 program — Wave 1 (Universal Perishable Engine,
incl. V20-022), Wave 2 (Warehouse Intelligence, `wms_analytics`), Wave 3
(Pharmacy Packaging Engine, `wms_pharmacy`).

> **This is a readiness report, not a release.** Nothing has been merged, tagged,
> or published. The `v20 → main` cutover and any production tag are **held for
> explicit owner approval** (see §11).

---

## 1. What was delivered

| Wave | Addon(s) | Scope | Status |
|------|----------|-------|--------|
| Wave 1 | `wms_perishable` 19.0.1.20.0 | Per-lot FEFO, expiry, recall, quarantine, lot labels/timeline, near-expiry guard, **V20-022 per-kind shelf-life + short-dated-issue guard** | Complete |
| Wave 2 | `wms_analytics` 19.0.2.0.0 | All 15 Warehouse-Intelligence features | Complete |
| Wave 3 | `wms_pharmacy` 19.0.3.0.0 | Box→Strip→Tablet engine: packaging hierarchy, nested barcodes, open-strip tracking, dose dispensing (strip-level FEFO + open-package optimisation), pharmaceutical genealogy, animal medication history | Complete |

Wave 2 features (all built, wired, tested): KPI dashboard, Expiry Risk Engine,
AI-forecast risk, Supplier Analytics + ledger, Disposal Analytics, Stock Health
Score, KPI trends (occupancy snapshots + FEFO compliance), Advanced Ledgers
(lot/product/warehouse + department/animal/medicine), Recall Dashboard, Lot Audit
Score, status-aware Heat Map, Cold Chain, Bulk Operations, Cycle-Count
Intelligence, Advanced Traceability.

---

## 2. Files changed / added

- **New addons:** `addons/wms_analytics/` (Wave 2), `addons/wms_pharmacy/` (Wave 3).
- **Wave 1 completion:** additive changes in `addons/wms_perishable/` (V20-022).
- **Docs:** `docs/wms-program/` (phase-0 traceability + this report), per-addon
  CHANGELOGs, root CHANGELOG + README.
- **CI/repo:** `.github/workflows/ci.yml` (installs/tests all 10 addons),
  `.github/CODEOWNERS`.
- Wave 2/3 delta on the branch: ~10 commits; no edits to the frozen Wave 1
  behavioural addons beyond additive `_inherit` (see §3 architecture note).

---

## 3. Test statistics (local, executed — not asserted)

All figures from real `odoo-bin --test-enable` runs against a fresh-installed
Postgres DB (`--http-port` isolated from the production instance on :8069).

| Suite | Tests | Result |
|-------|------:|--------|
| `wms_analytics` (Wave 2) | 61 | 0 failed / 0 error |
| `wms_pharmacy` (Wave 3) | 31 | 0 failed / 0 error |
| **Full 10-addon regression** | **619** | **0 failed / 0 error** |

The full regression installs all ten addons from scratch and runs the CI tag set
(`wms, wms_audit, wms_delete, wms_health, wms_ui_cert`); the fail-on-skip guard
confirms there are **0 skipped** `wms_*` tests.

---

## 4. Independent audit (7 read-only teams)

Run adversarially over the Wave 2 + Wave 3 code (Wave 1 was certified at beta1).

| Team | Verdict |
|------|---------|
| Architecture | ✅ PASS |
| Security | ✅ PASS |
| Performance | ✅ PASS (after remediation, re-audited) |
| QA | ✅ PASS |
| Documentation | ✅ PASS |
| DevOps | ✅ PASS |
| Repository | ✅ PASS |

Initial pass: 0 critical, 1 high, 7 medium, 12 low. **All findings of
severity ≥ medium that warranted code change were remediated** and re-verified:

- **High (Performance):** heat-map controller did one `stock.quant` query per
  tile (N+1) → now a single batched query; re-audited PASS.
- **Medium (Performance):** KPI inventory value loaded all forecast rows → SQL
  `_read_group` aggregate.
- **Medium (Security):** `wms.dispense.log` was immutable by convention only →
  now append-only (`write`/`unlink` guards); audit trail cannot be edited/deleted.
- **Medium (Security):** supplier-scorecard SQL flagged by bandit B608 → verified
  false positive (literal int constants), annotated `# nosec`; bandit now clean.
- **Medium (Docs):** root README now lists both new addons.
- **Medium (QA):** added tests for expired-lot FEFO exclusion, dispense-log
  immutability, and KPI value aggregation.

---

## 5. Security findings

No critical/high security defects. Every new model has ACL rows; all destructive
actions (bulk recall/quarantine/destroy, dispense, cold-chain auto-hold) are
manager/role-gated in code; both HTTP controllers are `auth=user` + group-gated;
no SQL injection (SQL views use static SQL / literal constants only); `sudo()`
uses are narrow and justified. `bandit -ll` over both new addons: **No issues
identified** (1 suppressed false positive).

## 6. Performance findings

SQL-view reports aggregate in SQL (CTEs joined on keys, no cartesian joins); the
dispense engine uses bounded queries with in-memory aggregation; the heat map and
KPI dashboard use batched/aggregate queries. Residual low items (structural
location queries bounded by warehouse topology; recall-dashboard in-memory split)
are non-blocking. Real warehouse-scale throughput benchmarking remains a
**pilot-time** activity (human-executed).

## 7. CI / GitHub health

CI (`.github/workflows/ci.yml`) lint + security + Odoo module tests + v19→HEAD
upgrade + native smoke + aggregate gate. The module-tests job now installs and
tests all ten addons (Wave 2/3 included); the upgrade job correctly treats the
v20 addons as fresh-install-verified (absent at `PREV_TAG=v19.0.46.0.0`).
CODEOWNERS covers the new addons. A PR from `v20-wave2-3` into `v20`/`main` runs
the full CI. **`main` branch protection requires the `CI status` check.**

## 8. Migration / rollback

- Wave 2 (`wms_analytics`) and Wave 3 (`wms_pharmacy`) are additive installs;
  uninstalling removes the new behaviour. No destructive migration.
- Wave 1's lot-tracking migration (V20-020) remains restore-from-backup for the
  in-place path, as documented for the pilot.
- The v20 addons do not exist at the previous release tag, so the upgrade hop
  installs them fresh (verified by the module-tests job).

## 9. Known limitations (all low severity / non-blocking)

- "Frozen Wave 1" means **behaviour-compatible and retested**, not byte-identical:
  Wave 1 source saw the V20 lot-tracking change + a security-hardening pass, and
  some Wave 1 test fixtures were updated for lot-tracking. Documented, retested green.
- Some classes/methods in the new addons lack docstrings (cosmetic).
- A few additional edge-case tests are worth adding over time (multi-location
  dispense pooling; non-packaged-product guard; rack-aggregation heat-map branch
  beyond the shared status logic already covered).
- Browser-automation, multi-user concurrency at scale, and fresh-clone-on-a-bare-
  machine validation are **human/pilot-time** steps (CI's native-smoke is the
  automated proxy for fresh install + boot).

---

## 10. GO / NO-GO decision

**Engineering verdict: GO for owner review / pilot inclusion of Wave 2 + Wave 3.**

All objective engineering gates are green: 619-test full regression 0 failed/0
error, 0 skipped; lint + bandit clean; all 7 independent audit teams PASS (after
remediation); CI configured to test all ten addons. No critical or high
defects remain.

This GO is an **engineering-readiness** recommendation. It is **not** an
instruction to release.

## 11. Human approval gate (HELD)

No merge, tag, or publish has been performed. The following are **held for explicit
owner approval** and will be done only on your GO:

1. Open a PR from `v20-wave2-3` → `v20` (or `main`); confirm CI is green on it.
2. Merge; tag the release; publish the GitHub Release.
3. Verify a fresh clone + clean install from the tag.
4. Produce the final Production Release Report.

The frozen change-control (spec §15) originally placed Wave 2 after a 2–4 week
Wave-1 pilot; building ahead on this branch was your explicit decision
(2026-06-27). Whether to pilot Wave 1 first or include Wave 2/3 in the pilot is
your call.
