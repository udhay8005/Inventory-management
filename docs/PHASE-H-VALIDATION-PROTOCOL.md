# WMS Production Validation Protocol & Operator Evidence Checklist

**Phase H · Build `v19.0.38.0.0` · Role: Validation Manager**
**Target:** live deployment on the warehouse PC (Windows 11 · PostgreSQL · Odoo service `:8069` · TSC TE244 · barcode scanner · Google Drive backup)

> **Purpose.** Separate the tests a browser/automation can prove on its own from the
> tests that **only the physical warehouse can prove**, and define the **exact
> evidence** required before any line may be marked **PASS**. This document is the
> certification record: fill it in, attach the evidence, and return it.

---

## How to use this document — the rules of evidence

1. **PASS is earned, not assumed.** A line may be marked `PASS` **only** when the
   required evidence (named per test below) is attached. No evidence → not PASS.
2. **Allowed marks:** `PASS` · `FAIL` · `NOT VERIFIED` · `CONFUSING` · `IMPROVEMENT REQUIRED`.
3. **Every hardware/physical test is tagged `🔴 REQUIRES HUMAN EVIDENCE`.** Automation
   (including any AI assistant) must **never** mark these PASS — it has no printer,
   scanner, Drive account, second machine, or human tester. It can only define them.
4. **Code/tests/CI are not evidence of PASS.** They show the code *can* work; this
   protocol proves it *does* work in the warehouse.
5. **Re-confirm on the live box.** Browser tests pre-checked on a scratch copy use the
   same code, but the certifying run must be on the **live `:8069`** instance after
   deploy.

---

## 0. Current readiness snapshot (entering Phase H)

| Dimension | State | Basis |
|---|---|---|
| Code readiness | **High** | 436 automated tests green; CI green; adversarial review GO; v38 hardening shipped. |
| Browser workflow readiness (catalogue/identity) | **High** | Product Master, structured SKU, PRD, freeze, duplicate-block, reports, Help Center verified live in a browser. |
| Hardware validation (printer/scanner) | **Not yet evidenced** | No evidence collected. |
| Backup / Restore / DR | **Not yet evidenced** | No evidence collected. |
| Storekeeper role (on a real keeper account) | **Not yet evidenced** | No provisioned keeper exercised. |
| **Production certification** | **PENDING** | Blocked on printer + backup + restore + storekeeper evidence. |

**Bottleneck is no longer development — it is real-world evidence collection from the floor.**

---

## 1. Test ledger — classification

| ID | Test | Class | Who proves it |
|---|---|---|---|
| A1 | Create product (guided) + SKU/PRD/EAN generation | **A — Browser** | Admin in browser |
| A2 | Structured SKU composition + 4-variant distinctness | **A — Browser** | Admin in browser |
| A3 | Duplicate-identity blocked (no auto-suffix) | **A — Browser** | Admin in browser |
| A4 | Category-driven required-field enforcement | **A — Browser** | Admin in browser |
| A5 | Family / Brand search facets | **A — Browser** | Admin in browser |
| A6 | Reports render (Dashboard, Movement, Dead/Low stock) | **A — Browser** | Admin in browser |
| A7 | Help Center articles load & open | **A — Browser** | Admin in browser |
| B1 | TSC TE244 printing (single/multi/rack/slot/location/reprint) + scan-back | **🔴 B — Operator** | Warehouse operator |
| B2 | Back Up Now → file + encryption + SHA-256 + Drive | **🔴 B — Operator** | Warehouse operator |
| B3 | Restore drill into `wms_restore_test` | **🔴 B — Operator** | Warehouse operator |
| B4 | Storekeeper role — allowed/denied + direct-URL attempt | **🔴 B — Operator** | Operator (real keeper acct) |
| B5 | Full inventory chain (receive→putaway→find→issue→return→damage→repair→re-issue) | **🔴 B — Operator** | Operator + scanner |
| B6 | Training — untrained person, Help Center only | **🔴 B — Operator** | A real new person |
| B7 | Disaster recovery — rebuild on a fresh machine | **🔴 B — Operator** | Operator + 2nd machine |
| B8 | Performance on the live PC | **🔴 B — Operator** | Operator with a stopwatch |

