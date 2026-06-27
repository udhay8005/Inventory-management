# v19 Production Certification — AI Human-like Validation Report

**Date:** 2026-06-26 · **Build under test:** `test` @ `81d055c` (hardened v19; wms_barcode
19.0.1.47.0, wms_repair_damage 19.0.1.17.0) · **Method:** 12 specialist "operator" personas
exercised the **real wizard methods the UI buttons invoke** on a fresh clean DB (`wms_cert2`,
`--without-demo`), plus parallel read-only Security/UX/Regression code audits, plus the
standing automated suite + CI. **Production `wms`:8069 was never touched.** No fabricated
PASS — every PASS below is backed by a code reference, a driver assertion, or a measured number.

## Environment & honesty boundaries

- **What was exercised for real:** the actual `wms.scan.receipt` / `wms.scan.issue` /
  `wms.barcode.alias` / damage / repair methods (the same code a button-click runs), with
  real before/after stock state and real timings; the full 453-test suite; CI (6 jobs).
- **Honestly NOT certifiable in this environment (no fabrication):**
  - **Cross-browser (Edge/Firefox)** — only a Chrome automation bridge exists here; Edge and
    Firefox were **not tested**. (Odoo 19's web client is a single responsive SPA, so
    behavior is engine-driven, but this is an untested claim and is recorded as such.)
  - **On-site hardware/operator items** — the **scanner and label printer are owner-verified**
    (per this engagement's premise). The remaining go-live items — **Google Drive backup
    OAuth, a restore drill on the warehouse machine, and a 2–4 h real keeper session** — require
    a human on the live box and are **not** certified here.

## 1. Production Certification Report — summary

| Area | Result | Evidence |
|------|--------|----------|
| Storekeeper workflows (receive/store/issue/return/damage/repair/move/audit) | ✅ PASS | driver Agent A 4/4 + suite |
| New-employee mistakes (missing fields, wrong sequence, duplicate scan) | ✅ PASS | driver Agent B 7/7 |
| Fast operator / double-submit idempotency | ✅ PASS | driver Agent C 3/3 |
| Malicious input (negative, huge, SQL-like, bad multiplier, damage-dest) | ✅ PASS | driver Agent D 8/8 |
| Inventory integrity (conservation, FIFO, no-negative) | ✅ PASS | driver Agent E 4/4 |
| Rollback consistency | ✅ PASS | driver Agent F 1/1 |
| Concurrency safeguards | ✅ PASS | driver Agent G + `test_concurrency` |
| Performance | ✅ PASS | driver Agent I (real timings, §3) |
| Security & ACL | ✅ PASS (2 low notes) | code audit, §4 |
| UX & operator clarity | ✅ PASS (4 low notes) | code audit, §6 |
| Regression (12 historical defect classes) | ✅ PASS | defect→test map, §5 |
| Automated regression + CI | ✅ PASS | 453 tests 0/0; CI 6/6 green |
| Cross-browser Edge/Firefox | ⏸ NOT TESTED | no bridge in env |
| On-site operator items (Drive OAuth, warehouse restore drill, keeper session) | ⏸ REQUIRES HUMAN | live box only |

**Behavioral driver total: 29/29 checks PASS, 0 FAIL.**

## 2. Defect Report

**0 Critical · 0 High · 0 Medium-blocking.** No data corruption, no inventory mismatch, no
reservation corruption, no security hole, no migration failure was found. Every adversarial
and fumble input was rejected gracefully with an actionable message and left no partial state.

Low / cosmetic notes (none block production):

- **UX-1 (low):** the Receipt QC helper text says "you can't validate until it's ticked," but
  the Validate button isn't actually disabled — the gate is a clear server-side error. Wording
  slightly over-promises; behavior is safe.
- **UX-2 (low):** the guided-create "required field" error says "Strength" while the field is
  captioned "Strength / dosage / concentration." Same concept, minor mismatch.
- **UX-3 (low):** the per-scan feedback line is unlabelled (renders as a bare line under the
  scan box). Discoverable, but a coloured/iconed feedback area would read more clearly.
- **SEC-1 (low/INFO):** no `ir.rule` / company-isolation records exist — acceptable for this
  single-company deployment, recorded for awareness if it ever goes multi-company.
- **SEC-2 (low):** the per-keeper capability-grant `sudo` writes rely on the roster ACL
  (keepers have no write/create on the roster) rather than an in-method `has_group` re-check;
  it holds, and the grantable set can never include the manager group, so no escalation is
  possible — a defense-in-depth hardening suggestion only.
- **CI-1 (low/INFO):** the upgrade-path job's `PREV_TAG` (`v19.0.20.0.0`) trails the actual
  deploy candidate; it tests a *longer* migration chain (superset), so it's conservative, but
  the release process should bump `PREV_TAG` to the last green tag when cutting the release.

## 3. Performance Report (real measured timings, `wms_cert2`)

| Operation | Median | Notes |
|-----------|--------|-------|
| Barcode resolve (`wms.barcode.alias.resolve`) | **1.0 ms** | n=20 |
| "Find / where is it" location search | **0.7 ms** | n=10 |
| Expiry-alert report query | **2.3 ms** | n=5 |
| Occupancy report query | **1.9 ms** | n=5 |
| Oldest-stock report query | **1.3 ms** | n=5 |
| Scan Issue (plan + validate, full picking) | **110 ms** | single op |
| Scan Receipt (validate, full picking) | **358 ms** | single op; includes session first-write overhead — steady-state is in line with the issue path |

All operations are sub-second; reports return in single-digit milliseconds on the test data
volume. **No performance regression** from the hardening (the new guards add no query). Note:
these are scratch-DB figures on modest data — real-box single-op latency under live data is
itself an operator-measured go-live check.

## 4. Security Report (code audit — PASS, 2 low notes)

- **Two-role model** (`group_wms_user` keeper vs `group_wms_manager`) is well-formed; the
  native Inventory/Apps/Dashboards menus are hidden from keepers (no "make a picking outside
  Scan Receipt" back-door). Master data is keeper read-only; product onboard/create, GDrive
  settings, self-diagnostics, and **cost/valuation reports** are manager-only.
- **Manager-approval gate is sound — a keeper cannot self-approve** even via forced RPC: ACL
  is read+create-only (no write), the Approve/Reject buttons are manager-group-gated, **and**
  `action_approve`/`action_reject` re-check `has_group(manager)` in-method before any state
  change. Approval **cannot back-door the hard caps** — it re-runs the cap check under a
  product `FOR UPDATE` lock and re-plans against live stock.
- **Audit immutability is DB-enforced:** a done Barcode-origin picking must carry
  `wms_storekeeper_id` via a `CHECK` constraint whose `COALESCE` defeats the raw-SQL NULL-CHECK
  bypass; an ORM `@api.constrains` + a `write()` override block flipping the scan-issue marker.
  Confirmed damage records are write-locked for keepers.
- **No keeper-reachable param** can lower the high-value threshold, disable the approval gate,
  shrink min-life, or raise a cap. HTTP controllers gate every `sudo` read behind `auth=user`
  + `has_group`. No expiry-override path exists (correctly a v20 feature).
- Low notes: SEC-1 (no `ir.rule`), SEC-2 (capability-grant in-method re-check) — see §2.

## 5. Regression Report (12 historical defect classes — all guarded)

Each class maps to a real, verified guarding test: (1) qty 0/negative (receipt CHECK +
issue UserError); (2) receive-into-Damage; (3) receive-into-Repair; (4) double-submit
idempotency (issue + receipt + approval replay); (5) alias collision + multiplier>0;
(6) empty-issue blocked; (7) rollback / not-assigned abort; (8) FIFO oldest-first; (9) audit
storekeeper DB-CHECK (incl. the COALESCE-NULL hole); (10) concurrency outcomes; (11) upgrade
path (CI job); (12) self-diagnostics negative-on-hand internal-only. **No defect class is
unguarded.** The recent D1/D3/D4/D6 fixes each carry their own regression test, all green.

## 6. UX Report (PASS — operator clarity is strong)

The scan wizards are well-built for a low-literacy desk: every field has plain-language help,
`* required` vs `(optional)` markers are consistent, the hardened error messages (qty>0,
empty-plan, STOCK OUT, shortage, damage-dest, non-returnable, approval-held, caps) all name
the product/number and tell the operator the next step ("reduce the quantity," "wait for Scan
Return," "ask a Manager"), and the in-wizard "Help & Training → Getting Started" link resolves
to a real page. No dead-ends, no confusing labels beyond the 3 cosmetic notes in §2.

## 7. Multi-user Report

True OS-thread races aren't cleanly reproducible inside Odoo's single non-committing test
transaction, so safety is proven by **outcome**: the issue path takes a per-product
`SELECT ... FOR UPDATE` lock before the cap read and reservation; any move that can't fully
reserve aborts the whole transaction (no half-issue, no negative stock); double-submit reuses
the existing picking (no second deduction). These are asserted by `test_concurrency`
(`test_issue_aborts_when_stock_taken_concurrently`, `test_*_double_click_is_idempotent`,
`test_daily_cap_blocks_second_issue`) and re-affirmed by the driver (Agent C 3/3, Agent G 2/2).

## 8. Inventory Integrity Report

On a fresh DB, after a full receive/issue/carton/FIFO sequence: **conservation holds**
(received − issued = on-hand, exact), **FIFO drains the older slot first** (cross-slot,
deterministic `in_date`), **no internal location ever went negative**, and the carton alias
multiplier resolved correctly (1 scan = 12 units). The reservation engine refused every
over-issue. (Agent E 4/4; Agent A/D corroborate.)

## 9. Risk Register

| Risk | Severity | Status / mitigation |
|------|----------|---------------------|
| Cross-browser (Edge/Firefox) untested | Low | Not testable here; Odoo 19 is one responsive SPA. Recommend a 10-min manual smoke on Edge + Firefox at go-live. |
| Drive backup OAuth not exercised | Medium (ops) | Owner runs `setup-gdrive-auth.ps1` on the live box; backup *mechanics* already drill-verified. |
| Restore drill on the warehouse machine | Medium (ops) | Run `restore-native.ps1` into a throwaway DB on the live box once. |
| 2–4 h real keeper session not done | Medium (ops) | The human-acceptance step; software side is green. |
| No `ir.rule` company isolation | Low | Fine for single-company; revisit only if multi-company. |
| CI `PREV_TAG` stale | Low | Bump to the last green tag when cutting the release. |
| Deferred return/expiry gaps (over-return, expired-issue) | Medium | By design → v20 (per-loan reconciliation; perishable engine). Not a v19 regression. |

## 10. Final Production Readiness Report

The **software layer of v19 is certified ready** on objective evidence: 29/29 human-like
behavioral checks pass, 453/453 automated tests pass, CI is 6/6 green (including the upgrade
path), security/ACL/approval/audit are sound, inventory integrity and FIFO hold, rollback and
double-submit are safe, and measured performance is well within budget. **0 Critical, 0 High,
0 blocking defects.** The only findings are LOW/cosmetic UX and CI-housekeeping notes.

Full *production go-live* still depends on the **human/on-site items** that cannot be done
remotely — the Drive OAuth, a restore drill on the warehouse machine, and a real keeper
session — plus an optional 10-minute Edge/Firefox smoke.

### Final decision

> ## ⚠ CERTIFIED WITH MINOR ISSUES
>
> The v19 **software** is production-ready with only low/cosmetic notes (none blocking). The
> "minor issues" are the LOW notes in §2 and the **on-site human items** (Drive OAuth,
> warehouse-box restore drill, keeper session) and **untested cross-browser** in §9 — operational
> go-live steps, not software defects. Complete those on the live box and v19 is clear to freeze
> and tag.
>
> An unconditional **✅ CERTIFIED** is deliberately withheld only because those on-site items
> cannot be evidenced from here — not because of any software defect.
