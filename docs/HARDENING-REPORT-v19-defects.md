# v19 Production Hardening — Real-World Logic Gap Fix Report

**Date:** 2026-06-26 · **Branch:** `test` (commit `81d055c`) · **Scope chosen by owner:**
Option 2 — *confirmed validation/logic defects only* + *config-toggle enablement guide*.
**Freeze respected:** no new fields, models, workflows, reports, permissions, or
architecture; nothing v20. Production `wms`:8069 was never touched (all testing on
scratch DB `wms_fixtest`).

This work came out of the real-world scenario review. A 7-agent read-only verification
pass checked every candidate against the actual code; **2 of 7 candidates were NOT
defects** (already handled / claim false) and were correctly left alone, which is as
important as the fixes.

---

## 1. Files changed

| File | Change |
|------|--------|
| `addons/wms_barcode/wizards/scan_issue.py` | D1 positive-qty guard in `action_plan`; D6(a) clearer empty-plan message |
| `addons/wms_barcode/wizards/scan_receipt.py` | D4 damage/repair-destination guard in `action_validate`; D6(c) docstring fix |
| `addons/wms_barcode/models/wms_barcode_alias.py` | D3 `CHECK(units_per_scan > 0)` constraint |
| `addons/wms_barcode/__manifest__.py` | version 19.0.1.46.0 → **19.0.1.47.0** |
| `addons/wms_barcode/tests/test_quantity_integrity.py` | +`TestIssueQuantity` (2 tests) |
| `addons/wms_barcode/tests/test_barcode_integrity.py` | +`test_units_per_scan_must_be_positive` |
| `addons/wms_repair_damage/tests/test_receipt_damage_dest.py` | **new** — `TestReceiptDamageDest` (4 tests) |
| `addons/wms_repair_damage/tests/__init__.py` | register the new test module |
| `addons/wms_repair_damage/__manifest__.py` | version 19.0.1.16.0 → **19.0.1.17.0** |

Diffstat: **9 files, +222 / −6.** No XML, no security CSV, no data files, no migrations.

## 2. Logic defects fixed

- **D1 — Scan Issue accepted a non-positive quantity and mis-reported it.** Issuing
  with qty `0` printed a fake success line (“Planned 0 × … across 0 slot(s)”); a
  negative qty raised a bogus “⚠ STOCK OUT” even when the product was fully in stock.
  Now `action_plan` refuses qty ≤ 0 up front with “Quantity must be greater than zero.”
- **D3 — A carton alias multiplier could be saved as 0 or negative.** `units_per_scan`
  was `required=True` (which only blocks NULL, not 0). A bad multiplier made every scan
  of that carton a silent dead-end on issues and a raw `IntegrityError` on receipts. Now
  blocked by `CHECK(units_per_scan > 0)`.
- **D4 — A receipt could be landed in a Damage/Repair location.** If an admin barcoded
  the auto-created Damage/Repair-Out location, scanning it routed good incoming stock
  there — and those locations are *deliberately excluded* from the FIFO issue picker, so
  the stock became on-hand-but-un-issuable, silently stranded. Now refused at validate.
- **D6 — Misleading operator messages.** (a) The empty-plan validate message now names
  the real cause (no stock / qty above zero) instead of only “you haven’t chosen what to
  issue.” (c) A stale `_auto_assign_slot` docstring promised a “will mix products”
  warning the code never emits — corrected to describe the silent last-resort fallback.

## 3. Root cause of each defect

- **D1:** `requested_qty` is a plain `Float(default=1.0)` with no positivity guard,
  unlike the receipt line’s `CHECK(quantity > 0)`. A qty ≤ 0 leaked into the planner,
  whose `remaining <= 0: break` loop returns an empty plan with `missing` = 0 (→ fake
  success) or negative (→ truthy → wrong STOCK-OUT branch). It never corrupted stock —
  validate hard-blocks the empty plan — it just diagnosed it wrong.