---

## 2. Class A — Browser-verifiable (autonomous) tests

> These need no hardware. They were **pre-verified on a scratch copy of this exact
> code**; the certifying run is on the **live `:8069`** after deploy. Evidence = a
> screenshot of the named end state.

| ID | Procedure | Exact PASS evidence (screenshot of …) | Pre-check (scratch) |
|---|---|---|---|
| **A1** | WMS → Operations → *Create Product (guided)*; name it, pick a category, Create. | The saved product form titled `[SKU] Name`, with a `PRD-NNNNNN` on the WMS Classification tab. | ✅ `[MED-ANALG-CIP-TAB-500MG-10]`, `PRD-000141` |
| **A2** | Create the 4 Paracetamol variants in Test Group 2 (Cipla 500mg, Cipla 650mg, Sun 500mg, Syrup 60ml). | The Products list showing **4 distinct SKUs** (no two equal). | ⏳ to run on live |
| **A3** | Re-create an identity that already exists. | The **"Invalid Operation / SKU already exists"** dialog naming the existing product + PRD. | ✅ blocked, named existing PRD-000141 |
| **A4** | In the guided wizard pick a Medicine category, leave Family/Brand/Form/Strength blank, click Create. | The **"Missing required fields"** block (creation refused). | ✅ blocked |
| **A5** | Products list → filter/group by Family, then by Brand. | The list filtered to the chosen Family and Brand. | ⏳ to run on live |
| **A6** | WMS → Reports → open Dashboard, Movement history, Dead stock, Low stock. | Each report rendering (data or a clear empty-state). | ✅ Movement history rendered |
| **A7** | Help & Training → Getting Started; open one article. | The article list (role-tagged) and one opened article body. | ✅ 9 articles listed |

**Class A acceptance:** A1–A7 each show the named end state on the **live** box.

---

## 3. Class B — Operator-verification tests · 🔴 REQUIRES HUMAN EVIDENCE

> An automated assistant **cannot** mark any B-test PASS. Each needs a human + the
> physical asset. Capture the evidence named in **bold**.

### B1 · TSC TE244 Printer & scan-back 🔴 REQUIRES HUMAN EVIDENCE
**Do:** From the live app, print: (1) a single product label, (2) multiple product
labels, (3) a Rack label, (4) a Slot label, (5) a Location label, (6) a **reprint** of
an existing label. Then **scan every printed label** with the barcode scanner.
**Required evidence:**
- **Photo** of each printed label type (6 photos), readable, ideally beside a ruler so
  alignment within the die-cut is visible.
- **Photo/close-up** proving **SKU**, **PRD code**, and **barcode** are all legible at
  arm's length.
- **Screenshot** of the app after each scan showing the scanner resolved the label to
  the **correct product/location** (e.g. the Find / Scan field populated correctly).
- The **darkness / speed** values used (note them).
**Acceptance (all must hold):** every barcode scans on the **first** try; text legible
without magnification; label aligned within the 100×25 mm die-cut; reprint matches the
original. Any scan miss → `FAIL`.

### B2 · Backup (Back Up Now) 🔴 REQUIRES HUMAN EVIDENCE
**Do:** Run **Back Up Now** in the app (or `scripts\backup-native.ps1`). If Google
Drive is configured, confirm the upload; if not, mark Drive `NOT VERIFIED`.
**Required evidence:**
- **Screenshot** of the in-app success notification (or the backup script's final
  output).
