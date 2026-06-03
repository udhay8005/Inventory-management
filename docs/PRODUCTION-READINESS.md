# Production Readiness Sign-off

**System:** WMS — Dakshin Vrindavan cow-care trust (internal warehouse management)
**Date:** 2026-06-02
**Release:** `v19.0.5.0.0` (production cleanup + hardening)
**Platform:** Odoo 19 CE · PostgreSQL (native Windows) · single-PC internal install
**Operating model:** the trust **buys and consumes** inventory (feed, medicine, ghee for pooja, tools). Nothing is ever sold — there is no sales/customer surface.

> Legend: ✅ done & verified · 🟡 action required by operator · ⬜ not applicable

---

## 1. Demo data removal (database) — ✅

All demo/test transactional data was wiped from the live `wms` database; production structure and assets were preserved.

| Removed | Kept |
| --- | --- |
| Demo products & test inventory | Warehouse structure — **59 locations** (Zones / Racks / Compartments / Slots) |
| Test stock moves / move lines / quants | Users (`admin`, `storekeeper`) |
| Test receipts / issues / returns (pickings) | Storekeeper master records (**5**) |
| Demo damages, repairs | Training Library (**94 articles**) |
| Demo inventory audits + lines | Help Center, Guided Tours, Visual Academy |
| Demo forecasts + history | Permissions / security groups |
| Demo carton aliases | Reports & Observability |

- SKU sequences reset → first real item will be `TOOL-00001` / `MED-00001` / etc. (18 sequences reset to `number_next = 1`).
- Verified post-wipe: products `0`, locations `59`, training articles `94`, active users `2`.
- Safety net: restore-verified backup `wms-20260602-160701.dump.gpg` taken before the wipe.

## 2. Demo scaffolding code removal — ✅

Removed and verified absent from a fresh install (CI green):

- `wms_barcode/wizards/wms_demo_seeder.py` (model `wms.demo.seeder`)
- `wms_demo_seeder_views.xml` (Demo Seeder wizard + **menu** + **action**)
- Demo Seeder **security** row (`ir.model.access.csv`)
- `wms_location/demo/demo.xml` + the `"demo": [...]` manifest block
- Demo-data scripts (`wipe-demo-data.ps1`, `_wipe_demo_data.py/.sql`, `reset-sku-sequences.sql`)
- Git-ignored dev leftovers `.runtime/seed.py`, `.runtime/setup.py`

Code search confirms **no** `seed_demo_data()` / `create_demo_inventory()` / `load_demo_products()` or any demo-generation logic remains anywhere in `addons/`. DB confirms the Demo Seeder menu/action/model are gone (`0` records).

## 3. Production validation — ✅

Backed by the security-group structure (single-assignment roles) + reachability counts + prior live smoke tests.

**Permission wiring**
- **Manager** (admin) implies → Administrator + all 5 capability groups + Store Keeper ✅
- **storekeeper** holds all 6 operational groups (Receipt, Return, Issue, Damage, Audit, Aliases) ✅
- Reachability: **46** WMS menus · **36** window-actions · **41** model-ACL rows ✅

| Admin | Storekeeper | Read-only |
| --- | --- | --- |
| ✅ Login | ✅ Scan Receipt | ✅ Reports |
| ✅ Warehouse Setup | ✅ Putaway | ✅ Inventory Search |
| ✅ Reports | ✅ FIFO Issue | ✅ Help Center |
| ✅ Users | ✅ Returns | |
| ✅ Backup Audit | ✅ Damage | |
| ✅ Health Monitoring | ✅ Inventory Audit | |
| ✅ Training Center | ✅ Guided Tour | |

## 4. Security hardening — ✅ (1 operator action)

| Item | Status | Evidence |
| --- | --- | --- |
| `list_db = False` | ✅ | DB-manager UI disabled in `config/odoo.native.conf` |
| Strong master password | ✅ | `admin_passwd` = 32-hex random (not a placeholder) |
| No placeholder secrets | ✅ | `.env` audited: `DB_PASSWORD`/`ODOO_ADMIN_PASSWD`/`BACKUP_PASSPHRASE` all real |
| No demo accounts (active) | ✅ | Only `admin` + `storekeeper` are active & can log in |
| No usable test credentials | ✅ | All non-production accounts are **inactive** (cannot authenticate) |
| Strong unique user passwords | 🟡 | **Run `scripts/set-user-passwords.ps1`** (see §9) |