- **D3:** `required=True` on a Float rejects only NULL/False, not `0.0`; no `@api.constrains`
  or CHECK touched `units_per_scan`, while the *other* alias field (barcode) was guarded
  rigorously. An oversight, not a deliberate choice.
- **D4:** `resolve()` returns the first location whose barcode matches with **no** filter
  on the damage/repair flags, and `action_validate` built the move with that destination
  without checking. The line field’s UI `domain` is client-side only and is bypassed by
  the programmatic scan write.
- **D6:** (a) the empty-plan guard’s wording was accurate only for the genuine
  “scanned nothing” case but reachable for “out of stock” too; (c) the doc promised a
  warning branch that was never implemented.

## 4. Tests added (7 new, all green)

| Test | Proves |
|------|--------|
| `TestIssueQuantity.test_issue_rejects_non_positive_requested_qty` | qty 0 and −2 raise “greater than zero”; qty 1 still plans |
| `TestIssueQuantity.test_validate_empty_plan_message_names_stock` | empty-plan validate names the real cause |
| `TestAliasBarcodeCollision.test_units_per_scan_must_be_positive` | multiplier 0 / −2 raise `IntegrityError`; 24 accepted |
| `TestReceiptDamageDest.test_receipt_into_damage_location_refused` | receipt into a Damage location is refused, no picking created |
| `TestReceiptDamageDest.test_receipt_into_repair_location_refused` | same for a Repair-Out location |
| `TestReceiptDamageDest.test_receipt_into_floor_still_validates` | a legitimate floor destination still validates to done (no over-block) |
| `TestReceiptDamageDest.test_post_init_created_damage_repair_locations` | fixture sanity (the flagged locations exist) |

(The D4 tests live in `wms_repair_damage`, not `wms_barcode`, because the
`wms_is_damage`/`wms_is_repair` flags are defined there — and `wms_repair_damage` depends
on `wms_barcode`, so a reverse dependency would cycle. The guard itself stays in
`wms_barcode` and accesses the flags via `getattr`, so it is safe even on a partial
install.)

## 5. Regression results

- **Full WMS suite on a clean DB (CI recipe, `--test-tags wms,wms_audit,wms_delete,wms_health,wms_ui_cert`): 0 failed, 0 error of 453 tests.** (446 prior + 7 new.)
- **Lint, all green:** black, isort, flake8, and the pylint-odoo security/deprecation gate
  (sql-injection, invalid-commit, deprecated-API, etc.).
- **No existing test changed or removed.** The two “not a defect” candidates (receipt-qty,
  negative-stock) keep their existing coverage untouched.
- **CI on `test` @ `81d055c`: all 6 jobs green** — Lint & static checks, Security scan,
  Odoo module tests, **Odoo upgrade path (prev tag v19.0.45.0.0 → HEAD)** (so the new CHECK
  constraint migrates cleanly), Native smoke, CI status.

## 6. Performance comparison

No measurable impact, by construction — the changes add only constant-time input
validation and reuse existing iteration:

- D1 is one `<= 0` comparison before any query.
- D3 is a Postgres `CHECK` enforced at write time — no application-side cost, no query.
- D4 is a `filtered()` over the receipt’s own lines (typically 1–few), which the validate
  path already iterates; it adds **zero** new database queries.
- D6 is message/comment text only.

The full-suite wall-clock was unchanged within noise between the pre- and post-change runs.
(No micro-benchmark numbers are reported because none of the changes touch a hot path or
add a query — fabricating timings would not be honest evidence.)

## 7. Security findings

- No new vulnerability introduced; the pylint-odoo **sql-injection / invalid-commit**
  gate passes. The new CHECK uses a static literal (no string interpolation).
- D4 is itself a small **integrity** hardening: it closes a path that stranded usable
  stock outside the issuable pool.