- **Directory listing** of `backups\` showing the new `wms_<stamp>.dump.gpg`, its
  filestore archive, and a `.sha256` file (e.g. `Get-ChildItem .\backups\ | Sort LastWriteTime -Desc | Select -First 5`).
- **SHA-256 verification** output showing the recomputed hash **matches** the recorded
  `.sha256` (proves the artifact isn't corrupt).
- **Encryption proof:** the file is `.gpg` and `pg_restore --list` on the *un*decrypted
  file fails / the GPG header is present (i.e. it is genuinely encrypted, not plaintext).
- **Google Drive (if configured):** **screenshot** of the Drive folder showing a
  `YYYY-MM-DD` folder containing `wms_YYYYMMDD_HHMMSS…` and Drive's reported checksum.
- **Screenshot** of `http://localhost:8069/wms/health` showing a small `last_backup_age_hours`.
**Acceptance:** file exists; SHA matches; file is encrypted; (Drive on) the set appears
in Drive with matching checksum.

### B3 · Restore drill 🔴 REQUIRES HUMAN EVIDENCE
**Do:** Restore the latest backup into a **throwaway** DB named `wms_restore_test`
(never the live `wms`):
`scripts\restore-native.ps1 -BackupFile backups\wms-<stamp>.dump.gpg -DbName wms_restore_test -Force`
then serve/inspect that DB.
**Required evidence (screenshots from the *restored* DB):**
- **Products** count and one product's SKU + **PRD code** matching the original.
- **Inventory / stock** on-hand for a known product matching the live figure.
- **Users** list present (e.g. `SELECT count(*) FROM res_users` > 0, or the Users list).
- **Attachments** — open one attachment/photo and confirm it renders.
- **Reports** — one report renders with the restored data.
- **Product Master data** — Families/Brands/Forms present.
- Restore command output showing **no errors**.
**Acceptance:** all six categories restore intact; no corruption; counts reconcile with
production. Drop `wms_restore_test` afterwards.

### B4 · Storekeeper role 🔴 REQUIRES HUMAN EVIDENCE
**Do:** On a **real storekeeper account** (created via Settings→Users with the **WMS
Store Keeper** role + password), log in as the keeper.
**Required evidence:**
- **Screenshot** showing the keeper **can** reach: Receipt, Issue, Return, Damage,
  Repair, Inventory Audit, Reports.
- **Screenshot** showing the keeper **cannot** see: Settings, Technical, Security,
  Product-Master configuration, User Management.
