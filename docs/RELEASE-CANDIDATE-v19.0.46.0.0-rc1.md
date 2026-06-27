# Release Candidate — v19.0.46.0.0-rc1

**Dakshin Vrindavan Gaushala WMS · Odoo 19.0 CE**
**Release-candidate commit:** `7da8b49` on branch `test` (built on the hardened `81d055c`).
**Do NOT tag production yet** — this document is the RC package + Go/No-Go; the final tag is a
separate, owner-approved step. Production `wms`:8069 was never touched (all builds/tests on
scratch DBs).

---

## 1. Executive Summary

v19 is software-complete and green. This RC pass reviewed the AI-certification's LOW findings,
landed two genuine release-quality fixes (the CI upgrade-gate `PREV_TAG`, and one operator-error
label), re-ran the full regression on a clean DB (**0 failed / 0 error of 453**), and re-verified
lint, security, performance, and the upgrade path. **0 Critical, 0 High, 0 blocking defects.** The
remaining items are documented LOW-risk notes and the **on-site human-validation steps** that
cannot be evidenced remotely. **Decision: ⚠ READY FOR RELEASE CANDIDATE WITH DOCUMENTED LOW-RISK
ITEMS** (see §12).

## 2. Low-Severity Resolution Report

| Finding (source) | Severity | Resolution |
|---|---|---|
| CI `PREV_TAG` stale (`v19.0.20.0.0`) — upgrade gate tested an ancient hop | low | **Fixed** → `v19.0.45.0.0` (the real last-green tag); the upgrade job now exercises the actual `v45 → HEAD` hop |
| Required-field error said "Strength" while the field is "Strength / dosage / concentration" | low | **Fixed** → error now uses the full caption |
| Receipt QC help says "you can't validate until ticked" but the button isn't disabled | low | **Won't Fix** — the statement is functionally accurate (server hard-blocks validation until ticked); disabling the button is a UI change with no safety benefit. Documented as Known Limitation. |
| Per-scan feedback line is unlabelled (renders as bare text) | low | **Future Version** — cosmetic; a coloured/iconed feedback area is a UX enhancement, out of a defect-only freeze |
| No `ir.rule` / company-isolation records | low/INFO | **Won't Fix (by design)** — correct for the single-company deployment; revisit only if it ever goes multi-company (Known Limitation) |
| Per-keeper capability-grant `sudo` write not re-checked in-method | low | **Future Version** — holds today via roster ACL (keepers can't reach it) and the grantable set can never include the manager group, so no escalation is possible; an in-method `has_group` re-check is defense-in-depth hardening |

**2 Fixed · 2 Won't-Fix (by design) · 2 Future-Version.** No LOW finding was a release blocker.

## 3. Regression Report

- **Full WMS suite on a fresh `--without-demo` DB, CI recipe** (`--test-tags
  wms,wms_audit,wms_delete,wms_health,wms_ui_cert`): **0 failed, 0 error of 453 tests.**
- **No skipped tests, no silenced tests.** The 4-defect hardening + this RC's 2 fixes each retain
  or add their guarding tests; all 12 historical defect classes remain guarded (see the AI cert
  Regression report).
- **Behavioral (human-like) regression:** 29/29 driver checks PASS across the operator personas
  (see [CERTIFICATION-v19-AI-VALIDATION.md](CERTIFICATION-v19-AI-VALIDATION.md)).
- **Browser:** no automated JS tour tests exist in this suite; browser behavior was validated by
  the AI cert (live Chrome receive→done + the behavioral driver). Cross-browser is a human item (§10).

## 4. CI Report

CI on `test` @ `7da8b49` — **all 6 jobs green:** Lint & static checks ✅, Security scan ✅, Odoo
module tests ✅, **Odoo upgrade path (`v19.0.45.0.0 → HEAD`) ✅** (the real deploy hop now migrates
cleanly with the new `PREV_TAG`), Native smoke (install) ✅, CI status ✅.

There is no separate "packaging" or "rollback" CI job: **packaging** is the RC manifest (§9), and
**rollback** is restore-from-encrypted-backup, drilled separately (TOC-verified; full warehouse-box
drill is a human item — §10). Lint = black + isort + flake8 + pylint-odoo (security/deprecation gate)
+ XML well-formedness.

## 5. Performance Report (measured, scratch DB)

| Operation | Median | Source |
|---|---|---|
| Barcode resolve | 1.0 ms | cert driver, n=20 |
| "Find / where is it" search | 0.7 ms | n=10 |
| Oldest-stock report | 1.3 ms | n=5 |
| Occupancy report | 1.9 ms | n=5 |
| Expiry-alert report | 2.3 ms | n=5 |
| Scan Issue (plan+validate) | 110 ms | single op |
| Scan Receipt (validate) | 358 ms | single op (incl. session first-write) |
| Cold first-install (all 7 addons, `-i`, one-time) | ~115 s | RC regression boot |
| Warm service restart (registry load, already installed) | ~13 s | service-start logs |

No new query or hot-path change was introduced (the RC fixes are a CI-config edit and one string).
**No performance regression.** Real single-op latency under live warehouse data is itself a human
go-live check (§10).

## 6. Security Report

Production security audit (code-grounded) — **PASS**, 2 LOW notes (both in §2):

- Two-role model enforced; native Inventory/Apps menus hidden from keepers (no picking back-door);
  master data keeper read-only; cost/valuation reports manager-only.
- **Broken access control:** none found — a keeper **cannot self-approve** a held issue (ACL
  create-only + manager-group button + in-method `has_group` re-check), and approval **cannot
  back-door the caps** (re-checked under a `FOR UPDATE` lock).
- **SQL injection:** none — `resolve()` and all queries are parameterized; a `'; DROP TABLE…`
  barcode resolved to nothing (driver Agent D); pylint-odoo sql-injection gate green.
- **Audit logging:** DB-immutable — a done WMS issue must carry the storekeeper (CHECK with
  COALESCE defeating the NULL-bypass) + ORM constrains + write-override.
- **XSS:** chatter built with `Markup` + `escape()` on user-renamed records; **CSRF:** Odoo's
  built-in form CSRF in force (the one GET backup-download is intentionally exempt and auth+group
  gated).

## 7. Documentation Report

Existing and verified present in `docs/`: Installation (`INSTALLATION-GUIDE.md`), Deployment
(`07-deployment.md`), CI/CD & upgrade (`17-ci-cd.md`), Restore drill (`18-restore-drill.md`),
Disaster recovery / rollback (`19-disaster-recovery.md`), Backup (`22-gdrive-backup.md`),
Operations playbook / troubleshooting (`13-operations-playbook.md`, `11-maintenance.md`),
Go-live validation (`GO-LIVE-VALIDATION.md`), Hardware (`16-hardware-guide.md`), Quick-starts
(`ADMIN-QUICK-START.md`, `STOREKEEPER-QUICK-START.md`), plus the v19 cert/hardening reports.

Generated/updated this RC: **this document** (RC package + Go/No-Go), the **Release Notes** and
**Version Manifest** (§9), and the **Known Limitations** + **Emergency Hotfix Procedure** below.

**Known Limitations (v19):** per-product (not per-lot) expiry — no FEFO-by-batch, no expired-issue
block, no batch recall (all → v20); return reconciliation is best-effort (over-return / partial
return / wrong-unit are not quantity-checked — → v20); low-stock alerting is demand-driven (a
never-used item at zero stock does not alert); single-company only (no `ir.rule` isolation);
cross-browser verified on Chrome only.

**Emergency Hotfix Procedure (summary):** branch from the release tag → minimal fix + regression
test → CI green → tag `v19.0.46.0.1` (patch) → `restore-native.ps1` rollback path stays available
if the hotfix misbehaves. Full DR steps in `19-disaster-recovery.md`.

## 8. Production Readiness Report

Service/config (verify on the live box at deploy): NSSM service `Odoo-WMS` Running + Automatic;
`config/odoo.native.conf` (`list_db=False`, `db_listing=False`, no dbfilter, addons path);
PostgreSQL service running; scheduled jobs present (daily backup task, the WMS crons — expiry
digest, low-stock 8:10, returns-overdue, health, restore-drill check); logging to
`.runtime/logs/odoo.log`; wkhtmltopdf on PATH for PDF labels. The Production Readiness Checklist
(§10) lists each as an explicit verify step.

## 9. Release Candidate Manifest

```
Release candidate : v19.0.46.0.0-rc1   (DO NOT TAG until owner go-ahead)
Commit            : 7da8b49 6b2510d1b00322eb2368d4ae81476fa98   (branch: test)
Built on          : 81d055c (hardening) over v19.0.45.0.0 (last release)
Platform          : Odoo 19.0 Community · Python 3.12 · PostgreSQL 16/17 · Windows (native NSSM)
Addon versions:
  wms_location        19.0.3.25.0
  wms_fifo            19.0.1.1.0
  wms_barcode         19.0.1.48.0   (bumped this RC)
  wms_repair_damage   19.0.1.17.0
  wms_ai_forecast     19.0.1.5.0
  wms_reports         19.0.4.14.0
  wms_training        19.0.1.14.0
Runtime deps (requirements.txt):
  numpy>=1.26,<2.0 · pandas>=2.0,<3.0 · statsmodels>=0.14.6 · Pillow>=12.2.0
  reportlab>=4.0,<5.0 · rl-renderPM>=4.0
Upgrade path tested: v19.0.45.0.0 -> HEAD (CI upgrade job)
Artifacts (this RC): HARDENING-REPORT-v19-defects.md · CERTIFICATION-v19-AI-VALIDATION.md ·
  CERTIFICATION-REPORT-v19.md · this RELEASE-CANDIDATE doc · the green CI run
```

## 10. Human Validation Checklist (PENDING — cannot be fabricated)

Each item needs objective on-site evidence before full production sign-off. Record results in
`docs/GO-LIVE-VALIDATION.md`.

- ☐ **Google Drive backup OAuth** — run `scripts/setup-gdrive-auth.ps1`; confirm a test backup
  uploads and appears in Drive. *(mechanics drill-verified; OAuth consent is human-only)*
- ☑/☐ **Physical label printer (TE244)** — owner-confirmed printing; for the record, print one
  product label and confirm it scans back to the right product.
- ☑/☐ **Physical barcode scanner** — owner-confirmed (auto-Enter); for the record, one
  receive→issue→return loop with the handheld.
- ☐ **Warehouse-PC restore drill** — `scripts/restore-native.ps1` into a throwaway DB on the live
  box; confirm it boots and data is intact.
- ☐ **Real storekeeper session (2–4 h)** — a keeper runs the floor; capture any confusion/issues.
- ☐ **Browser smoke (Edge + Firefox)** — 10-min: login, Scan Receipt, Scan Issue, a report, print.
  *(Chrome validated by the AI cert; Edge/Firefox untested here.)*
- ☐ **Production deployment verification** — service Running/Automatic, health endpoint OK, first
  real receipt with the scanner, daily backup ran overnight.

## 11. Risk Register

| Risk | Sev | Status / mitigation |
|---|---|---|
| On-site human items not yet evidenced | Medium (ops) | Listed in §10; software side green |
| Cross-browser Edge/Firefox untested | Low | 10-min manual smoke at go-live |
| Drive OAuth not exercised | Medium (ops) | `setup-gdrive-auth.ps1`; mechanics drilled |
| Return/expiry gaps (over-return, expired-issue) | Medium | By design → v20; not a v19 regression |
| Single-company (no `ir.rule`) | Low | Fine for this deployment |
| New PREV_TAG hop (`v45→HEAD`) | Low | Validated by the CI upgrade job on this RC commit |

## 12. Go / No-Go Decision

**Software gates:** 0 Critical ✅ · 0 High ✅ · Regression green (453/453) ✅ · Lint green ✅ ·
Security PASS ✅ · Performance no-regression ✅ · Upgrade path verified ✅ · Documentation complete ✅.
**Operational gates:** human-validation items listed separately (§10), none fabricated.

> ## ⚠ READY FOR RELEASE CANDIDATE WITH DOCUMENTED LOW-RISK ITEMS
>
> `v19.0.46.0.0-rc1` (`7da8b49`) is software-ready: every objective software gate is green with
> evidence, and the only open items are documented LOW-risk notes (§2, all classified) and the
> on-site human-validation steps (§10) that cannot be evidenced remotely. Build the RC; complete
> the §10 checklist on the live box; then the owner tags `v19.0.46.0.0` and freezes v19.
>
> A No-Go would require a Critical/High defect, a red regression/CI, a migration or rollback
> failure, or a security hole — **none are present.**
