# Go-Live Validation & Evidence Sheet

**Dakshin Vrindavan Gaushala WMS** · Baseline: **v19.0.37.0.0** · Status: **development frozen — operational validation in progress**

> Run every step on the **actual warehouse PC** (the live `wms` server). Record the
> real result, attach a screenshot/photo where useful, and note any issue. The
> system is **Production-Certified only when the 🔴 Critical rows all PASS** (see
> §4). Development stays frozen until then; the findings here become the P4/P5
> roadmap.

Tester: ________________  Date: ____________  Build deployed: ____________

---

## 1. Deploy (one command brings v31 → v37 to the live box)

```powershell
cd D:\Udhay\projects\Inventory_mngt
git pull
scripts\upgrade-service.ps1
```
Additive `-u` (runs the PRD back-fill on existing products). The `<string>:NN
Unexpected indentation` lines in the output are harmless docutils RST warnings, not
errors. Confirm the service ends **Running** and the app serves on `:8069`.

---

## 2. Evidence table (fill PASS/FAIL · screenshot Y/N · notes)

| # | Test area | Result | Shot | Notes |
|---|---|---|---|---|
| 1 | Deploy v37 (service Running, no upgrade error) | ☐ | ☐ | |
| 2 | Product Master — create real medicine/feed/tool/consumable | ☐ | ☐ | |
| 3 | SKU generation (see expected values below) | ☐ | ☐ | |
| 4 | PRD code + barcode generated on each | ☐ | ☐ | |
| 5 | Duplicate blocking (re-create same identity → blocked) | ☐ | ☐ | |
| 6 | Receipt flow | ☐ | ☐ | |
| 7 | Putaway | ☐ | ☐ | |
| 8 | Issue flow | ☐ | ☐ | |
| 9 | Return flow | ☐ | ☐ | |
| 10 | Damage flow | ☐ | ☐ | |
| 11 | Repair flow + re-issue | ☐ | ☐ | |
| 12 | Product search (name / SKU / barcode) | ☐ | ☐ | |
| 13 | TSC TE244 — single product label | ☐ | ☐ | |
| 14 | TSC TE244 — multiple labels | ☐ | ☐ | |
| 15 | Rack label | ☐ | ☐ | |
| 16 | Slot label | ☐ | ☐ | |
| 17 | Reprint label | ☐ | ☐ | |
| 18 | Barcode scan-back (scanner reads the printed label) | ☐ | ☐ | |
| 19 | Back Up Now — PostgreSQL dump + filestore + GPG + SHA256 | ☐ | ☐ | |
| 20 | Google Drive upload *(only after OAuth — see §3)* | ☐ | ☐ | |
| 21 | Restore drill into a TEST DB (not `wms`) | ☐ | ☐ | |
| 22 | Storekeeper login + daily operations | ☐ | ☐ | |
| 23 | Storekeeper denied Config/Settings/Technical | ☐ | ☐ | |
| 24 | Company branding (name + logo set) | ☐ | ☐ | |
| 25 | Demo data removed (no REF0001–10, no demo user) | ☐ | ☐ | |

**Expected SKUs for row 3** (create the masters first, or via the wizard's inline
"Create and edit"): Brand `ABC`/`Bosch`, Family `Cattle Feed`/`Drill`, Form `Cordless`.
```
Paracetamol / Cipla / Tablet / 500mg / 10  → MED-PARA-CIP-TAB-500MG-10
Premium Cattle Feed / ABC / Pellet / 50kg  → FEED-CATFD-ABC-PREM-PEL-50KG
Bosch Drill / Bosch / Cordless / 18V       → TOOL-DRILL-BOSCH-CORD-18V
```
Print darkness/size: 100×25 mm Gap stock, 203 dpi, print at Actual size (see
`docs/LABEL-PRINTING.md` / `docs/DIRECT-PRINTING.md`).

---

## 3. Backup / restore specifics

- **Back Up Now**: WMS → *Back Up Now*. Produces a local GPG-AES256 archive +
  SHA256. **Google-Drive upload is inert until the one-time OAuth is done** —
  `scripts\setup-gdrive-auth.ps1`, then `gdrive-test.ps1` (see
  `docs/22-gdrive-backup.md`). Mark row 20 N/A if you haven't set up Drive yet.
- **Restore drill** into a throwaway DB, never the live one:
  `scripts\restore-drill.ps1` (or `gdrive-restore.ps1 -List` then restore). The prod
  guard requires **both** `-Force` and `-ConfirmTarget wms` to touch the live DB, so
  a test-DB restore is safe by default. Verify products / stock / users / reports /
  attachments came back. See `docs/18-restore-drill.md`.

---

## 4. What blocks production

**🔴 Critical — STOP go-live if any fail:**
- Printer cannot print readable labels
- Barcode does not scan reliably
- Backup fails
- Restore drill fails
- Stock movement corrupts inventory
- Storekeeper cannot perform daily operations

**🟠 Fix soon (does NOT block go-live):** label layout, long-SKU readability, search
usability, report improvements. → these become **P5**.

**🟢 Future enhancements:** **P4** catalog governance (merge Families/Brands/Forms,
duplicate detection, legacy classification, Product-Master health dashboard); **P5**
UX. → only after live feedback.

---

## 5. Certification

When **Deploy + Printer + Backup + Restore all PASS** and a **storekeeper completes a
full day's workflow**, mark:

> ☐ **✅ Production-Certified for Warehouse Operations** — certified by: __________ on __________

At that point core inventory logic is frozen; only improvements driven by real
warehouse feedback proceed (P4, then P5).

---

## 6. Findings log (becomes the P4/P5 roadmap)

| # | Severity (🔴/🟠/🟢) | Finding | Where | Suggested fix |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