- The audit-trail and approval controls are untouched (no change to who can do what).
  Precise scope (re-verified): every **done** Barcode-origin issue picking is DB-enforced
  to carry **`wms_storekeeper_id`** (a `CHECK` + `@api.constrains` on `stock.picking`);
  `wms_taken_by` is `required=True` at the wizard, and `wms_ordered_by` is intentionally
  optional. So the *storekeeper* is the enforced invariant, not a NOT-NULL triplet — by
  design (an optional authoriser is part of the documented contract).
- `getattr` access to the damage/repair flags is safe (default `False`); it cannot be
  used to bypass the guard.

## 8. Remaining Medium issues (out of this scope — by owner decision)

These are real but were explicitly excluded from Option 2 (they are features, redesigns of
documented-intentional behavior, or v20 work):

- **Return flow does not check quantity or identity** — over-returns inflate stock, a
  partial return clears the whole loan, a second return re-receives the unit, and returning
  a different copy of a tool clears someone else’s loan. *Documented “lean by design / F3
  contract”; changing it is a redesign — needs an explicit owner decision, not a defect fix.*
- **Issuing already-expired stock is silent; two batches of one medicine can’t be tracked
  separately.** *v20 perishable engine (per-lot expiry + FEFO + expired-issue block).*
- **Blind-trusted scan** — scanning the right label while handing out the wrong physical
  item silently mis-states both products. *Needs a confirmation-of-identity design decision.*
- **Supplier short-ship unflagged** — Scan Receipt isn’t tied to the PO. *Needs PO
  integration (feature).*
- **Damaged/in-repair stock still counts in native on-hand** — native valuation and WMS
  reports don’t reconcile at month-end. *Reporting/design decision.*

## 9. Remaining Low issues (out of scope)

- New / never-used items at zero stock never trigger a low-stock alert; no plain
  at-or-below-zero alert. *Alerting is demand-driven by design; a static min-level is a
  schema/feature change.*
- No cycle-count adjustment workflow (reason/approval/variance) — falls back to native Odoo.
  *Feature.*
- Products created via plain form / import / bulk onboard can skip required identity fields.
  *Documented intentional (only the guided wizard enforces them).*
- Near-duplicate misspelled master names (Bosch vs Bosche) aren’t caught. *By design — the
  autocomplete is the guard.*

## 9a. Severity of the fixes & closure of remaining open items (2026-06-26)

**Severity of the defects fixed** (none caused data corruption or downtime — all were
safely blocked or self-correcting; this is hardening, not incident response):

- **Critical: 0.**
- **High: 1 — D4** (a barcoded Damage/Repair location could absorb a receipt → good stock
  silently became on-hand-but-un-issuable; an inventory-integrity loss with no error). Now
  blocked.
- **Medium/Low: 3 — D1, D3, D6** (confusing-but-safely-blocked qty diagnosis; an
  admin-config dead sticker / raw IntegrityError; message + docstring wording).

**Remaining open items — a focused 4-agent read-only pass closed each; no additional
freeze-safe defect was found:**

- **Duplicate same-product scan on a receipt** → *cosmetic, left as-is*. The stock total is
  always correct (Odoo merges the same-key non-lot moves, and the fill path sums either
  way; `test_receipt_double_click_is_idempotent` confirms). Merging at scan-time would have
  to special-case lot **and** destination and would touch the validated lot move-line split
  that `test_two_lots_same_product_keep_separate_move_lines` guards — exactly the regression
  risk the freeze forbids.
- **Return validation (no-match / over-return / duplicate-return / wrong-unit)** →
  *intentional design + v20*. The no-match silence and "clear the oldest debt" are the
  documented *lean-by-design / F3* contract, locked by `test_no_match_leaves_nothing_changed`
  and `test_scan_return_clears_oldest_first`. Over-return inflation and duplicate-re-receive
  can only be caught with per-loan/per-unit reconciliation (new fields + a returned-qty
  rollup) — a redesign the owner explicitly routed to v20. A message-only fix is also
  structurally impossible: `action_validate` navigates to the receipt picking, so the
  wizard's feedback is never shown.
