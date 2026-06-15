# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) conventions with Odoo-style
semantic version tags (`v19.0.<release>`). Each entry maps to a published
[GitHub Release](https://github.com/udhay8005/Inventory-management/releases).

## [v19.0.25.0.0] — 2026-06-15 — Fix: WMS app landed on the Find page; honest Find quantities

Two fixes to the `/wms/find` quick-search feature. Manifest bump: `wms_reports`
**19.0.4.8.0 → 19.0.4.9.0** (view + controller only; applies on `-u`, no migration).

- **Clicking the WMS app opened the standalone Find page instead of a normal
  screen.** The `menu_wms_find` item sat at `sequence="1"` under Operations, and
  Odoo opens an app on its first leaf menu — Find is an `act_url` that jumps out
  of the backend to `/wms/find`, so the app "landed" there. Re-sequenced to **15**
  (after the daily scan trio) so the app now opens on **Slots** (the storage-map
  landing with its wayfinding empty-state). Find stays one tap away in Operations.
- **Find rounded measured quantities.** The product card formatted on-hand and
  per-slot quantities with `%.0f`, so a 2.5 L fluid or 1.5 kg feed showed as a
  whole number. Now formatted with a decimal-trimming helper (`2.5` stays `2.5`,
  `3.0` shows `3`) — correct for the trust's litre/kg stock. Audited the rest of
  the Find controller: the chip queries (low / expiring / dead / damaged / repair)
  all reference valid model states, barcode-alias fallback and the storage-only
  quant filter are correct — no other issues found.

## [v19.0.24.0.0] — 2026-06-15 — UX overhaul: wayfinding, plain language, grouped menus

A value-gated, low-risk usability pass so a non-technical keeper or manager can
read every screen at a glance and find any action fast. Every change is a label,
help text, empty-state, decoration, default, or menu sequence/grouping — no model
logic, security, or action rewiring. Each is independently view-smoke-testable and
revertible.

Manifest bumps: `wms_location` **19.0.3.17.0 → 19.0.3.18.0**, `wms_barcode`
**19.0.1.34.0 → 19.0.1.35.0**, `wms_repair_damage` **19.0.1.15.0 → 19.0.1.16.0**,
`wms_reports` **19.0.4.7.0 → 19.0.4.8.0**, `wms_training`
**19.0.1.11.0 → 19.0.1.12.0**. The view/menu changes apply on `-u`; the only
migration is a `wms_training` pre-migrate that refreshes the five noupdate help
articles whose menu-path wording changed (see below).

**Navigation & menus**
- **Daily verbs first.** The scan trio now sits at the very top of Operations —
  Scan Receipt, Scan Issue, Scan Return (seq 5/6/7) — above the browse screens
  (Slots, Floor Zones pushed to 30/32). The app opens on what keepers actually do.
- **Reports grouped into three plain-language folders** instead of a flat wall of
  20+ entries: **Find stock** (Warehouse Map, Where is product X?, Slot occupancy,
  Oldest stock, Tool/Spare fleet, Movement history), **Alerts & to-dos** (Low
  stock, Expiry, Returns due, Cycle Count Due, Dead stock, Reorder summary), and
  **Value & money** (Stock Value, Consumption Value, Product Lifecycle —
  manager-only). Store Keeper Activity is its own manager folder with the
  weekly/monthly/yearly summaries as real nested children (the old `-- ` dash-prefix
  indentation hack is gone).
- **Maintenance moved out of Reports.** Self-Diagnostics and Backup & DR Audit now
  live under Configuration where they belong.
- De-jargoned: **"Scan Issue (FIFO)" → "Scan Issue"** (menu, form, action,
  capability help); the issue button **"Plan FIFO" → "Check stock"**. Casing
  aligned so breadcrumbs match the tapped menu (Repair orders).

**First impressions & empty-states**
- The landing **Slots** screen is now wayfinding: "This is your storage map…" with
  pointers to Scan Receipt / Scan Issue and Help & Training.
- Friendly empty-states added across the previously blank screens — Racks,
  Compartments, Zones, Floor Zones, Damages, Repair orders, Issue Approvals, and
  the report screens (Reorder summary, Oldest stock, Slot occupancy, Where is
  product X?, Movement history).

**Daily wizards clarified**
- **Scan Issue:** plain field labels (Quantity, Scan here), plain plan columns
  (Slot, Arrived, Expires, On shelf, Will take), a clear short-stock hint instead
  of a dead-looking form when stock is insufficient, the noisy "Short Qty: 0.00"
  hidden on healthy plans, and `* required` / `(optional)` markers on the audit
  panel. The banner explains oldest-first in words and points to Help.
- **Scan Receipt:** the quality-check box is now visibly `* required` with a hint;
  a mode-aware commit button ("Validate & Print" vs "Validate Return"); banner
  notes that each scan adds 1 and the Qty cell is editable for bulk.

**Reports polish**
- Plain column labels and sensible default ordering on Reorder summary, Oldest
  stock, Slot occupancy, Cycle Count Due, and Where is product X?; blank-vendor
  rows greyed on Reorder summary; a search view (almost-full / empty / group-by)
  added to Slot occupancy; the "Pick next?" flag rendered read-only.
- **Audit dead-end fixed:** the rejected state now shows in the status bar with a
  next-step alert, and the button is honestly labelled "Reject" (it does not
  re-open).

**Safety**
- **Scrap** on a repair order now asks for confirmation before writing the item off.

**Training kept in sync**
- Five in-app help articles had their step-by-step navigation updated to the
  renamed menus ("Scan Issue", "Repair orders"); the FIFO concept is still taught
  in prose. A `wms_training` pre-migration refreshes these noupdate articles on
  upgrade so existing installs match the UI.

## [v19.0.23.0.0] — 2026-06-15 — Honest diagrams + returns-due timezone fix

Finishes the FEFO-honesty work (the teaching diagrams) and fixes the minor
returns-due day-count timezone edge — the last two deferred items.

Manifest bumps: `wms_reports` **19.0.4.6.0 → 19.0.4.7.0** (SQL view recreated on
`-u`; no migration) and `wms_barcode` **19.0.1.33.0 → 19.0.1.34.0** (onboard
error-text fix below). The diagram SVGs are static assets (no version bump).

- **Teaching diagrams redrawn** to match the honest behaviour (both the `docs/`
  and `wms_training/static/img` copies):
  - `fifo-vs-fefo.svg` → two panels, **"At issue: FIFO"** (oldest in-date first,
    every product, no expiry-sort at the picker) vs **"Manage expiry: the Expiry
    Alerts report"** (flags soonest-to-expire; you rotate perishables).
  - `fifo-issue.svg` → the plan step now reads "FIFO — oldest in-date first,
    every item" (was "FIFO … / FEFO soonest-expiry").
  - `scan-issue.svg` → the banner now says FIFO pulls oldest first for every
    item; use Expiry Alerts to rotate. Diagram README captions updated.
- **Returns-due report timezone fix** — `days_overdue` / `state` are now computed
  against *today in the company timezone* instead of raw `CURRENT_DATE` (the UTC
  session date), so the count matches the trust's local calendar day. (Previously
  off by one in the hours around UTC midnight on a non-UTC / IST deployment.) The
  test is now timezone-deterministic.
