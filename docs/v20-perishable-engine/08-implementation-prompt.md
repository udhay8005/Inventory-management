# v20 Wave 1 — Implementation Kickoff Prompt

> **DO NOT RUN THIS UNTIL ALL THREE PRECONDITIONS ARE TRUE.** This prompt assumes
> "planning complete, design frozen" — which is only true once the gates below are met. Running it
> earlier violates the v19 freeze and the owner's locked roadmap.

## ▶ PRECONDITIONS (gates — all must be TRUE before running)
1. **Spec approved & frozen** — the 9 OWNER sign-off decisions in
   [`07-functional-specification.md`](07-functional-specification.md) are confirmed; the spec is
   the frozen contract.
2. **v19 certified & frozen** — warehouse certification passed with evidence (printer, inventory,
   backup, restore, storekeeper, training, go-live sheet); v19 tagged "Production Certified" and
   frozen.
3. **v20 branch cut** — implementation happens on a **new `v20` branch** off `main`, never on the
   frozen v19 line. The lot-tracking migration runs on a fresh / zero-stock DB.

When (1)+(2)+(3) hold, execute the prompt below verbatim.

---

## ROLE
Lead Software Architect, Odoo 19 CE Expert, Warehouse Systems Engineer, QA Lead, Database Engineer,
Security Auditor, DevOps Engineer, Performance Engineer, Release Manager — implementing **v20
Universal Perishable Engine (Wave 1)** for the Dakshin Vrindavan Gaushala WMS. Implementation work;
planning complete; design frozen; the specification is the contract. Implement everything —
production code, no shortcuts, no TODOs, no placeholders, no mocked logic, no fake tests.

## AUTHORITY ORDER (on contradiction: STOP → document → fix design → continue; never silently invent)
1. Functional Specification (`07`) → 2. Architecture (`01`) → 3. Database & Migration (`03`) →
4. Backlog (`04`) → 5. Operational Gap Analysis (`06`).

## DO NOT REDESIGN
Design is frozen. No new workflows / models / permissions / UI / reports / dashboards unless
required to fix an implementation defect.

## PHASES (exact order; each ends fully green before the next)
- **P0 Scaffold** — `wms_perishable` addon, manifest, deps, `product_expiry` integration, install
  tests, upgrade scripts. Verify install / update / uninstall / reinstall all pass.
- **P1 Lot Engine** — lifecycle; receipt batch/mfg/expiry/supplier capture; duplicate-lot
  detection; automatic lot naming; tracking guard; never-merge rule. Test every scenario.
- **P2 FEFO Engine** — `wms_effective_expiry`; FEFO order + FIFO fallback; auto-split; reservation
  ordering; indexes; performance. Regression against every FIFO workflow — nothing outside
  perishables may change.
- **P3 Issue Safety** — expired block + manager approval; FEFO bypass; issue + resulting-balance
  preview; FEFO explanation; shortfall explanation; short-dated warning; lot-aware reversal;
  concurrency locking. Stress-test with multiple users.
- **P4 Recall & Quarantine** — quarantine; recall; lot freeze; reservation cancellation; picker
  exclusion; hold/release; locate-lot; recall notice; supplier recall. Test every transition.
- **P5 Reporting** — per-lot expiry report; thresholds; digest; diagnostics; lot barcode; lot
  label; lot timeline. Every report verified against DB values.
- **P6 Migration** — fresh DB / zero-stock / legacy-lot / rollback / recovery / dry-run / failure
  + interrupted-migration recovery. Fully documented.
- **P7 Hardening** — 100+ automated tests; browser validation; warehouse simulation; performance
  benchmark; CI. No skipped tests.

## DATABASE
SQL constraints, indexes, FKs, unique constraints, cascade rules, transactional + rollback-safe,
migration-safe, no duplicate data.

## SECURITY
Immutable audit history for every manager override / expiry correction / recall / destroy /
migration / configuration / approval.

## PERFORMANCE TARGETS
Receipt <1 s · Issue planning <1 s · FEFO planning <200 ms · Barcode lookup <50 ms · Dashboard
<2 s · Migration measured + reported.

## ERROR HANDLING
Power loss; interrupted receipt/issue; rollback; partial migration; deadlock; concurrent issue;
duplicate scans; invalid expiry; duplicate batch; wrong product; wrong barcode — all handled.

## TESTING (per ticket)
Unit · Integration · Browser · Regression · Performance · Security · Migration · Concurrency ·
Recovery · Warehouse simulation. Do not stop until every test passes.

## SELF-HEAL LOOP (per phase)
Analyze → implement → run tests → collect failures → root-cause → fix → retest → regression →
repeat until green. Never stop after the first pass.

## MULTI-AGENT EXECUTION
Parallel specialist teams (Architecture / Backend / Frontend / Database / Migration / Security /
Performance / QA / Regression / Documentation / DevOps / Release), each working independently;
merge only after all blockers resolved.

## QUALITY GATES (every phase)
lint · formatting · typing · install · upgrade · migration · rollback · browser · regression · CI
· documentation — no phase proceeds until completely green.

## FINAL ACCEPTANCE (objectively verified — no fabricated PASS)
Every backlog ticket implemented · every automated test passes · 0 critical / 0 high bugs · 0
skipped tests · 0 failing CI jobs · migration validated · rollback validated · browser validation
complete · warehouse simulation passes · docs updated · performance targets met · security audit
passes.

**Final implementation report:** files changed · features implemented · database changes ·
migration summary · performance results · security audit · test statistics · known limitations ·
deployment checklist · production-readiness assessment. Do not declare completion until every
acceptance criterion is objectively verified.