- **Warehouse/location configuration validation** → *already handled*. There is no
  per-location "allow negative" flag to misconfigure; over-issue is prevented by the
  reservation abort; missing picking types raise clear errors at point-of-use; the one real
  config hazard (a damage-flagged location as a stock destination) is now blocked by D4. The
  only residual (an admin manually flagging a *populated* storage slot via the raw backend)
  is unreachable through any wizard and a probe for it would risk false-positives — out of
  scope for a defect-only freeze.
- **Already-handled audit** → confirmed verbatim for: unknown-barcode rejection on issue,
  unknown-barcode feedback on receipt, the QC gate, the all-or-nothing issue abort, and the
  per-product `FOR UPDATE` serialization. The audit invariant is **storekeeper**-enforced at
  the DB (see §7).

**v20 backlog entry (from this pass):** per-loan return reconciliation — issued-qty vs
returned-qty and unit/lot identity, so Scan Return can warn on over-return, flag a duplicate
re-receive of an already-returned loan, and match the specific unit instead of clearing the
oldest. Needs new qty/loan-link fields on the issue picking + a returned-qty rollup on the
Returns-due report.

## 10. Config-toggle enablement (Option 2, part 2 — owner applies; not auto-flipped)

These safeguards are **already built and tested**; they ship OFF so existing behavior is
unchanged. Because they live as runtime data in the **production** database (which must not
be touched from here), they are delivered as a reversible enablement step for the owner to
apply, not flipped remotely. Each is validated by an existing suite test (which the green
run above re-confirms).

| Safeguard | Switch | Scope | Default | Enable | Effect / risk |
|-----------|--------|-------|---------|--------|---------------|
| Per-issue cap | product field **Max per issue** (`wms_max_per_issue`) | per-product | 0 (off) | set a positive number on the product | hard-blocks a single issue over the cap; a too-tight cap blocks legit bulk draws |
| Daily cap (24h rolling) | product field **Daily cap** (`wms_daily_cap`) | per-product | 0 (off) | set a positive number on the product | hard-blocks once the rolling 24h total would exceed; set below true daily use and the afternoon feed issue is blocked |
| Slot-capacity enforcement | System Parameter `wms_location.enforce_capacity` | global | `0` | set to `1` (Settings → Technical → System Parameters) | turns soft capacity hints into hard walls; can refuse an over-filling receipt |
| Low-stock **email** digest | System Parameter `wms_reports.alert_email` | global | `0` | set to `1` | sends the manager alerts as email too (in-app is always on); needs a mail server or sends are silently dropped |
| “Requested again too soon” gate | System Parameter `wms_location.default_min_life_days` | global (per-product `wms_min_life_days` wins) | `0` | set to a positive integer | routes a same-dept same-product re-request within N days to manager approval; a trust-wide floor adds approval friction |

To enable any global one: **Settings → Technical → System Parameters → New** (key + value
above). All are reversible (delete the parameter or set back to `0`). The per-product caps
are set on the product form. Recommended starting point for this gaushala: leave caps at 0
until a product shows real over-pull; consider `enforce_capacity=1` only once real slot
capacities are entered.

## Production-readiness verdict

**The fixes are production-ready as freeze-safe defect hardening:** every change is a
minimal, additive guard or message; the two non-defects were correctly left alone; the full
WMS suite is **0 failed / 0 error of 453** on a clean DB and all lint gates pass; no schema,
no migrations, no behavior change to any currently-successful path. This does **not** alter
the standing v19 certification status — it remains **software-ready, pending the operator
items** (real label print + scanner floor run, Drive OAuth, warehouse-box restore drill,
storekeeper session). The Medium/Low items in §8–§9 are deliberately deferred (features /
v20 / owner decisions), not regressions.