- **Two last FIFO/FEFO code mislabels fixed** — the Onboard "expiry required"
  error said *"use the oldest stock first (FEFO)"* (oldest-first is FIFO); it now
  explains the expiry date powers the Expiry Alerts report. And the
  `EXPIRY_SENSITIVE_KINDS` code comment, which still described per-batch FEFO at
  the picker, now states that removal is FIFO (the expiry-sort branch collapses
  to FIFO in the single-template Scan Issue path) and rotation is via the report.

With this, the FEFO→FIFO alignment is complete end to end — behaviour, docs,
in-app help, diagrams, and the last user-facing/code strings.

## [v19.0.22.0.0] — 2026-06-15 — Docs & training accuracy (honest FIFO-at-issue)

Brings the documentation and in-app training in line with the v19.0.20.0.0
FEFO→FIFO behaviour change. The system pulls **oldest-arrived stock first
(FIFO) at every issue, for every product** (a single issue is one product, and
expiry is tracked per product, so there is nothing to expiry-sort at the
picker); perishables are rotated via the **Expiry Alerts report**. The training
previously taught "FEFO — earliest expiry first" at the picker, which no longer
happens.

Manifest bump: `wms_training` **19.0.1.10.0 → 19.0.1.11.0** (pre-migration).
Docs-only files have no version.

- **In-app help reframed** — 12 articles in `help_articles.xml` (incl. the
  dedicated `what-is-fefo`, `faq-fifo-vs-fefo`, `admin-path-stock-flow-fifo-fefo`,
  `safety-double-check-fefo-medicine`, and the Scan-Issue lessons) + the training
  index now teach FIFO-at-issue and point perishable rotation at the Expiry
  Alerts report. Slugs/xmlids preserved so links still resolve.
