# WMS — Admin Quick Start (≈15 minutes)

The **fast path** to a working system. For full detail, fixes, and verification
gates, see the **[Installation & Setup Guide](INSTALLATION-GUIDE.md)**.

> Run everything in an **Administrator PowerShell** (right-click → Run as
> administrator). Project root in examples: `D:\Udhay\projects\Inventory_mngt`.

---

## 1. Install (≈10 min, once)
```powershell
git clone https://github.com/udhay8005/Inventory-management.git Inventory_mngt
cd Inventory_mngt
copy .env.example .env        # edit: set a strong DB_PASSWORD and BACKUP_PASSPHRASE
scripts\install-native.ps1    # installs PostgreSQL + Python + Odoo + the wms DB
scripts\install-odoo-service.ps1   # run Odoo as the auto-starting Odoo-WMS service
```
Open **<http://localhost:8069>**, sign in `admin` / `admin`.
**Apps** → search `wms` → install in order:
`wms_location → wms_fifo → wms_barcode → wms_repair_damage → wms_ai_forecast → wms_reports → wms_training`.

**Secure it now:**
```powershell
scripts\set-user-passwords.ps1 -Users "admin,storekeeper"   # copy the printed passwords once
```

## 2. Create the warehouse
**WMS → Configuration**:
- **Zone Generator** → make a zone (e.g. `East`).
- **Rack Generator** → code `R01`, set shelves × columns × slots → builds rack +
  compartments + slots + barcodes automatically.
- **Floor Zone Generator** → flat areas `F-01…` (for pallets/sacks).

Check **WMS → Warehouse Map**.

## 3. Create users
- **WMS → Configuration → Store Keepers** → add the human names (Ramesh, Lakshmi…).
- **Settings → Users → New**:
  - Manager → group **WMS / Manager**.
  - Store Keeper → **WMS / Store Keeper** + the capabilities they need
    (`Scan Receipt + Scan Return`, `Scan Issue`, `File damage`, `Submit audits`).
  - Read-only → **WMS / Store Keeper** with **no** capability groups.

## 4. Create products
**WMS → Products → Onboard Product** — enter name, **Kind**, UoM, expiry (for
perishables). Optional columns for SKU, barcode, Category, UoM, and unit
cost let a paste-from-Excel batch carry existing labels and feed the value
reports. The wizard **pre-validates the whole batch** (duplicate SKU /
barcode / invalid slot / missing expiry on perishables) before writing
anything, so a row-50 typo can't leave 49 half-saved products behind. It
also assigns auto-SKUs + auto-barcodes where you leave them blank, then
prints the
**4×1 in thermal label**. Calibrate the printer's gap sensor first.

## 5. Receive inventory
**WMS → Scan Receipt** — pick the on-duty keeper + audit fields → scan product →
quantity → scan destination slot → **Validate**. Confirm via
**Operations → Find / Where is it?** (smart search page) or
**Reports → Where is product X?** (drill-down).

## 6. Backup
```powershell
scripts\install-backup-tasks.ps1   # daily backup + weekly restore drill (scheduled)
scripts\backup-native.ps1          # take one now
scripts\restore-drill.ps1          # prove the latest backup is recoverable
```
Verify: **<http://localhost:8069/wms/health>** → `HEALTHY` with a recent backup.

---

## ✅ Go-live (the short list)
```
□ Odoo-WMS service Running/Automatic     □ admin + keeper passwords rotated
□ /wms/health = HEALTHY                  □ warehouse + slots built (barcodes)
□ users + roster created                 □ a label prints and scans back
□ a test receipt lands in its slot       □ backup taken + restore drill passed
```
Everything ticked → you're live. Full reference & troubleshooting:
**[INSTALLATION-GUIDE.md](INSTALLATION-GUIDE.md)**.
