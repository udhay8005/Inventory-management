# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) conventions with Odoo-style
semantic version tags (`v19.0.<release>`). Each entry maps to a published
[GitHub Release](https://github.com/udhay8005/Inventory-management/releases).

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