- **Screenshot of a direct-URL attempt** to a forbidden page (e.g. paste the Settings /
  Users URL) returning **"Access Denied"** (proves the gate isn't just hidden menus).
**Acceptance:** every Allowed item works; every Denied item is blocked **including the
direct-URL attempt**. Any forbidden page reachable → `FAIL`.

### B5 · Full inventory chain 🔴 REQUIRES HUMAN EVIDENCE
**Do (with the scanner):** Receive → Putaway → Find → Issue → Return → Damage → Repair →
Re-issue, on a real product into a real slot.
**Required evidence:** **screenshot** of On-Hand quantity after each step (it should move
correctly), the **Movement history** report listing every step, and the **audit trail**
on one picking showing who/when. **Acceptance:** quantity is accurate at every step;
every movement is logged; barcode-driven steps resolve the right product.

### B6 · Training (untrained person) 🔴 REQUIRES HUMAN EVIDENCE
**Do:** A person who has never used the system, **Help Center only**, no dev/admin help,
attempts: Create Product, Receive, Issue, Find, Print Label.
**Required evidence:** for each task — completed (Y/N), **time taken**, and the **exact
article/step** where they got stuck. **Acceptance:** all five completed unaided; record
every confusion point as `IMPROVEMENT REQUIRED`.

### B7 · Disaster recovery 🔴 REQUIRES HUMAN EVIDENCE
**Do:** Assume the PC is destroyed. On a **fresh machine, using `docs/INSTALLATION-GUIDE.md`
+ `docs/18-restore-drill.md` only**: install → restore DB → restore filestore → configure
the service → verify the app serves and data is intact.
**Required evidence:** note any **missing or confusing step** in the docs, and the total
**recovery time**. **Acceptance:** a competent operator reaches a working, data-complete
system using docs alone.

### B8 · Performance (live PC) 🔴 REQUIRES HUMAN EVIDENCE
**Do:** With a stopwatch on the live PC, measure: login, product search, receipt, issue,
report load, dashboard load. **Required evidence:** the six timings. **Acceptance:**
typical actions feel responsive (subjective, ≲2–3 s for routine screens); note any slow
area.

---

## 4. Evidence specification catalog (quick reference)

| Test | Minimum artifacts to attach |
|---|---|
| B1 Printer | 6 label photos · 1 legibility close-up · scan-back screenshots · darkness/speed noted |
| B2 Backup | success screenshot · `backups\` listing · SHA-match output · encryption proof · Drive screenshot (if on) · health screenshot |
| B3 Restore | restore output (no errors) · 6 screenshots (products/stock/users/attachment/report/masters) |
| B4 Storekeeper | allowed-menu screenshot · denied-menu screenshot · denied-URL "Access Denied" screenshot |
| B5 Inventory | per-step On-Hand screenshots · Movement-history screenshot · audit-trail screenshot |
| B6 Training | per-task done/time/stuck-point |
| B7 DR | doc-gap notes · recovery time |
| B8 Performance | 6 timings |

---

## 5. Operator fill-in checklist (complete, attach evidence, return)

Operator: ______________________  Date: ____________  Build: `v19.0.38.0.0`

**Class A — browser (re-confirm on live):**
- [ ] A1 Create product → `PASS / FAIL / NOT VERIFIED` — evidence attached: ☐
- [ ] A2 Four distinct SKUs → `____` — evidence: ☐
- [ ] A3 Duplicate blocked → `____` — evidence: ☐
- [ ] A4 Required fields enforced → `____` — evidence: ☐
- [ ] A5 Family/Brand search → `____` — evidence: ☐
- [ ] A6 Reports render → `____` — evidence: ☐
- [ ] A7 Help Center loads → `____` — evidence: ☐

**Class B — operator/hardware (🔴 evidence mandatory):**
- [ ] B1 Printer + scan-back → `PASS / FAIL / NOT VERIFIED` — evidence attached: ☐
- [ ] B2 Backup (+Drive) → `____` — evidence: ☐
- [ ] B3 Restore drill → `____` — evidence: ☐
- [ ] B4 Storekeeper role (+URL) → `____` — evidence: ☐
- [ ] B5 Full inventory chain → `____` — evidence: ☐
- [ ] B6 Training (new person) → `____` — evidence: ☐
- [ ] B7 Disaster recovery → `____` — evidence: ☐
- [ ] B8 Performance → `____` — evidence: ☐

Findings / improvements: ______________________________________________

---

## 6. Final Go / No-Go criteria

**✅ PRODUCTION CERTIFIED — only if ALL of the following are `PASS` *with attached evidence*:**
- B1 Printer (labels scan + legible) · B2 Backup (file + SHA + encryption; Drive if used) ·
  B3 Restore (all six categories intact) · B4 Storekeeper (allowed work + denied incl. URL) ·
  B5 Inventory chain (quantities accurate, movements logged) ·
- A1–A7 confirmed on the live box · no open `FAIL` · no open Critical finding.

**❌ NOT READY — if any of:**
- Any B1–B5 test is `FAIL` **or** `NOT VERIFIED` (missing evidence) ·
- Any forbidden page reachable by a storekeeper · a label that won't scan · a backup
  that won't restore · stock quantities that don't reconcile.

> B6 (training) and B8 (performance) are **quality gates, not hard blockers** — record
> them as `IMPROVEMENT REQUIRED`; they shape post-go-live polish, not certification.

**Sign-off on certification:**
> ☐ **✅ PRODUCTION CERTIFIED** — by ______________ on ____________
> ☐ **❌ NOT READY** — blocking items: ______________________________