**Notes / flags**

- `ODOO_USER` / `ODOO_USER_PASSWORD` in `.env` read as placeholders **by design** — they belong to the *optional* AI-forecast service account (`scripts/start-ai-worker.ps1`), which **refuses to start on placeholder values**. The AI worker stays off until you provision a real service account; this is not a live credential.
- **Two inactive accounts** exist and **cannot log in**:
  - `testkeeper_alpha` — a QA test account (recommend you delete it: *Settings → Users*, or leave archived).
  - `krishnadas` — a real-looking name; **confirm whether this is a real staffer**. Reactivate (and set a password) if real, otherwise delete.
  - These were **not hard-deleted** — permanent user deletion is left to you, and archiving preserves audit-trail integrity.

## 5. Backup & recovery — ✅

| Item | Status | Evidence |
| --- | --- | --- |
| Scheduled backups enabled | ✅ | Windows task **`WMS Daily Backup`** — daily 13:00, missed-run catch-up, runs `backup-native.ps1` |
| Encrypted backups | ✅ | pg_dump piped straight into GPG-AES256 (`BACKUP_PASSPHRASE`); plaintext never hits disk |
| Restore drill passes | ✅ | Full restore validated; health recovered CRITICAL → HEALTHY |
| Backup audit records | ✅ | `wms_backup_audit` — 4 records, latest today |
| Retention | ✅ | Old encrypted snapshots retained as safety net |

## 6. Monitoring & observability — ✅

| Item | Status | Evidence |
| --- | --- | --- |
| Health endpoint | ✅ | `GET /wms/health` → HTTP 200, `HEALTHY` |
| Backup-freshness checks | ✅ | Daily cron `_cron_check_backup_freshness` escalates stale backups |
| Restore-drill checks | ✅ | DR drill validated end-to-end |
| Event-log monitoring | ✅ | Drill + health events recorded; Windows Event Log target available |

## 7. Training assets (production, not demo) — ✅ kept

- **94** Help Center articles
- Role-based **Guided Tours** (first-login, storekeeper, admin, read-only) with deep links
- **Visual Academy** — SVG workflow diagrams + annotated screen-maps
- **12 SOPs** + narration scripts
- Video-upload placeholders (ready for real recordings)

## 8. Release process

| # | Step | Status |
| --- | --- | --- |
| 1 | Clean demo data | ✅ |
| 2 | Remove demo scaffolding code | ✅ |
| 3 | Upgrade modules | ✅ (`wms_barcode` 19.0.1.10.0, `wms_location` 19.0.3.1.0) |
| 4 | Run full CI | ✅ (cleanup `3c5dce7`: all 5 jobs green) |
| 5 | Admin smoke test | ✅ |
| 6 | Storekeeper smoke test | ✅ |
| 7 | Verify restore drill | ✅ |
| 8 | Create release tag | ⏳ `v19.0.5.0.0` |
| 9 | Merge `test → main` | ⏳ |
| 10 | Deploy | ✅ live on prod `wms` (DB already cleaned) |

## 9. Operator action items 🟡

> **Recommended run mode:** install Odoo as an auto-starting service — `.\scripts\install-odoo-service.ps1` (auto-start on boot + restart on failure; see [RUN-AS-SERVICE.md](RUN-AS-SERVICE.md)). Without it, Odoo must be launched by hand and stops on reboot.

1. **Set strong unique passwords** — run once before go-live:
   ```powershell
   .\scripts\set-user-passwords.ps1 -Users "admin,storekeeper"
   ```
   The new passwords print **once** on your console (never stored, never sent anywhere). Record them in your password manager, then clear the terminal. Re-run with `-Users "<login>"` whenever you add a real user.
2. **Decide on the two inactive accounts** (`testkeeper_alpha`, `krishnadas`) — see §4.
3. **Begin operator onboarding** using the Training Library → *Start Here*.

## 10. Final production state

✅ Clean warehouse structure   ✅ Clean user accounts   ✅ No demo inventory
✅ No demo transactions   ✅ No demo seeding tools   ✅ Security hardened
✅ Observability enabled   ✅ DR verified   ✅ Training academy available
✅ Guided tours available   ✅ Visual learning available   ✅ CI green

**The project is production-ready for onboarding real inventory and real warehouse operations** once the operator action items in §9 are completed.
