# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) conventions with Odoo-style
semantic version tags (`v19.0.<release>`). Each entry maps to a published
[GitHub Release](https://github.com/udhay8005/Inventory-management/releases).

## [v19.0.16.0.0] — 2026-06-07 — FPAT remediation (4 Criticals + 19 Highs)

Closes every Critical and the highest-impact High findings from the FPAT
(Final Production Acceptance Test). Five fix-batches (FX-1..FX-5), each
CI-green with regression tests reproducing the auditor's exact scenarios.

### Critical — fixed + tested (FX-1)
- **`wms.damage.action_confirm` crashed 100%** — Selection lambda on related field; read the static list from `product_tmpl_id`.
- **`wms.audit.action_review_accept` had no row lock** — `flush_recordset` + `SELECT FOR UPDATE` + re-check state from DB.
- **FIFO planner could pull from Damage / Repair-Out** — excluded `wms_is_damage` / `wms_is_repair` from the planner domain (NOT from `_gather` — internal repair moves source from there legitimately).
- **Backup ScheduledTask LogonType=Interactive** — switched to `NT AUTHORITY\SYSTEM` / `LogonType=ServiceAccount` so DR survives a locked console / reboot.

### High — fixed + tested
- **FEFO is now actually FEFO** for `EXPIRY_SENSITIVE_KINDS` (sort by `wms_expiry_date asc`, falls back to in_date). The Scan Issue wizard's "earliest expiry first" banner is honest. (FX-2)
- **Consumption Value snapshots unit cost** at validate-time on `stock.move.line.wms_unit_cost_at_done`; a later `standard_price` change cannot rewrite past months. (FX-2)
- **`damage_value` is a hard snapshot** set at `action_confirm`; not a recomputed field. Editing quantity post-confirm doesn't rewrite history. (FX-2)
- **Expiry value-at-risk excludes non-storage sinks** (Trust internal use / Damage / Repair-Out). (FX-2)
- **`/wms/find` substring router → exact-match keywords** — searching "Slow Cooker" no longer renders the dead-stock list. (FX-2)
- **`/wms/find` alias fallback typo** — column is `barcode`, not `name`; every auto-EAN-13 was returning 500. (FX-1)
- **Bulk-onboard Barcode column crash** — same alias-column typo in the pre-validator. (FX-1)
- **Bulk-onboard UoM column crash** — wrote `uom_po_id` which Odoo 19 removed; dropped. (FX-1)
- **Stored XSS in low-stock cron's Discuss inbox** — product names now `escape()`d. (FX-3)
- **BACKUP_PASSPHRASE silently truncated by cmd.exe** at `& | < > ^ %` — switched to `--passphrase-file` (file, not shell). (FX-3)
- **`/wms/health` open by default** — `install-native.ps1` now auto-generates a 32-char token into `wms_reports.health_token`. (FX-3)
- **`.env` placeholder deny-list** — install fails with clear instruction if `admin` / `odoo_local_dev_pw` / `changeme_*` remain. (FX-3)
- **`wms_is_scan_issue` ORM-immutable** on done WMS pickings; clearing it would silently rewrite Consumption Value + daily cap. (FX-3)
- **Capacity guard row-lock** under concurrent writers. (FX-3)
- **Scan Issue + Scan Receipt idempotency moved INSIDE the row lock** — `SELECT FOR UPDATE` the wizard row before reading `picking_id`. (FX-4)
- **Onboard wizard double-click guard** — `_do_onboard` raises on re-entry instead of silently creating duplicate products with different auto-SKUs. (FX-4)

### Documentation (FX-5)
- This CHANGELOG refreshed (was frozen at v19.0.10). Each FPAT-batch summary above tracks the Critical/High closures with file refs in the commit messages.
- Menu paths corrected in INSTALLATION-GUIDE / ADMIN-QUICK-START / STOREKEEPER-QUICK-START: "Reports → Where is it?" → "Operations → Find / Where is it?".
- README "What's in the box" expanded to mention v11-v15 features (Dashboard, Smart Find, value reports, Self-Diagnostics, Undo, capacity, off-site backup).

## [v19.0.11.0.0..v19.0.15.0.0] — 2026-06-06 — Maturity Sprint

Five releases over one day shipping the WMS Real-World Maturity Expansion
Sprint (Executive Dashboard, Undo + opt-in Capacity enforcement, Cost/Value
reports + Lifecycle, In-app alerts + email + photos, Smart Find /wms/find)
plus Round 2 (money value on risk reports, Issued-for classification, alert
hardening with inbox delivery, bulk-onboard pre-validation). All releases
detailed in commit history and PR descriptions; CHANGELOG consolidated here
to recover from the v11..v15 gap.

## [v19.0.10.0.0] — 2026-06-04 — Production remediation (High + Medium)

Completes the pre-production enterprise-audit remediation on top of
`v19.0.9.0.0`. All High and Medium findings are fixed-with-tests or explicitly
justified; CI green at every step. **This is the production release.**

### High — fixed + tested
- Audit-accept **delta reconcile** + product `FOR UPDATE` lock (no stale-snapshot overwrite).
- Damage/Repair **abort-on-failed-reservation** + shared validate helper (no phantom deduction; TOCTOU-safe).
- **UoM-aware daily cap** via an immutable flag (no fragile origin-string match).
- Forecast engine: history-based consumable flag, batched signal prefetch, bounded history retention.
- Optional **token gate** on `/wms/health`; restore-drill `PGPASSWORD` safety.
- Audit-triplet change tracking; polyomino compartment rendering; Beginner-Mode scrap confirmation.
- Scripted service-mode **upgrade path** + supervised AI-worker service.

### Medium — fixed + tested or justified
- HTML-safety (expiry-digest `Markup`, backup stderr XSS escape); scrap row-lock.
- **Capability-group ACLs** on scan/damage/audit (closes the RPC bypass); controller group-gating; DB-manager destructive-route lockdown.
- Cycle-count freshness; audit no-quant reconcile; reorder-summary join; forecast-history index.
- Repair lifecycle tests; dead-code removal; damage note-required UX.

### Low — addressed or justified
- Lower-impact performance / i18n / cleanup items fixed where clean, otherwise
  explicitly justified at the trust's data scale (see `docs/REMEDIATION-CLOSURE.md`).

### Production cleanup
- Production DB verified clean: **0 demo/test data, demo never loaded**; the
  `TestKeeperAlpha` test identity removed across users/partners/storekeepers;
  obsolete sample artifacts cleared.

### Quality
- **11 new automated test files (+~515 lines).** Scores — Production 92 ·
  Security 90 · Operational 93 · Training 90 · Maintainability 88. **GO.**
- Full closure matrix: `docs/REMEDIATION-CLOSURE.md`.

## [v19.0.9.0.0] — 2026-06-04 — Critical production blockers resolved

First hardening release from the audit. Closes all **8 Critical** (go-live) findings.

### Critical — fixed + tested
- **Single FEFO/FIFO removal engine** (strict per-product pooling; no name-based sibling widening).
- **Quantity integrity** `CHECK` constraints (damage / repair / receipt / audit).
- **SKU uniqueness** (`UNIQUE(default_code)` + de-dup migration).
- **Cross-table NULL-safe barcode uniqueness** (product / location / lot).
- **Guided-tour link stability** (resolved by XML id at install).
- **Reproducible backup + weekly restore-drill** scheduled tasks.
- **`/wms/health` probes reality** (live DB + backup-file presence + disk-free).

## [v19.0.1.0.0 – v19.0.8.0.0] — Foundational build & training academy

Initial build of the WMS and its enablement assets:

- **7 Odoo 19 addons** — `wms_location` (Rack → Compartment → Slot, polyomino
  shapes), `wms_fifo`, `wms_barcode` (scan receive/issue, thermal 4×1 labels),
  `wms_repair_damage`, `wms_ai_forecast` (offline Holt-Winters/SES), `wms_reports`
  (SQL-view dashboards + observability), `wms_training`.
- **Native Windows deployment** (NSSM `Odoo-WMS` service; Docker removed).
- **Two-role security model** (Admin + Store Keeper) with per-keeper capabilities.
- **Training & Visual Academy** — in-app searchable Help Center, role-based
  guided tours, SOPs, annotated SVG screen-maps, workflow diagrams, a
  beginner-mode toggle, and a video-production tracker
  (`addons/wms_training/`, `docs/training/`).

[v19.0.10.0.0]: https://github.com/udhay8005/Inventory-management/releases/tag/v19.0.10.0.0
[v19.0.9.0.0]: https://github.com/udhay8005/Inventory-management/releases/tag/v19.0.9.0.0