- **Migration** — `help_articles.xml` is `noupdate=1`, so a pre-migration
  deletes the 12 reframed articles and the corrected XML recreates them on `-u`
  (raw SQL; nothing has an FK to `wms.help.article`, so it's safe).
- **Docs reframed** — `03-fifo-issue.md` (worst offender: worked FEFO example +
  the removed banner quote), the other training SOPs, `00-training-map.md`,
  `STOREKEEPER-QUICK-START.md`, `08-security.md`, `INSTALLATION-GUIDE.md`,
  `21-training-system.md`.
- **Also fixed** — `06-reports.md`: Consumption Value is broken down **by
  Department** (the F1 field), not "by purpose / Issued for".
- **Still pending** — the 3 FIFO/FEFO teaching SVGs are captioned as conceptual
  (issue is FIFO); a visual redraw remains a follow-up.

## [v19.0.21.0.0] — 2026-06-14 — DR-catalog hardening, CI upgrade-path, multi-user UI certification

Closes the two follow-ups flagged in v19.0.20.0.0 and adds an automated
multi-user UI certification layer. Full suite **345 tests, 0 failures**.

Manifest bumps: `wms_reports` **19.0.4.5.0 → 19.0.4.6.0** (carries a data
migration — `migrations/19.0.4.6.0/`, idempotent + a no-op on the empty
production catalog) and `wms_location` **19.0.3.16.0 → 19.0.3.17.0** (the
barcode-gate below).

**Google-Drive DR-catalog hardening**
- The `wms.gdrive.backup` catalog can no longer accumulate duplicate
  disaster-recovery rows under concurrent backups: a migration de-duplicates
  any existing rows (newest-wins), then adds a partial-unique index on
  `set_stamp` and a unique index on `name`; the PowerShell writer
  (`gdrive-lib.ps1`) now uses an atomic `INSERT … ON CONFLICT` upsert.

**CI hardening**
- New **`odoo_upgrade`** job: installs the addons at the previous release tag,
  then `-u all` to HEAD — so a migration that would break the live upgrade is
  caught before it ships (PREV_TAG now `v19.0.20.0.0`).
- **Fail-on-skip** guard (no silently-skipped `wms_*` tests) and **pylint-odoo +
  flake8** promoted to hard gates.

**Multi-user UI certification (`wms_ui_cert`)**
- A per-role **menu smoke** drives every menu each role can see (Manager, every
  keeper-capability variant, Buyer, Repair Tech, plain user) and asserts each
  opens without error, with a non-vacuity guard and the visibility matrix
  (forbidden-for-baseline / capability-gated).
- A **controller route matrix** certifies the act_url gates per role over HTTP
  (dashboard manager-only; find/map/rack-grid keepers-not-outsiders; backup/
  restore refuse keepers).
- **Label render + paperformat** (both thermal labels carry name + barcode on
  the 100×25mm format; batch print) and the **Onboard → print** flow.
- **Role actions + a fix the cert caught**: certified the Buyer's
  forecast→draft-PO action; and **gated the bulk barcode-generate server action
  to Manage Catalog** — it sudo-wrote product barcodes and was previously
  runnable by any keeper from the product Action menu. Wired `wms_ui_cert` into
  the CI test tags.

## [v19.0.20.0.0] — 2026-06-14 — Deep-audit hardening (correctness, permissions, UX)

A full read-only audit of every addon drove this release. It fixes the few
things that genuinely mattered, tightens the real-world Admin-vs-Storekeeper
permission model, and removes daily friction for non-technical staff. The
production database was still empty (configured, not yet in daily use), so the
correctness fixes land before go-live. ~330 tests, 0 failures in CI.

Manifest bumps: `wms_ai_forecast` **→ 19.0.1.4.0**, `wms_barcode`
**→ 19.0.1.33.0**, `wms_location` **→ 19.0.3.16.0**, `wms_repair_damage`
**→ 19.0.1.15.0**, `wms_reports` **→ 19.0.4.5.0**. No new data migrations —
existing databases converge on the per-module `-u` upgrade (SQL report views
are recreated, ACLs/menus reloaded, the capability backfill re-runs). After
deploy, run the forecast cron once so reorder history retrains on real data.

**Correctness**
- **Forecast & low-stock alerts now see the trust's consumption (Critical).**
  The forecast engine only counted moves to customer/production locations, but
  every Scan Issue routes stock into the *internal* "Trust internal use" sink —
  so it observed zero outflow and reported every product "dead", silencing the
  AI buying recommendations and the daily out-of-stock alert. It now counts
  done Scan-Issue move-lines (the same signal the Consumption-Value report
  uses) and excludes the consumed-goods sink from on-hand. `wms_ai_forecast`
  now depends on `wms_barcode`.
- **24h daily-cap & min-life windows fixed for IST (High).** Both used
  server-local time against the UTC `create_date` column, shrinking the rolling
  window by the timezone offset and letting the abuse caps fail *open*. Now
  computed in UTC.
- **Reorder Summary no longer double-counts** a product across multiple
  vendors, and no longer drops variant-level suppliers (picks one preferred
  supplier per product before aggregating).
- **Oldest-Stock (FIFO age) report now includes floor-zone stock** (the INNER
  joins silently dropped every floor quant).
- **Floor-zone generator** no longer mints a duplicate barcode when two parent
  areas share a 4-character name prefix (was rolling back the whole batch).
- **Inventory-audit line populator** counts warehouse storage only, excluding
  the consumed-goods sink and Damage/Repair locations that bloated the count
  list with bogus variances.
- **Photo gate** now classifies by the UoM `relative_uom_id` chain: counted
  bundles (Pack of 6, Dozens) stay photo-free; only measured items
  (kg/Litre/Metre) require a photo.

**Permissions — real-world Admin vs Storekeeper**
- **Audit accept/reject are now Manager-only at the method layer** (the buttons
  were only hidden in the view, so a keeper could self-accept their own count
  over RPC and overwrite live stock).
- **Finalised records are frozen against keeper edits** (defence-in-depth): a
  submitted/reviewed/rejected audit and a confirmed damage can no longer be
  revised by a keeper over RPC; managers bypass, and the keeper's normal
  file→confirm / draft→submit flow and repair-order linking still work.
- **The upgrade backfill no longer re-grants "Manage Catalog"** to keepers
  (catalog/label editing is an Admin task) — it now matches the four-cap set
  the roster's Create-login action grants.
- **Raw Cycle Count (the quant editor) is now Manager-only**; keepers count
  through the reviewed Inventory-audit flow.
- **The Returns-due report is now keeper-visible** (read-only) — the people who
  do the returns can self-serve the due/overdue list.

**Usability**
- Scan Issue/Receipt **default the on-duty Store Keeper from the logged-in
  user** (no re-picking yourself every time; empty for the shared desk login).
- "Ordered by" on Scan Issue is **optional** (was forced free-text); the
  destination field is relabelled **"Used by / area"**.
- Held issues now raise a **systray To-Do activity on managers** (a reliable
  badge), cleared on approve/reject — not just a missable Discuss ping.

**Honesty**
- The Scan Issue banner no longer promises "FEFO: earliest expiry first": a
  single issue is one product (one template-level expiry), so removal is
  oldest-arrival-first (FIFO). Perishable rotation is surfaced by the
  Expiry-Alert report. The expiry sort engine is retained for any future
  cross-product caller.

**Deferred to focused follow-ups** (flagged, not forgotten): the Google-Drive
DR-catalog unique index + `ON CONFLICT` upsert (the feature isn't live yet);
CI hardening (an upgrade-path job, pylint-odoo as a hard gate, flake8 over the
migrations); and a broad docs sweep of stale FEFO wording across the training
material. **Update:** the first two shipped in **v19.0.21.0.0** (below); only
the docs sweep remains deferred.

## [v19.0.19.0.0] — 2026-06-14 — Gaushala issue controls (F1–F7)

Tightens the outgoing-issue flow for the trust's gaushala operation: every
Scan Issue now records *where* the stock went and *why*, the base unit follows
the product Kind, returnable items are chased when overdue, and risky issues
(too-soon re-requests, high value) route to a manager before any stock leaves.
A folded-in fix corrects the measured-item photo gate, and the 4×1 in thermal
label is hardened. Setup and operation: `docs/ISSUE-DIMENSIONS.md`,
`docs/UOM-BY-KIND.md`, `docs/RETURNABLE-ITEMS.md`, `docs/ISSUE-APPROVALS.md`,
and the updated `docs/LABEL-PRINTING.md`.

Manifest bumps: `wms_location` **→ 19.0.3.14.0**, `wms_barcode`
**→ 19.0.1.30.0**, `wms_reports` **→ 19.0.4.2.0**, and `wms_training`
**19.0.1.9.0 → 19.0.1.10.0** (training content + docs; carries a data
migration — see *Docs + training*). Existing databases converge via
per-module migrations; fresh installs read everything from XML + field
defaults.

### F1 — Issue dimensions (Department / Purpose / Animal)
- Every Scan Issue now captures a **Department** (required, defaults to
  *Other*), an optional **Purpose / reason**, and an optional **Animal / cow**,
  all stored on the resulting `stock.picking` alongside the unchanged audit
  triplet (**Taken by / Ordered by / Store Keeper**).
- New configurable masters under **WMS → Configuration** (manager-only):
  **Departments**, **Purposes**, **Animals**. A fresh install seeds 11
  departments (Gaushala / Cowshed, Veterinary Hospital, R&D / Panchgavya,
  Dairy, Fodder & Agriculture, Kitchen / Bhojanalaya, Maintenance,
  Construction / Project, Administration, Temple / Pooja, Other), a starter
  purpose list, and an empty animal register. Departments / purposes are
  **archived, not deleted**, so historical pickings stay readable.
- The **Consumption Value** report now splits by **Department**; the legacy
  *Issued for* grouping is retained as a secondary dimension.
- The legacy six-value **Issued for** tag is kept and **auto-derived from the
  department** on every new issue, so old reports and searches keep working;
  historical values are left untouched. Existing pickings are back-filled to a
  department via the legacy-code map (idempotent migration).

### F2 — Unit of Measure by Kind
- New products get the right base unit **from their Kind at onboarding**:
  **fluid → Litre**, **feed → kg**, **everything else → Units**. The onboard
  UoM column is now shown so an operator can override.
- **Medicine defaults to Units** (counted vials / strips), deliberately — a
  volume default would wrongly trip the measured-item photo gate.
- **pipe / rope / cable / cloth** default to Units but are switchable to
  **Metre** per product when stocked / issued by length (no special "length"
  Kind added).
- The UoM stays editable, and **existing products are never retrofitted** — no
  migration rewrites the unit on already-classified products.

### F3 — Returnable items + expected return + overdue alert + report
- Products can be marked **returnable** with an **expected-return period**,
  both **Kind-seeded** (tools / spares 14 days; textile / safety 7 days) and
  editable, with a global fallback (`wms_reports.default_return_days`,
  default 7).
- Issuing a returnable item stamps an **expected return date** on the picking
  (advisory — issuing is never blocked).
- A **daily cron** notifies managers (Discuss inbox, optional email) about
  overdue, not-yet-returned items; quiet when healthy; reversed issues are
  ignored.
- A new **Returns due / overdue** report under **WMS → Reports** lists
  everything outstanding (read-only for keepers and managers).
- **Scan Return** marks the matched issue returned, dropping it off the report
  and the alert (best-effort match by product + department; never silently
  reconciles a non-match).

### F4 + F5 — Issue approvals (min-life guard + high-value)
- **F4 min-life re-request guard**: products can carry a minimum re-request
  interval (`wms_min_life_days`; sanitation / textile / safety seeded 7 days;
  global fallback `wms_location.default_min_life_days`). The **same department**
  re-requesting the **same product** inside that window must enter a reason and
  get manager approval before it issues.
- **F5 high-value approval**: an issue worth more than the configurable
  threshold (`wms_barcode.high_value_threshold`, default Rs 5000) also requires
  manager approval. The value is snapshotted at request time.
- **Approval mechanism**: a held request becomes a **Pending Approval** under
  **WMS → Approvals** (manager-only). The keeper can *see* it but **cannot
  approve** — read + create only, no self-approval, no password handshake.
  A manager **Approves** (re-checks live stock, then issues — idempotent, never
  a half-picking) or **Rejects** (nothing issued); managers are notified in
  Discuss. Master switch: `wms_barcode.issue_approval_enabled` (default `1`).

### Folded fix — measured-item photo gate
- Scan Issue now correctly **requires a photo when issuing a measured item**
  (Litre / kg / Metre); counted **Units** items do not need one. (This also
  motivates F2's Medicine-as-Units default.)

### F6 — Label hardening (4×1 in thermal)
- The 100×25 mm label keeps the **logo in the left 1 inch, barcode across the
  right 3 inches**, with a minimum scannable barcode size enforced. Print at
  **Actual size / 100% (not Fit-to-page)** on 100×25 mm Gap / die-cut stock at
  **203 DPI**. A guarded migration realigns any saved logo-right profile.
  `docs/LABEL-PRINTING.md` carries the actual-size + 203 DPI guidance.

### F7 — Docs + training (`wms_training` 19.0.1.9.0 → 19.0.1.10.0)
- New docs: `docs/ISSUE-DIMENSIONS.md`, `docs/UOM-BY-KIND.md`,
  `docs/RETURNABLE-ITEMS.md`, `docs/ISSUE-APPROVALS.md`; `docs/LABEL-PRINTING.md`
  updated for F6; the README docs index + feature list and
  `docs/13-operations-playbook.md` (issue / approvals sections) updated to
  point at them.
- `wms_training` adds short in-app help articles + a Scan-Issue tour update for
  the new Department / Purpose / Animal fields and the approval flow. Training
  data is `noupdate=1`: fresh installs read the edited XML; existing databases
  converge via the `19.0.1.10.0` migration delegating to the shared,
  idempotent hooks (the established `post-migrate.py` → `hooks` pattern).

## [v19.0.17.0.0] — 2026-06-12 — Google Drive automated backup & restore

Adds an off-site cloud tier on top of the existing local backup pipeline:
every backup is encrypted locally (the unchanged GPG AES256 envelope), then
uploaded to Google Drive with tiered retention, an in-app Backup Now wizard,
a manager-only restore browser, and a scripted download/verify/restore
orchestrator. The Drive stage is failure-safe — a Drive error never fails the
local backup — and **local backup behavior is unchanged when Drive is
disabled**. Setup, runbooks and troubleshooting: `docs/22-gdrive-backup.md`.

Manifest bumps: `wms_reports` **19.0.2.17.0 → 19.0.3.0.0**; `wms_training`
**19.0.1.7.0 → 19.0.1.8.0** (training content, carries a data migration —
see *Docs + training*).

### Scripts layer
- `scripts/gdrive-lib.ps1` (new) — shared Drive REST library: OAuth token
  handling, resumable uploads (8 MiB chunks for files > 5 MB), retry with
  2/4/8 s backoff + jitter, upload verification against Drive's
  `sha256Checksum`.
- `scripts/setup-gdrive-auth.ps1` (new) — one-time browser consent; prints
  the connected account + quota. Requires `GDRIVE_CLIENT_ID` /
  `GDRIVE_CLIENT_SECRET` in `.env` (user-created GCP OAuth Desktop client;
  the consent screen **must be published to "In production"** —
  Testing-status refresh tokens expire in 7 days). Service accounts are
  impossible on consumer Gmail (no storage quota).
- `scripts/gdrive-test.ps1` (new) — connection / upload test harness; also
  invoked by the Settings page's Test Connection / Test Upload buttons.
- `scripts/backup-native.ps1` — new **Stage 5**: after local backup +
  offsite copy, uploads the set to
  `Inventory_Backups/YYYY/MM-MonthName/YYYY-MM-DD/` on Drive as
  `WMS_DB_YYYY-MM-DD_HH-MM-SS.dump.gpg` + `WMS_FILESTORE_….zip.gpg` +
  `SHA256.txt` + `backup-info.json`. Local filenames are **unchanged**
  (`wms-<stamp>.dump.gpg`). Failure-safe: Drive errors warn
  "(LOCAL backup is intact)" and never fail the local backup.
- **Drive retention tiers**: daily 30 days / weekly 6 months / monthly
  2 years (`wms_gdrive.retention_*` parameters); manual + emergency sets are
  exempt unless `wms_gdrive.delete_manual=1`. Local retention unchanged (14).
- `scripts/install-backup-tasks.ps1` — **"WMS Daily Backup" default moved
  from 1:00 PM to 4:30 PM** (`-BackupAt` still overrides). Existing installs
  keep their registered time until operators **re-run
  `install-backup-tasks.ps1`** to adopt the new default. "WMS Weekly Restore
  Drill" unchanged (Sun 3:00 AM). New third task **"WMS Manual Backup"** (no
  trigger; run by the Backup Now wizard via `schtasks /Run`). All tasks
  registered under `NT AUTHORITY\SYSTEM`.
- **Failure handling**: offline / auth-expired / quota-full / interrupted
  uploads keep the local backup, write a failed audit row + a pending
  catalog row, ping the `/fail` heartbeat (`HEALTHCHECK_GDRIVE_URL`), and
  are retried by the next run's pending sweep. Auth expiry raises
  `GDRIVE_AUTH_EXPIRED` (health DEGRADED + manager notification); the fix is
  to re-run `setup-gdrive-auth.ps1`.
- Housekeeping: `.env.example` gains the `GDRIVE_*` keys, token artifacts
  are gitignored, and CI's test invocation adds the `wms_gdrive` test tag.

### Odoo layer (`wms_reports` 19.0.2.17.0 → 19.0.3.0.0)
- **Backup Now** menu under the WMS root, gated by the new capability group
  "WMS / Can Run Backup Now" (implied into Manager, grantable per keeper);
  the success screen shows filename / size / upload time.
- **Settings** (manager-only, WMS → Configuration): enable flags, backup
  time (16:30), notify flags, retention tiers, folder name, plus Test
  Connection / Test Upload buttons (subprocess `gdrive-test.ps1`).
- **Restore browser** (manager-only): read-only catalog (Year > Month > Day)
  with size / checksum / creator and a copy-paste `gdrive-restore.ps1`
  command. Keepers see no restore surface.
- **Health**: `/wms/health` + Self-Diagnostics now report `gdrive_enabled`,
  `drive_connected`, `last_upload_age_hours`, storage used/limit MB, and
  `next_backup_at`. Drive problems are **DEGRADED only, never CRITICAL**.
- **Crons**: daily upload-freshness check at 08:05 (26 h stale threshold,
  20 h notification dedupe) and an hourly event notifier at :25 delivering
  to the manager Discuss inbox.
- Every upload carries a `backup-info.json` manifest (schema version, set
  stamp, timestamps, DB name, backup type auto|manual|emergency, creator,
  hostname, WMS/Odoo versions, encryption metadata, TOC entry count,
  local↔Drive filename map with sizes + SHA-256s, retention exemption flag,
  restore hint).

### Restore orchestrator (`scripts/gdrive-restore.ps1`, new)
- `-List` prints the Drive backup tree; `-SetStamp <yyyyMMdd-HHmmss>` alone
  is download-only mode — it downloads and verifies (triple SHA-256 check +
  GPG envelope verification) and renames artifacts back to their local names
  (`-DownloadTo` overrides the target directory).
- `-AutoRestore -TargetDb <db>` runs the full chain: emergency backup first
  (`backup-native -Source emergency -FilePrefix 'emergency-'`) →
  download/verify → `pg_restore --list` ≥ 100 TOC gate → live-aware service
  stop → `restore-native -Force` → probes → restart + health poll →
  `restore_gdrive` audit row.
- **Prod guard**: restoring over the live `wms` DB requires BOTH `-Force`
  AND the literal `-ConfirmTarget wms`; anything less is refused with
  exit 5 **before any side effect**.
- One-shot **"WMS Restore Once"** SYSTEM task via `-AsTask` / `-AtNextBoot`.
- Exit codes 0/1/2/3/4/5/6 (OK / SET_NOT_FOUND / DOWNLOAD_FAILED /
  VERIFY_FAILED / RESTORE_FAILED / PROD_GUARD / AUTH_EXPIRED). Logs to
  `.runtime\logs\gdrive-restore.log` + the `WMS_Backup_Drill` Event Log
  source.

### Security
- OAuth scope is **`drive.file` only** — the app sees only files it created
  (and needs no Google review). Operators must **not** manually reorganize
  the `Inventory_Backups` tree in the Drive UI.
- The refresh token is stored DPAPI machine-scope at
  `config\gdrive-token.json.dpapi` — readable by SYSTEM on this box, useless
  off-box, gitignored.
- Drive only ever holds ciphertext: the existing GPG AES256 envelope and
  SHA-256 sidecars are produced before upload; nothing is decrypted in the
  cloud.
- Restore remains manager-only end to end: the in-app catalog is read-only,
  and the actual restore is the operator-run script behind the prod guard
  above.

### Docs + training
- `docs/22-gdrive-backup.md` (new) — canonical guide: GCP project + OAuth
  setup (including the publish-to-Production / 7-day-token trap),
  `setup-gdrive-auth.ps1` walkthrough, Settings, Backup Now, restore
  browser, `gdrive-restore.ps1` runbook, troubleshooting, security model.
- `docs/training/sop/13-cloud-backup.md` (new) + visual-academy
  `cloud-backup.svg` diagram + training-map / permissions-matrix updates.
- `wms_training` 19.0.1.7.0 → 19.0.1.8.0 — two new Help-Center articles
  ("Cloud backup (Google Drive)", "How to back up to Google Drive now"),
  admin-tour step 7 "Cloud safety net" (Back Up Now), and a post-migration
  that applies the `noupdate="1"` edits (4:30 PM wording + the tour step)
  to existing databases; fresh installs get them from the XML.
- Drive sections added or updated across `docs/INSTALLATION-GUIDE.md`,
  `docs/18-restore-drill.md`, `docs/19-disaster-recovery.md`,
  `docs/07-deployment.md`, `docs/ADMIN-QUICK-START.md`,
  `docs/11-maintenance.md`, `docs/08-security.md`, `SECURITY.md`,
  `README.md`; the 4:30 PM default propagated through all backup-time
  references.

### Also in this release
- `scripts/install-native.ps1` — step 7.5 health-token block unbroken under
  `Set-StrictMode -Version Latest` + PowerShell 5.1 (commit `b32950f`).

### Verification status
- **Mock-Drive E2E proven** on scratch DBs: a marker row survived
  backup → upload → download → restore; a tampered artifact was rejected at
  verify; the prod guard refused a live-`wms` restore without
  `-ConfirmTarget wms`.
- **Live Drive E2E pending** the user's GCP credentials (one-time setup in
  `docs/22-gdrive-backup.md`).
- **Supervised production restore drill pending** — schedule one after the
  first live upload lands.

## [v19.0.16.5.0] — 2026-06-08 — Documentation & Training certification

Doc-only patch release on top of v16.4. No code, schema, scripts, addons, or
manifests changed. 26 docs edited + 1 new (`docs/19-disaster-recovery.md`);
+668 lines, −300 lines.

Sprint outcome: **CERTIFIED_GOLD** for handover (handover-readiness 9.5/10).

### Blockers closed (4)
- `docs/INSTALLATION-GUIDE.md` Phase 4 health probe rewritten to use the live
  v16.4 token gate (`?token=` or `X-Health-Token` header; full 401/200/503
  response matrix documented; `odoo.tools.consteq` named).
- `docs/INSTALLATION-GUIDE.md` Phase 13 — new **Step 0** for
  `BACKUP_OFFSITE_DIR` with the **NT AUTHORITY\SYSTEM** principal-reachability
  caveat (user-only OneDrive paths warned against).
- `docs/18-restore-drill.md` — manual `Register-ScheduledTask` snippet replaced
  with `scripts\install-backup-tasks.ps1`; the CR-1 locked-console DR failure
  cannot re-emerge from copy-pasting the doc.
- `docs/07-deployment.md` — rewritten to canonical 7-module install,
  `Odoo-WMS` service name, `install-odoo-service.ps1` /
  `install-backup-tasks.ps1` / `install-ai-worker-service.ps1`, and
  `PostgreSQL 15/16/17 (auto-detected; winget installs 17 by default)`.

### Disaster-recovery runbook (new)
- `docs/19-disaster-recovery.md` — 10-section "PC died, rebuild on a new box"
  end-to-end runbook. Targets ~85-minute round-trip from clean Windows to
  smoke-passed restore. Explicitly grounds:
  - `scripts\restore-native.ps1 -Force` is **mandatory** on a fresh-box
    rebuild (`install-native.ps1` pre-seeds the `wms` DB).
  - The `pg_restore --list ≥ 100 TOC` sanity gate lives in
    `restore-drill.ps1` only — not the production restore path. Operators
    wanting a pre-flight TOC check run the drill first.
  - SHA-256 sidecars are written by `backup-native.ps1` at backup time and
    verified by the operator (§3.3 `Get-FileHash`) at restore time;
    `restore-native.ps1` does not auto-verify.
  - `$psql` auto-detection block (§3.4) defined before first use; all later
    references use the call operator (`& $psql ...`).
  - Troubleshooting covers the `-Force` trap, BACKUP_PASSPHRASE failures,
    SYSTEM-unreachable `BACKUP_OFFSITE_DIR`, `service-err.log` inspection.

### CHANGELOG history repaired
- `v19.0.16.2.0` section inserted (closure-sprint hotfix: `gpg` via `cmd /c`).
- `v19.0.16.3.0` section inserted (closure-sprint: CR-3 health-token doc
  clarification + companion commits; CR-1, CR-2, CR-4, CR-5 left
  un-enumerated where commit subjects don't name them, with a pointer to PR #41).

### Security documentation completeness
- New "Shipped security controls" section in `SECURITY.md` and
  `docs/08-security.md` enumerating the 8 controls in play: DB manager UI
  lockdown (`list_db=False`, `db_listing=False`, `/web/database/*` redirect),
  roles + 5 capability sub-groups (all in the `wms_location` namespace),
  `/wms/health` `consteq` gate, backup envelope (GPG `--symmetric
  --cipher-algo AES256` via `cmd /c`), SHA-256 integrity + `pg_restore --list`
  ≥ 100 TOC gate (drill-only), `BACKUP_OFFSITE_DIR` semantics, scheduled
  tasks under `NT AUTHORITY\SYSTEM`, placeholder password deny-list.
- `README.md` role table expanded from 2 to canonical 3 base roles
  (Store Keeper, Manager, Repair Tech) + optional Buyer + 5 capability
  sub-groups, with cross-link to `docs/08-security.md`.

### Menu-path & vocabulary sweep
- `WMS → Products → Onboard Product` → `WMS → Configuration → Onboard Products`
  (no such submenu existed; Onboard Products lives under Configuration).
- `Label Config` → `Label Settings` (the displayed view name) — 4 sites.
- `OdooWMS` → `Odoo-WMS` (canonical hyphenated service name) — 5 sites in
  `docs/07-deployment.md`.
- `odoo-native.log` → `odoo.log` — 2 sites; matches the live file written by
  `install-native.ps1`.
- `Damages → New` removed everywhere — Damages is a single leaf, with a
  New button on the list view.
- `Levels / Dividers / Slots` and `L-3/D-2/S-1` slot codes purged from
  `docs/15-onboarding-script.md`; replaced with `Rack / Compartment / Slot`
  and `R01-SH01-C01-SL01`-style codes.
- `wms.return` (no such model) → `wms.scan.receipt` (return mode) in
  `docs/02-data-model.md` and `docs/06-reports.md` after grep-confirming the
  live model.
- Help & Training surfaced as a **top-level Odoo app** (not a WMS submenu) in
  `STOREKEEPER-QUICK-START.md`, `ADMIN-QUICK-START.md`,
  `21-training-system.md`, `INSTALLATION-GUIDE.md`.

### Stale operational instructions removed
- `docs/04-barcode-flow.md` "The container generates a PDF" → "Odoo".
- `docs/05-ai-prediction.md` "Optional ai_worker container" → native
  `scripts/start-ai-worker.ps1` / `Odoo-WMS-AIWorker` NSSM service.
- `docs/08-security.md` L128 "never in compose or in git" → "never in
  checked-in config or in git".
- `docs/11-maintenance.md` L51 "ai_worker profile so statsmodels doesn't
  live in Odoo's RAM" → native process phrasing; L96 "statsmodels installed
  in container?" → ".venv\Scripts\pip show statsmodels".
- `docs/INSTALLATION-GUIDE.md` L324 `Get-RandomBytes 16` (not a PS 5.1
  cmdlet) → `RandomNumberGenerator::Create().GetBytes()` for the health-token
  rotation snippet.
- `docs/08-security.md` L194 bash `&&` chaining → PS-5.1-valid
  `cmd1; if ($?) { cmd2 }`.

### 21-training-system.md realigned to the live addon
- Fictional directory tree replaced with the actual addon shape
  (3 view XMLs, 3 data XMLs; no JS, no assets bundle, no client widgets, no
  `menus.xml` file, no `static/description/icon.png`).
- Tours described accurately as HTML articles with `action-PENDING-*`
  placeholders rewritten by `hooks.apply_tour_action_links` at install
  (4 tours; 4 / 5 / 6 / 5 steps). They are not Odoo JS tour-service tours.
- "Show me how" / "Reset my tours" surfaces marked as planned-not-in-this-release.

### Other corrections
- `docs/01-architecture.md` module-layering diagram now includes `wms_training`
  at the top of the stack with its true `depends` set.
- `docs/09-roadmap.md` Phase 7 items ticked with their shipped-in-vX
  annotations (restore drill, capability ACLs, training docs, load test).
- `docs/REMEDIATION-CLOSURE.md` carries a historical-record banner.
- `docs/PRODUCTION-READINESS-v19.0.5.md` historical callout updated to point
  at the current CHANGELOG head.
- `docs/13-operations-playbook.md` role section updated to the 3 + 5
  two-tier model; hard-coded "2,304 slots" replaced with site-dependent
  pointer.
- `docs/training/sop/03-fifo-issue.md` mandatory-audit-fields list aligned
  with the live `wms_barcode/wizards/scan_issue.py` (4 mandatory + optional
  `Issued for` category).
- `docs/LABEL-PRINTING.md` adds a role-visibility callout (Store Keeper
  sources vs Manager-only Configuration sources).
- `.github/pull_request_template.md` adds `wms_training` to the module
  checkbox list.
- All Docker-era historical mentions kept (`README`, `01-architecture`,
  `INSTALLATION-GUIDE`, `07-deployment`, `09-roadmap`, `17-ci-cd`, `CHANGELOG`)
  — only stale operational instructions were rewritten.

### Sprint methodology
Five-workflow agent arc: ground-truth verification → per-file edits →
verify + 3 persona simulations (Storekeeper / Admin / DR) + Help & Training
audit → Critical/High fixup pass → polish pass. ~115 specialised agents,
~5.7M agent tokens.

### Out of scope (tracked, not blocking)
- `scripts/install-native.ps1` end-of-install hint still lists only 6
  modules (not 7) — this is code, not docs, and a code-touching change is
  deferred to a future patch.
- `docs/17-ci-cd.md` L65 still uses `postgresql-x64-16` as the local-dev
  analogy. CI does pin 16 (parity with the Windows install) so this isn't a
  contradiction — just minor phrasing drift from the new canonical PG line.
- `docs/09-roadmap.md` Phase 7 load-test bullet annotated via a doc
  cross-link instead of a literal `shipped in v19.0.X.0.0` tag like its
  siblings.

## [v19.0.16.4.0] — 2026-06-08 — Final cleanup sprint

The final pre-handover sprint. No new features. Repository tidied, prod
hardened, docs refreshed, security policy added.

### Prod hardening (live + verified)
- `/wms/health` token gate **active** on prod. Anonymous probes now return
  `{"status":"unauthorized"}` HTTP 401; the auto-generated 32-char hex token
  (stored in `wms_reports.health_token` System Parameter) is required via
  `?token=` query string or `X-Health-Token:` header. Closes the live HIGH
  security gap surfaced by the v16.1 closure verification.
- `config/odoo.native.conf` (live) + `scripts/install-native.ps1` template:
  - `db_listing = False` — defence in depth alongside the existing `list_db = False`.
  - `without_demo = True` — a fresh `-i` install of any module on prod cannot
    silently load demo data into the live `wms` DB.

### Documentation refresh
- `docs/08-security.md` — stale Docker-subnet `pg_hba` ref rewritten; closure
  state of `list_db`/`db_listing`/`/wms/health` token gate documented.
- `docs/10-testing.md` — "Docker compose smoke" replaced with the native
  PowerShell test invocation that CI actually runs.
- `docs/11-maintenance.md` — `odoo.conf` references renamed to
  `config/odoo.native.conf`; `workers` default corrected to 0.
- `docs/18-restore-drill.md` — off-site backup section now leads with the
  built-in `BACKUP_OFFSITE_DIR` mechanism; rclone/robocopy demoted to
  optional second-tier redundancy.
- `docs/ADMIN-QUICK-START.md` — Backup section opens with `BACKUP_OFFSITE_DIR`;
  health-token reference under System Parameters added.
- `README.md` — PostgreSQL version detection language aligned with installer
  (16/17 auto-detected).
- `SECURITY.md` — **new** community-profile file (security-report contact
  `office.dakshinvrindavan@gmail.com`, in/out-of-scope, latest-tag-only
  support policy).

### Repository cleanup
- **Files archived** (moved to `docs/training/archive/`): `STEP7-VISUAL-ACADEMY-REPORT.md`,
  `TRAINING-COVERAGE-REPORT.md`, `VISUAL-COVERAGE-REPORT.md` — historical
  phase-completion reports superseded by the FPAT/closure docs.
- **Files removed (committed)**: `docs/INSTALLATION-GUIDE.pdf` (stale snapshot
  of the .md), `addons/wms_barcode/data/wms_barcode_data.xml` (stub with no
  records, manifest line removed alongside).
- **Files removed (gitignored, no git impact)**: 7 audit-helper Python scripts
  under `.runtime/`, 5 stale runtime logs, `.runtime/screenshots/`,
  `.runtime/odoo-requirements-win.txt`, `.runtime/sample-4x1-labels.pdf`,
  `.runtime/.master-passwd-temp`, `.runtime/test-data/` (~63 MB scratch DB
  data dir). **~68 MB reclaimed.**
- **Local branches pruned**: 10 fully-merged `feat/*` branches deleted
  non-destructively (still present in `reflog` if recovery is ever needed);
  2 ahead-of-main `feat/buying-recommendations` + `feat/thermal-labels`
  branches deleted per owner decision (work not planned for re-merge).

### Final state
- Production-readiness **8/10** (unchanged from v16.3 baseline; the live
  security gap that would have docked it is now closed).
- 0 Critical, 0 High open findings.
- All 7 modules at the v16.3 manifest versions; this is a config/docs/cleanup
  release with no module manifest bumps.

## [v19.0.16.3.0] — 2026-06-07 — Closure-sprint: 5 Highs discharged (CR-1..CR-5)

Docs-and-hardening release on top of v16.2. No module manifest bumps. Five
closure-review High findings (CR-1..CR-5) discharged; only **CR-3** is named
in a commit subject in this repo — the rest are referenced by PR #41's
description, not by per-commit subjects.

- **CR-3 — health-token doc clarification** (commit `e2714d6`,
  "docs(install): clarify auto-generated health_token"). `docs/INSTALLATION-GUIDE.md`
  §6.4 rewritten to document the install-time auto-generated **32-hex**
  `wms_reports.health_token` System Parameter, the `odoo.tools.consteq`
  comparison gate, and both accepted forms — `?token=<value>` query string
  **or** `X-Health-Token: <value>` request header. Missing/wrong returns
  HTTP 401 `{"status":"unauthorized"}`.
- **CR-1 — scheduled-task principal hardening (docs + verification)** —
  documented and verified the `NT AUTHORITY\SYSTEM` principal registration
  for `WMS Daily Backup` / `WMS Weekly Restore Drill` in
  `scripts/install-backup-tasks.ps1` (`LogonType=ServiceAccount`,
  `RunLevel=Highest`, `-StartWhenAvailable`, `ExecutionTimeLimit=2h`,
  `MultipleInstances=IgnoreNew`) so DR survives a locked console / reboot.
  The underlying SYSTEM-principal switch first shipped in **v19.0.16.0.0**
  (FX-1 Critical batch); v16.3 CR-1 is the formal docs + commit
  consolidation of that change.
- **README cosmetic expansion** (commit `93be697`, "docs(readme): surface
  issued-for + alert-hardening in 'What's in the box'") — surfaces the v15
  Issued-for classification and alert-delivery hardening in the top-level
  feature list. Closure-cosmetic only.
- **CR-2, CR-4, CR-5** — not enumerated in commit subjects in this repo;
  see PR #41 description for full per-finding mapping.

Tagged at merge `f1e0c6c` (PR #41).

## [v19.0.16.2.0] — 2026-06-07 — Closure-sprint hotfix: gpg via cmd /c

Scripts-only release. No addon manifest bumps. Fixes the v16.1 regression
where `& $gpg ... 2>$errFile` running under PowerShell 5.1 with
`$ErrorActionPreference = 'Stop'` wrapped gpg-agent's harmless startup
stderr as a fatal `NativeCommandError`, breaking unattended backup and
restore-drill runs.

- **Fix:** invoke `gpg` via `cmd /c` so PowerShell never wraps the native
  stderr stream. `gpg --symmetric --cipher-algo AES256` is now executed
  through `cmd /c "<gpg.exe> ... --passphrase-file <tempfile> ..."`,
  matching the existing short-lived `--passphrase-file` convention.
- **Touches** `scripts/backup-native.ps1`, `scripts/restore-native.ps1`,
  `scripts/restore-drill.ps1`. Commit `426f21f`; tagged at merge `d39c9c9`
  (PR #40).

## [v19.0.16.1.0] — 2026-06-07 — Closure-sprint hotfix

Single security-relevant patch identified by the v16 re-FPAT pass.

- **`scripts/install-native.ps1` placeholder deny-list silently no-op** — line 508 referenced an undefined `$RepoRoot`; PowerShell's default loose mode let `Join-Path` resolve to just `.env`, so on a fresh install + non-repo CWD the gate skipped without warning. A leftover `BACKUP_PASSPHRASE=changeme_backup_passphrase` could ship to prod and produce externally-decryptable backup artifacts.
  - Use the already-resolved `$EnvPath` built at the top of the script.
  - Add `Set-StrictMode -Version Latest` so the same class of typo fails loudly at install time instead of silently skipping security gates.

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
