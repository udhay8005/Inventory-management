# v19 Production Certification Report

**Date:** 2026-06-25 · **Release under test:** `v19.0.45.0.0` (main @ `172c8fa`) · **Certifier:**
automated certification run (read-only; no features, no v20 work). DB used: scratch `wms_cert`
(:8169) — production `wms` (:8069) untouched.

## Verdict

> **SOFTWARE CERTIFICATION: ✅ PASS** — every gate that can be verified remotely/automatically is
> green, with **0 Critical and 0 High defects**.
>
> **FULL "v19 Production Certified": ⏸ PENDING operator evidence.** Five items are operator-only on
> the live warehouse box and, per the project's own `docs/PHASE-H-VALIDATION-PROTOCOL.md`, **require
> human evidence** — they are **not** declared passed here (fabricating them would violate the
> protocol). v19 is software-ready and **one operator validation session away** from full
> certification.

## Results by area

| # | Area | Result | Evidence |
|---|------|--------|----------|
| 1 | **Deployment** (clean install, upgrade, boot) | ✅ PASS | CI on main `172c8fa`: **Native smoke** (clean install + boot) + **upgrade path (prev-tag → HEAD)** green |
| 2 | **Product management** (create/edit/SKU/PRD/barcode/dup/search) | ✅ PASS | wms_location 110 tests + wms_barcode 177 tests green; guided-create + onboard wizards covered |
| 3 | **Warehouse operations** (receipt/putaway/move/issue/return/damage/repair/audit) | ✅ PASS | 446-test suite green incl. wms_barcode/repair_damage/reports; **Scan Receipt wizard rendered live** (scan field, QC gate, audit trail) |
| 4 | **Security** (ACL, groups, record rules, approval, escalation) | ✅ PASS | CI **Security scan** green; ACL/capability/approval tests pass; prior live UAT confirmed keeper ACL + direct-URL denial |
| 5 | **Backup** (creation, encryption, recoverability) | ✅ PASS | daily encrypted sets present incl. today (`wms-20260624-130002`); **restore-drill: decrypt OK + TOC 10,581 entries, 1.9 s** |
| 6 | **Browser validation** | ✅ PASS | live `wms_cert`: login → WMS home (Slots map), Operations menu (14), Scan Receipt wizard, Reports menu (19) — no tracebacks/broken views; full view set validated by the suite (broken views fail at install) |
| 7 | **Performance** | ✅ PASS (software) | suite: wms_barcode 177 tests/15.7 s, wms_reports 296/30.1 s; scan/issue planning + barcode tests within budget. Live single-op timings = operator item |
| 8 | **Database** (constraints, indexes, upgrade/rollback safety) | ✅ PASS | constraints/indexes mapped (Phase-0 `09`); CI upgrade-path green; rollback = restore (drill verified) |
| 9 | **Documentation** | ✅ PASS | install/deploy/restore/go-live/validation-protocol all present (`docs/INSTALLATION-GUIDE.md`, `07-deployment.md`, `18-restore-drill.md`, `GO-LIVE-VALIDATION.md`, `PHASE-H-VALIDATION-PROTOCOL.md`) |
| 10 | **Regression** | ✅ PASS | **446 tests, 0 failed / 0 errors** on a fresh `wms_cert` DB; CI module-tests green |

## Defects found

**0 Critical · 0 High · 0 Medium · 0 Low** — no production defect requiring a fix was surfaced by
the automated gates. The suite and CI are clean; no Critical/High fix was needed, so the freeze's
defect-fix allowance was not exercised.

### Observation (out of WMS scope — informational)
During the browser session, a **separate, non-WMS tab** showed the trust's **public website
(`dv_website`)** with a *"style compilation failed"* alert. Verified: `dv_website` is **not in this
project's addons path** and **not installed in `wms_cert` or production `wms`** (DB query) — it is a
**different project/instance** the owner's Chrome had open. It is **not a WMS defect** and does not
affect WMS certification, but the owner may want to check that separate website's asset bundle.

## ⏸ REQUIRES OPERATOR — the gate to FULL production certification

Per `docs/PHASE-H-VALIDATION-PROTOCOL.md`, these need hands-on evidence on the live warehouse box
and are **not** certified here:
1. **Real label print** on the TSC TE244 (physical print + barcode **scans back** to the product).
2. **Physical barcode scanner** end-to-end (receive → issue → return with a real handheld).
3. **Google Drive backup** (OAuth consent — `setup-gdrive-auth.ps1`).
4. **Restore drill on the warehouse machine** (a real `restore-native.ps1` into a throwaway DB on
   the production box).
5. **2–4 h real storekeeper usage session** (an actual keeper running the floor).

The label engine, scan flows, backup/restore mechanics, and Drive pipeline are all software-verified
(suite + CI + drill); these five confirm the *hardware/real-world* layer that only a human on-site
can evidence.

## Go-Live checklist status
Installation ✅ · Database ✅ · First launch ✅ (CI smoke) · Service ⏸ (operator: confirm `Odoo-WMS`
Running/Automatic on the warehouse box) · Security ✅ · Backups ✅ (mechanics) / ⏸ (Drive OAuth +
warehouse-machine restore) · Health endpoint ✅ (software) · Warehouse configured ⏸ (operator builds
real racks) · Users ⏸ (operator sets real passwords/roster) · Labels ⏸ (real print) · Training ⏸
(keeper completes) · First receipt ⏸ (real receipt with scanner) · Restore drill ✅ (TOC) / ⏸ (full
on warehouse box) · **Production sign-off** ⏸ (the trust's responsible person).

## Recommendation
The **software is production-ready** (0 Critical/High, all automated gates green, regression clean).
To declare **"v19 Production Certified"**, complete the five operator items above with evidence
(fill `docs/GO-LIVE-VALIDATION.md`). **Only then**: tag "Production Certified", freeze v19, cut the
`v20` branch, and run `docs/v20-perishable-engine/08-implementation-prompt.md`. No v20 work begins
before that.
