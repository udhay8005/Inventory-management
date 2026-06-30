# Dakshin Vrindavan Gaushala WMS — Operations Manual

**Every process, step by step, role-wise.**

**Build:** v20.0.0 (Wave 1 Perishable Engine · Wave 2 Warehouse Intelligence · Wave 3 Pharmacy) — 10 addons, Odoo 19 Community Edition, native Windows.
**Audience:** Administrators (WMS Managers) and Storekeepers (WMS Users).
**How this was written:** every step, field, button, error message, and role below was extracted directly from the addon source code (models, wizards, view XML, controllers, security rules), not from memory.

---

## How to read this manual

Each process is documented in a fixed shape so you can scan it quickly:

- **Role** — who can do it: *Admin only* (WMS Manager) or *Both* (Storekeeper + Admin).
- **Menu path** — where to click from the top WMS menu.
- **Purpose** — one line on what it achieves.
- **Steps** — the numbered click-by-click sequence.
- **Fields / Buttons** — the real form fields and action buttons, with required ones marked.
- **Validation / errors** — the constraints and on-screen messages that can stop you.
- **Result** — the record/state/printout you end with.

### The two roles, and the operator toggles

The WMS has two functional roles on top of an Odoo login: the **Administrator / WMS Manager** (`group_wms_manager`) sees and does everything; the **Storekeeper / WMS User** (`group_wms_user`) gets the operational floor surface. What a Storekeeper can actually *do* inside the screens they see is further controlled by four per-person operator toggles the Admin assigns: **Scan Receive**, **Scan Issue**, **File Damage**, and **Submit Audit** (plus **Approve Issue** and **Repair Tech**, which are manager-adjacent). Security is enforced in depth — at the menu, at the action/route, and at the database ACL — so a permission a Storekeeper lacks cannot be reached by guessing a URL or forcing an RPC.

### Key facts worth knowing before you start

A few details that are easy to assume wrong (all verified in code):

- **Scan Return is the Scan Receipt screen** opened in return mode — its Validate button reads "Validate Return"; only the return gate differs.
- **Dispensing is entered in tablets.** The Pharmacy dispense wizard takes a tablet quantity and derives strips/boxes internally (FEFO + open-strip first); there is no box/strip/tablet dropdown on the wizard. The box→strip→tablet *tiers* are defined under Pharmacy / Packaging Barcodes.
- **Lot states are** available / quarantine / recalled / destroyed. "Near-expiry" and "expired" are not lot states — they are status bands computed by the expiry reports and the FEFO planner.
- **The dispense/medication history is immutable** — it can be created but not edited or deleted (write/unlink are guarded).
- **Maintenance screens** (Backup & DR Audit, Self-Diagnostics, Google Drive Backups, DR settings) live under **WMS / Configuration**, not Reports.
- **"Find / Where is it?"** is served by a web page (`/wms/find`), reachable from both Operations and Reports.

---

## Table of contents

1. **Operations — Receiving, Issuing & Scanning** — Scan Receipt, Scan Issue, Scan Return, Find, Products, Create/Onboard Product, Issue Approvals, Carton/Packaging barcodes, Label printing.
2. **Configuration & Warehouse Setup** — Zone→Rack→Compartment→Slot layout, the three bulk generators, catalogue masters (Animals/Brands/Categories/Families/Purposes/Departments/Forms), Store Keepers roster, the role/group model.
3. **Perishable Lifecycle, Damage & Repair** — Shelf-life policy/settings, expiry alerts, Lot Quarantine, Lot Recall, Lot Migration, the lot-state machine, Damages, Repair orders.
4. **Forecasting, Reports & Backup/DR** — demand forecasting & reorder, every report (alerts, find-stock, value/money, store-keeper activity, dashboard), and the full Backup & Disaster-Recovery suite.
5. **Pharmacy — Dispensing & Packaging** — the Box→Strip→Tablet dispense engine, Open Strips, Packaging Barcodes, Packaging Genealogy, immutable Medication History.
6. **Intelligence Analytics & Help** — all 21 analytics views (Expiry Risk, Stock Health, ledgers, scorecards, usage, traceability, FEFO, cycle-count priority, cold chain, bulk lot actions) plus the Training Academy.

Appendix A — Common errors & what they mean.
Appendix B — The security model in one picture.

---
## 1. Operations — Receiving, Issuing & Scanning

> Scope note: This section documents the user-facing processes delivered by the
> `wms_barcode` addon (Odoo 19, module version 19.0.1.48.0), plus the closely
> related **Find / Where is it?** page which lives in the sibling `wms_reports`
> addon but is presented to operators as a WMS Operations menu. Every field
> label, button name, menu path, and error message below is taken from the
> actual source (models, wizards, views, reports, and security files); where a
> label is only set in a view (not the model) it is marked **(label from view)**.

### How roles are decided (read this first)

The WMS uses **capability sub-groups**, not one flat "user" role. The base role
`group_wms_user` only grants read access and the menu shell. On top of it sit
five capability groups (all defined in `wms_location/security/wms_security.xml`,
each implying `group_wms_user`):

- `group_wms_can_scan_receive` — Scan Receipt **and** Scan Return menus
- `group_wms_can_scan_issue` — Scan Issue menu
- `group_wms_can_file_damage` — Damage workflow (not in this section)
- `group_wms_can_submit_audit` — Inventory audits (not in this section)
- `group_wms_can_manage_catalog` — Carton Barcodes + Label config editing

`group_wms_manager` (the **Admin**) implies all five capability groups plus the
manager-only `group_wms_can_approve_issue` (defined in
`wms_barcode/security/wms_approval_security.xml`), so an Admin sees and can do
everything. A Store Keeper sees a menu only if their linked Odoo login holds the
matching capability group. Capabilities are granted per keeper from the Store
Keeper form (see "Store Keepers / capability grants" inside the relevant
processes). Throughout this section, **"Both (Storekeeper + Admin)"** means the
keeper needs the named capability; **"Admin only"** means the menu/action is
gated on `group_wms_manager`.

---

### Scan Receipt
**Role:** Both (Storekeeper + Admin) — menu gated on `group_wms_can_scan_receive`
**Menu path:** WMS / Operations / Scan Receipt
**Purpose:** Bring purchased / delivered goods inward by scanning, then validate to create and complete an incoming transfer (receipt) into warehouse stock.

**Steps:**
1. Open **WMS / Operations / Scan Receipt**. The wizard opens as a pop-up with a blue "Scanner ready" banner. The cursor sits in the scan field automatically.
2. Confirm the **Warehouse** (defaults to the first warehouse).
3. Leave **Return entry** OFF for a normal inward receipt (see the separate "Scan Return" process for the ON case).
4. Scan each item. A product unit barcode adds 1; a carton/alias barcode adds its preset unit count; a lot/serial barcode adds the item and records the lot. Each scan is processed automatically (no button press) and a green feedback line shows e.g. "Added 24 × Coke 350ml".
5. To put a line in a specific slot, scan that slot's location barcode — it is applied to the most recent line that has no destination yet ("Slot R01-… assigned"). Otherwise leave the destination blank and the system auto-assigns a slot at validate.
6. Adjust the **Qty** cell on any line for loose/bulk items (the editable list lets you tap the quantity).
7. Tick **Quality check passed** (required) after physically counting/inspecting. Optionally add **QC notes** and a **Delivery photo** (camera on mobile).
8. Confirm the **Store Keeper on duty** (defaults to the roster entry linked to your login) and optionally fill **Delivered by**.
9. Press **Validate & Print**. The receipt transfer is created, confirmed, assigned, and validated; the picking opens.

**Fields:**
- **Warehouse** *(required)* — source warehouse; defaults to first.
- **Scan here** *(label from view; field is `last_scan`)* — the scan input; keep cursor here.
- **Return entry** — toggle; OFF for normal receipt. **(label from view: "Return entry")**
- **Quality check passed** *(required to validate)* — receiver confirms count/condition.
- **QC notes** — optional free text.
- **Delivery photo** — optional image (opens camera on phones); attached to the receipt.
- **Store Keeper on duty** *(required)* — picked from the active `wms.storekeeper` roster; defaults to the roster entry linked to your Odoo login.
- **Delivered by** — optional name of driver/vendor/courier.
- Line fields: **Product** *(required)*, **Quantity** *(required, must be > 0)*, **Lot** *(optional, hidden column by default)*, **Destination** (slot/floor; blank = auto-assign).

**Buttons:**
- **Process scan** → `action_process_scan` — manually process whatever is typed in the scan field (normally automatic via the scanner).
- **Validate & Print** → `action_validate` — creates and completes the incoming picking, posts the audit message, attaches the photo, opens the receipt. (This is the label shown when Return entry is OFF.)
- **Cancel** → closes the wizard without receiving.

**Validation / errors (real messages):**
- No lines: "No lines to receive."
- QC not ticked: "Mark 'Quality check passed' first. This confirms you've physically counted and inspected the delivery."
- Destination is a Damage/Repair location: "Cannot receive stock into a Damage or Repair location — … Scan a storage slot or floor zone instead, or leave the destination blank to auto-assign."
- No slots/floor zones exist for auto-assign: "No slots or floor zones are set up in warehouse … Use Create Rack or Generate Floor Zones in the WMS Configuration menu first."
- Warehouse not set up to receive: "Warehouse … isn't configured to receive incoming stock. Ask an Administrator to enable Receipts in the Inventory settings."
- Receipt line qty ≤ 0 is blocked by a DB CHECK: "Receipt quantity must be greater than zero."
- Double-submit is safe: a second Validate re-opens the receipt already created (idempotency guard on `picking_id`).

**Result:** A validated **incoming** `stock.picking` (origin "Barcode scan"), with stock placed in the chosen/auto-assigned slots (and scanned lots carried onto the move lines). The picking records `wms_taken_by` (= Delivered by) and `wms_storekeeper_id`, and carries a "Receipt received" audit message in the chatter (plus a "Delivery photo attached at receipt." note if a photo was added).

---

### Scan Issue
**Role:** Both (Storekeeper + Admin) — menu gated on `group_wms_can_scan_issue`
**Menu path:** WMS / Operations / Scan Issue
**Purpose:** Issue stock out by scanning a product; the system plans a strict FIFO (oldest-arrival-first) deduction across all slots, captures full audit detail, and either issues immediately or routes the request to a Manager for approval.

**Steps:**
1. Open **WMS / Operations / Scan Issue** (pop-up with a blue "Set the quantity, then scan the product." banner).
2. Confirm **Warehouse** and **Used by / area** (the destination; defaults to the trust's internal-use location — change only to charge a specific area on the day).
3. Set **Quantity** (default 1). For a carton/alias barcode the count is multiplied by the carton's units-per-scan.
4. Scan the product. The wizard plans the deduction against the oldest stock and lists the planned lines (Product, Slot, Arrived date, Expires, On shelf, Will take). Feedback reads e.g. "Planned 5 × Feed across 2 slot(s) — oldest stock first."
5. If stock is short, a warning appears and **Short by** is shown — lower the quantity and press **Check stock** again, or Cancel.
6. Fill the **Audit trail** block: **Taken by** *(required)*, optionally **Ordered by**, and **Store Keeper on duty** *(required, defaults to your linked roster entry)*.
7. Choose **Department** *(required, defaults to "Other")*; optionally **Purpose / reason** and **Animal / cow**.
8. Type the **Reason / usage note** *(required)* explaining why the stock is taken.
9. If the planned product is measured by weight/volume/length (kg, L, Metre, …), an **Item photo** is required — take/attach it.
10. If the issue is high-value or the same department requested this item too recently, an orange "This issue needs a Manager's approval" banner appears and a **Reason for the Manager** box becomes required. Type the justification.
11. Press **Validate**. If no approval is needed, the outbound transfer is created, reserved, validated, and opened. If approval is required, **nothing is issued** — the request is saved as a held approval and opened read-only.

**On-duty Store Keeper capture (important):** Every issue records **who** physically took the stock (**Taken by**), **who** authorised it (**Ordered by**), and **which roster keeper was on the desk** (**Store Keeper on duty**, a `wms.storekeeper` record). The Store-Keeper field defaults to the roster entry linked to the logged-in user via `_default_storekeeper_id` (empty for a shared desk login, so the keeper picks who is at the desk). At validate these are copied onto the picking (`wms_taken_by`, `wms_ordered_by`, `wms_storekeeper_id`) and written into the chatter audit message ("Issued. Taken by … ; ordered by … ; Store Keeper on duty: … ; logged in as: …"). A WMS-originated picking **cannot be marked done without a storekeeper** — enforced by both a DB CHECK constraint and an `@api.constrains` (see Validation below).

**Fields:**
- **Warehouse** *(required)*.
- **Used by / area** *(required; field `destination_id`)* — destination location (customer/production/internal); defaults to the trust internal-use location.
- **Quantity** *(field `requested_qty`, default 1)*.
- **Scan here** *(field `last_scan`)*.
- **Taken by** *(required)*, **Ordered by** *(optional)*, **Store Keeper on duty** *(required)*.
- **Department** *(required, default "Other")*, **Purpose / reason** *(optional)*, **Animal / cow** *(optional)*.
- **Reason / usage note** *(required)*.
- **Item photo** *(required only when a measured-UoM product is planned)*.
- **Reason for the Manager** *(field `keeper_reason`; required only when the approval gate trips)*.
- Plan line columns: Product, **Slot**, **Arrived** (`in_date`), **Expires** (colour-coded: red ≤30 days, amber ≤90 days), **On shelf** (`available`), **Will take** (`take`).

**Buttons:**
- **Check stock** → `action_plan` — resolve the scanned barcode and build the FIFO plan; shows shortfalls.
- **Validate** → `action_validate` — issue the stock (or, if the gate trips, create the held approval). Hidden while **Short by** > 0.
- **Cancel** → closes without issuing.

**Validation / errors (real messages):**
- Qty ≤ 0 on plan: "Quantity must be greater than zero. Enter how many units you want to issue (the default is 1)."
- Nothing scanned: "Scan a product barcode before planning the issue. …"
- Unknown barcode: "That barcode isn't linked to any product in the warehouse. …"
- Stock-out feedback: "⚠ STOCK OUT — no … available anywhere in the warehouse. …" or "⚠ Only … on hand (oldest stock first) — that's … less than you asked for. …"
- Validate with shortfall: "The warehouse doesn't have enough stock. You're short by … ."
- Measured product without photo: "This product is measured by weight or volume. Take a photo of what you're issuing and attach it before you finish — the trust needs proof of measured items."
- **Max per issue** cap exceeded: "You asked for more … than is allowed in a single issue. You requested …, but the most you can give out in one go is … . …"
- **Daily cap (rolling 24h)** exceeded: "You've reached the daily limit for … . You've already given out … in the last 24 hours. … over the daily limit of … . …"
- Approval needed but no reason typed: "This issue needs a Manager's approval (it's high value, or your department requested this item too recently). Type the reason in the 'Reason for the Manager' box below and submit again — … No stock has moved."
- Concurrency abort (stock taken mid-flow): "Another keeper took some of this stock while you were finishing up, so it can no longer be issued in full. Nothing was issued. Please scan again …"
- Audit-trail constraint on done picking: "Picking … is WMS-originated but has no storekeeper recorded. Re-run the scan wizard to record who handled this transfer before marking it done."

**Result:** Either (a) a validated **outbound** transfer (internal transfer for internal/production destinations, outgoing for customer), flagged `wms_is_scan_issue=True`, carrying the audit fields, a frozen `wms_unit_cost_at_done` per line, the usage note on the picking and chatter, and an expected-return date if any product is returnable; or (b) a **held `wms.issue.approval`** record in state Pending (nothing issued) routed to Managers — see "Issue Approvals" below.

---

### Scan Return
**Role:** Both (Storekeeper + Admin) — menu gated on `group_wms_can_scan_receive` (same capability as Scan Receipt)
**Menu path:** WMS / Operations / Scan Return
**Purpose:** Receive returnable items back into stock (e.g. a tool back from production, a borrowed spare), and best-effort clear the matching outstanding issue so it drops off the Returns-due report.

**Steps:**
1. Open **WMS / Operations / Scan Return**. It is the **same wizard as Scan Receipt** opened with **Return entry** pre-ticked (an orange "Return entry mode." banner shows). The action sets `default_is_return = True`.
2. Confirm the **Warehouse** and leave **Return entry** ON.
3. Scan each item coming back (and optionally a slot barcode to place it; otherwise auto-assign applies).
4. Adjust quantities as needed.
5. Tick **Quality check passed** (required), optionally add **QC notes** / **Delivery photo**.
6. Confirm **Store Keeper on duty** (required) and optionally **Delivered by**.
7. Press **Validate Return**.

**Fields:** Identical to Scan Receipt (Warehouse, Return entry [ON], Quality check passed, QC notes, Delivery photo, Store Keeper on duty, Delivered by; line Product/Quantity/Lot/Destination). The only difference is the `is_return` flag.

**Buttons:**
- **Process scan** → `action_process_scan`.
- **Validate Return** → `action_validate` — the label shown when Return entry is ON; validates the inward transfer and runs the return-matching step.
- **Cancel**.

**Validation / errors (real messages):**
- Non-returnable products are refused at validate: "These products cannot be received as a return — they are flagged not-returnable on the product form (fluids, consumables, single-use items): … Ask the Admin to either change the product's WMS Kind / Returnable flag, or scrap these items via the Damages workflow instead." (A product is returnable per `wms_is_returnable`, seeded from its WMS Kind; tools/spares/raw materials default returnable, fluids/consumables not.)
- All Scan Receipt validations also apply (QC tick, no Damage/Repair destination, slots must exist, qty > 0).

**Result:** A validated incoming transfer with origin "Barcode scan (return)" and a "Return received" chatter message. For each returned returnable product the system finds the oldest still-open Scan Issue picking for that product (with an expected-return date, not yet returned, not reversed) and sets `wms_returned=True` on it, posting a "Returned." note there — clearing it from the Returns-due report. If no confident match is found, the item simply stays 'due' (safe default; not a strict per-unit reconciliation).

---

### Find / "Where is it?"
**Role:** Both (Storekeeper + Admin) — open to any `group_wms_user` (re-checked server-side in the controller)
**Menu path:** WMS / Operations / Find / Where is it?
**Purpose:** One search box that answers the warehouse's most common questions — where an item is, how much is on hand, and what is low / expiring / dead / damaged / under repair.

> Implementation note: this is a standalone server-rendered page at the URL `/wms/find` (route `@http.route("/wms/find", auth="user")` in `wms_reports/controllers/main.py`, template `wms_reports.find_page`). The menu item (`menu_wms_find`) is an `ir.actions.act_url` that opens it in a new tab. No JavaScript; mobile-friendly.

**Steps:**
1. Open **WMS / Operations / Find / Where is it?** (opens the Find page in a new browser tab).
2. To locate a product, type its **name, SKU, or barcode** in the box and press **Find** (or scan the barcode into the box).
3. Read the result card: product name (with a **LOW** badge if at/below reorder level), SKU + barcode, **On hand** total with unit, and a per-slot breakdown ("slot → quantity"). If it is not in any slot it shows "Not in any storage slot right now."
4. For a quick list instead of a single product, tap one of the chips: **low stock**, **expiring**, **dead stock**, **damaged**, or **under repair**.
5. Use the footer links **Warehouse map** (`/wms/warehouse/map`) or **Back to Odoo** as needed.

**Fields:**
- **q** — the single search box (placeholder "Product name, SKU, or barcode…"). Matches barcode (exact), SKU/`default_code` (exact or contains), product name (contains), and carton **alias** barcodes (exact).

**Buttons / controls:**
- **Find** — submits the search (GET to `/wms/find`).
- Quick chips — `?q=low`, `?q=expiring`, `?q=dead`, `?q=damaged`, `?q=repair` (only these exact keywords route to a list; any other text is treated as a product lookup).

**Validation / errors:** No match shows: 'No match for "…". Check the spelling, or scan the barcode.' Empty query shows guidance to type a name/SKU/barcode or tap a chip. Non-WMS users get a "not found" response (server-side group check).

**Result:** A read-only answer page. Nothing is changed in the system — Find only reads stock, forecast, expiry, damage and repair data.

---

### Products (the WMS product list / form)
**Role:** Both (Storekeeper + Admin) — menu gated on `group_wms_user` (everyone with WMS access can view; creating/editing follows standard product permissions)
**Menu path:** WMS / Operations / Products
**Purpose:** See every product the trust stocks, open its WMS classification, and print its barcode label — without leaving the WMS app for the Inventory app.

> The list binds to `product.template` (action `action_wms_products`), with the list view = Odoo's `product.product_template_tree_view` and the form view explicitly bound to `product.product_template_only_form_view` so **New** always opens the WMS-classified template form (the F1 fix). The WMS-specific fields below are added by `wms_location` and grouped on a **WMS Classification** tab.

**Steps:**
1. Open **WMS / Operations / Products** to browse the catalogue.
2. Click a product to open its form; review the **WMS Classification** tab for the WMS fields.
3. To create one product here, click **New** and fill the classification (or use the guided "Create Product" wizard / "Onboard Products" for many — see those processes).
4. To print labels, tick one or more rows and choose **Action → Print labels (direct)** (the direct-print wizard; see "Label printing" below).

**Fields that matter for WMS (on `product.template`, all real field labels):**
- **WMS Kind** (`wms_product_kind`) — classification driving SKU prefix, default unit, returnable/expiry/min-life defaults.
- **Returnable** (`wms_is_returnable`) — whether Scan Return accepts it; auto-seeded from Kind, Admin can override.
- **Expected return (days)** (`expected_return_days`) — return SLA; 0 = use global default. Drives the overdue-returns alert.
- **Min re-request interval (days)** (`wms_min_life_days`) — how long the same department should wait before re-requesting; a too-soon request routes to Manager approval. 0 = no per-product guard.
- **Max per issue** (`wms_max_per_issue`) — hard single-issue cap (0 = none).
- **Daily cap (24h rolling)** (`wms_daily_cap`) — hard rolling-24h cap across all keepers (0 = none).
- **Expiry date** (`wms_expiry_date`), **Batch / lot number** (`wms_batch_number`) — power the Expiry Alert report / traceability.
- **Family** (`wms_family_id`), **Brand** (`wms_brand_id`), **Form / Model** (`wms_form_id`), **Variant** (`wms_variant`), **Pack size** (`wms_pack_size`), **Dosage / strength** (`wms_dosage`) — the structured identity that composes the human-readable Business SKU (`default_code`) and the immutable **Internal product code** (`wms_product_code`, PRD-######).
- Kind-specific extras (shown by kind): e.g. **Weight per unit (kg)** (`wms_weight_kg`), **Size**/**Colour**/**Material**, **Grade / specification**, **Dimensions**, **Diameter (mm)**/**Length (m)**, **Voltage (V)**/**Wattage (W)**, **Serial number** (`wms_serial_number`).
- The **barcode** (Code128 / EAN-13) and **SKU** are normally generated automatically on create.

**Buttons:**
- **New** — opens the WMS template form to create a classified product.
- **Action → Print labels (direct)** — opens `wms.label.print.wizard` for the selected rows (bound to both `product.template` and `product.product`).

**Validation / errors:** Standard product constraints apply. SKU prefix is checked against the kind (`@api.constrains` on `default_code`/`wms_product_kind`). Duplicate structured identity (Family + Brand [+ Form]) is blocked by `product.template.create()`.

**Result:** A maintained product catalogue; per product a generated SKU + barcode and the WMS classification used by issuing, returns, caps, expiry and reports.

---

### Create Product (guided) wizard
**Role:** Admin only — menu and action gated on `group_wms_manager` (ACL `model_wms_product_create` is manager-only)
**Menu path:** WMS / Operations / Create Product (guided)
**Purpose:** Walk an Admin through creating **one** fully classified product with a live SKU/barcode preview, category-driven required fields, inline creation of Family/Brand/Form, and an automatic duplicate block.

**Steps:**
1. Open **WMS / Operations / Create Product (guided)** (full-page form).
2. Pick the **Category** — it sets the **WMS Kind** and which identity fields are required.
3. Fill the **Identity**: **Family** (required), then **Brand / Form / Strength / Pack** as the category requires (use "Create and edit" to add a new Family/Brand/Form with its code). Optionally **Variant**.
4. Review the **Unit** (suggested from Form or Kind; editable) and optional **Unit cost**.
5. Edit the suggested **Product name** if needed (it is auto-suggested from the identity).
6. Watch the **Preview** block update live: **SKU**, **Code128**, **Internal product code**, **EAN-13**, and any duplicate warning.
7. Press **Create** (opens the new product), or **Create & New** (saves and reopens a blank wizard pre-set to the same Category).

**Fields:**
- **Category** (`categ_id`) *(required)*.
- **WMS Kind** (`wms_product_kind`) — derived from category (read-only compute).
- **Family** (`wms_family_id`) *(required)*; **Brand** *(required if category flags it)*; **Form / Model** *(required if flagged)*; **Strength / dosage / concentration** (`wms_dosage`) *(required if flagged)*; **Pack size** (`wms_pack_size`) *(required if flagged)*; **Variant** *(optional)*.
- **Unit** (`uom_id`) — computed/suggested, editable.
- **Unit cost (optional)** (`standard_price`).
- **Product name** (`name`) *(required)*.
- Preview (read-only): **SKU**, **Code128**, **Internal product code**, **EAN-13**, duplicate warning.

**Buttons:**
- **Create** → `action_create` — runs `product.template.create()` and opens the new product form.
- **Create & New** → `action_create_and_new` — creates and reopens the wizard for the next item (same category).
- **Cancel**.

**Validation / errors (real messages):**
- Missing required identity for the category: "This category requires: … . Fill them in so the product is properly classified and gets a complete SKU."
- Duplicate identity is blocked by the engine (`product.template.create()`), with a live heads-up in the form: "A product with SKU … already exists: …" plus "— adjust the Brand / Variant / Pack / Strength to make it distinct."

**Result:** One new `product.template` (type Goods, storable) with a composed Business SKU (`default_code`), an immutable internal code (PRD-######), and minted Code128 + EAN-13 barcodes.

---

### Onboard Products wizard
**Role:** Admin only — menu and action gated on `group_wms_manager` (ACLs `model_wms_product_onboard` / `..._line` are manager-only)
**Menu path:** WMS / Configuration / Onboard Products
**Purpose:** Bulk-create products, place their initial stock, and (optionally) print all their labels in one editable table — collapsing the old "create product → scan receipt → print label" loop into one screen, for one row or two hundred.

**Steps:**
1. Open **WMS / Configuration / Onboard Products** (pop-up with an editable table; a blue tip explains pasting names from Excel and the UoM behaviour).
2. Add rows (type, or paste a column of names from Excel/Sheets). For each row set **Product name** and **WMS Kind** (Kind drives the auto-SKU prefix and the default unit).
3. Set **Initial qty** (default 1; set 0 for catalog-only rows) and a **Slot** — pick from the dropdown or scan the slot's barcode into **Scan slot** (it auto-fills the Slot).
4. Fill conditional columns where relevant: **Expiry** (required for Medicine/Feed), **Batch**, **Litres**, **Return days**, **SKU**, **Barcode**, **Category**, **UoM**, **Unit cost**, **Default supplier**, **Unit price**.
5. Press **Onboard + Print labels** to create everything and open a combined label PDF, or **Onboard only** to create without printing.

**Fields (per row):**
- **Product name** (`name`) *(required)*; **WMS Kind** (`wms_product_kind`) *(required)*.
- **Initial qty** (`initial_qty`, default 1); **Slot** (`location_id`; required when qty > 0); **Scan slot** (`location_scan`).
- **Expiry** (`expiry_date`; required for medicine/feed), **Batch** (`batch_number`), **Litres** (`volume_litres`), **Return days** (`expected_return_days`).
- **SKU (optional)** (`default_code`), **Barcode (optional)** (`barcode`) — auto-generated if blank; must be globally unique if set.
- **Category** (`categ_id`), **UoM** (`uom_id`, restricted to warehouse-relevant units), **Unit cost (optional)** (`standard_price`), **Default supplier (optional)** (`supplier_id`), **Unit price (optional)** (`list_price`).

**Buttons:**
- **Onboard + Print labels** → `action_onboard` — validate, create products + initial stock, then open the combined thermal-label PDF.
- **Onboard only** → `action_onboard_no_print` → shows a success toast and closes (no PDF).
- **Cancel**.

**Validation / errors (real messages):**
- No rows: "You haven't added any products yet. Add at least one product row (with name, kind, quantity, and slot) before you can submit."
- Duplicate/used SKU: "SKU '…' is repeated on more than one row." / "SKU '…' is already used by an existing product."
- Duplicate/used barcode: "Barcode '…' is repeated on more than one row." / "Barcode '…' is already used by an existing product / alias."
- Invalid slot: "Slot '…' isn't a valid storage location - pick a slot or a floor zone."
- Missing kind: "Row '…' is missing a WMS Kind. Pick one (Tool, Consumable, Feed, Medicine, Pooja, Fluid) …"
- Negative qty: "Row '…': initial quantity cannot be negative."
- Qty without slot: "Row '…' has a starting quantity, so it needs a slot to live in. Scan the slot barcode, or pick it from the list. If you only want this product in the catalog (no stock yet), set the quantity to 0."
- Medicine/Feed without expiry: "Row '…' is a … product, and you must enter an expiry date from the supplier's label. …"
- Re-submit of an already-submitted batch: "This onboarding batch has already been submitted (…). Open a new 'Onboard products' wizard for the next batch."
- Soft (non-blocking) duplicate-name heads-up when typing a name that already exists; and a "Slot not found" warning if a scanned slot barcode doesn't match an internal location.

**Result:** N new products (each with auto SKU + Code128 + EAN-13 alias), initial stock placed in the chosen slots, and — for "Onboard + Print labels" — one combined PDF with a label per created product. A summary line reports e.g. "12 products onboarded with 240 units of stock placed."

---

### Issue Approvals (approve over-threshold / too-soon issues)
**Role:** Admin only — menu gated on `group_wms_manager`; Approve/Reject gated on `group_wms_can_approve_issue` (manager-only) **and** re-checked in-method against `group_wms_manager`. A keeper's ACL is read+create only, so a keeper can see a held request was created but cannot decide it.
**Menu path:** WMS / Operations / Approvals
**Purpose:** Let a Manager review a Scan Issue that was held because it is high-value or re-requested too soon, then **Approve** (which issues the stock against live inventory) or **Reject** (nothing moves).

**Steps:**
1. A keeper's high-value or too-soon issue is held automatically (state Pending), Managers are pinged via Discuss/inbox and get a To-Do activity. Nothing is issued yet.
2. Open **WMS / Operations / Approvals** (defaults to the Pending queue).
3. Open a request. Read **Why it was held** (High value / Requested too soon, the frozen **Issue value**, the too-soon product + last-issued date), the **Keeper's justification**, and the **Request** snapshot (warehouse, destination, department/purpose/animal, taken/ordered by, store keeper, usage note, planned lines, photo).
4. Press **Approve** to issue, or **Reject** to decline.

**Fields (read-only snapshot):** **Reason: High value** / **Requested too soon**, **Issue value** (frozen), **Too-soon product**, **Last issued (same dept)**, **Keeper's justification**, **Warehouse**, **Used by/area** (`destination_id`), **Department**, **Purpose / reason**, **Animal / cow**, **Expected return**, **Taken by**, **Ordered by**, **Store Keeper on duty**, **Reason / usage note**, **Planned lines** (Product/Slot/Will take/Expires), **Item photo**, **Status** (Pending/Approved/Rejected), and after a decision **Approved / rejected by** + decision date + **Issued delivery**.

**Buttons:**
- **Approve** → `action_approve` — re-plans against live stock, re-enforces the per-issue + rolling-24h caps as of now, then creates and validates the outbound delivery; state → Approved; opens the delivery.
- **Reject** → `action_reject` — state → Rejected; nothing issued; reason logged in chatter.
- **Delivery** (stat button) → `action_open_picking` — opens the issued delivery (after approval).

**Validation / errors (real messages):**
- Non-manager forced call: "Only a WMS Manager can approve or reject a held issue. Ask a Manager to review this request." (`AccessError`).
- Already decided: "This request has already been approved/rejected — there is nothing left to approve." / "… it can no longer be rejected."
- Stock moved since the request: "Stock for … has moved since this request was made — the warehouse can no longer cover the requested quantity (…, short by …). Nothing was issued. Reject this request and ask the keeper to scan it again …"
- Caps re-checked at approval may still block with the same Max-per-issue / Daily-cap messages as Scan Issue.
- Double/concurrent approve is safe — the second caller re-opens the already-created delivery (row-lock idempotency on `picking_id`).

**Result:** On Approve, a validated outbound delivery (origin "Barcode FIFO issue (approved APR-#####)") with the full audit trail and the keeper's photo carried onto it; the approval flips to Approved and links the delivery. On Reject, the approval flips to Rejected and no stock moves. The held record is append-only (no delete) and the Manager's To-Do activity is cleared either way.

**Approval thresholds (Admin-tunable System Parameters, in `data/wms_approval_params.xml`):** master switch `wms_barcode.issue_approval_enabled` ('1' = on); high-value threshold `wms_barcode.high_value_threshold` (default 5000); the too-soon window comes from each product's **Min re-request interval (days)** (`wms_min_life_days`) or the global `wms_location.default_min_life_days`.

---

### Carton / Packaging / Alias Barcodes
**Role:** Both (Storekeeper + Admin) — menu gated on `group_wms_can_manage_catalog` (typically Admin work; the keeper "Can manage Carton aliases + Labels" capability is OFF by default). Per the ACL, `group_wms_user` can read the alias table but only `group_wms_manager` can create/edit.
**Menu path:** WMS / Operations / Carton Barcodes
**Purpose:** Map many physical barcodes to one product so a vendor carton sticker (e.g. "CTN-COKE-24") resolves to the product with the right unit count — while the product's own unit barcode still works.

**Steps:**
1. Open **WMS / Operations / Carton Barcodes** (an editable list).
2. Add a row: enter the **Barcode** (the carton/box sticker code), choose the **Product**, set **Units per scan** (how many product units one scan represents), and an optional **Note**.
3. Save. The alias now resolves on every scan in Scan Receipt / Scan Issue (a carton scan auto-fills its unit count).

**Fields:**
- **Barcode** (`barcode`) *(required, unique)*.
- **Product** (`product_id`) *(required)*.
- **Units per scan** (`units_per_scan`) *(required, must be > 0; default 1)*.
- **Note** (`note`) — optional.

**Buttons:** Standard editable-list controls (inline add/edit/save). No custom action buttons.

**Validation / errors (real messages):**
- Duplicate alias barcode: "Each carton barcode must be unique." (DB constraint.)
- Units per scan ≤ 0: "Units per scan must be greater than zero."
- Collision checks (`@api.constrains`): the alias barcode is format-validated (EAN-13 check digit) and rejected if it duplicates a product's unit barcode ("Barcode … is already a product's unit barcode."), a location barcode ("… is already a location barcode."), or a lot/serial ("… is already a lot / serial number.").

**Result:** A `wms.barcode.alias` row. The scan resolver (`resolve()`) searches product unit barcode → carton alias → lot → location, so scanning the carton code anywhere in the scan wizards yields the right product and multiplied quantity.

---

### Label printing + Label Printers + Label Settings
This covers three related pieces: how staff **print labels**, how an Admin sets up the **printer profile**, and how an Admin tunes the **label layout/geometry**.

#### A) Print labels (direct to printer) — the everyday action
**Role:** Both (Storekeeper + Admin) — the wizard ACL `model_wms_label_print_wizard` allows `group_wms_user`; the action is reachable from the Products / Slots / Racks / Compartments Action menu.
**Where:** Action (cog) menu → **Print labels (direct)** on the **Products** list/form and on the **Slots / Racks / Compartments** (`stock.location`) list/form. (Bound to `product.product`, `product.template`, and `stock.location`.)
**Purpose:** Send labels straight to the thermal printer in its native TSPL language — no browser print dialog, no PDF.

**Steps:**
1. Tick one or more products (or locations).
2. Choose **Action → Print labels (direct)**.
3. In the pop-up, confirm the **Printer** (defaults to the default printer) and **Copies** (default 1).
4. Press **Print**. A success toast reports e.g. "Sent 12 label(s) ×1 to Thermal label printer." (and notes any records skipped for having no barcode).

**Fields:** **Printer** (`printer_id`, required), **Copies** (default 1, required), **Selected** count summary (read-only).

**Buttons:** **Print** → `action_print`; **Cancel**.

**Validation / errors (real messages):**
- Wrong screen: "Label printing isn't available for this screen. Use it from the Products list or the Slots / Racks / Compartments lists."
- Copies < 1: "Copies must be at least 1."
- None of the selected has a barcode: "None of the selected records has a barcode to print. Set a barcode on them first (Configuration → Onboard Products, or the location form)."

**Result:** One physical label per selected record (× copies). Products print the name, SKU + unit sub-line, and the Code128/EAN-13 barcode; locations print the barcode + name with the parent path + location type.

> Fallback path: a QWeb PDF report **WMS Product Label (100×25mm)** / **WMS Location Label (100×25mm)** also exists (`action_report_wms_product_label_thermal` / `..._location_...`) on a 100×25 mm portrait paper format at 203 DPI. It is **unbound from the Print menu on purpose** (direct printing is the primary path to avoid browser scaling) but is still used by the Onboard wizard's combined PDF.

#### B) Label Printers — printer profile setup
**Role:** Admin only — menu gated on `group_wms_manager` (ACL is manager-only for create/edit).
**Menu path:** WMS / Configuration / Label Printers
**Purpose:** Define the reusable thermal-printer profile (which spooler/network printer, media size, darkness, alignment), so staff can print with one click. The trust's TSC TE244 is seeded by default (`data/wms_label_printer_data.xml`).

**Steps:**
1. Open **WMS / Configuration / Label Printers** → **New** (or open the seeded "Thermal label printer").
2. Pick **Connection**: "Windows printer (USB / local)" or "Network (IP)".
3. For USB/local, set the **Windows printer name** (use **Detect printers** to see exact names); for network, set **IP address** (and **Port**, default 9100).
4. Set **Label media** (**Label width/height (mm)**, **Gap between labels (mm)**, **dpi**) and **Print quality** (**density**, **speed**).
5. Optionally set **Alignment** nudges (**Shift right (mm)**, **Shift down (mm)**) and a **Brand line**.
6. Tick **Default printer** if this should be pre-selected. Press **Test print** to check setup/alignment.

**Fields:** **Name** *(required)*, **Default printer** (`is_default`), **Connection** *(required)*, **Windows printer name** (`system_name`; required for spooler), **IP address** (`host`; required for network), **Port** (`port`, default 9100), **Label width (mm)** / **Label height (mm)** *(required, > 0)*, **Gap between labels (mm)**, **dpi** *(required, 203)*, **density** (0–15), **speed**, **Shift right (mm)** / **Shift down (mm)**, **Brand line** (default "Mercy & Care For Cows Dakshin Vrindavan PCT"), **Notes**.

**Buttons:** **Test print** → `action_test_print` (sends a sample label, then a success toast); **Detect printers** → `action_detect_printers` (lists Windows printers the server can see).

**Validation / errors (real messages):**
- "Label width and height must be greater than 0."
- "A USB / local printer needs the Windows printer name." / "A network printer needs an IP address."
- At print time, unreachable network printer: "Could not reach printer … at host:port — …"; missing pywin32 on a non-Windows server: "Direct USB printing needs pywin32 on the server (Windows). … Use a Network printer, or print the PDF label as a fallback."; unknown spooler name: "Printer '…' was not found on the server. Available: … Fix the name in Configuration → Label Printers, or check the printer is on."; print failure: "Printing to '…' failed: … Check the printer is on, connected, and not paused, then try again."
- Barcode too long / non-ASCII for the printer: "Barcode '…' is too long to print: … a label can encode at most 48. …" / "Barcode '…' cannot be printed: it contains a character … the label printer does not support. …"
- Only one printer can be the default (others are un-defaulted automatically).

**Result:** A reusable `wms.label.printer` profile used by the Print-labels wizard and the Onboard wizard.

#### C) Label Settings — label layout/geometry
**Role:** Admin only — menu under Configuration; ACL allows `group_wms_user` read but only `group_wms_manager` create/edit.
**Menu path:** WMS / Configuration / Label Settings
**Purpose:** Control where the barcode, logo and text sit on the thermal sticker (used by the QWeb PDF label and the logo on direct-print labels). All measurements are millimetres; set a width/height to 0 to hide an element.

**Steps:**
1. Open **WMS / Configuration / Label Settings** → **New** (or open the existing profile).
2. Set **Sticker size** (width/height/gap) and toggle **Active**.
3. Position the **Barcode** block (left/top/width/height), and choose whether to **Show the number below the bars** (and its font size).
4. Upload an optional **Logo** and place it (left/top/width/height).
5. Toggle/position **Product / location name** (title) and **SKU / sub-line**, with font sizes/bold.
6. Save.

**Fields (real labels):** **Profile** (`name`, default "Default thermal label"), **Active**, **Company**; **Label width (mm)** / **Label height (mm)** / **Gap between labels (mm)**; **Logo** + **Logo left/top/width/height (mm)**; **Show product / location name** + **Title left/top/width (mm)**, **Title font size (pt)**, **Title bold**; **Show SKU / sub-line** + **Sub-line left/top/width (mm)**, **Sub-line font size (pt)**; **Barcode left/top/width/height (mm)**, **Show the number below the bars**, **Number font size (pt)**.

**Buttons:** Standard form save. (No custom action buttons.)

**Validation / errors (real messages):** The barcode box must stay scannable at 203 DPI: "Barcode width is … mm; it must be at least 40.0 mm so the Code128 bars stay scannable at 203 DPI. The default is 74 mm." and "Barcode height is … mm; it must be at least 8.0 mm … The default is 12 mm."

**Result:** A `wms.label.config` profile (resolved per company by `get_active()`). If no profile exists the shipped defaults are used, so labels still print on a fresh install.

---

### Quick reference — menus and gating (this section)

| Menu | Path | Action | Role gate |
|---|---|---|---|
| Scan Receipt | WMS / Operations / Scan Receipt | `action_wms_scan_receipt` | `group_wms_can_scan_receive` |
| Scan Issue | WMS / Operations / Scan Issue | `action_wms_scan_issue` | `group_wms_can_scan_issue` |
| Scan Return | WMS / Operations / Scan Return | `action_wms_scan_return` | `group_wms_can_scan_receive` |
| Find / Where is it? | WMS / Operations / Find / Where is it? | `action_wms_find` (URL `/wms/find`) | `group_wms_user` |
| Approvals | WMS / Operations / Approvals | `action_wms_issue_approval` | `group_wms_manager` |
| Products | WMS / Operations / Products | `action_wms_products` | `group_wms_user` |
| Create Product (guided) | WMS / Operations / Create Product (guided) | `action_wms_product_create` | `group_wms_manager` |
| Carton Barcodes | WMS / Operations / Carton Barcodes | `action_wms_barcode_alias` | `group_wms_can_manage_catalog` |
| Onboard Products | WMS / Configuration / Onboard Products | `action_wms_product_onboard` | `group_wms_manager` |
| Store Keepers | WMS / Configuration / Store Keepers | `action_wms_storekeeper` | (Configuration menu; create-login + capability edits gated on `group_wms_manager`) |
| Label Printers | WMS / Configuration / Label Printers | `action_wms_label_printers` | `group_wms_manager` |
| Label Settings | WMS / Configuration / Label Settings | `action_wms_label_config` | (Configuration menu; edit gated on `group_wms_manager`) |
| Print labels (direct) | Action menu on Products / Locations | `wms.label.print.wizard` | `group_wms_user` (via Action menu) |

*Store Keepers note:* the roster + per-keeper capability grants live on the
`wms.storekeeper` form (WMS / Configuration / Store Keepers). An Admin creates a
keeper's Odoo login with **Create Odoo login** (`action_create_login`, defaults
ON: Scan Receipt/Return, Scan Issue, file Damage, submit Audit; Manage Catalog
OFF) and toggles each capability checkbox (**Can Scan Receipt / Return**, **Can
Scan Issue**, **Can file Damage events**, **Can submit Inventory audits**, **Can
manage Carton aliases + Labels**) — these write through to the matching Odoo
groups. The on-duty keeper picked on each Scan Issue / Scan Receipt comes from
this roster.
## 2. Configuration & Warehouse Setup

This section covers the one-time and occasional setup an Admin (WMS / Manager) performs before and during daily warehouse operation: building the physical location hierarchy, the bulk generators that create it quickly, the catalogue master registers that feed structured SKUs and the Scan Issue form, the Store Keeper roster, and the security/role model that decides who can do what.

Almost everything in this section lives under the **WMS / Configuration** menu, which is itself restricted to the WMS / Manager group (`menu_wms_config` carries `groups="wms_location.group_wms_manager"`). A few browse-only views (Slots, Floor Zones) live under **WMS / Operations** and are visible to Store Keepers as well.

A naming note used throughout: where a heading says "(label from view)" the visible field label is set in the form/list XML and may differ from the underlying technical field name; where a real string is quoted it is taken verbatim from the model `string=` attribute or the view.

---

### Warehouse layout hierarchy: Zones, Racks, Compartments, Slots, Floor Zones

**Role:** Admin only (creation); Both (Storekeeper + Admin) can browse Slots and Floor Zones
**Menu path:** WMS / Configuration (Zones, Racks, Compartments) and WMS / Operations (Slots, Floor Zones)
**Purpose:** Defines how physical storage is modelled as nested `stock.location` records so every scan, FIFO/FEFO issue, and report resolves to a precise place.

**How the levels nest.** Every level is one `stock.location` row carrying a `wms_location_type` (technical field, labelled "WMS Type"). The selection values (from `LOCATION_TYPES` in `models/stock_location.py`) are:

1. **Warehouse view** (`warehouse_view`) — the top container (Odoo's own warehouse/stock view location).
2. **Zone** (`zone`, label "Zone (building / floor / area)") — a `usage='view'` umbrella such as "1st Floor", "Ground Floor / East", "Outside Yard". A zone holds racks and/or floor zones. Zones are optional: racks and floors can also sit directly under the warehouse stock location.
3. **Rack** (`rack`) — a `usage='view'` shelving unit. Carries `wms_rack_code` ("Rack code", e.g. R01, PHARM01), `wms_shelf_count` ("Shelves", default 6) and `wms_column_count` ("Columns", default 3). Shelves and columns are *grid coordinates*, not their own location rows.
4. **Compartment** (`compartment`) — a `usage='view'` 2D rectangle on the rack grid. Carries the bounding box `wms_shelf_top` / `wms_shelf_bottom` ("Shelf top"/"Shelf bottom") and `wms_column_left` / `wms_column_right` ("Column left"/"Column right"), plus `wms_slot_count` ("Slots", default 1). A compartment may be a single 1x1 cell, or span several shelves (tall), several columns (wide), or a block. Non-rectangular (L/T/U) shapes store their exact cells in `wms_cells_json`.
5. **Slot** (`slot`) — a `usage='internal'` row; this is the only rack level that actually holds stock (`stock.quant`). Carries `wms_slot_number` ("Slot #") and an optional `wms_capacity_units` ("Capacity (units)", a soft hint, not enforced). One or more slots sit inside each compartment.
6. **Floor / Open area** (`floor`, label "Floor / Open area") — a `usage='internal'` row that holds stock directly with no rack/compartment/slot beneath it. Used for pallet areas, single-shelf slabs, outside-yard bays, receiving/staging benches.

So the rack branch is exactly three location levels deep — Rack (view) -> Compartment (view) -> Slot (internal) — with shelf/column being coordinates on the rack. Floor zones are a parallel one-level branch that hangs under a zone or the warehouse stock location.

**Display names** are made self-contained automatically (`_compute_display_name`): a compartment reads like `R12 / SH01-03 / C01` and a slot like `R12 / SH01 / C01 / SL01`. Shelf ranges render as `SH01` or `SH01-03`; column ranges as `C01` or `C01-03`.

**Fields (on the location form, "WMS hierarchy" group):** `wms_location_type` (WMS Type); plus rack-only `wms_rack_code`, `wms_shelf_count`, `wms_column_count`; compartment-only `wms_shelf_top/bottom`, `wms_column_left/right`, `wms_slot_count`; slot-only `wms_slot_number`, `wms_capacity_units`. Read-only occupancy fields `wms_current_qty` ("On hand"), `wms_occupancy_pct` ("Occupancy %") and `wms_product_ids` ("Products here") are computed from live quants.

**Validation / errors (DB and Python constraints):**
- A rack must have at least 1 shelf and at least 1 column; a compartment at least 1 slot; shelf_bottom must be >= shelf_top and column_right >= column_left (SQL CHECK constraints).
- Hierarchy guard (`_check_hierarchy`): "A compartment's parent must be a Rack ...", "A slot's parent must be a Compartment ...". A compartment's shelf/column numbers must fall inside the parent rack's 1..N ranges, else e.g. "shelf_top=7 is outside the rack's 1..6 shelf range."
- Barcode uniqueness (`_check_barcode_globally_unique`): a location barcode must be globally unique — "Location barcode <code> is already used by another location." This is stricter than Odoo core (which allows NULL company collisions).
- Delete guard (`_wms_block_delete_when_used`): a rack/compartment/slot/floor cannot be deleted if it still has sub-locations, holds stock, or has any stock-move history; the message tells the operator to empty it and **archive (deactivate)** instead, e.g. "... still has N sub-location(s) inside it ...", "... still has X unit(s) of stock in it ...", and the history case "... mark it as 'Archived' (inactive) ...".

**Result:** A nested tree of `stock.location` records that the scan, FIFO/FEFO planner, and reports use. Stock only ever lands in slots and floor zones (the `internal` levels).

---

### Generate Zone wizard (bulk zone + racks + floor zones)

**Role:** Admin only
**Menu path:** WMS / Configuration / Generate Zone
**Purpose:** Create a named zone and, in the same click, generate any number of identical racks and/or floor zones inside it.

**Steps:**
1. Open WMS / Configuration / Generate Zone (a dialog opens; model `wms.zone.generator`).
2. Confirm **Warehouse** (`warehouse_id`, required, defaults to the first warehouse).
3. Confirm **Parent location** (`parent_location_id`, required; domain limited to `usage='view'` locations; defaults to the warehouse stock location) — where the new zone will live.
4. Enter the zone name in **zone_name** (required, placeholder "1st Floor").
5. Under "Racks", set how many racks and their grid (leave Racks count 0 for a pure container zone).
6. Under "Floor zones (no rack)", set how many open floor zones to create (leave 0 to skip).
7. Click **Generate**.

**Fields:**
- `warehouse_id` (required), `parent_location_id` (required, view-only domain), `zone_name` (required).
- Racks group: `rack_count` (default 0); and, shown only when rack_count > 0: `rack_start_number` ("Starting rack number", default 1 — use 33 if R01..R32 already exist), `rack_prefix` (default "R", so R -> R01, R02 …), `rack_shelf_count` ("Shelves per rack", default 6), `rack_column_count` ("Columns per rack", default 3), `rack_slot_count` ("Slots per compartment", default 1), `rack_capacity_per_slot` (default 0).
- Floor group: `floor_count` (default 0); and, shown only when floor_count > 0: `floor_start_number` (default 1), `floor_prefix` (default "F"), `floor_capacity` (default 0).

**Buttons:** **Generate** (`action_generate`) builds the zone, then the racks, then the floor zones, and opens the new zone's form. **Cancel** closes without changes.

**Validation / behaviour:** Idempotent and safe to re-run. If a zone with the same name already exists under the parent it is reused (and re-typed to `zone` if needed). Racks delegate to the Create Rack wizard in quick-grid mode (every rack the same shelves x columns); a rack code that already exists anywhere is skipped (`continue`). Floor zones delegate to the Generate Floor Zones wizard. After running, the result-form context carries a summary like "Created zone with N new rack(s) and M floor zone(s)."

**Result:** One zone `view` location plus the requested racks (each with its compartments and slots) and floor zones, all parented under the zone.

---

### Create Rack wizard (single rack, quick grid or visual layout)

**Role:** Admin only
**Menu path:** WMS / Configuration / Create Rack
**Purpose:** Create one rack with its compartments and slots, either as a uniform grid or as a custom layout drawn in the visual Rack Builder.

**Steps (Quick grid):**
1. Open WMS / Configuration / Create Rack (dialog opens; model `wms.rack.generator`).
2. Set **Warehouse** (`warehouse_id`, required).
3. Set **Parent location** (`parent_location_id`, required; defaults to the warehouse stock location) — usually a Zone (e.g. "Pharmacy") or the warehouse stock location.
4. Enter **rack_code** (required, default "R01", placeholder "R01"); optionally a **Display name** (`rack_name`, placeholder "Optional display name").
5. Optionally set **capacity_per_slot** (soft cap per slot).
6. On the "Quick grid" tab set `shelf_count` ("Shelves", default 6), `column_count` ("Columns", default 3), `default_slot_count` ("Slots per compartment", default 1).
7. Click **Create rack**.

**Steps (Visual builder / custom layout):**
1. Switch to the "Visual builder" tab.
2. Click cells in the preview to select, then use **Merge up** / **Merge down** / **Split** to build spanning or merged compartments and set slot count per compartment in the side panel (the widget writes `layout_json` for you).
3. Click **Create rack**. When `layout_json` has a value it overrides the Quick grid inputs.

**Fields:** `warehouse_id` (required), `parent_location_id` (required), `rack_code` (required), `rack_name` (optional), `capacity_per_slot` (optional), `shelf_count` (required), `column_count` (required), `default_slot_count` (required), `layout_json` ("Custom layout", auto-generated — leave alone unless hand-crafting).

**Buttons:** **Create rack** (`action_generate`) builds the rack and opens its form. **Cancel** (`special="cancel"`). In the Visual builder: **Merge up / Merge down / Split** (Rack Builder OWL widget) shape compartments before generating.

**Validation / errors:**
- "You must have at least 1 shelf and 1 column on the rack ..." if shelf_count or column_count < 1; "Slots per compartment must be at least 1." if default_slot_count < 1.
- Duplicate rack: "A rack with code <code> already exists under <parent>."
- Custom layout: malformed JSON -> "The custom layout file isn't formatted correctly ..."; missing keys -> "The custom rack layout is incomplete (missing <key>) ..."; out-of-range cells -> "Compartment #N references shelf/column ... out of range 1..M"; overlap -> "Cell (shelf S, column C) is covered by two compartments ... Compartments cannot overlap."

**Result:** One rack (`view`) with its compartments (`view`) and slots (`internal`). Slots receive auto-generated, globally-unique barcodes of the form `<rack_code>-SH<top>[-<bottom>]-C<left>[-<right>]-SL<slot>` (zero-padded), e.g. `R01-SH01-C01-SL01` or `R01-SH01-03-C01-03-SL01`. The rack's own barcode equals its rack code.

---

### Generate Floor Zones wizard (open-area locations)

**Role:** Admin only
**Menu path:** WMS / Configuration / Generate Floor Zones
**Purpose:** Create one or more open-area stocking locations (no rack/shelf/slot hierarchy) that hold stock directly and are scannable.

**Steps:**
1. Open WMS / Configuration / Generate Floor Zones (dialog opens; model `wms.floor.zone.generator`).
2. Set **Warehouse** (`warehouse_id`, required).
3. Set **Parent area** (`parent_location_id`, required; domain limited to `usage='view'`; defaults to the warehouse stock location).
4. Set **zone_prefix** (required, default "F"; prefix for names + barcodes, e.g. F -> F-01, F-02).
5. Set **start_number** (required, default 1) and **count** (required, default 1).
6. Optionally set **capacity_units** (soft capacity per zone).
7. Click **Generate**.

**Fields:** `warehouse_id` (required), `parent_location_id` ("Parent area", required), `zone_prefix` (required), `start_number` (required), `count` (required), `capacity_units` (optional).

**Buttons:** **Generate** (`action_generate`) creates the zones and opens the resulting list so labels can be printed immediately. **Cancel** (`special="cancel"`).

**Validation / behaviour:** "Count must be at least 1." if count < 1. Idempotent — a floor zone whose name already exists under the parent is skipped; if nothing new is created the wizard shows an info toast "Nothing to do / Every requested zone already exists." Barcodes are built from the parent name's first 4 alphanumerics plus the code (e.g. `PHAR-F-01`); on a barcode clash it falls back to a parent-id-keyed barcode, and only if that also clashes does it error: "Cannot generate floor zone <code>: the barcode <bc> already belongs to <loc>. Rename the parent location or choose a different zone prefix ..."

**Result:** One `internal` `stock.location` per requested number (`wms_location_type='floor'`), each with a unique scannable barcode, ready for receiving, FIFO/FEFO issue, and reports.

---

### Browse Slots

**Role:** Both (Storekeeper + Admin)
**Menu path:** WMS / Operations / Slots
**Purpose:** The storage map — view every slot, its barcode, on-hand quantity, occupancy, and which products sit there.

**Steps:**
1. Open WMS / Operations / Slots (action `action_wms_slots`, domain `wms_location_type='slot'`).
2. The list opens grouped by compartment (`search_default_group_rack` is on by default). Switch to Kanban for a quick visual occupancy board, or open a slot's form.
3. Search by **Slot** name (`complete_name`) or **barcode**; use the "Group by Compartment" filter.

**Fields shown (list):** `complete_name` (as "Slot"), `barcode`, `wms_slot_number`, `wms_capacity_units`, `wms_current_qty`, `wms_occupancy_pct` (percentage), `wms_product_ids` (tags).

**Buttons:** None specific — this is a browse view. The empty-state help points operators to Scan Receipt / Scan Issue (Operations) and, for managers, to Configuration -> Generate Zone / Create Rack.

**Result:** Read-only visibility into slot occupancy. Slots are created by the generators, not here.

---

### Browse Floor Zones

**Role:** Both (Storekeeper + Admin)
**Menu path:** WMS / Operations / Floor Zones
**Purpose:** List the open-area floor locations and their barcodes.

**Steps:**
1. Open WMS / Operations / Floor Zones (action `action_wms_floor_zones`, domain `wms_location_type='floor'`).
2. Browse the list or open a floor zone's form.

**Fields:** Standard location list/form (each floor zone carries `barcode` and optional `wms_capacity_units`).

**Buttons:** None specific (browse view). Empty-state help points managers to Configuration -> Generate Floor Zones.

**Result:** Read-only visibility into floor zones. (Racks and Compartments have equivalent manager-side browse actions under Configuration: `action_wms_racks`, `action_wms_compartments`; Zones under Configuration via `action_wms_zones`.)

---

### Move racks / floor zones to a Zone (batch reparent)

**Role:** Admin only
**Menu path:** Action menu on any rack/floor list -> "Move to Zone" (no standalone Configuration menu)
**Purpose:** Reorganise existing racks or floor zones by moving them under a chosen zone in one transaction (e.g. move 32 racks created under WH/Stock into a new "1st Floor" zone).

**Steps:**
1. In a list of locations (e.g. Racks or Floor Zones) tick the racks/floor zones to move.
2. Open the list Action menu (the hamburger / ☰ Action) and choose **Move to Zone**.
3. In the dialog (`wms.move.to.zone`) pick the **Target zone** (`target_zone_id`, required; domain limited to `zone` locations). The selected locations are listed read-only.
4. Click **Move**.

**Fields:** `target_zone_id` ("Target zone", required), `location_ids` ("Locations to move", read-only list; domain rack/floor only).

**Buttons:** **Move** (`action_move`) reparents the records; **Cancel**.

**Validation / errors:** The Action entry itself is gated in code — non-managers get "Only WMS Managers can move racks or zones. Ask an admin." Selecting nothing of the right type -> "Select at least one Rack or Floor zone to move." Cross-company target -> "Location <x> belongs to company <a> but target zone is in <b>." On success a toast reads "N location(s) moved under zone <name>." Existing quants do not move; only the parent changes.

**Result:** The selected racks/floor zones now hang under the chosen zone; history and stock are untouched.

---

### Catalogue masters — overview

**Role:** Admin only to add/edit; Store Keepers have read-only access (per `ir.model.access.csv`: every `*_user` row is read=1, write/create/unlink=0; `*_manager` rows have full rights).
**Menu path:** WMS / Configuration / (Departments, Purposes, Animals, Families, Brands, Forms, Categories)
**Purpose:** Small admin-editable registers that feed two things: the structured SKU builder (Family / Brand / Form codes, plus the Category tree) and the Scan Issue form's classification fields (Department, Purpose, Animal).

The seven masters and what each is for:

1. **Families** (`wms.family`) — the generic group an item belongs to (Paracetamol, Cow Feed, Liv52, Floor Cleaner). Its short UPPERCASE code (e.g. PARA) becomes a SKU segment.
2. **Brands** (`wms.brand`) — the manufacturer or label (Himalaya, Cipla, Lizol, Bosch, "Local"). Short code (e.g. CIP) becomes a SKU segment.
3. **Forms** (`wms.form`) — the physical form (Tablet, Syrup, Spray, Powder, Pellet) or, for tools/spares, the Model. Short code (e.g. TAB) becomes a SKU segment; also carries a "Suggested unit" that pre-fills a new product's unit of measure.
4. **Categories** (`product.category`, extended) — the native, admin-editable product hierarchy (Animal Care > Medicines, Feed > Concentrate, …). Each category can set a default WMS kind and a required-identity matrix for new products.
5. **Departments** (`wms.department`) — the issue department / cost centre on Scan Issue (Gaushala, Veterinary Hospital, Dairy, …).
6. **Purposes** (`wms.purpose`) — the reason an item is issued (Routine consumption, Animal treatment, Vaccination …); an optional second dimension on an issue.
7. **Animals** (`wms.animal`) — a lightweight register of animals (by name / ear-tag) an issue can optionally be attributed to.

Common behaviour: Families/Brands/Forms share an abstract base (`wms.coded.master`) — `name` (required, translatable), `code` (required), `sequence`, `active`. Codes are forced UPPERCASE and trimmed on save; names are whitespace-normalised. Rows are **archived, never deleted**, so old SKUs and pickings keep resolving. The list views are editable inline (`editable="bottom"`) with a drag handle for `sequence`.

---

### Catalogue master: Families

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Families
**Purpose:** Maintain the product-family register whose codes form a SKU segment.

**Steps:** Open WMS / Configuration / Families. The list is inline-editable: click the bottom blank row (or "Add a line"), type the **name** and **code**, optionally drag the handle to reorder, and save. Or open the form to edit name, code, sequence, active.

**Fields:** `name` (required), `code` (required, UPPERCASE, max 6 chars, letters/digits only), `sequence`, `active` (archive toggle, shown via "Archived" ribbon on the form).

**Buttons:** Standard save/discard; no custom action buttons.

**Validation / errors:** Code too long -> "Code '<x>' is too long — keep it to 6 characters or fewer."; non-alphanumeric -> "Code <x> may use letters and digits only ..."; duplicate code -> "This family code is already used — each code must be unique."; near-duplicate name (case/whitespace, incl. archived) -> "“<name>” already exists (code <code>). Pick the existing entry instead of creating a near-duplicate ..."

**Result:** A reusable family row whose stable code feeds the structured SKU builder.

---

### Catalogue master: Brands

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Brands
**Purpose:** Maintain the brand/manufacturer register whose codes form a SKU segment.

**Steps:** Open WMS / Configuration / Brands; add a line in the inline list (name + code) or use the form.

**Fields:** `name` (required), `code` (required, UPPERCASE, max 6 chars, alphanumeric), `sequence`, `active`.

**Buttons:** Standard save/discard.

**Validation / errors:** Same coded-master rules as Families; duplicate code -> "This brand code is already used — each code must be unique."

**Result:** A reusable brand row feeding SKUs.

---

### Catalogue master: Forms

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Forms
**Purpose:** Maintain the form/model register (tablet, syrup, powder, … or tool model) whose codes feed SKUs and which can suggest a default unit for new products.

**Steps:** Open WMS / Configuration / Forms; add a line with **name**, **code**, and optionally **default_uom_id** ("Suggested unit"); or use the form.

**Fields:** `name` (required), `code` (required, UPPERCASE, **max 4 chars**, alphanumeric), `default_uom_id` ("Suggested unit", optional), `sequence`, `active`.

**Buttons:** Standard save/discard.

**Validation / errors:** Coded-master rules with the 4-char cap; duplicate code -> "This form code is already used — each code must be unique." The suggested unit only seeds a new product's UoM; it never changes the unit once stock exists.

**Result:** A reusable form row feeding SKUs and the new-product UoM suggestion.

---

### Catalogue master: Categories

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Categories
**Purpose:** Maintain the editable product-category tree and, per category, the default WMS kind and which identity fields a new product must carry.

**Steps:** Open WMS / Configuration / Categories. Create or open a category; set its parent to build the hierarchy. In the "WMS classification" group set the options below. Save.

**Fields (WMS classification group, added to the native category form):** `active` (archive toggle, default on); `wms_default_kind` ("Default WMS kind") — one-way hint that pre-selects the Kind in the new-product wizard; `wms_form_is_model` ("Show 'Form' as 'Model'") — relabels Form as Model for tools/spares. Required-identity sub-group "Required for new products in this category": `wms_req_brand` ("Brand required"), `wms_req_form` ("Form required"), `wms_req_strength` ("Strength required"), `wms_req_size` ("Size required"), `wms_req_pack` ("Pack required"). (These required flags are carried/inherited down the tree but are inert until a later phase wires enforcement.)

**Buttons:** Standard save/discard.

**Validation / errors:** Duplicate name under the same parent (case/whitespace, archive-inclusive) -> "A category named “<name>” already exists under the same parent. Rename it or reuse the existing one." A "Cleaning" under two different parents is allowed.

**Result:** An editable category hierarchy; each category can steer new-product defaults and (eventually) required fields.

---

### Catalogue master: Departments

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Departments
**Purpose:** Maintain the issue department / cost-centre register selected on Scan Issue.

**Steps:** Open WMS / Configuration / Departments; add a line with **name** and **code** (and optionally `legacy_issued_for`), or use the form.

**Fields:** `name` (required, translatable), `code` (required, unique), `sequence`, `legacy_issued_for` (old selection key kept for reporting reconciliation), `active`.

**Buttons:** Standard save/discard.

**Validation / errors:** Duplicate code -> "Department code must be unique."

**Result:** A department row available to the Scan Issue form. The module seeds a starter list (Gaushala/Cowshed, Veterinary Hospital, R&D/Panchgavya, Dairy, Fodder & Agriculture, Kitchen/Bhojanalaya, Maintenance/Repairs, Construction/Project, Administration/Office, Temple/Pooja, Other) with `noupdate="1"` so edits survive upgrades; "Other" (`dept_other`) must always exist as the Scan Issue default.

---

### Catalogue master: Purposes

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Purposes
**Purpose:** Maintain the optional "reason for issue" register.

**Steps:** Open WMS / Configuration / Purposes; add a line with **name** (and optional **note**), or use the form.

**Fields:** `name` (required), `sequence`, `note` (optional), `active`.

**Buttons:** Standard save/discard.

**Validation / errors:** No special constraints beyond `name` being required.

**Result:** A purpose row available as an optional dimension on an issue. Seeded starter list: Routine consumption, Animal treatment, Vaccination / deworming, Maintenance / repair, Research / Panchgavya, Other.

---

### Catalogue master: Animals

**Role:** Admin only (Store Keepers read-only)
**Menu path:** WMS / Configuration / Animals
**Purpose:** Maintain a lightweight register of animals an issue can optionally name (a treatment, a feed ration).

**Steps:** Open WMS / Configuration / Animals; add a line with **name** and optionally **tag**, **shed**, **age_class**; or use the form.

**Fields:** `name` (required), `tag` ("Ear-tag / token number", optional), `shed` (free text), `age_class` (selection: Calf, Heifer, Cow, Dry / Pregnant, Bull, Ox, Retired), `active`.

**Buttons:** Standard save/discard.

**Validation / errors:** Duplicate ear-tag -> "Animal tag must be unique." (Many blank tags are allowed — only entered tags must be unique.)

**Result:** An animal row that can be referenced from a Scan Issue; never required.

---

### Store Keepers (the roster used by Scan Issue)

**Role:** Admin only (the roster lives under manager-gated Configuration; capability toggles and the login buttons are further restricted to WMS / Manager)
**Menu path:** WMS / Configuration / Store Keepers
**Purpose:** Hold the list of humans who work the store desk so every Scan Issue / Damage / Audit records the real person, and optionally give each keeper their own Odoo login with a tickable set of capabilities.

> Note: the Store Keeper roster model (`wms.storekeeper`) and this menu are defined in the `wms_barcode` addon, but the capability checkboxes map 1:1 to the security groups defined in `wms_location/security/wms_security.xml`. It is documented here because it is part of warehouse setup and drives the role model below.

**Steps (add a keeper):**
1. Open WMS / Configuration / Store Keepers (model `wms.storekeeper`).
2. Click New; enter **Name** (required, placeholder "e.g. Ramesh"); optionally **Phone**, **Email**, **Notes**.
3. Save. At this point the keeper exists on the roster and can be picked as "on duty" on Scan Issue even with no Odoo login (shared-desk model).

**Steps (give the keeper their own login):**
1. On the keeper's form, in the "Set up individual Odoo login" block (only visible while no login is linked), enter **Login** (lowercase, no spaces, e.g. "suresh") and an **Initial password** (temporary).
2. Click **Create Odoo login** in the header (manager-only button).
3. The system creates a `res.users`, links it via `user_id`, and turns ON four default capabilities — Scan Receipt/Return, Scan Issue, File Damage, Submit Audit. **Manage Catalog stays OFF.** The initial password is then cleared from the roster row (the hash lives on `res.users`).
4. In the "Capabilities (advantages)" group (now visible, manager-only) untick any capability you don't want, or tick **Can manage Carton aliases + Labels** to grant catalogue/label editing. Each tick writes the matching group onto the user immediately.
5. Use **Open login record** to jump to the `res.users` for password reset / archive / finer permissions.

**Fields:** `name` (required), `phone`, `email`, `note`, `active` ("On the roster"); `login`, `initial_password` (login-creation only); `user_id` ("Odoo login", read-only once set); the five capability toggles `can_scan_receive` ("Can Scan Receipt / Return"), `can_scan_issue` ("Can Scan Issue"), `can_file_damage` ("Can file Damage events"), `can_submit_audit` ("Can submit Inventory audits"), `can_manage_catalog` ("Can manage Carton aliases + Labels"); `has_login` (computed, drives button visibility).

**Buttons:** **Create Odoo login** (`action_create_login`, shown when no login, manager-only) — materialises the user with the four default capabilities. **Open login record** (`action_open_login`, shown when a login exists, manager-only) — opens the `res.users` form.

**Validation / errors:** Unique roster name -> "Each Store Keeper name must be unique on the roster."; one login per entry -> "An Odoo login can be tied to only one roster entry." On Create login: already linked -> "'<name>' already has an Odoo login ..."; missing login -> "Pick a Login for '<name>' before creating the user ..."; missing password -> "Set an Initial password so '<name>' has something to type ..."; taken login -> "Login '<x>' is already taken (by <name>). Pick another."; whitespace in login -> "Login '<x>' contains whitespace. Use a short, lowercase, single-word handle ..." Archiving a keeper (untick "On the roster") also archives the linked login, and archiving the login in Settings archives the roster entry — the two stay in lockstep so a disabled keeper drops out of the on-duty picker.

**Result:** A roster name (audit trail for issues) and, optionally, a real per-person Odoo login carrying exactly the capabilities the Admin ticked.

---

### The role / group model and assigning a Storekeeper

**Role:** Admin only
**Menu path:** Settings / Users & Companies / Groups (to inspect groups); WMS / Configuration / Store Keepers (the practical way to assign a person)
**Purpose:** Define who can do what in the WMS via a two-role model (Manager vs Store Keeper) plus five per-keeper capability sub-groups.

**The groups defined (in `wms_location/security/wms_security.xml`):**

1. **WMS / Store Keeper** (`group_wms_user`) — the base every-day operator role. Implies Odoo's `stock.group_stock_user`. On its own it grants login, the ability to *see* the WMS app, and **read-only** access to inventory and to all catalogue masters (per the `*_user` ACL rows). A user in this group alone can browse but the Scan Receipt menu, Damage form, and Audit list do **not** appear — those are gated by the capability sub-groups below. (The XML id is `group_wms_user` for historical/ACL-compatibility even though the display name is "Store Keeper".)

2. **WMS / Capability: Scan Receipt + Scan Return** (`group_wms_can_scan_receive`) — implies `group_wms_user`; shows the Scan Receipt + Scan Return menus and grants create on those wizards.

3. **WMS / Capability: Scan Issue (outbound)** (`group_wms_can_scan_issue`) — implies `group_wms_user`; shows the Scan Issue menu and grants create on that wizard.

4. **WMS / Capability: File damage events** (`group_wms_can_file_damage`) — implies `group_wms_user`; allows opening the Damage form and submitting a damage report (but not creating Repair Orders).

5. **WMS / Capability: Submit inventory audits** (`group_wms_can_submit_audit`) — implies `group_wms_user`; lets the keeper open an audit, count slots, and submit the result for manager acceptance.

6. **WMS / Capability: Manage carton aliases + labels** (`group_wms_can_manage_catalog`) — implies `group_wms_user`; grants editing of the carton-barcode alias table and the thermal label profile. This is normally Admin work and is **OFF by default** for new keeper logins.

7. **WMS / Manager** (`group_wms_manager`) — the Admin role. Implies `stock.group_stock_manager`, the base `group_wms_user`, **and all five capability sub-groups** via `implied_ids`, so a manager sees and can do everything. The built-in `admin` user is added to this group on install (`user_ids` eval adds `base.user_admin`). Managers also get write/create/unlink on every catalogue master and the generators (per the `*_manager` ACL rows).

(Two optional sub-roles, Repair Tech and Buyer, are defined in the `wms_repair_damage` and `wms_ai_forecast` addons and start empty — out of scope here.)

**What the groups gate, concretely:** The WMS / Configuration menu is manager-only. Cycle Count (raw quant adjustment) is manager-only. Odoo's built-in Inventory app root menu, the Apps menu, and Spreadsheet Dashboards are all re-restricted to managers so a Store Keeper's app picker shows only Discuss + WMS and cannot bypass Scan Receipt to move stock. Catalogue masters and Slots/Floor Zones are visible to keepers read-only.

**How an admin assigns a person as a Storekeeper (with which toggles):**
1. Add the person on the roster (WMS / Configuration / Store Keepers -> New -> Name).
2. Give them a login: enter Login + Initial password, click **Create Odoo login**. This creates a `res.users` in `group_wms_user` plus the four daily-work capability groups (Scan Receipt/Return, Scan Issue, File Damage, Submit Audit) with **Manage Catalog OFF**.
3. Tune the toggles in the "Capabilities (advantages)" group: untick any of the four to remove that ability, or tick **Can manage Carton aliases + Labels** to also grant catalogue/label editing. Each toggle writes the matching group onto the user via the inverse methods (source of truth is `res.users.group_ids`, so editing under Settings -> Users stays in sync).
4. To make someone an Admin instead, add them to **WMS / Manager** under Settings -> Users (they then inherit all capabilities automatically).
5. On upgrade, a backfill (`_wms_backfill_capabilities`) grants any pre-existing keeper the four daily-work capabilities so they don't lose menus — deliberately excluding Manage Catalog so an upgrade never silently re-widens power.

**Validation / errors:** Capability ticks on a roster entry with no login are deferred until the login is created. See the Store Keepers section above for the login-creation error messages.

**Result:** A precise, least-privilege assignment: each keeper holds exactly the capabilities ticked, the Manager role holds everything, and the audit trail always records the real human on each issue.
## 3. Perishable Lifecycle, Damage & Repair

This section documents two custom WMS addons: `wms_perishable` (the per-lot expiry / FEFO / quarantine / recall engine) and `wms_repair_damage` (damage logging and the tool/equipment repair workflow). Every step, label, field, button, and validation message below is taken directly from the addon source (models, wizards, and `views/*.xml`).

A note on roles used throughout this section. The base operator role is **Store Keeper** (`wms_location.group_wms_user`); the elevated role is **Manager / Admin** (`wms_location.group_wms_manager`), which implies every capability sub-group. Two narrower groups also appear here: the per-keeper **File damage events** capability (`wms_location.group_wms_can_file_damage`) and **WMS / Repair Tech** (`wms_repair_damage.group_repair_tech`). Where this section says "Admin only" it means `group_wms_manager`.

---

### Shelf-life Policy

**Role:** Admin only (menu and write access are gated to `wms_location.group_wms_manager`; Store Keepers have read-only ACL).
**Menu path:** WMS / Configuration / Shelf-life Policy
**Purpose:** Maintain a per-kind table of shelf-life rules (total life, minimum life required at receipt, minimum life required at issue) for each perishable product kind.

**Steps:**
1. Open WMS / Configuration / Shelf-life Policy. The list (`wms.shelf.life.policy.list`) is editable inline (`editable="bottom"`).
2. Click into the bottom blank row (or **New**) to add a kind, or click an existing row to edit it.
3. Pick the **Product kind** from the dropdown (the selection is the live WMS kind list, including the five perishable kinds vaccine / supplement / chemical / fertilizer / food).
4. Enter **Total shelf life (days)**, **Min @ receipt (days)**, and **Min @ issue (days)**.
5. Leave **Active** on (boolean toggle) to keep the row in force.
6. Save. The form view repeats the precedence rule in help text: a per-product override beats this kind policy, and the global Shelf-life Settings apply only when neither is set; 0 = fall back to the global setting.

**Fields:** `product_kind` (Selection, **required**), `total_days` (Integer; "0 = per product / not enforced"), `min_receive_days` (Integer; "0 = fall back to the global setting"), `min_issue_days` (Integer; "0 = fall back to the global setting"), `active` (Boolean, default True).

**Buttons / state transitions:** None — this is a configuration table with no lifecycle state. (The settings form's "Open policy table" button, below, navigates here.)

**Validation / errors:** UNIQUE constraint on `product_kind` — "Each product kind can have only one shelf-life policy." CHECK constraint `min_receive_days >= 0 AND min_issue_days >= 0 AND total_days >= 0` — "Shelf-life days cannot be negative."

**How the policy is applied (resolution order):** `product.template._wms_resolve_shelf_life()` returns total / min_receive / min_issue per product, choosing for each field: a non-zero per-product override first, then this per-kind policy row, then the global fallback parameter. The receipt guard (`scan_receipt._wms_short_dated_lines`) and the issue guard (`scan_issue._wms_short_dated_issue_lines`) both read this.

**Result:** A persisted per-kind rule set that feeds the short-dated-at-receipt and short-dated-at-issue guards.

---

### Shelf-life Settings

**Role:** Admin only (menu gated to `group_wms_manager`; `action_save` re-checks the group server-side).
**Menu path:** WMS / Configuration / Shelf-life Settings
**Purpose:** Set the two global fallback shelf-life thresholds (minimum days at receipt and at issue) used for perishable kinds that have no policy row and no per-product override.

**Steps:**
1. Open WMS / Configuration / Shelf-life Settings. A dialog opens (transient model `wms.shelf.life.settings`, `target="new"`), pre-loaded from the stored parameters by `default_get`.
2. Edit **Global min shelf life @ receipt (days)** (default 60) and **Global min shelf life @ issue (days)** (default 0).
3. Click **Save** to persist, or **Open policy table** to jump to the per-kind Shelf-life Policy, or **Cancel** to discard.

**Fields:** `min_receive_days` (Integer, default 60; "0 disables the global receipt guard"), `min_issue_days` (Integer, default 0; "0 disables the global issue guard"). These are stored as `ir.config_parameter` keys `wms_perishable.min_receive_shelf_life_days` and `wms_perishable.min_issue_shelf_life_days`.

**Buttons / state transitions:** **Save** (`action_save`, btn-primary) writes both parameters and closes; **Open policy table** (`action_open_policy`, btn-secondary) opens the Shelf-life Policy action; **Cancel** (special=cancel). No record state.

**Validation / errors:** `action_save` raises "Only a Manager can change the shelf-life settings." if the user is not in `group_wms_manager`, and "Shelf-life days cannot be negative." if either value is below zero.

**Result:** The two global fallback parameters are updated and apply to any perishable kind lacking a policy row / product override.

---

### Expiry alerts (near-expiry and expired lots)

**Role:** Both (Store Keeper + Admin). The per-batch report has read ACL for `group_wms_user`; its menu sits under WMS / Reports (not manager-gated). The short-dated guards below are enforced for everyone but can only be overridden by a Manager.
**Menu path:** WMS / Reports / Lot Expiry (per batch)
**Purpose:** Surface every on-shelf batch with its own expiry, days-to-expiry, on-hand quantity, and value at risk, banded into threshold statuses — and additionally warn (and gate) at the moment short-dated stock is received or issued.

There are three distinct surfaces for near-expiry / expired stock; document them together:

**(a) The Lot Expiry report (`wms.lot.expiry.alert`).** A read-only SQL view, scoped to genuine on-shelf storage (internal locations, excluding damage/repair, under a warehouse's `lot_stock_id`), keyed on each quant's stored effective expiry (`stock_quant.wms_effective_expiry`).

**Steps:**
1. Open WMS / Reports / Lot Expiry (per batch). The list opens with the "Within 30 days" filter applied by default (`context {'search_default_near': 1}`).
2. Read each row: **Product**, **Batch** (lot), **Expiry date**, **Days to expiry** (negative = already expired, 0 = today), **On hand (units)**, **Value at risk** (summed in the footer), **Lot state**, and **Status**.
3. Use the search filters **Expired** (`status = 'expired'`) or **Within 30 days** (`status in expired/d7/d15/d30`), and group by **Status**, **Product**, or **Supplier**.

**Fields (report columns):** `product_id`, `lot_id`, `expiry_date`, `days_to_expiry`, `on_hand`, `unit_cost` (hidden by default), `value_at_risk`, `lot_state` (related to `lot.wms_lot_state`), `supplier_id` (hidden by default), `status`. The **Status** Selection bands are: `expired`, `d7` (Within 7 days), `d15` (Within 15 days), `d30` (Within 30 days), `d60` (Within 60 days), `d90` (Within 90 days), `d180` (Within 180 days), `ok` (More than 180 days). The list colour-codes expired rows red (`decoration-danger`), within-30-days amber (`d7/d15/d30`), and 60/90-day rows blue.

**Buttons / state transitions:** None (read-only view, `create="false"`).

**(b) The computed expired flag on the lot.** `stock.lot.wms_is_expired` is a non-stored computed Boolean: true when the lot's `expiration_date` is in the past. It is shown on the lot form alongside `wms_lot_state`.

**(c) The short-dated guards (received / issued).** At Scan Receipt validate, `_wms_short_dated_lines()` flags any lot-tracked line whose remaining shelf life is below that product's resolved min-receive days, raising "Short-dated stock. These line(s) have less than their kind's minimum shelf life for receiving: ... A Manager must approve short-dated stock before it can be received." At Scan Issue, `_wms_short_dated_issue_lines()` flags any FEFO-drawn lot with fewer days left than the product's min-issue (but not yet expired), raising "Short-dated at issue. ... A Manager must approve issuing short-dated stock." Each has a Manager-only override (`action_receive_short_dated_override` / `action_override_short_dated_issue`).

**Validation / errors:** See the two guard messages above. Both overrides raise "Only a Manager can ..." for non-managers.

**Result:** Operators can see and act on near-expiry / expired stock by value; expired or short-dated stock cannot silently move without Manager sign-off. (Note: expired stock is also automatically excluded from the FEFO issue plan — see the lot state model below.)

---

### Lot Quarantine (QC hold)

**Role:** Admin only. Menu gated to `group_wms_manager`; every action calls `_check_manager()`. (Store Keepers have read-only ACL on `wms.lot.quarantine`.)
**Menu path:** WMS / Operations / Lot Quarantine
**Purpose:** Put suspect lots on a QC hold that freezes them (excluded from issue) and cancels their open reservations, then release them back to issuable or reject and destroy them.

**Steps:**
1. Open WMS / Operations / Lot Quarantine and click **New**.
2. Enter the **Reason** for the hold (required) and add one or more lots under **Held lots** (required).
3. Save. Creation itself applies the hold (`create` calls `_wms_apply_hold`): the record *is* the hold — there is no separate "place on hold" button. The lots are set to `wms_lot_state = 'quarantine'`, their open (non-done, non-cancel, qty>0) move lines are unreserved, and `held_on` / `held_by_id` / `unreserved_count` are stamped. The number is auto-assigned from sequence `wms.lot.quarantine`.
4. After QC, use the header buttons: **Release (QC pass)**, **Reject (QC fail)**, or **Destroy**. Add **QC notes** to record the decision.

**Fields:** `name` (auto, default "New", readonly), `reason` (Text, **required**), `lot_ids` (Many2many to stock.lot, **required**), `product_ids` (computed from the lots), `state` (Selection: held / released / rejected / destroyed, default held), `qc_notes` (Text), `held_on` / `held_by_id` (readonly, stamped on hold), `decided_on` / `decided_by_id` (readonly, stamped on decision), `unreserved_count` (readonly).

**Buttons / state transitions:**
- **Release (QC pass)** (`action_release`, btn-primary, visible only when state=held; confirm: "Release these lots back to issuable 'available' state?") — sets state **held → released** and flips lots still in `quarantine` back to `available`.
- **Reject (QC fail)** (`action_reject`, btn-warning, visible only when held) — sets state **held → rejected** (lot states unchanged).
- **Destroy** (`action_destroy`, btn-danger, visible when state in held/rejected; confirm: "Mark these lots DESTROYED? They become permanently un-issuable. Physical write-off is a separate Damage action.") — sets state **held/rejected → destroyed** and flips affected lots (quarantine/recalled/available) to `wms_lot_state = 'destroyed'`.

State statusbar: held, released, rejected, destroyed. The `lot_ids` list is editable only while state=held.

**Validation / errors:** Any action by a non-Manager raises "Only a Manager can quarantine, release, reject or destroy a lot." Creating/holding with no lots raises "Add at least one lot to quarantine." `action_release` / `action_reject` raise "Only a lot currently on hold can be released." / "... can be rejected." if state is not held; `action_destroy` raises "Only a held or rejected lot can be destroyed." if state is otherwise.

**Result:** Held lots are frozen and off the issue plan; on decision the record is stamped (who/when) and the lots are released to `available`, left held-but-rejected, or marked `destroyed` (permanently un-issuable; physical write-off is a separate Damage move). Lifecycle hook events `quarantined`, then `released` / `rejected` / `destroyed`, fire on the lots.

---

### Lot Recall

**Role:** Admin only. Menu gated to `group_wms_manager`; `action_recall` / `action_release` call `_check_manager()`. (Store Keepers have read-only ACL on `wms.lot.recall`.)
**Menu path:** WMS / Operations / Lot Recalls
**Purpose:** Freeze recalled lots so they cannot be issued, cancel their open reservations, and release them back to available once the recall is cleared — with full who/when history.

**Steps:**
1. Open WMS / Operations / Lot Recalls and click **New**. The record starts in **Draft**.
2. Choose the **Mode**: "Internal / manual" or "Supplier notice". For a supplier notice, fill **Supplier** and **Supplier notice ref** (both shown only when mode = supplier).
3. Enter the **Reason** (required) and add the affected lots under **Recalled lots** (required).
4. Save, then click **Activate Recall**. The number is auto-assigned from sequence `wms.lot.recall`.
5. When the recall is cleared, click **Release Recall**.

**Fields:** `name` (auto, default "New", readonly), `mode` (Selection manual/supplier, **required**, default manual), `supplier_id` (Many2one res.partner), `supplier_notice_ref` (Char), `reason` (Text, **required**), `lot_ids` (Many2many stock.lot, **required**), `product_ids` (computed), `state` (Selection draft/active/released, default draft), `recalled_on` / `released_on` (readonly), `recalled_by_id` / `released_by_id` (readonly), `unreserved_count` (readonly).

**Buttons / state transitions:**
- **Activate Recall** (`action_recall`, btn-danger, visible only when state=draft; confirm: "Activate this recall? The lots will be frozen (un-issuable) and any open reservations cancelled.") — sets state **draft → active**, flips lots to `wms_lot_state = 'recalled'`, unreserves their open move lines, and stamps `recalled_on` / `recalled_by_id` / `unreserved_count`.
- **Release Recall** (`action_release`, btn-primary, visible only when state=active; confirm: "Release this recall? The lots return to issuable 'available' state.") — sets state **active → released** and flips lots still in `recalled` back to `available` (it deliberately does not resurrect lots already `destroyed`). Stamps `released_on` / `released_by_id`.

State statusbar: draft, active, released. The `lot_ids` list is editable only while state=draft.

**Validation / errors:** Non-Manager raises "Only a Manager can recall or release a lot." `action_recall` raises "Only a draft recall can be activated." (wrong state) and "Add at least one lot before activating the recall." (no lots). `action_release` raises "Only an active recall can be released." if not active.

**Result:** Active recalls keep their lots frozen and off the issue plan; an in-flight issue cannot ship a recalled lot because the open reservation is cancelled at activation. Releasing returns surviving lots to `available`. Lifecycle hook events `recalled` then `released` fire on the lots.

---

### Perishable Lot Migration

**Role:** Admin only. Menu gated to `group_wms_manager`; `action_migrate` calls `_check_manager()`. (Dry run is not group-checked in-method but the menu/ACL restrict access to managers.)
**Menu path:** WMS / Operations / Perishable Lot Migration
**Purpose:** Bring legacy, non-lot-tracked perishable products onto lot tracking — either a clean tracking flip (zero stock) or, for products with stock on hand, assigning their on-hand quants to a legacy lot first so no stock is orphaned without a lot.

**Steps:**
1. **Take a verified backup first.** The form opens (transient `wms.lot.migration`, `target="new"`) with a warning banner: rollback is only by restoring the pre-migration backup, because once lot tracking is set with stock on hand it cannot be cleanly undone.
2. Click **Dry run** to preview. The **report** field lists every perishable product that still needs migration and the path it would take — "clean flip (zero stock)" or "legacy-lot (has N on hand)". Dry run changes nothing.
3. Click **Migrate** (after confirming the backup). For each target product with on-hand quants, the wizard creates a lot named `LEGACY-<date>-<product id>`, assigns the no-lot on-hand quants to it, then sets the template to `tracking='lot'` with `use_expiration_date=True`. Products at zero stock are clean-flipped. The report summarises how many were clean-flipped vs migrated via a legacy lot.
4. Click **Close** when done.

Which products are targeted: variants whose template kind is in the expiry-sensitive set and whose `tracking != 'lot'`. On-hand quants are internal-location quants with quantity > 0 and no lot.

**Fields:** `report` (Text, readonly — the dry-run / migration output).

**Buttons / state transitions:** **Dry run** (`action_dry_run`, btn-secondary — preview only); **Migrate** (`action_migrate`, btn-danger; confirm: "Have you taken a verified backup? Migration cannot be cleanly rolled back — only restored. Proceed?"); **Close** (special=cancel). No record state — this is a one-shot wizard.

**Validation / errors:** `action_migrate` raises "Only a Manager may run the perishable lot migration." for non-managers. There is no automatic rollback; recovery is by restoring the backup.

**Note on "merging" lots:** This wizard moves a product's existing on-hand stock onto one new legacy lot per product. It does not merge two distinct existing batches. Distinct supplier batches are deliberately never merged on receipt either (`scan_receipt._wms_find_or_create_lot` matches an existing lot by product + batch name, otherwise creates a new lot, and backfills blank metadata only — it never silently combines two different batches).

**Result:** Legacy perishable products become lot-tracked with expiry enabled; products that had stock carry it on a `LEGACY-...` lot so FEFO and the issue planner keep working.

---

### The lot state model (`wms_lot_state`)

**Role:** Both (the state field is read on the lot form by all WMS users; only the recall/quarantine actions that change it are Manager-gated).
**Menu path:** The state is shown on each lot at Inventory's lot form (extended view "stock.lot.form.perishable"); recalls/quarantines are driven from WMS / Operations as documented above.
**Purpose:** Track each lot's lifecycle position so non-available lots are kept off the FEFO issue plan and the lot's history is auditable.

**Important correction to the field's values.** The actual `stock.lot.wms_lot_state` Selection has exactly four values: **available**, **quarantine**, **recalled**, **destroyed** (default `available`, required, indexed). There is no "near" or "expired" *state*. "Near-expiry" and "expired" are not lot states — they are (a) the banded `status` of the per-batch Lot Expiry report (`expired`, `d7`…`d180`, `ok`) and (b) the computed `stock.lot.wms_is_expired` flag (true when `expiration_date` is past). Expiry therefore gates issuing via the FEFO planner and the short-dated guards, independently of `wms_lot_state`.

**How a lot moves between states:**
1. **available** — the default for every lot from creation (perishables are lot-tracked from creation; received batches get/find a lot at Scan Receipt validate). Only a lot in `available` may be issued.
2. **available → quarantine** — creating a Lot Quarantine record (`_wms_apply_hold`) sets the held lots to `quarantine` and unreserves their open lines.
3. **quarantine → available** — Lot Quarantine **Release (QC pass)** (`action_release`).
4. **available → recalled** — Lot Recall **Activate Recall** (`action_recall`) sets the lots to `recalled` and unreserves their open lines.
5. **recalled → available** — Lot Recall **Release Recall** (`action_release`) flips lots still `recalled` back to `available` (it skips any already `destroyed`).
6. **→ destroyed** — Lot Quarantine **Destroy** (`action_destroy`) sets affected lots (from quarantine / recalled / available) to `destroyed`. This state is terminal in the model: no action flips a `destroyed` lot back, and Release Recall explicitly will not resurrect a destroyed lot.

**FEFO exclusion (where the state takes effect):** `stock.location.find_oldest_quants_for_product` (overridden in `wms_perishable`) plans issues only from quants that are not expired (removal_date not in the past) and whose lot is `wms_lot_state = 'available'` (or has no lot). So recalled, quarantined, and destroyed lots — and expired stock — are excluded from the Scan Issue plan. A Manager can still issue expired stock via `action_override_expired_issue` (which re-plans including expired lots), but there is no override that issues a recalled / quarantined / destroyed lot — only releasing it back to `available` makes it issuable again.

**Fields (lot lifecycle / traceability, all additive on `stock.lot`):** `wms_lot_state` (Selection, **required**), `wms_supplier_id` (Many2one res.partner), `wms_supplier_batch` (Char), `wms_supplier_invoice` (Char), `wms_manufacture_date` (Date), `wms_is_expired` (computed Boolean), `wms_movement_count` (computed Integer — completed done move lines).

**Buttons / state transitions:** State changes happen only through the recall and quarantine actions above. The lot form also exposes two stat buttons: **Timeline** (`action_wms_lot_timeline`, opens the lot's immutable done move lines, newest first; visible when movement_count > 0) and **Print label** (`action_wms_print_lot_label`).

**Validation / errors:** The state transitions enforce their own "Only a lot currently on hold can be released", "Only a draft recall can be activated", etc. (see Quarantine and Recall above). Printing a label with no configured printer raises "No label printer is configured. ...".

**Result:** Each lot carries an auditable lifecycle position; the issue planner honours it so only `available`, in-date lots are issued by default.

---

### Damages

**Role:** Both, but gated by the per-keeper **File damage events** capability (`wms_location.group_wms_can_file_damage`) — not every Store Keeper has it. Managers have it implicitly. ACL gives both `group_wms_can_file_damage` and `group_wms_manager` read/write/create on `wms.damage` (no delete for either).
**Menu path:** WMS / Operations / Damages
**Purpose:** Log a damaged-stock event and, on confirm, move the affected quantity from its slot to the warehouse's Damage location while snapshotting the loss value and audit trail.

**Steps:**
1. Open WMS / Operations / Damages and click **New** the moment something breaks, spoils, or expires. The record starts in **Draft** (number auto-assigned from sequence `wms.damage`).
2. Under **What & where**, set **Product** (required), **Quantity** (required, default 1.0), and **Source slot** (required — any slot or floor zone). The **Warehouse** is computed (readonly).
3. Pick a **Reason**: Broken (default), Expired, Contaminated, or Other.
4. If reason is **Other**, write a **Note** (required in that case). Optionally attach a **Damage photo** (camera opens on phone/tablet).
5. Under **Who reported it**, fill **Reported by**, **Authorised by**, and **Store Keeper on duty** (picked from the active roster). Drafts may be saved with placeholders, but confirm requires all three.
6. Review the auto-derived **Spare-stock check** block ("Other units on hand" + a recommended action badge: No action needed / Schedule repair / Urgent buy / Note for future order, etc.) and the matching coloured advice banner.
7. Click **Confirm**. This creates an internal-transfer picking from the source slot to the Damage location, validates it (reserving the stock), sets the record **Confirmed**, snapshots **Loss value**, and posts a "Damage confirmed" audit message to the chatter. If the recommendation is "Urgent buy", every WMS Manager is notified via Discuss.
8. If the item can be fixed, click **Create Repair Order** (appears only for confirmed records whose recommendation is a repair action and that have no linked repair order yet).

**Fields:** `name` (auto, readonly), `state` (Selection draft/confirmed/cancelled, default draft, tracked), `product_id` (**required**), `quantity` (Float, **required**, default 1.0), `source_slot_id` (Many2one stock.location, domain slot/floor, **required**), `reason` (Selection broken/expired/contaminated/other, **required**, default broken), `note` (Text; **required when reason=other**), `damage_photo` (Binary), `wms_reported_by` (Char — required at confirm), `wms_authorized_by` (Char — required at confirm), `wms_storekeeper_id` (Many2one wms.storekeeper — required at confirm), `damage_value` (Float, readonly — snapshot loss value), `picking_id` (readonly), `warehouse_id` (computed, stored), `repair_order_id` (readonly), plus computed `remaining_on_hand` / `recommended_action` / `recommendation_message`.

**Buttons / state transitions:**
- **Confirm** (`action_confirm`, btn-primary, visible only when draft) — **draft → confirmed**; creates and validates the Damage picking and snapshots `damage_value = quantity × standard_price`.
- **Create Repair Order** (`action_create_repair_order`, btn-warning; visible only when confirmed, no existing repair order, and the recommendation is a repair action) — opens a new pre-filled `wms.repair.order` (also reachable via the "Repair Order" stat button once linked).
- **Cancel** (`action_cancel`; visible unless already cancelled) — **draft → cancelled**.

**Validation / errors:**
- `quantity` CHECK constraint `> 0` — "Damage quantity must be greater than zero."
- Note constraint — if reason is Other and note is blank: "If the damage reason is 'Other', you must write a quick note explaining what happened ...".
- Slot-stock guard (`_check_source_slot_stock`) — refuses to damage more than the slot has *free* (total − reserved). Two messages: if some stock is reserved by a pending issue, "Slot %s has %g × %s, but %g unit(s) are already spoken for by a pending issue ... Only %g are really free ..."; otherwise "You're trying to file %g × %s as damaged at slot %s, but only %g unit(s) are actually there. Re-count the slot ...".
- Confirm audit guard — missing Reported/Authorised/Store Keeper: "Fill in the audit-trail field(s) before confirming this damage event: ...".
- Confirm infrastructure guards — "No Damage location for warehouse %s.", or "Warehouse %s is not configured for internal stock transfers. ..." when there is no internal picking type.
- Reservation guard at validate (`validate_reserved_or_abort`) — if the slot cannot fully reserve: "Not enough stock to send to Damage %s. Requested %g %s at %s, but the slot could not reserve that much. Nothing was moved ...".
- Confirmed-record lock — a Store Keeper editing a confirmed damage (any field except linking a repair order / chatter) hits AccessError: "Damage %s is already confirmed — only a Manager can change it. ...". Managers bypass.
- Cancel guard — cancelling a confirmed record raises "Cancel the stock transfer that was created for this damage event before cancelling the record."

**Result:** A confirmed, immutable damage record; the affected quantity sits in the Damage location; the loss value and full audit trail (who reported/authorised, which keeper) are recorded in chatter; and a repair order can be spun off if the item is fixable.

---

### Repair orders

**Role:** Mixed. Store Keepers can create and read repair orders (ACL: `group_wms_user` read+create). The state-transition buttons and write access are restricted to **WMS / Repair Tech** (`group_repair_tech`) and **Manager** (`group_wms_manager`) — the buttons carry those groups so a Store Keeper never sees a button that would fail with AccessError. The Repair orders **menu** itself is Manager-only.
**Menu path:** WMS / Operations / Repair orders (also opened from a Damage event via **Create Repair Order**)
**Purpose:** Run a damaged returnable item through repair — moving it Damage → Repair-Out → back to a slot — or scrap it if it is beyond repair, with an audit trail at each step.

**Steps:**
1. Open a repair order — usually via **Create Repair Order** on a confirmed Damage event (which pre-fills product, quantity, original slot, return slot, and the audit fields from the damage), or via WMS / Operations / Repair orders / New. It starts in **Draft** (number auto-assigned from sequence `wms.repair`).
2. Under **What & where**, confirm **Product** (required), **Quantity** (required, default 1.0), **Original slot**, **Return slot** (defaults to original), and assign a **Technician**. **Warehouse** is computed (readonly).
3. Under **People involved**, ensure **Reported by**, **Authorised by**, and **Store Keeper on duty** are filled (required to move past draft).
4. Click **Start Repair** (Tech/Manager). This creates and validates a picking Damage → Repair-Out, sets state **In repair**, and posts a "Repair started" audit note.
5. When the technician finishes, click **Mark Done** (Tech/Manager). This creates and validates a picking Repair-Out → the return slot (or original slot), sets state **Done**, posts a "Repair done" note, and notifies managers that the item is back in stock.
6. If the item cannot be fixed, click **Scrap** (Tech/Manager) while In repair — it write-offs the unit from Repair-Out via Odoo's native scrap and sets state **Scrapped**.
7. A draft order with no movement yet can be **Cancel**led.

**Fields:** `name` (auto, readonly), `state` (Selection draft/in_repair/done/scrapped/cancelled, default draft, tracked), `damage_id` (Many2one wms.damage), `product_id` (**required**), `quantity` (Float, **required**, default 1.0), `original_slot_id` / `return_slot_id` (Many2one stock.location, domain slot/floor), `warehouse_id` (computed, stored), `technician_id` (Many2one res.users), `start_picking_id` / `finish_picking_id` (readonly), `repair_notes` (Text), and the audit triplet `wms_reported_by` / `wms_authorized_by` / `wms_storekeeper_id`.

**Buttons / state transitions:**
- **Start Repair** (`action_start_repair`, btn-primary, visible when draft; groups Repair Tech + Manager) — **draft → in_repair**; picking Damage → Repair-Out.
- **Mark Done** (`action_finish_repair`, btn-primary, visible when in_repair; Tech + Manager) — **in_repair → done**; picking Repair-Out → return/original slot.
- **Scrap** (`action_scrap`, visible when in_repair; Tech + Manager; confirm: "Scrap this item? It will be written off and cannot be repaired afterwards.") — **in_repair → scrapped**; native stock scrap from Repair-Out.
- **Cancel** (`action_cancel`, visible when draft; Tech + Manager) — **draft → cancelled**.

State statusbar (visible): draft, in_repair, done.

**Validation / errors:**
- `quantity` CHECK constraint `> 0` — "Repair quantity must be greater than zero."
- Audit guard before leaving draft (`_check_audit_complete`) — "Fill in the audit-trail field(s) before moving this repair order: ...".
- Start guard — missing locations: "Damage / Repair locations missing for %s.".
- Finish guard — no destination: "No destination slot.".
- Scrap guard — "Only in-repair items can be scrapped." if state is not in_repair.
- Cancel guards — "This repair order is already %s — cancelling would orphan the stock moves it generated. ..." for done/scrapped; "Item is currently at the Repair-Out location. Either finish the repair (Mark Done) or scrap it before cancelling ..." for in_repair.
- Reservation guard at each picking (`validate_reserved_or_abort`) — if stock can't be reserved, e.g. "Not enough stock to send to Repair %s ... Nothing was moved ..." (and similarly "return from Repair").

**Result:** The unit is repaired and returned to a slot (Done) and managers are notified it is issuable again, or it is written off (Scrapped), with every transition recorded in the chatter audit trail.
## 4. Forecasting, Reports & Backup/DR

This section documents the `wms_ai_forecast` and `wms_reports` addons. Every menu path, field, button, and message below is taken from the actual code (models, wizards, views, controllers, crons). Roles are derived from `ir.model.access.csv` and the `groups=` attribute on each menu/action: **Both** = visible to any WMS user (`wms_location.group_wms_user`); **Admin only** = `wms_location.group_wms_manager`. A separate per-keeper capability group, `wms_reports.group_wms_backup_now` ("WMS / Can Run Backup Now"), gates only the Back Up Now wizard; managers inherit it automatically.

---

### Forecasts (AI demand forecasting & reorder suggestions)
**Role:** Both (visible to any WMS user)
**Menu path:** WMS / Forecast / Reorder / Forecasts
**Purpose:** Show one row per storable product with its demand forecast, velocity class, and a suggested reorder quantity the buyer can turn into a draft purchase order.

**How forecasts are generated / refreshed.** There are three triggers, all of which run the same engine (`wms.forecast.engine`):

1. **Nightly cron (automatic).** The scheduled action "WMS — Retrain forecasts" runs `model.run_all_forecasts()` once every 1 day as the root user. It searches every product where `active = True` and `is_storable = True` (services and combos are skipped), batch-prefetches each product's on-hand / on-order / safety-stock signals, retrains every product, then prunes forecast-history rows older than `wms_ai_forecast.history_retention_days` (default 365).
2. **"Retrain now" button (single product).** On a forecast's form, the header button **Retrain now** (`action_retrain`) re-runs the engine for just that product.
3. **Indirectly, via the Low stock alerts / Dead stock screens**, which read the same `wms.forecast` rows (see Alerts section).

**How a forecast is computed (per product).** The engine gathers up to 2 years of daily consumption events. Consumption for this trust means a **Scan Issue** — a `stock.move.line` whose picking has `wms_is_scan_issue = TRUE` and is not reversed (`wms_reversed_by_id IS NULL`) — so returns and undone issues do not count. The daily series is resampled to weekly and a model is chosen by series length: Holt-Winters additive (24+ weekly observations), Simple Exponential Smoothing (4–23), or a pure-Python "Naive30" 30-day average fallback (fewer than 4 observations, or when statsmodels/pandas is unavailable). Products with no usage history get a "Manual" model and the note "No usage history yet — monitor only".

**How reorder suggestions appear.** After forecasting, the engine computes `reorder_qty` deterministically: reorder point = lead-time-days × daily_avg + safety_stock; suggested order qty = (daily_avg × 30-day horizon + safety_stock − on_hand − on_order), floored at 0. Lead time comes from the product's first vendor (`seller_ids[:1].delay`, default 7 days); safety stock comes from a `stock.warehouse.orderpoint` minimum if one exists, else 0. Any product with `reorder_qty > 0` is a live reorder suggestion. The list opens with the **Reorder now** filter applied by default (`search_default_reorder_now`), so the buyer immediately sees only what needs ordering.

**Steps (to act on a suggestion):**
1. Open WMS / Forecast / Reorder / Forecasts. The default filter shows products needing a reorder.
2. Read the row: velocity class, monthly average, on-hand, suggested reorder quantity, and the date stock is expected to hit the reorder point.
3. Click the cart icon **Create PO** on the row (or open the form and click **Create draft PO**). This creates a *draft* `purchase.order` for the product's main supplier at the suggested quantity; you then review and confirm it in Purchase.
4. To refresh a single product's numbers immediately, open the form and click **Retrain now**.

**Fields / columns.**
- `daily_avg` (Float) — forecasted average daily consumption (drives the reorder math); shown on the form as part of "AI output".
- `monthly_avg` (Float) — daily_avg × 30; the headline "how fast it moves" figure in the list.
- `velocity_class` (Selection: Fast / Normal / Slow / Dead) — Fast when monthly_avg > 100, Normal > 10, Slow otherwise, Dead when there was no movement in the last 12 weeks. List rows are colour-coded (green/blue/amber/grey).
- `reorder_qty` (Float) — suggested quantity to order; list column totals as "Total to order".
- `predicted_qty` (Float) — total forecast demand over the 30-day horizon.
- `reorder_date` (Date) — when on-hand + on-order is projected to fall to the reorder point.
- Supporting columns: `on_hand`, `stock_value` (on-hand × standard cost, totalled as "Capital tied up"), `model_name` (HoltWinters / SES / Naive30 / Manual), `rmse` (holdout error; 0 for Naive), `last_trained`, plus form-only `is_consumable`, `lead_time_days`, `safety_stock`, and `note`.

**Buttons:**
- **Create PO** / **Create draft PO** (`action_push_to_po`) — creates a draft purchase order at `reorder_qty` for the product's main vendor and opens it. Hidden when `reorder_qty <= 0`.
- **Retrain now** (`action_retrain`, form header) — re-runs the engine for that one product.

**Search filters:** Reorder now (`reorder_qty > 0`), Fast moving, Dead stock, and Group by Velocity.

**Validation / errors:** If you click Create PO on a product with no vendor configured, no order is created and a warning notification appears: title **"No vendor"**, message **"Configure a vendor on the product first."**

**Result:** A live, daily-refreshed reorder worklist; one click turns any suggestion into a reviewable draft PO.

---

## Alerts & to-dos

All "Alerts & to-dos" reports live under **WMS / Reports / Alerts & to-dos** (the folder hides itself if a user can see none of its children). These are read-only SQL-view dashboards; most also have a matching cron that pushes a Discuss-inbox notice to managers so nobody has to remember to open the screen.

### Cycle Count Due
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Cycle Count Due
**Purpose:** List storage slots (and floor zones) that have not been physically counted in more than 30 days, oldest first, so they can be recounted.
**Steps:**
1. Open the report; rows are sorted by days-since-count descending.
2. Read the colour coding: blue = over 30 days, amber = over 60, red = over 90.
3. Walk each slot and reconcile it using the Cycle Count wizard (under Operations), then the slot drops off this list on the next refresh.
**Fields / columns:** Slot (`location_id`), Rack (`rack_id`), "Last counted on" (`last_counted`), "Days since last count" (`days_since_count`), "Units in slot" (`on_hand`), "Different products" (`distinct_products`). "Last counted" is the most recent of the slot's quant last-count-date or stock-arrival date.
**Buttons:** None (list is read-only).
**Validation / errors:** None. Empty-state message: "All slots counted within 30 days."
**Result:** A prioritized recount worklist. A weekly cron ("WMS — Weekly cycle-count reminder", Monday 09:00) posts a manager notice when any slots are stale.

### Dead stock
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Dead stock
**Purpose:** Show products with no consumption in the recent window (velocity class "dead") so capital tied up in non-moving stock can be freed.
**Steps:**
1. Open the report (it is the `wms.forecast` list filtered to `velocity_class = 'dead'`).
2. Review on-hand and `stock_value` (capital tied up) per product.
3. Decide to clear the slot, return to vendor, or reclassify.
**Fields / columns:** Same columns as Forecasts (product, velocity class, monthly avg, on-hand, stock value, etc.), restricted to dead rows.
**Buttons:** Create PO appears only where `reorder_qty > 0` (rare for dead stock); Retrain now on the form.
**Validation / errors:** None. Empty-state: "Nothing dead here — clean inventory."
**Result:** A short list of stagnant products with the money they tie up.

### Expiry alerts
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Expiry alerts
**Purpose:** Surface perishable products (those with an expiry date set — medicine, feed, ghee, oil) that have expired or are approaching expiry, with the on-hand value at risk.
**Steps:**
1. Open the report. It opens pre-filtered to Expired + Within 30 days + Within 90 days (`search_default_f_expired/f_urgent/f_soon`).
2. Read the colour coding: red = expired, amber = within 30 days, blue = within 90 days, grey = comfortable.
3. Rotate or dispose of stock; for urgent rows plan the next purchase. Filter "On hand > 0" to ignore items you no longer hold.
**Fields / columns:** Product, Kind (`wms_product_kind`), Expiry date, "Days to expiry" (negative = already expired), On hand, Unit cost (hidden by default), "Value at risk" (on-hand × cost, totalled), Batch, Status. Only products with an expiry date appear; on-hand counts warehouse storage only (excludes the Trust-internal-use sink and Damage/Repair locations).
**Buttons:** None.
**Validation / errors:** None. Empty-state prompts the user to set an Expiry date on perishable products.
**Result:** A rotate/dispose/reorder worklist. A weekly cron ("WMS — Weekly expiry alert digest", Monday 09:05) emails/posts the urgent+expired rows to managers.

### Low stock alerts
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Low stock alerts
**Purpose:** List products whose forecast has driven on-hand to or below the reorder point (`reorder_qty > 0`).
**Steps:**
1. Open the report (the `wms.forecast` list filtered to `reorder_qty > 0`).
2. Review the suggested order quantity per product.
3. Click **Create PO** on a row, or **Retrain now** to refresh a product's prediction first.
**Fields / columns:** Same as Forecasts; the key column is `reorder_qty` (suggested order qty).
**Buttons:** Create PO (`action_push_to_po`); Retrain now (`action_retrain`, on the form).
**Validation / errors:** Same "No vendor" warning as Forecasts when a product has no supplier. Empty-state: "No alerts."
**Result:** A buy-now list. A daily cron ("WMS — Daily low-stock alert", 08:10) posts a manager notice listing up to 50 products at/below reorder level (email too when `wms_reports.alert_email = 1`).

### Reorder summary by vendor
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Reorder summary
**Purpose:** Roll up all products needing reorder into one line per preferred vendor, so the buyer places a single order per supplier.
**Steps:**
1. Open the report; rows are sorted by total quantity to buy, descending.
2. Each row is one vendor with the count of items and the total quantity to buy.
3. Grey rows have **no vendor set** — open those products and set a preferred vendor so they join a supplier's order.
**Fields / columns:** "Preferred vendor" (`partner_id`), "Items to order" (`product_count`), "Total qty to buy" (`total_qty`, totalled). Each product's reorder qty lands in exactly one vendor bucket (variant-specific supplier first, then lowest sequence), or the NULL "no vendor" bucket.
**Buttons:** None.
**Validation / errors:** None. Empty-state: "Nothing to reorder right now."
**Result:** A per-supplier shopping list.

### Returns Due / Overdue
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Returns due / overdue
**Purpose:** Track returnable items (tools, spares, safety gear) that went out via a Scan Issue with an expected return date and have not yet been brought back via Scan Return.
**Steps:**
1. Open the report. It opens pre-filtered to **Overdue** (`search_default_filter_overdue`).
2. Read the colour coding: red = more than 7 days overdue, amber = overdue. Switch to the "Due soon" filter to see items not yet late.
3. Follow up with the borrower, then clear each item by scanning it back in with **Scan Return**.
**Fields / columns:** Issue (`picking_id`), Product, Department, Store Keeper, "Qty out", "Expected return" date, "Days overdue" (negative while still within the window), Status (Due soon / Overdue). "Days overdue" is computed in the company timezone. A pivot view (Department × Status) is also available.
**Buttons:** None on the report; the return itself is done in the Scan Return flow.
**Validation / errors:** None. Empty-state: "Nothing out on loan."
**Result:** An outstanding-loans follow-up list. A daily cron ("WMS — Daily overdue-returns alert", 08:30) posts a manager notice naming up to 20 overdue pickings.

---

## Find stock

All "Find stock" reports live under **WMS / Reports / Find stock**. Two of them (Warehouse Map, Where is product X? via the find page) are also standalone server-rendered web pages.

### Movement history
**Role:** Both
**Menu path:** WMS / Reports / Find stock / Movement history
**Purpose:** Trace every completed stock movement (received, issued, moved between slots), grouped by product.
**Steps:**
1. Open the report. It is Odoo's standard `stock.move` list filtered to `state = 'done'`, grouped by product by default.
2. Expand a product to see its moves; switch to pivot for aggregates.
3. Use the standard stock.move search to filter by date, location, etc.
**Fields / columns:** Standard Odoo stock.move columns (reference, product, quantity, source/destination location, date, state).
**Buttons:** Standard list/form controls only.
**Validation / errors:** None. Empty-state: "No movements recorded yet."
**Result:** An item-level audit trail of physical stock movement.

### Oldest stock (FIFO)
**Role:** Both
**Menu path:** WMS / Reports / Find stock / Oldest stock (FIFO)
**Purpose:** Show every live quant ordered by arrival date so the oldest batch of each product is picked first.
**Steps:**
1. Open the report; rows are sorted by age (days) descending.
2. Read the colour coding: red = over 365 days, amber = over 180, blue = over 90.
3. Pick from the oldest batch first; use the pivot (Rack × Product) for a layout view.
**Fields / columns:** Product, Qty, Slot (`location_id`), Compartment, Rack, "Received on" (`in_date`), "Age (days)". Floor-zone stock (no rack chain) is included.
**Buttons:** None.
**Validation / errors:** None. Empty-state: "No stored stock yet."
**Result:** A FIFO age-ranked stock list.

### Slot occupancy
**Role:** Both
**Menu path:** WMS / Reports / Find stock / Slot occupancy
**Purpose:** Show how full each slot (or floor zone) is — capacity, units on hand, % full, distinct products.
**Steps:**
1. Open the report; rows are sorted by % full descending.
2. Read the colour coding: red = over 90% full, amber = over 75%, grey = empty.
3. Use the filters "Almost full (over 75%)" or "Empty", or group by Rack / Slot type.
**Fields / columns:** Slot (`location_id`), "Slot type" (Rack slot / Floor zone), Compartment, Rack, "Max capacity" (`capacity`), "Units in slot" (`on_hand`), "% full" (`occupancy_pct`, percentage widget), "Different products" (`distinct_products`).
**Buttons:** None.
**Validation / errors:** None. Empty-state: "No slots configured yet."
**Result:** A fill-level map for finding space or congestion.

### Tool / Spare fleet recommendations
**Role:** Both
**Menu path:** WMS / Reports / Find stock / Tool / Spare fleet
**Purpose:** For returnable Tools and Spares, estimate how many physical units were simultaneously checked out at the 90-day peak and recommend a fleet size (peak + 1 spare), flagging shortages.
**Steps:**
1. Open the report. It opens filtered to **Has shortage** (`search_default_filter_shortage`), sorted with the biggest gaps first.
2. Read the row: peak concurrent checkouts, the recommended fleet size, and the shortage (how many more to buy). Red = shortage > 0; grey = fewer than 5 movements (statistically unreliable).
3. Untick "Has shortage" to see well-stocked fleets too; filter Tools only / Spares only / "≥ 5 movements (reliable)".
**Fields / columns:** Product, Kind, "Peak concurrent out (90d)", "Movements (90d)" (`event_count`), "On hand (now)", "Recommended fleet", "Shortage". Only products whose kind is `tool` or `spare` appear (consumables have no return event).
**Buttons:** None.
**Validation / errors:** None. Empty-state: "Nothing to recommend — congrats!"
**Result:** A buy-more shortlist for shared returnable equipment.

### Warehouse Map
**Role:** Both
**Menu path:** WMS / Reports / Find stock / Warehouse Map (opens the standalone page `/wms/warehouse/map` in a new tab)
**Purpose:** Whole-warehouse, one-screen layout overview: every zone with its racks and floor zones, colour-coded by % full.
**Steps:**
1. Click the menu; a mobile-friendly HTML page opens.
2. The header summarises zone / rack / floor-zone counts and total units on hand. A legend explains the colours: Empty (grey), Some stock (blue), Low (green), Most full (amber), Full (red).
3. Each zone card lists its racks (with fill bars) and floor zones; click into a rack to drill down to its slot grid (`/wms/rack/<id>/grid`).
**Fields / columns:** Per rack: on-hand, slots total/occupied, % full. Per floor zone: on-hand, % full, products held.
**Buttons:** Page links — "Warehouse map" and "Back to Odoo".
**Validation / errors:** The controller returns "not found" if the user is not a WMS user; the rack-grid page returns "not found" for a non-rack id.
**Result:** A live visual heat-map of the whole warehouse.

### Where is product X?
**Role:** Both
**Menu path:** WMS / Reports / Find stock / Where is product X? (the in-backend report). A companion standalone search page is at WMS / Operations / Find / Where is it? (`/wms/find`).
**Purpose:** Show every storage slot a product sits in, with quantity and FIFO pick order.
**Steps (backend report):**
1. Open the report. It groups by product by default.
2. Type a product name or scan its barcode in the search box (search fields: product, barcode, location, rack).
3. The row marked **Pick next?** (green, bold) is the oldest batch — take that one first. Use the "Next to pick (FIFO)" filter to see only the lead batch per product.
**Fields / columns:** Product, Barcode, Qty, "Free to pick" (`available_quantity`), Reserved (hidden), Slot, "Slot type", Compartment, Rack, "Arrived" (`in_date`), "Age (days)", "Pick next?" (`is_oldest`). Both rack slots and floor zones are included.
**Steps (standalone `/wms/find` page):** Type a name / SKU / barcode and press **Find**, or tap a chip (low stock, expiring, dead stock, damaged, under repair). For a product lookup it shows total on hand, a LOW badge if it is at/below reorder, and the per-slot breakdown.
**Buttons:** "Find" (find page); pivot/list toggles in the backend report.
**Validation / errors:** Find page shows "No match for …" when nothing is found; only exact keyword chips route to the quick lists (so a product literally named "Slow Cooker" is searched as a product, not treated as the dead-stock keyword).
**Result:** Instant "where is it / how much" answers for any product.

---

### Lot Expiry (per batch)
**Role:** Both
**Menu path:** WMS / Reports / Alerts & to-dos / Expiry alerts
**Purpose:** This is the same report as **Expiry alerts** above; in this WMS the expiry date and batch number are tracked on the product (`wms_expiry_date`, `wms_batch_number`), so per-batch expiry surfaces as the Batch column on the Expiry alerts list rather than as a separate lot screen.
**Steps:** See **Expiry alerts**. Filter or sort by the Batch column to focus on a specific batch; "Days to expiry" tells you how long that batch has left.
**Fields / columns:** As Expiry alerts, with **Batch** (`batch_number`) being the per-batch identifier and **Value at risk** the money exposure for that stock.
**Buttons:** None.
**Validation / errors:** None.
**Result:** Per-batch expiry visibility within the Expiry alerts report.

---

## Value & money (Admin only)

The **WMS / Reports / Value & money** folder is gated to `group_wms_manager`; every action inside it is manager-only.

### Stock Value
**Role:** Admin only
**Menu path:** WMS / Reports / Value & money / Stock Value
**Purpose:** Show the capital currently sitting on the shelves — each product's unit cost × on-hand quantity.
**Steps:**
1. Open the report (list, sorted by stock value descending).
2. Read per-product value; the list totals "On hand" and "Total value".
3. Switch to **Pivot** or **Graph** to see value by category; filter/group by Category or Product.
**Fields / columns:** Product, Category, "On hand" (`qty_on_hand`), "Unit cost", "Stock value" (totalled), Company (hidden). Counts only warehouse storage locations (excludes the Trust-internal-use sink). Cost is the company-specific `standard_price`.
**Buttons:** None (create/edit/delete disabled).
**Validation / errors:** None. Empty-state: "No stock on hand yet."
**Result:** Total on-hand inventory valuation, sliceable by category.

### Consumption Value
**Role:** Admin only
**Menu path:** WMS / Reports / Value & money / Consumption Value
**Purpose:** Show what was consumed, by value, per month — each Scan Issue's quantity × the cost frozen at validate time.
**Steps:**
1. Open the report. It opens grouped by month (`search_default_group_month`).
2. Read the monthly consumed value per product/department; the list totals "Issued" and "Total consumed value".
3. Use Pivot (Department × Month) or Graph (line over months); filter/group by Department, "Issued for", Month, Category, or Product.
**Fields / columns:** Month (`period`), Product, Department, "Issued for" (hidden), Category, "Issued qty" (`qty_out`), "Unit cost", "Consumption value" (totalled), Company (hidden). Counts only done Scan-Issue move lines, excluding undone issues. Unit cost is the snapshot taken at validate time (`wms_unit_cost_at_done`), so later cost changes never rewrite past months.
**Buttons:** None.
**Validation / errors:** None. Empty-state: "Nothing issued yet."
**Result:** A monthly consumption-cost trend to reconcile against budget.

### Product Lifecycle
**Role:** Admin only
**Menu path:** WMS / Reports / Value & money / Product Lifecycle
**Purpose:** Show every event in a single product's life — received, issued, returned, damaged, repaired — in one place.
**Steps:**
1. Open the report. It reuses the Store Keeper Activity log, grouped by product (`search_default_group_product`).
2. Expand a product to see its full timeline, newest first.
3. Switch to Pivot/Graph for aggregates.
**Fields / columns:** Same as Store Keeper Activity (When, Store Keeper, Activity type, Reference, Product, Quantity, Counterparty).
**Buttons:** None.
**Validation / errors:** None. Empty-state: "No movements yet."
**Result:** A per-product event history (the activity log re-sliced by product).

---

### Store Keeper Activity (Weekly / Monthly / Yearly) (Admin only)
**Role:** Admin only
**Menu path:** WMS / Reports / Store Keeper Activity (with children: Weekly summary, Monthly summary, Yearly summary)
**Purpose:** A one-row-per-event timeline of everything each Store Keeper has done (Scan Receipt / Return / Issue / internal move / damage filed / repair order), so the Admin can answer "who did what, when?" — important because the warehouse runs on a shared `storekeeper` login while the real humans rotate and pick "Store Keeper on duty" per action.
**Steps:**
1. Open **Store Keeper Activity**. It opens grouped by Day + Store Keeper, filtered to the last 30 days (`search_default_group_day`, `group_keeper`, `filter_30d`).
2. Switch between List (flat timeline), Pivot (day × keeper × activity-type matrix), and Graph (stacked bars).
3. For the canned period views, click the child menus: **Weekly summary** (this week, grouped by keeper + activity, pivot with Quantity + count measures), **Monthly summary** (this month, grouped by week + keeper), **Yearly summary** (this year, grouped by month + activity).
4. Use the rich filter set: activity-type filters (Receipts/Issues/Returns/Damages), rolling windows (Today / 7d / 30d / 90d / 365d), and group-by at any interval (Day/Week/Month/Quarter/Year) or by Keeper/Activity/Product.
**Fields / columns:** When (`activity_datetime`), Store Keeper (`storekeeper_id`), Activity (Selection), Reference, Product, Quantity, Counterparty (`partner_name` — the Delivered-by / Taken-by / Reported-by), plus hidden Odoo user, Picking, Damage, Repair links. Events are bucketed by the company-local calendar day. Rows are colour-coded by activity type.
**Buttons:** None (read-only; create/edit/delete disabled).
**Validation / errors:** None. Empty-state: "No Store Keeper activity yet."
**Result:** A complete, sliceable audit of per-keeper warehouse activity.

---

### Dashboard
**Role:** Admin only
**Menu path:** WMS / Reports / Dashboard (opens the standalone page `/wms/dashboard` in a new tab)
**Purpose:** One server-rendered screen giving the Admin stock totals, attention badges, today's activity, and system health — no JavaScript, loads fast.
**Steps:**
1. Click the menu; the "Warehouse Dashboard" page opens (manager-gated in the controller).
2. Read the four cards: **System health** (status HEALTHY/DEGRADED/CRITICAL, database reachable, last-backup age, any warnings), **Stock totals** (storable product count, on-hand units, counts of zones/racks/compartments/slots/floor zones), **Needs attention** (count badges for Low stock / reorder, Expiring/expired, Dead stock, Damaged, Under repair, Pending audits, Slots due for count), and **Today's activity** (counts of Receipts/Issues/Returns/Damages/Repairs/Internal moves for today).
3. Use the bottom links to jump to the Warehouse map or back to Odoo.
**Fields / columns:** Badge counts only; each "Needs attention" row links a label to a live count from the matching report model. On-hand counts warehouse storage only (excludes the Trust-internal-use sink).
**Buttons:** Page links — "Warehouse map", "Back to Odoo".
**Validation / errors:** Returns "not found" for a non-manager user. Health card surfaces any backup/DR warnings inline.
**Result:** A single executive snapshot of the whole operation.

---

## Backup & Disaster Recovery suite

This is the most operationally important area. The actual heavy lifting (pg_dump, GPG encryption, Google Drive upload, restore) runs **out of process** under Windows Task Scheduler / PowerShell scripts in the project `scripts/` folder, never in the Odoo web thread. Odoo's role is to *trigger* tasks (`schtasks /Run`), *display* status (reading append-only audit rows and the catalog the scripts write via psql), and *configure* the pipeline (namespaced `wms_gdrive.*` / `wms_reports.*` system parameters). No secret (OAuth client secret, refresh token, GPG passphrase) is ever stored, displayed, or logged by Odoo; backup artifacts on Drive are ciphertext.

Three fixed Scheduled-Task names are referenced by the code: **"WMS Daily Backup"**, **"WMS Manual Backup"**, and **"WMS Pending Upload Sweep"**, all registered once by `scripts/install-backup-tasks.ps1`. Files (encrypted `.dump.gpg` artifacts) go to the project `backups/` directory locally (overridable via `wms_reports.backup_dir`) and to the Drive folder tree (default root "Inventory_Backups", organised Year / Month / Day).

### Back Up Now
**Role:** Both *if granted* — gated by `group_wms_backup_now` ("WMS / Can Run Backup Now"); managers always have it, keepers only when the Admin grants it on their user form.
**Menu path:** WMS / Back Up Now (a top-level WMS menu item, not under Reports)
**Purpose:** Let a non-technical user trigger an immediate full backup (local + Google Drive) safely, with plain-language progress.
**Steps:**
1. Open WMS / Back Up Now. An info box explains it makes a safe copy now and nothing is deleted.
2. Click **Back Up Now**. The wizard writes a requester-attribution handshake (`wms_gdrive.last_manual_requester = "<login>|<UTC timestamp>"`), records a poll watermark, and fires the "WMS Manual Backup" Scheduled Task via `schtasks /Run` — so the manual backup runs in the same SYSTEM context as the nightly one. The state badge turns to **Running**.
3. Click **Refresh** to poll progress. The wizard reads `wms.backup.audit` rows recorded since you clicked: "Still working…" while running, then "Backup complete." with the filename, size, and time (and the Google Drive upload result) when done. You may close the window and keep working.
**Fields / columns:** State badge (Ready / Running / Done / Failed), `requested_at` (poll watermark, hidden), `result_html` (plain-language outcome).
**Buttons:** **Back Up Now** (`action_backup_now`, visible in Ready/Failed), **Refresh** (`action_refresh`, visible while Running), **Close**.
**Validation / errors:**
- If manual backups are disabled (`wms_gdrive.manual_enabled = 0`): "Backup Now is turned off." (the daily automatic backup still runs).
- If the "WMS Manual Backup" task is not installed / cannot start: "Could not start the backup. The 'WMS Manual Backup' scheduled task is not installed… Ask your administrator to run scripts\install-backup-tasks.ps1 once… Your daily automatic backup is not affected."
- If a backup row lands with failure and no success: "The backup did not complete. Nothing was lost — all previous backups are untouched. Ask your administrator to open WMS › Reports › Backup & DR Audit…" (Note: the underlying audit/settings screens actually live under Configuration; this is the wizard's wording.)
- Defense-in-depth `AccessError` "You are not allowed to run backups. Ask your administrator." if a user without the capability reaches the action.
**Result:** An on-demand encrypted backup, taken in the same trusted pipeline as the nightly run, with friendly completion feedback.

### Google Drive Backups (restore browser / catalog)
**Role:** Admin only
**Menu path:** WMS / Configuration / Google Drive Backups
**Purpose:** A read-only catalog of every Drive backup set (one row per set), grouped Year › Month › Day like the Drive folder tree, used to find a set and obtain its restore command. Restore itself is deliberately CLI-only.
**Steps:**
1. Open WMS / Configuration / Google Drive Backups. Rows are grouped by Year/Month/Day; amber rows are pending upload, blue rows are non-automatic (manual/emergency) sets.
2. Filter by Uploaded / Pending upload / Automatic / Manual / Pre-restore emergency, or group by Year/Month/Day/Type.
3. Open a set to see its facts (size, SHA-256 checksum, encrypted flag, restored count, Drive ids) and a **copy-paste restore command** (`scripts\gdrive-restore.ps1 -SetStamp <stamp>`, `CopyClipboardChar` widget). A warning box documents the full restore procedure.
**Fields / columns:** Backup time, name (local filename), backup type (Automatic / Manual / Pre-restore emergency), size MB (totalled), WMS version, checksum, creator, uploaded flag, upload time, set stamp, Drive name, restored count. Plus queue-state lifecycle fields written by the scripts (created / waiting / uploading / uploaded / failed / abandoned).
**Buttons:** None that act — create/edit/delete are disabled; the form is view-only and exposes the restore command for copy-paste.
**Validation / errors:** Empty-state explains rows are written automatically by `scripts/backup-native.ps1` after each upload and to run `scripts\setup-gdrive-auth.ps1` once to enable the Drive stage.
**Result:** A searchable disaster-recovery index from which any set's verified restore command can be copied.

### Download encrypted backup
**Role:** Admin only (operator at the server console)
**Menu path:** No Odoo button — this is part of the restore browser's documented flow and the `gdrive-restore.ps1` command it surfaces.
**Purpose:** Pull a chosen encrypted set down from Google Drive and verify it before any restore.
**Steps:**
1. In WMS / Configuration / Google Drive Backups, open the desired set and copy its restore command (`scripts\gdrive-restore.ps1 -SetStamp <stamp>`).
2. On the WMS server, open PowerShell in the project folder and run it. The script downloads the set from Drive and **triple-verifies the checksums** (SHA256.txt vs backup-info.json vs freshly computed hashes), renames the files back to the local convention, bumps the set's `restored_count`, and prints the exact `restore-native.ps1` command to run next.
**Fields / columns:** N/A (CLI). The catalog row shows the artifact's size, checksum, and encrypted flag as pre-download facts.
**Buttons:** N/A (the catalog provides the copy-paste command only).
**Validation / errors:** The script writes a `restore_gdrive` audit row (success/failure); failures surface to managers via the Drive-event notifier cron.
**Result:** A locally present, checksum-verified, still-encrypted backup ready to restore.

### Restore from backup (CLI)
**Role:** Admin only (operator at the server console)
**Menu path:** No Odoo button by design — restore can never be triggered from a screen so a misclick cannot wipe the live database. The procedure is documented on the catalog set's form.
**Purpose:** Restore a verified set into a database.
**Steps (as documented on the set form):**
1. Run the `gdrive-restore.ps1 -SetStamp <stamp>` command (above) to download + verify the set; it prints the next `restore-native.ps1` command.
2. Run that `restore-native.ps1` command. To restore automatically add `-AutoRestore -TargetDb <name>`: an **emergency backup of the current database is taken FIRST** (catalogued as a "Pre-restore emergency" set).
3. Restoring into the **live** database additionally requires `-Force` **plus** `-ConfirmTarget`. See `docs/22-gdrive-backup.md`.
**Fields / columns:** N/A (CLI). The restored set's `restored_count` increments after a successful restore.
**Buttons:** None in Odoo (intentional).
**Validation / errors:** Restore drills and restores write `restore_drill` / `restore_gdrive` audit rows; failures are escalated to managers (see Backup & DR Audit). The triple-checksum verification aborts on any mismatch.
**Result:** A safe, multiply-guarded restore with an automatic pre-restore safety backup.

### Backup & DR Audit
**Role:** Admin only
**Menu path:** WMS / Configuration / Backup & DR Audit
**Purpose:** The append-only operational log of every backup, Drive upload, restore, restore drill, staleness warning, and health-critical escalation — the screen to consult when something goes wrong.
**Steps:**
1. Open WMS / Configuration / Backup & DR Audit. Rows are newest first; red = failure, green = success.
2. Filter by "Failures only", Backups, Drive uploads, Restore drills, or Staleness warnings; group by Type or Outcome.
3. Open a row to read its full message/error, size, TOC entry count, duration, checksum, and host.
**Fields / columns:** Event time, Audit type (Database backup / Filestore backup / Off-site copy / Google Drive upload / Google Drive restore / Restore drill / Staleness warning / Health CRITICAL escalation), Name, Success toggle, Verified, Size MB (totalled), TOC entries, Duration, Host, Message. Rows are written directly via psql by the PowerShell scripts, so the trail survives even when Odoo's HTTP layer is down.
**Buttons:** None (create/edit/delete disabled).
**Validation / errors:** None on the screen. Several crons act on these rows: daily 08:00 backup-freshness check (escalates a backup older than 24h or a restore drill older than 7d to a manager notice), daily 08:05 Google Drive freshness (stale > 26h, DEGRADED only), hourly :15 restore-drill failure alert, every-4h health-CRITICAL escalation, hourly :25 Drive-event notifier, hourly :45 pending-upload retry.
**How health is determined:** `_health_snapshot()` ranks HEALTHY < DEGRADED < CRITICAL. CRITICAL = no successful DB backup ever recorded, the most recent recorded backup file is missing from disk, or a live DB query probe fails. DEGRADED = backup older than 24h, no/old restore drill, low free disk on the backup volume, or any Google Drive problem (Drive issues never escalate to CRITICAL — the local artifact is the backup that pages). The same snapshot feeds the public `/wms/health` endpoint (returns JSON; HTTP 503 when CRITICAL; optionally token-gated via `wms_reports.health_token`).
**Result:** A complete, tamper-evident backup/DR history with proactive manager alerting.

### Self-Diagnostics
**Role:** Admin only
**Menu path:** WMS / Configuration / Self-Diagnostics
**Purpose:** One-button aggregation of read-only health and data-integrity checks; nothing here writes or can corrupt data.
**Steps:**
1. Open WMS / Configuration / Self-Diagnostics. Checks run automatically on open (and again via the **Re-run checks** button).
2. Read the overall badge (All good / Warnings / Action needed) and the results table, sorted with failures first then warnings.
3. Act on any FAIL/WARN rows.
**Fields / columns:** A results table of Result (OK/WARN/FAIL, colour-coded), Check, and Detail. Checks run: System health (DB + backup file + disk free, from `_health_snapshot`), Duplicate SKUs (FAIL), Duplicate barcodes (FAIL), Negative on-hand on internal locations (FAIL), Storable products without a barcode (WARN), Orphan slots with no compartment parent (WARN), Dead stock count (WARN). Each probe is an isolated read-only SELECT so one failure cannot abort the rest.
**Buttons:** **Re-run checks** (`action_run`).
**Validation / errors:** A probe that errors is shown as a "check skipped: …" warning rather than crashing the page.
**Result:** A single pass/warn/fail integrity report the Admin can run anytime.

### Backup & Disaster Recovery (settings page)
**Role:** Admin only
**Menu path:** WMS / Configuration / Backup & Disaster Recovery
**Purpose:** The friendly front end over the `wms_gdrive.*` parameters and the operational controls for the Drive tier — enable/disable, schedule, retention, notifications, offline-queue tuning, connection testing, and retry — with a hard credential boundary (no raw secret is ever accepted, shown, stored, or logged).
**Steps:**
1. Open WMS / Configuration / Backup & Disaster Recovery. A live **health strip** shows backup status, last local backup age, Drive connected state, last Drive upload age, next backup time, and Drive storage used.
2. Configure: enable Google Drive upload / allow Backup Now; review Connection status and presence-only credential status; set the backup folder (paste a Drive folder URL — only the bare folder id is extracted and stored, never the URL); set daily backup time and the three Drive retention tiers; toggle manager notifications; tune the offline upload queue. Click **Save**.
3. Use the action buttons to verify and operate the Drive tier (see below).
**Fields / columns (editable):** Upload backups to Google Drive, Allow Backup Now, Daily backup time (HH:MM), Notify on success / failure, retention (daily days / weekly months / monthly years), Apply retention to manual & emergency sets, Drive folder name, Drive folder URL/ID, and offline-queue tuning (max upload attempts, retry window days, max sets per sweep, backoff base minutes). **Read-only status:** connection status, credential presence (Client ID / Client Secret / Refresh token — shown as configured/not configured/present only), folder-validation result, schedule timezone note, and the offline-queue panel (pending / waiting / abandoned / last upload / last failure / highest retry count).
**Buttons:**
- **Save** (`action_save`) — validates and writes the parameters.
- **Test Connection** (`action_test_connection`) — runs `gdrive-test.ps1 -Mode connection`; shows account email + storage used.
- **Validate Folder** (`action_validate_folder`) — runs `gdrive-test.ps1 -Mode validate-folder -FolderId <bare id>`; reports name/owner/writable.
- **Refresh Token** (`action_refresh_token`) — re-runs the connection test as live proof the stored token still works.
- **Disconnect** (`action_disconnect`, with confirm) — runs `setup-gdrive-auth.ps1 -Revoke` to revoke Drive auth and delete the token; local backups unaffected.
- **Connect…** (`action_connect_help`) — shows the one-time console instruction (`scripts\setup-gdrive-auth.ps1`); the OAuth consent must be done at the server, not from this page.
- **Retry Now** (`action_retry_now`) — fires the "WMS Pending Upload Sweep" task to re-attempt queued uploads (no-ops if still offline).
- **Apply Schedule** (`action_apply_schedule`) — `schtasks /Change` on the daily task to the new time.
- **Close**.
**Validation / errors:** Save rejects non-positive retention/queue values ("The <name> value must be a whole number greater than zero (got …)."), a malformed backup time ("The daily backup time must be 24h HH:MM, e.g. 16:30 …"), an empty folder name ("The Drive folder name cannot be empty."), and an invalid folder id ("The Drive folder ID looks invalid…"). Each subprocess action degrades gracefully when a script/task is missing (e.g. "Could not start the retry. The 'WMS Pending Upload Sweep' scheduled task is not installed…"). A non-manager hitting any action gets `AccessError` "Only WMS managers can change backup settings."
**Result:** A single manager console to configure, test, and operate the Google Drive off-site backup tier — while the local encrypted backups always run regardless of these settings.

---

### Backup / restore workflow at a glance
1. **Nightly:** the "WMS Daily Backup" Scheduled Task runs `backup-native.ps1` → pg_dump + GPG-encrypt → write to `backups/` → upload to Google Drive (Year/Month/Day tree) → INSERT `wms.backup.audit` rows and UPSERT a `wms.gdrive.backup` catalog row via psql.
2. **On demand:** WMS / Back Up Now fires the "WMS Manual Backup" task (same pipeline, attributed to the requester).
3. **If offline:** failed uploads queue (queue_state created/waiting/failed); the hourly :45 reconnect cron and the "Retry Now" button fire the "WMS Pending Upload Sweep" task, which uploads once connectivity returns.
4. **Monitoring:** crons escalate stale backups / failed drills / CRITICAL health to managers' Discuss inbox; `/wms/health` exposes status to external monitors; the Dashboard and the DR-page health strip show it in-app.
5. **Recovery:** from WMS / Configuration / Google Drive Backups, copy a set's restore command → run `gdrive-restore.ps1` (downloads + triple-verifies) → run the printed `restore-native.ps1` (with `-AutoRestore`/`-Force`/`-ConfirmTarget` for a live restore, which takes a pre-restore emergency backup first). Restore is CLI-only by design.
## 5. Pharmacy — Dispensing & Packaging

*Module: `wms_pharmacy` (v19.0.3.0.0) — "WMS — Pharmacy packaging engine". Depends on `wms_perishable` and `wms_barcode`. Implements the Box → Strip → Tablet packaging hierarchy, FEFO (first-expiry-first-out) tablet-level dispensing, open/partial-strip tracking, an immutable pharmaceutical genealogy log, and per-animal medication history.*

### How the roles map (read this first)

All Pharmacy menus live under **WMS / Pharmacy** (`menu_wms_pharmacy`, sequence 30 under the WMS root). The role names used below come from `wms_location/security/wms_security.xml`:

- **Storekeeper** = `group_wms_user` ("WMS / Store Keeper"), the everyday operator. The "Scan Issue" advantage is the sub-group `group_wms_can_scan_issue`.
- **Admin** = `group_wms_manager` ("WMS / Manager"). The Manager group *implies* every capability sub-group (including Scan Issue) plus the base Store Keeper role, so an Admin sees and can do everything below.

Menu gating (from `views/menus.xml`):

| Menu | XML group | Who sees it |
|---|---|---|
| Dispense Medicine | `group_wms_can_scan_issue` | Storekeeper *with the Scan Issue advantage* + Admin |
| Medication History | `group_wms_user` | Both (every WMS user) |
| Packaging Genealogy | `group_wms_user` | Both (every WMS user) |
| Open Strips | `group_wms_manager` | **Admin only** |
| Packaging Barcodes | `group_wms_manager` | **Admin only** |

A note on terminology: the dispense wizard does **not** present a box/strip/tablet "tier" dropdown to the operator. The operator always enters the quantity **in tablets**; the engine works out internally how many sealed strips to break open and how many tablets are left over. The explicit box/strip/tablet *tiers* are defined per product in **Packaging Barcodes** (one barcode label per tier) and in the product's packaging counts — see those sections.

---

### Dispense Medicine
**Role:** Both (Storekeeper with the Scan Issue advantage + Admin) — menu gated by `group_wms_can_scan_issue`; ACL `access_wms_dispense_wizard_user` grants read/write/create on the wizard to that group.
**Menu path:** WMS / Pharmacy / Dispense Medicine (opens the wizard as a pop-up dialog, `target="new"`).
**Purpose:** Dispense a set number of tablets of a packaged medicine, automatically drawing from the best lot by FEFO and using any already-open strip before breaking a sealed one, then record the deduction and a full genealogy log.

**Steps:**
1. Open **WMS / Pharmacy / Dispense Medicine**. A dialog titled "Dispense Medicine" appears with a blue info banner explaining that the system draws from the earliest-expiry available lot (FEFO) and uses any open strip before breaking a new one.
2. In **Medicine**, pick the product to dispense. The dropdown is filtered to packaged products only (domain `product_tmpl_id.wms_is_packaged = True`); creating products inline is disabled (`no_create`).
3. In **Tablets to dispense**, enter the number of individual tablets (defaults to 1; must be at least 1).
4. *(Optional)* In **Animal**, select the animal receiving the dose. When set, this dispense is linked to that animal's Medication History.
5. In **Storage location**, choose the internal location (shelf / rack / slot) to draw stock from. The dropdown is limited to internal locations (domain `usage = internal`); inline create is disabled.
6. *(Optional)* In the **Note** box, type a treatment reason or dosage instruction; it is stored on the genealogy log.
7. Click **Dispense**. On success a green "Dispensed" toast summarises the tablets, lot, animal (if any), how many sealed strips were opened, and the new log number. The dialog closes.

**What the engine does on Dispense (`action_dispense`), in order:**
1. **Guards the product** — re-checks `wms_is_packaged`; if the product also has no "Tablets per strip" configured, it stops with an error.
2. **Selects the lot (strip-level FEFO + open-package optimisation, `_select_fefo_lot`):** searches all live `stock.quant` rows for the product at or below the chosen location (`child_of`, quantity > 0, with a lot); excludes any lot that is not `available` (`wms_lot_state`) or is expired; aggregates available quantity per lot; sorts by **(expiry ascending, then "has an open strip here" preferred)** so on an expiry tie the lot that already has an open strip wins; returns the first lot that alone can cover the full request.
3. **Accounts for strips:** draws first from any existing open strip for that (product, lot, location) — `find_for` — reducing it (and deleting the open-strip row if it hits zero); then "opens" sealed strips one at a time for the remainder, counting `strips_opened`. The leftover from the last opened strip (`tablets_per_strip` minus what was needed) is registered as a new open strip via `open_new`.
4. **Deducts stock** for the full quantity via the Odoo 19 done-move recipe (`_create_done_move`): creates a `stock.move` from the location to the Customers location, confirms it, clears the auto-created move line, creates one `stock.move.line` carrying the chosen `lot_id` and exact quantity, sets `picked = True`, and calls `_action_done()`.
5. **Writes the genealogy log** — creates one immutable `wms.dispense.log` row (see below), under `sudo()` so the operator does not need write access on the log model.

**Fields:**
- **Medicine** (`product_id`, Many2one → `product.product`) — *required*. Packaged products only.
- **Tablets to dispense** (`quantity`, Integer) — *required*, default 1, must be ≥ 1.
- **Animal** (`animal_id`, Many2one → `wms.animal`) — optional.
- **Storage location** (`location_id`, Many2one → `stock.location`) — *required*, internal locations only.
- **Note** (`note`, Text) — optional.

**Buttons:**
- **Dispense** — `type="object"`, method `action_dispense()` (runs the full FEFO → strip-accounting → stock-deduction → log flow above; returns the success notification).
- **Cancel** — `special="cancel"` (closes the dialog, no effect).

**Validation / errors (real messages):**
- **Zero/negative quantity** — `@api.constrains('quantity')` raises a `UserError`: "Tablets to dispense must be at least 1. Got: …" (fires on create, so an invalid quantity is rejected before Dispense is even clicked).
- **Product not packaged** — `UserError`: "Product '…' is not flagged as packaged (Box→Strip→Tablet). Configure the Pharmacy packaging counts on the product form first."
- **No tablets-per-strip configured** — `UserError`: "Product '…' has no 'Tablets per strip' configured. Set it on the WMS Classification tab before dispensing."
- **No stock at all** — `UserError`: "No stock found for '…' at '…'. Receive stock first before dispensing."
- **No *available* stock** (everything quarantined / recalled / expired) — `UserError`: "No available (non-quarantined, non-recalled, non-expired) stock of '…' found at '…'."
- **Insufficient stock in any single lot** — `UserError` stating Requested vs. Total available across all eligible lots, and "No single lot has enough to cover the full dispense. Reduce the quantity or receive more stock." (The dispense will not split across lots.)
- **Quarantined / recalled / expired lots are silently skipped** during FEFO selection (verified by tests `test_fefo_skips_quarantined_lots`, `test_fefo_skips_expired_lot`); expired stock is never drawn down.

**Result:** One `stock.move` (state *done*) deducts `quantity` tablets (product base UoM = Units) from the chosen lot at the storage location, moving them to the Customers location. One `wms.dispense.log` row is created. An open-strip row may be created/updated (leftover tablets) or deleted (strip exactly consumed or open strip exhausted). The success toast confirms tablets, lot, optional animal, strips opened, and the log id.

**Partial-strip handling (worked behaviour, from the code + tests):**
- Dispense **7** tablets from a 10-per-strip product with no open strip → opens **1** sealed strip, leaves an open strip of **3** tablets (`strips_opened = 1`).
- Dispense **10** (exact strip) → opens **1** strip, **no** open strip remains.
- Dispense **25** → opens **3** strips (ceil 25/10), open strip of **5** remains.
- With an existing open strip of **4** tablets, dispense **3** → comes entirely from the open strip (`strips_opened = 0`), open strip now **1**.
- Open strip of **6**, dispense **14** → 6 from the open strip, then **1** sealed strip opened for the remaining 8, open strip of **2** remains.
- Dispense exactly the open strip's remaining tablets → that open-strip row is **deleted**.

---

### Open Strips
**Role:** Admin only — menu gated by `group_wms_manager`. (ACL: Store Keepers get read-only on `wms.open.strip` via `access_wms_open_strip_user`, but the menu is hidden from them; Managers get full read/write/create/unlink via `access_wms_open_strip_mgr`.)
**Menu path:** WMS / Pharmacy / Open Strips
**Purpose:** View and manage the loose tablets left in partially-used strips, one record per (product, lot, location), kept in sync automatically by the dispense wizard.

**Steps:**
1. Open **WMS / Pharmacy / Open Strips** to see the list of open strips: Product, Lot, Location, Tablets remaining, Opened on, Opened by.
2. Use the search filters — search by Product / Lot / Location, or group **By product** / **By location**.
3. Click a row to open its form (read-only operational fields) showing the Location group (Product, Lot, Location) and State group (Tablets remaining, Opened on, Opened by).
4. As an Admin you *can* manually create or adjust a row, but normally these are created and decremented automatically by the dispense wizard and deleted when they reach zero.

**Fields:**
- **Product** (`product_id`, Many2one → `product.product`) — *required*.
- **Lot** (`lot_id`, Many2one → `stock.lot`) — *required*.
- **Location** (`location_id`, Many2one → `stock.location`) — *required*.
- **Tablets remaining** (`tablets_remaining`, Integer) — *required*, must be > 0 (see constraint).
- **Opened on** (`opened_on`, Datetime) — read-only, defaults to now.
- **Opened by** (`opened_by`, Many2one → `res.users`) — read-only, defaults to the current user.

**Buttons:** No custom buttons. The model exposes helper methods used internally by the dispense wizard — `find_for(product, lot, location)` (returns the matching open strip with tablets remaining) and `open_new(product, lot, location, tablets_remaining)` (creates or replaces the row for that combination).

**Validation / errors:**
- **UNIQUE(product_id, lot_id, location_id)** (`_open_strip_unique`) — only one open strip per product/lot/location: "Only one open strip record is allowed per product / lot / location."
- **CHECK(tablets_remaining > 0)** (`_tablets_positive`) — "Tablets remaining must be positive — delete the row when it reaches zero." (The wizard deletes the row rather than letting it hit zero.)
- `open_new` raises a `UserError` if asked to register zero or negative tablets: "Cannot register an open strip with zero or negative tablets (…). Use find_for() to check first."

**Result:** Maintains the authoritative count of loose tablets per open strip. The next dispense for the same product/lot/location draws from this row first (open-package optimisation) before breaking a new sealed strip.

---

### Packaging Barcodes
**Role:** Admin only — menu gated by `group_wms_manager`. (ACL: Store Keepers read-only via `access_wms_pharma_barcode_user`; Managers full CRUD via `access_wms_pharma_barcode_mgr`.)
**Menu path:** WMS / Pharmacy / Packaging Barcodes
**Purpose:** Define one barcode per packaging tier (Box, Strip, Tablet) for a packaged medicine, so a single scan resolves to the product and the number of tablets it represents.

**Steps:**
1. Open **WMS / Pharmacy / Packaging Barcodes** to see all packaging barcodes: Product, Tier, Barcode, Base units.
2. Click **New** and select the **Product** (packaged products only).
3. Choose the **Tier** — *Box (sealed full box)*, *Strip (one sealed strip)*, or *Tablet (individual tablet)*.
4. Enter the **Barcode** string printed on that label.
5. Save. **Base units** is computed automatically and shown read-only: Box → the product's tablets-per-box; Strip → tablets-per-strip; Tablet → 1.
6. Use the search view to filter by tier (Box / Strip / Tablet) or group **By product** / **By tier**.

**Fields:**
- **Product** (`product_id`, Many2one → `product.product`) — *required*. Packaged products only.
- **Tier** (`tier`, Selection: `box` / `strip` / `tablet`) — *required*.
- **Barcode** (`barcode`, Char) — *required*, must be globally unique (see constraints).
- **Base units (tablets)** (`base_units`, Integer) — computed (`_compute_base_units`), stored, read-only.

**Buttons:** No custom action buttons. The public API is the class method `resolve(barcode)` — used by the dispense/scanner layer — which returns `{'kind': 'pharma', 'product': …, 'tier': …, 'base_units': …}` for a known barcode, or `{'kind': None}` for an unknown/empty string so the caller falls through to the standard `wms.barcode.alias` resolver.

**Validation / errors:**
- **UNIQUE(barcode)** (`_barcode_unique`) — "Each pharmacy packaging barcode must be unique." (The same string cannot be reused across tiers either.)
- **Collision guard** (`@api.constrains('barcode')` → `_check_no_collision`, `ValidationError`): rejects a barcode already used as a product unit barcode ("Barcode '…' is already a product's unit barcode."), a location barcode ("…is already a location barcode."), or a lot/serial number ("…is already a lot / serial number.").

**Result:** A reusable barcode-to-tier mapping; scanning resolves to the product plus the correct tablet count (box/strip/tablet), feeding stock and dispense logic.

---

### Packaging Genealogy
**Role:** Both (every WMS user) — menu gated by `group_wms_user`. (Read-only for Store Keepers; this is the same underlying log model as Medication History, opened with a product-grouped view.)
**Menu path:** WMS / Pharmacy / Packaging Genealogy
**Purpose:** Trace pharmaceutical lineage — which lot/batch of which medicine was dispensed, how many strips were opened, and the frozen packaging counts — grouped by product/lot for recall and box→strip→tablet traceability.

**Steps:**
1. Open **WMS / Pharmacy / Packaging Genealogy**. It opens the dispense-log list pre-grouped **By product** (action `action_wms_dispense_genealogy`, context `search_default_group_product`).
2. Expand a product (or regroup) and read each event's Lot/Batch, Tablets dispensed, Sealed strips opened, and the Tablets-per-strip / Tablets-per-box snapshots.
3. To answer "which animals received stock from lot X?" (e.g. during a recall), search or group **By product** and inspect the lots; the lot link gives full batch traceability.
4. Click any row to open the read-only genealogy form (see Medication History / Genealogy Log for the form layout).

**Fields:** Same model as the genealogy log — see the field list under *Medication History / Genealogy Log* below. The genealogy emphasis is on `lot_id` (batch), `strips_opened`, and the `tablets_per_strip` / `tablets_per_box` snapshots.

**Buttons:** None (list is `create="false" edit="false"`; the form is `create="false"`). View/search only.

**Validation / errors:** Records are immutable (see the write/unlink guards under the log section). No editing is possible from this view.

**Result:** A grouped, read-only trace of dispense lineage. No records are created or changed by viewing.

---

### Medication History / Genealogy Log
**Role:** Both (every WMS user) — menu gated by `group_wms_user`. (ACL: Store Keepers read-only via `access_wms_dispense_log_user`; Managers read/write/create/unlink via `access_wms_dispense_log_mgr` — but see the immutability guards, which block edits/deletes even for Managers.)
**Menu path:** WMS / Pharmacy / Medication History
**Purpose:** The append-only audit trail of every dispense — what was given, from which lot, to which animal, by whom, and when — and the per-animal medication record.

**Steps:**
1. Open **WMS / Pharmacy / Medication History**. The list opens pre-grouped **By animal** (action `action_wms_dispense_log`, context `search_default_group_animal`). Columns: Dispense date, Product, Lot/Batch, Animal, Tablets dispensed, Sealed strips opened, Tablets per strip, Tablets per box, Dispensed by.
2. Use the search view to search by Product / Lot / Animal / Dispensed by, apply the **This month** filter, or group **By animal** / **By product** / **By month**.
3. Click a row to open the read-only "Dispense genealogy log" form: a Dispense-event group (Dispense date, Product, Lot/Batch, Animal | Tablets dispensed, Dispensed by, Issue picking), a Packaging-genealogy snapshot group (Sealed strips opened, Tablets per strip, Tablets per box), and a Note group.
4. **Per-animal view:** open an animal (`wms.animal`) form — a **Medication** smart button (medkit icon, hidden when the count is 0) shows the dispense count and opens that animal's history (`action_view_dispense_logs`), and a **Medication History** notebook page lists the animal's dispense events (Dispense date, Product, Lot, Tablets dispensed, Sealed strips opened, Dispensed by). Both the smart-button list and the notebook list are read-only (`create="false" edit="false"`).

**Fields (model `wms.dispense.log`):**
- **Product** (`product_id`, Many2one → `product.product`) — *required*, `ondelete="restrict"`.
- **Lot / Batch** (`lot_id`, Many2one → `stock.lot`) — *required*, `ondelete="restrict"`.
- **Animal** (`animal_id`, Many2one → `wms.animal`) — optional, `ondelete="set null"`.
- **Tablets dispensed** (`quantity`, Integer) — *required*.
- **Dispense date** (`dispense_date`, Datetime) — *required*, defaults to now.
- **Sealed strips opened** (`strips_opened`, Integer) — default 0 (0 when served entirely from an already-open strip).
- **Tablets per strip (snapshot)** (`tablets_per_strip`, Integer) — frozen at dispense time.
- **Tablets per box (snapshot)** (`tablets_per_box`, Integer) — frozen at dispense time.
- **Dispensed by** (`dispensed_by`, Many2one → `res.users`) — *required*, `ondelete="restrict"`.
- **Note** (`note`, Text) — optional, free text (this is the **only** field that stays editable).
- **Issue picking** (`picking_id`, Many2one → `stock.picking`) — read-only, `ondelete="set null"`.

**Buttons:** None on the log itself (the form is `create="false"`; the list is `create="false" edit="false"`). On the animal form: **Medication** smart button → `action_view_dispense_logs()` (opens this animal's history, with create disabled).

**Validation / errors — immutability (what users can and cannot edit):**
- **Editing is blocked** for the genealogy content. `write()` checks the change against `_PROTECTED_FIELDS` = {`product_id`, `lot_id`, `quantity`, `strips_opened`, `tablets_per_strip`, `tablets_per_box`, `dispense_date`, `dispensed_by`}; touching any of these raises a `UserError`: "Dispense genealogy records are immutable — the pharmaceutical audit trail cannot be edited." This applies **even to a Manager/Admin**, despite the ACL granting write.
- **Deletion is blocked** by an `@api.ondelete(at_uninstall=False)` guard (`_prevent_dispense_log_unlink`) raising a `UserError`: "Dispense genealogy records cannot be deleted — they are the pharmaceutical audit trail." (Implemented as an `@api.ondelete` guard rather than a raising `unlink()` override, satisfying pylint-odoo's no-raise-unlink; `at_uninstall=False` still allows the module to uninstall cleanly.)
- **What users *can* edit:** only the free-text **Note** (not in the protected set). The `animal_id` and `picking_id` fields are deliberately left out of the protected set so their `ondelete="set null"` cascades still work when a linked animal or picking is removed. (Behaviour verified by `test_dispense_log_is_append_only`: setting `quantity` raises, `unlink()` raises, setting `note` succeeds.)

**Result:** A permanent, append-only record per dispense event. Rows are created only by the dispense wizard; thereafter they cannot be edited (except the note) or deleted, preserving the pharmaceutical audit trail and the per-animal medication history (`animal.dispense_log_ids` / `wms_medication_count`).
## 6. Intelligence Analytics & Help

The Warehouse Intelligence layer (addon `wms_analytics`, version 19.0.2.0.0) is an additive analytics module that reads the Wave 1 perishable data (lots, quants, forecast, damage, recall, quarantine) and owns a set of read-only reporting models. Almost every view is an `_auto=False` PostgreSQL view (always fresh, no stored data, read-only), so the list/graph/pivot dashboards reflect the live database every time they are opened.

All of these views live under one app menu: **WMS app root → Intelligence** (`menu_wms_analytics_root`, sequence 60). The root Intelligence menu is gated to `wms_location.group_wms_user`, so a Store Keeper sees the Intelligence section. Visibility and role gating per view are summarised below; the underlying security comes from `addons/wms_analytics/security/ir.model.access.csv`, where every SQL-view model grants read-only access (`perm_read=1`, no write/create/unlink) to **both** `group_wms_user` and `group_wms_manager`. The two exceptions that allow data entry are the Cold Chain reading model (user can read + create; manager full CRUD) and the bulk server actions (code-gated to manager).

Role legend used below: **Both** = visible/usable by Store Keeper (`group_wms_user`) and Manager (`group_wms_manager`); **Admin/Manager only** = `group_wms_manager`.

---

### KPI Dashboard
**Role:** Admin only (Manager).
**Menu path / URL:** Intelligence → KPI Dashboard (`menu_wms_intelligence_dashboard`, sequence 5, `groups="wms_location.group_wms_manager"`). Opens the server-rendered page at **/wms/intelligence** in a new browser tab (an `ir.actions.act_url`, target `new`). The controller `WmsIntelligenceDashboard.intelligence` returns `not_found()` unless the user is in `group_wms_manager`, so the URL is manager-gated even if reached directly.
**Answers:** "What is the overall state of the warehouse right now — across stock, quality, movement and risk — on a single screen?"
**Key columns/metrics:** Plain KPI tiles grouped into three sections (no list/graph). Computed in `controllers/main.py::_kpis`.
- Inventory section: **Products** (count of `product.product` where `is_storable = True`); **Total inventory (units)** (sum of `wms.stock.health.total_qty`); **Inventory value** (SQL `_read_group` sum of `wms.forecast.stock_value`); **Stock health** (`100 × healthy_qty / total_qty` from `wms.stock.health`, shown green ≥90, amber ≥70, red below).
- Needs attention section: **Near expiry**, **Expired**, **Recalled**, **Quarantined** (the `near_qty` / `expired_qty` / `recall_qty` / `quarantine_qty` roll-ups from `wms.stock.health`); **Damaged** (`wms.damage` count in state `confirmed`); **Under repair** (`wms.repair.order` count in state `in_repair`); **Expiry risk: critical** and **Expiry risk: high** (counts of `wms.lot.expiry.risk` with `risk_band` critical / high).
- Movement & replenishment section: **Fast moving** / **Slow moving** / **Dead stock** (`wms.forecast` counts where `velocity_class` = fast / slow / dead); **Overstock risk** (`wms.forecast` where `overstock_risk` in medium/high); **Low stock / reorder** (`wms.forecast` where `reorder_qty > 0`).
**Views & filters:** None — it is a static read-only HTML tile board, no filters or group-bys.
**How to use:**
1. Open Intelligence → KPI Dashboard (opens /wms/intelligence in a new tab).
2. Scan the three tile blocks top-to-bottom; the Stock-health tile is colour-coded for an at-a-glance health read.
3. For any worrying number (e.g. Expired, Recalled, Expiry risk: critical) jump to the matching detail dashboard below to act.
**Role notes:** Manager-only by both the menu `groups` and the controller group check.

---

### Heat Map
**Role:** Both (Store Keeper + Manager).
**Menu path / URL:** Intelligence → Heat Map (`menu_wms_heatmap`, sequence 8). Opens the server-rendered page at **/wms/intelligence/heatmap** in a new tab. Controller `WmsIntelligenceDashboard.heatmap` requires `group_wms_user`.
**Answers:** "Walking the floor, which racks/zones need attention — because of a quality problem (recall/quarantine/expiry) or because they are full/empty?"
**Key columns/metrics:** A grid of coloured tiles, one per rack / floor location, grouped by zone (and an "<warehouse> / Unzoned" group per warehouse). Each tile shows the location name, a status label, and on-hand units. Colour is chosen by strict precedence in `_tile` / `_status_from_quants` / `_occ_color`: status colour wins over occupancy colour. Status precedence (worst first): **Recall** (#7f1d1d) > **Quarantine** (#b45309) > **Expired** (#b91c1c, any quant's `wms_effective_expiry` < today) > **Near expiry** (#d97706, effective expiry within 30 days). If no status applies, the tile falls back to occupancy: **Empty** (grey, on-hand ≤ 0), **Stocked** (blue, pct ≤ 0 but stock present), **Full** (#dc2626, pct ≥ 100), **Most full** (#f59e0b, pct ≥ 75), **OK** (#16a34a). Rack occupancy pct = occupied slots / total slots; floors use `wms_occupancy_pct`. Status is resolved from a single batched `stock.quant` query (no per-tile lookups).
**Views & filters:** None — static colour grid with a legend; no filters.
**How to use:**
1. Open Intelligence → Heat Map.
2. Read the legend, then scan for dark-red/amber tiles first (these are recall/quarantine/expiry, not just fullness).
3. Note the location name and on-hand on the tile, then go inspect or act on that rack/zone.
**Role notes:** Visible to Store Keeper and Manager (`group_wms_user`).

---

### Expiry Risk
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Expiry Risk (`menu_wms_lot_expiry_risk`, sequence 10). Model `wms.lot.expiry.risk` (SQL view). Action defaults to filter **High + Critical** (`search_default_at_risk`).
**Answers:** "Which lots will expire before they are consumed?" — sharper than a flat calendar-distance expiry list, because it folds in consumption velocity.
**Key columns/metrics:** **Risk band** (badge: Low/Medium/High/Critical — red critical, amber high, blue medium); **Lot / batch** (`lot_id`); **Product**; **Days to expiry** (`expiration_date - CURRENT_DATE`; negative = expired); **On hand** (live issuable units in internal storage, excluding damage/repair sinks); **Daily avg** (`wms.forecast.daily_avg` consumption); **Days of cover** (`on_hand / daily_avg`; blank when no measured consumption); **Value at risk** (on-hand × unit cost, summed in the list). Risk band logic (SQL CASE): already expired → critical; if no consumption → high/medium/low purely by ≤30 / ≤90 / >90 days; otherwise compares days-of-cover to remaining shelf life (cover ≥ 2× shelf life → critical, cover > shelf life → high, cover > 0.75× shelf life → medium, else low).
**Views & filters:** list / pivot / graph (pivot rows = risk band, measures value-at-risk + on-hand; bar graph value-at-risk by band). Filters: Critical, High, **High + Critical** (default), **No measured consumption** (`daily_avg = 0`). Group-bys: Risk band, Product.
**How to use:**
1. Open Intelligence → Expiry Risk (lands pre-filtered on High + Critical).
2. Sort or group by Risk band; watch the **Value at risk** total to prioritise money exposure.
3. For a critical/high lot, push it for issue (FEFO), discount, transfer, or flag for disposal.
**Role notes:** Read-only for both roles.

---

### Stock Health
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Stock Health (`menu_wms_stock_health`, sequence 20). Model `wms.stock.health` (SQL view) — one row per company.
**Answers:** "What proportion of my on-hand stock is healthy versus near-expiry / expired / quarantined / recalled?"
**Key columns/metrics:** **Company**; **Health score** (badge: red <60, amber 60–84, green ≥85 — equals Healthy %, the % of on-hand that is healthy); quantity buckets **Total / Healthy / Near expiry / Expired / Quarantine / Recall** (each summed); and the matching percentages **Healthy % / Near expiry % / Expired % / Quarantine % / Recall %**. Every live storage quant is placed in exactly one bucket by strict precedence Recall > Quarantine > Expired > NearExpiry > Healthy (recall/quarantine from `stock.lot.wms_lot_state`; expired/near from per-quant `wms_effective_expiry`, near = within 30 days). The quantity buckets are aggregated in SQL; the percentages and score are Python computes.
**Views & filters:** list / graph (bar graph of the five quantity buckets by company). Filter/group-by: Company.
**How to use:**
1. Open Intelligence → Stock Health.
2. Read the Health score badge per company; expand the bucket columns to see where unhealthy stock sits.
3. Drill into Expiry Risk / Recall Dashboard / Cold Chain to clear the offending buckets.
**Role notes:** Read-only for both roles.

---

### Disposal / Loss Analytics
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Disposal / Loss Analytics (`menu_wms_disposal_report`, sequence 20). Model `wms.disposal.report` (SQL view). Action defaults to group by Month.
**Answers:** "What is the trust losing as physical loss (not consumption), why, and what does it cost — trended over time?"
**Key columns/metrics:** **Disposal date**; **Source** (badge: Damage event = amber, Destroyed lot = red); **Reason** (damage reason — Broken/Expired/Contaminated/Other — or "Destroyed lot"); **Product**; **Quantity** (summed); **Disposal value** (summed). The report UNIONs two branches: confirmed `wms.damage` events (value = the frozen `damage_value` snapshot) and destroyed lots (`stock.lot.wms_lot_state = 'destroyed'`, valued at current on-hand × unit cost as a proxy). A **Month** column (first of month) drives trend grouping.
**Views & filters:** list / pivot / graph (pivot rows = month, cols = source, measures disposal-value + quantity; bar graph value by month). Filters: Damage events, Destroyed lots. Group-bys: **Month** (default), Reason, Source, Product.
**How to use:**
1. Open Intelligence → Disposal / Loss Analytics (lands grouped by month).
2. Switch to pivot/graph to see the monthly loss-value trend; group by Reason to see the dominant loss cause.
3. Feed findings back to receiving / storage / supplier management to cut recurring loss.
**Role notes:** Read-only for both roles.

---

### Lot Audit
**Role:** Both (read-only list; badge also appears on the lot form).
**Menu path / URL:** Intelligence → Lot Audit (`menu_wms_lot_audit`, sequence 20). Action over `stock.lot` using a dedicated list sorted by audit score ascending (worst-documented first). The audit fields are added by `addons/wms_analytics/models/stock_lot.py` and also render on the standard lot form under a "Traceability audit" group.
**Answers:** "Which lots are under-documented — missing supplier, expiry, storage, or movement history?"
**Key columns/metrics:** **Lot/Name**; **Product**; **Audit score** (0–7, a non-stored live compute); **Audit band** (badge: High = 6–7 green, Medium = 4–5 amber, Low = 0–3 red); and the individual check booleans **Batch / Supplier / Barcode / Expiry / Timeline / Movement / Storage OK**. The seven checks: batch (name present and not auto `LOT-…`), supplier (`wms_supplier_id` set), barcode (name present), expiry (`expiration_date` set), timeline (`wms_movement_count > 0`), movement (has live quants), storage (has a quant in a real internal slot, not a damage/repair sink). `Audit %` = score / 7.
**Views & filters:** list, form. (No graph/pivot; ordering is by `wms_audit_score`.) On the form the same score, %, band and seven check flags appear in the "Traceability audit" group.
**How to use:**
1. Open Intelligence → Lot Audit (worst-scored lots at the top).
2. Read across the OK columns to see which metadata is missing for a low lot.
3. Open the lot and fill the gap (supplier, expiry, etc.); the score refreshes live.
**Role notes:** Read-only list for both roles; the data is computed on the fly so it is always current.

---

### Supplier Scorecard
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Supplier Scorecard (`menu_wms_supplier_scorecard`, sequence 30). Model `wms.supplier.scorecard` (SQL view) — one row per supplier partner that has ever supplied a lot.
**Answers:** "Which suppliers deliver good stock, and which cause recalls, QC rejections, damage, or expiries?"
**Key columns/metrics:** **Quality band** (badge: Poor red <50, Watch amber 50–79, Good green ≥80); **Supplier**; **Quality score** (starts at 100, subtracts weighted penalties — 15/recall, 10/QC rejection, 5 if any damage, 3/expired lot — clamped to 0); **Acceptance rate** and **Rejection rate** (share of received lots that were / were not recalled+rejected+expired, capped at 100%); **Lots received**; **Recalls**; **QC holds**; **QC rejections**; **Damaged qty**; **Damaged value**; **Expired lots**. Recalls are attributed both ways (named on the recall, or any recall touching the supplier's lots) and de-duplicated.
**Views & filters:** list / pivot / graph (pivot rows = supplier, measures quality-score + recalls + QC rejections + damaged value + expired lots; bar graph quality-score by supplier). Filters: Poor / Watch / Good, Has recalls, Has QC rejections, Has damage, Has expired lots. Group-by: Quality band.
**How to use:**
1. Open Intelligence → Supplier Scorecard (sorted worst-score first).
2. Filter Poor/Watch or "Has recalls" to find problem vendors.
3. Drill into the **Supplier Ledger** to see the individual batches behind a bad score.
**Role notes:** Read-only for both roles.

---

### Supplier Ledger
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Supplier Ledger (`menu_wms_supplier_ledger`, sequence 31). Model `wms.supplier.ledger` (SQL view) — one row per received lot. Action defaults to group by Supplier.
**Answers:** "What individual batches did each supplier deliver, and what is their state and remaining quantity?"
**Key columns/metrics:** **Received on** (lot create date); **Supplier**; **Product**; **Batch / lot**; **Supplier batch** (`wms_supplier_batch`); **Supplier invoice** (hidden by default); **Expiration date**; **Lot state** (badge: Available green, Quarantine amber, Recalled/Destroyed red); **On hand** (live issuable units, summed).
**Views & filters:** list / pivot / graph (pivot rows = supplier → product, measure on-hand). Filters: On hand, Recalled, Quarantine. Group-bys: **Supplier** (default), Product, Lot state, Received (month).
**How to use:**
1. Reach it from a Supplier Scorecard row, or open Intelligence → Supplier Ledger directly.
2. Group/filter to the supplier of interest; read each batch's state and on-hand.
3. Use it as the receipt history behind a scorecard verdict.
**Role notes:** Read-only for both roles.

---

### Recall Dashboard
**Role:** Both for viewing (read-only list/graph/pivot); recall lifecycle actions are Manager-only.
**Menu path / URL:** Intelligence → Recall Dashboard (`menu_wms_recall_dashboard`, sequence 40). Model is `wms.lot.recall` (the Wave 1 recall, extended in `wms_recall_dashboard.py` with stored roll-up measures). List is `create="false" edit="false"`. Both `group_wms_user` and `group_wms_manager` can read `wms.lot.recall`; only managers can write it.
**Answers:** "For each recall, how much of the recalled stock was issued out, is still on hand, was destroyed, and came back?"
**Key columns/metrics:** **Name** (recall reference); **State** (badge: Active amber, Released muted); **Supplier**; **Recalled on**; and four stored roll-ups computed over the recalled lots: **Issued out** (`issued_quantity`, total done out-moves that left internal storage), **Still on hand** (`remaining_quantity`, live internal on-hand excluding damage/repair sinks), **Destroyed** (`destroyed_quantity`, quantity of recalled lots now in `destroyed` state), **Returned in** (`returned_quantity`, done in-moves back into storage). All four are summed in the list. `is_open` = state is `active`.
**Views & filters:** list / graph / pivot (graph rows = state, measures still-on-hand + issued + destroyed; pivot rows = supplier, cols = state, all four measures). Filters: Open (active), Released. Group-bys: Supplier, State.
**How to use:**
1. Open Intelligence → Recall Dashboard.
2. Filter Open (active) and read **Still on hand** — that is the stock the recall has not yet contained.
3. A Manager works the recall to closure on the recall record itself (this dashboard is read-only).
**Role notes:** Viewing is Both; activating/releasing/destroying a recall is Manager-only (the recall model's write/actions are manager-gated).

---

### Lot Ledger
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Lot Ledger (`menu_wms_lot_ledger`, sequence 40). Model `wms.lot.ledger` (SQL view over done `stock.move.line`, restricted to lot-tracked moves). Action defaults to group by Lot.
**Answers:** "Every completed movement of a lot-tracked batch — receipts, issues and internal relocations — in chronological order."
**Key columns/metrics:** **Date** (when stock physically moved); **Lot**; **Product**; **Direction** (badge: In green / Out red / Internal muted — derived from source vs destination location usage); **Quantity** (summed); **From** (`location_id`); **To** (`location_dest_id`); **Transfer** (`picking_id`).
**Views & filters:** list / pivot / graph (pivot rows = lot, cols = direction, measure quantity; bar graph quantity by direction). Filters: In, Out, Internal. Group-bys: **Lot** (default), Product, From location, To location, Direction, Date.
**How to use:**
1. Open Intelligence → Lot Ledger (grouped by lot).
2. Search a lot or product; read its in/out/internal trail down the date axis.
3. Use it to reconstruct exactly where a batch went and when.
**Role notes:** Read-only for both roles.

---

### Product Ledger
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Product Ledger (`menu_wms_product_ledger`, sequence 41). Model `wms.product.ledger` (SQL view over all done move lines). Action defaults to group by Product.
**Answers:** "Every completed stock movement, by product — a full in/out/internal trail."
**Key columns/metrics:** Same projection as the Lot Ledger — **Date, Product, Lot, Direction** (badge), **Quantity** (summed), **From, To, Transfer** — but keyed/grouped on product (includes non-lot moves).
**Views & filters:** list / pivot / graph (pivot rows = product, cols = direction, measure quantity). Filters: In, Out, Internal. Group-bys: **Product** (default), Lot, From location, To location, Direction, Date.
**How to use:**
1. Open Intelligence → Product Ledger (grouped by product).
2. Filter Out to see total issues of a product, or In to see receipts, over a date range.
3. Read it as the per-product movement history.
**Role notes:** Read-only for both roles.

---

### Warehouse Ledger
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Warehouse Ledger (`menu_wms_warehouse_ledger`, sequence 42). Model `wms.warehouse.ledger` (SQL view over all done move lines). Action defaults to group by To location.
**Answers:** "What landed where, and what left — every completed movement by location/warehouse."
**Key columns/metrics:** Same projection but column order leads with **To** (`location_dest_id`) then **From**, plus **Date, Product, Lot, Direction** (badge), **Quantity** (summed), **Transfer**. Search also exposes **To warehouse** (`dest_warehouse_id`).
**Views & filters:** list / pivot / graph (pivot rows = To location, cols = direction, measure quantity). Filters: In, Out, Internal. Group-bys: **To location** (default), From location, To warehouse, Product, Direction, Date.
**How to use:**
1. Open Intelligence → Warehouse Ledger (grouped by destination location).
2. Group by To warehouse to see inter-warehouse flow, or by To location for what filled a given bay.
3. Read it as the location-centric movement history.
**Role notes:** Read-only for both roles.

---

### Department Usage
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Department Usage (`menu_wms_department_usage`, sequence 40). Model `wms.department.usage` (SQL view). Action defaults to group by Department.
**Answers:** "Which department/cost-centre consumed what, and what did it cost?"
**Key columns/metrics:** **Month** (`period`); **Department**; **Product**; **Category** (hidden by default); **Issued qty** (`qty_out`, summed); **Usage value** (summed). Source = done Scan Issue move lines (`stock_picking.wms_is_scan_issue`, excluding undone/reversed pickings). Value uses the frozen `wms_unit_cost_at_done` snapshot, falling back to live company `standard_price` only for legacy rows. One row per department/product/company/month.
**Views & filters:** list / pivot / graph (pivot rows = department, measures usage-value + issued-qty; bar graph usage-value by department). Filters/group-bys: **Department** (default), Product, Category, Month.
**How to use:**
1. Open Intelligence → Department Usage (grouped by department).
2. Switch to pivot to drill department → product, or to chart monthly spend.
3. Use it for cost-centre consumption reporting.
**Role notes:** Read-only for both roles.

---

### Animal Usage
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Animal Usage (`menu_wms_animal_usage`, sequence 41). Model `wms.animal.usage` (SQL view). Action defaults to group by Animal.
**Answers:** "What was consumed for a specific named animal (cow), and what did it cost?"
**Key columns/metrics:** **Month** (`period`); **Animal / cow** (`animal_id`); **Product**; **Category** (hidden by default); **Issued qty** (summed); **Usage value** (summed). Same Scan-Issue source and costing as Department Usage, but counts only issues that named an animal (`wms_animal_id` set), so department-wide issues don't drown the per-animal signal.
**Views & filters:** list / pivot / graph (pivot rows = animal, measures usage-value + issued-qty; bar graph usage-value by animal). Filters/group-bys: **Animal** (default), Product, Month.
**How to use:**
1. Open Intelligence → Animal Usage (grouped by animal).
2. Select an animal to see treatments/feed issued and their value over time.
3. Use it for per-animal cost/treatment tracking.
**Role notes:** Read-only for both roles.

---

### Medicine Consumption
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Medicine Consumption (`menu_wms_medicine_consumption`, sequence 42). Model `wms.medicine.consumption` (SQL view). Action defaults to group by Medicine.
**Answers:** "How much veterinary medicine was consumed over time, and for which department / animal?"
**Key columns/metrics:** **Month** (`period`); **Medicine** (`product_id`); **Department**; **Animal / cow**; **Issued qty** (summed); **Unit cost** (hidden by default); **Consumption value** (summed). Restricted to products whose `product.template.wms_product_kind = 'medicine'` (the trust has no separate "vaccine" kind — vaccines are the medicine kind). Same Scan-Issue source and snapshot costing as the other usage views. One row per product/department/animal/company/month.
**Views & filters:** list / pivot / graph (pivot rows = medicine, cols = month, measures consumption-value + issued-qty; **line** graph of consumption-value over month). Filters/group-bys: **Medicine** (default), Department, Animal, Month.
**How to use:**
1. Open Intelligence → Medicine Consumption (grouped by medicine).
2. Use the line graph to watch a medicine's usage trend, or pivot product × month.
3. Filter by Department/Animal to attribute medicine spend.
**Role notes:** Read-only for both roles.

---

### Lot Traceability
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Lot Traceability (`menu_wms_lot_traceability`, sequence 55). Model `wms.lot.traceability` (SQL view) — one row per lot, the full chain.
**Answers:** "Where did this batch come from, where is it now, who consumed it, and how did it end?" — in a single record instead of hopping across forms.
**Key columns/metrics:** **Lot/batch**, **Product**, **Supplier** (`partner_id`), **Supplier batch**, **Supplier invoice** (hidden), **Received on** (earlier of lot create date and first inbound move), **Expiration date** (hidden), **On hand** (live issuable units), **Current location** (the internal slot holding the most of this lot), **First issue date** (earliest Scan Issue), **Animal / cow** (the animal the first issue was for; hidden), **Returned** (any movement on a transfer flagged returned; hidden), **Repair count** (movements into a repair-station location), **Lot state** (badge: Destroyed red, Recalled amber, Quarantine blue). Each chain endpoint is a CTE keyed on lot id, LEFT JOINed to every lot so even a fresh batch appears.
**Views & filters:** list only. Filters: On hand, Issued, Returned, Repaired, and by lot state (Available / Quarantine / Recalled / Destroyed). Group-bys: Supplier, Lot state, Product.
**How to use:**
1. Open Intelligence → Lot Traceability.
2. Search a lot (or filter by supplier/state); read the origin → current → consumption → end columns left to right.
3. Use it for audit/recall investigations of a single batch.
**Role notes:** Read-only for both roles.

---

### Occupancy Over Time
**Role:** Both (read-only; Manager can also edit/clear snapshots).
**Menu path / URL:** Intelligence → Occupancy Over Time (`menu_wms_occupancy_snapshot`, sequence 70). Model `wms.occupancy.snapshot` — a STORED table (not a live view), one row per storage location per day, captured by a daily cron (`_cron_capture`, idempotent per day). Users have read-only access; managers have full CRUD.
**Answers:** "How full was each rack slot / floor zone over time — what is the occupancy trend?" (The live Wave 1 occupancy report only shows "right now"; this is its historical companion.)
**Key columns/metrics:** **Date** (`snapshot_date`); **Location**; **Location kind** (Rack slot / Floor zone); **Capacity** (soft `wms_capacity_units` at capture); **On hand** (summed); **Occupancy %** (`on_hand / capacity × 100`; red ≥90, amber ≥70; 0 when capacity unset); **Distinct products**. Maths mirror the live occupancy report so the trend agrees with it.
**Views & filters:** graph (default — **line** of occupancy % over day) / pivot (location × day) / list. Filters: Rack slots, Floor zones. Group-bys: Date, Location, Kind.
**How to use:**
1. Open Intelligence → Occupancy Over Time (opens on the line graph).
2. Pick a location (or filter slots/floors) and read the occupancy trend over days.
3. Note that data accrues only after the daily cron has run for a few days.
**Role notes:** Read-only for Store Keepers; Managers can edit/clear snapshots. The daily snapshot is captured automatically by the cron.

---

### FEFO Compliance
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → FEFO Compliance (`menu_wms_fefo_compliance`, sequence 75). Model `wms.fefo.compliance` (SQL view).
**Answers:** "When perishable stock is issued, is the earliest-expiry batch actually the one drawn (first-expiry-first-out)?"
**Key columns/metrics:** **Issue date**; **Transfer** (`picking_id`); **Product**; **Lot issued** (`lot_id`); **Quantity** (summed); **Drawn expiry** (the issued lot's expiry); **Earliest expiry** (earliest expiry among the product's lots with live internal stock — the FEFO target); **Compliant** (boolean toggle; red when not compliant — true when the drawn lot's expiry is the earliest available). Scope: done Scan Issue move lines of lot-tracked, dated products that left internal storage. Compliance is a current-state proxy (Odoo keeps no per-instant shelf snapshot). A **Month** column drives the rate graph (average of the boolean per month).
**Views & filters:** graph (default — bar of compliance rate by month) / pivot (month × product) / list. Filters: Compliant, Violations. Group-bys: Month, Product, Compliant.
**How to use:**
1. Open Intelligence → FEFO Compliance (opens on the monthly rate graph).
2. Filter Violations to find issues that skipped a shorter-dated batch.
3. Coach pickers / tighten putaway so FEFO is honoured.
**Role notes:** Read-only for both roles.

---

### Cycle Count Priority
**Role:** Both (read-only).
**Menu path / URL:** Intelligence → Cycle Count Priority (`menu_wms_cycle_count_priority`, sequence 80). Model `wms.cycle.count.priority` (SQL view). Action defaults to filter High priority.
**Answers:** "With limited counting hours, which storage slot should I count first?" — risk-ranked, not just age-ranked like the Wave 1 Cycle Count Due list.
**Key columns/metrics:** **Priority band** (badge: High red, Medium amber, Low blue); **Priority score**; **Slot** (`location_id`); **Rack** (`rack_id`); **Days since count** (`days_since_count`, since `wms_last_counted`; never counted → 999 sentinel); **Mismatch count** (past audit lines at the slot with non-zero variance); **Velocity class** (fastest AI velocity among products stored there); **On hand**; **Distinct products**; plus the score components **Age points / Mismatch points / Velocity points** (hidden by default). Score = age points (0–40 stepped by ≥180/90/60/30 days) + mismatch points (10 each, capped 30) + velocity points (fast 30 / normal 20 / slow 10 / dead 0). Band: ≥50 High, ≥20 Medium, else Low.
**Views & filters:** list / pivot / graph (pivot rows = band, measure score; bar graph score by band). Filters: High priority (default), Medium priority, Has past variance. Group-bys: Priority band, Velocity, Rack.
**How to use:**
1. Open Intelligence → Cycle Count Priority (lands on High priority).
2. Work the list top-down (highest score first); the points columns explain why a slot ranks high.
3. Count those slots next; recording the count updates `wms_last_counted` and drops the slot's age score.
**Role notes:** Read-only for both roles. (The actual count is performed in the Wave 1 cycle-count / audit flow.)

---

### Cold Chain (temperature readings — data entry)
**Role:** Both can log a reading (Store Keeper: read + create; Manager: full control). The auto QC-hold it can trigger runs with manager rights.
**Menu path / URL:** Intelligence → Cold Chain (`menu_wms_cold_chain_reading`, sequence 120). Model `wms.cold.chain.reading` (a real stored model with create rights, not a view). ACL: `group_wms_user` = read + create; `group_wms_manager` = read/write/create/unlink.
**Answers:** "Is this temperature-sensitive lot (e.g. a vaccine) being kept inside its allowed temperature band — and if not, pull it from issuing automatically."
**Key columns/metrics:** **Reading time** (`reading_datetime`, defaults to now); **Lot / batch** (required); **Product** (derived from the lot, read-only); **Temperature (C)** (required); **In range** (badge: green in / red out — true when `temp_min ≤ temperature ≤ temp_max` from the product's band); **QC hold raised** (`quarantine_id`, link to the auto-created hold, blank if in range); **Recorded by** (defaults to current user); **Note** (free text — fridge id, excursion duration, corrective action). Cold-chain band lives on the product (`wms_cold_chain`, `wms_temp_min`, `wms_temp_max`; vaccine-kind products default to cold chain, 2–8 °C).
**Hold logic:** On create, for any out-of-range reading on a cold-chain product whose lot is still `available`, the system AUTO-creates a `wms.lot.quarantine` over that lot (which freezes the lot to `quarantine` state and cancels its open reservations), and stamps the hold back on the reading's **QC hold raised** field. Because creating a quarantine is manager-gated, the hold is created as the WMS admin when a non-manager keeper records the reading. Already held/recalled/destroyed lots are skipped.
**Views & filters:** list / form. Filters: Out of range, In range, **Raised a QC hold** (`quarantine_id` set). Group-bys: Product, Recorded by.
**How to use (data entry):**
1. Open Intelligence → Cold Chain, then click **New**.
2. Pick the **Lot / batch** (Product auto-fills); enter the measured **Temperature (C)**; adjust **Reading time** if logging after the fact; add a **Note** (fridge id, excursion detail).
3. Save. **In range** is computed immediately.
4. If the reading is out of range on a cold-chain product, a QC hold is raised automatically — the **QC hold raised** field links to it and the lot is frozen and unreserved. Use the "Raised a QC hold" filter to review excursions; a Manager then works that quarantine (release/reject/destroy) in the QC-hold flow.
**Role notes:** Store Keepers can record readings (read + create) but cannot edit/delete past readings; Managers have full control. The protective auto-hold always runs, even when a non-manager logs the reading (it elevates to the admin user to create the quarantine).

---

### Lots (bulk) + bulk server actions (recall / quarantine / destroy)
**Role:** The Lots (bulk) list is visible to Both; the three bulk actions are **Manager-only** (enforced in code).
**Menu path / URL:** Intelligence → Lots (bulk) (`menu_wms_lot_bulk`, sequence 80). A multi-select list over `stock.lot`. The actions are three `ir.actions.server` records bound to `stock.lot` (binding_view_types = list) that appear in the list **Actions** menu when rows are ticked. Each calls a bulk method in `wms_bulk_ops.py`; Odoo 19 server actions have no `groups_id`, so each method gates on `group_wms_manager` in code (`_wms_bulk_check_manager`, raising "Only a Manager can run bulk lot operations.") — and the underlying recall/quarantine actions are manager-gated too.
**Answers:** "Act on many lots at once — recall, quarantine, or destroy a whole selection under one ticket."
**Key columns/metrics (list):** **Name**, **Product**, **Lot state** (badge: Available green, Quarantine amber, Recalled/Destroyed red), **Expiration date** (shown), **Expired?** (`wms_is_expired`, hidden), **Supplier** (hidden), **Company** (hidden, multi-company only).
**The three server actions:**
- **Recall selected lots** → `action_wms_bulk_recall`: creates ONE `wms.lot.recall` (mode manual, reason "Bulk recall of N selected lot(s).") spanning the selection and calls `action_recall()`.
- **Quarantine selected lots** → `action_wms_bulk_quarantine`: creates ONE `wms.lot.quarantine` over the selection (the record itself applies the hold on create).
- **Destroy selected lots** → `action_wms_bulk_destroy`: creates a quarantine over the selection then calls `action_destroy()` to flip them all to the `destroyed` state.
Each shows a success notification (e.g. "N lot(s) recalled under <ref>."). The selection is read from the list's `active_ids`; an empty selection raises "Select at least one lot to act on."
**Views & filters:** list, form. Search filters: Available, Quarantine, Recalled, Destroyed. Group-bys: Product, Lot state.
**How to use (running a bulk action):**
1. Open Intelligence → Lots (bulk).
2. Filter/search to the lots you want (e.g. all of one supplier's batches, or one product), then **tick the checkboxes** of the rows to act on.
3. Open the list **Actions** menu (top toolbar) and choose **Recall selected lots**, **Quarantine selected lots**, or **Destroy selected lots**.
4. The system creates one recall/quarantine over the whole selection and shows a confirmation notification; the lots move to the corresponding lifecycle state.
**Role notes:** Only a Manager can run any of the three bulk actions — a Store Keeper attempting one gets "Only a Manager can run bulk lot operations." The list itself is browsable by both roles.

---

The two features below come from the separate **`wms_training`** addon (version 19.0.1.14.0). They are NOT under the Intelligence menu — they live under their own top-level **Help & Training** menu (`menu_wms_training_root`, sequence 6, `groups="base.group_user"`), so every internal user (not just WMS roles) sees them. Both read the same `wms.help.article` model, whose ACL gives every internal user read-only access and WMS Managers (`group_wms_manager`) full edit/create/delete.

### Getting Started
**Role:** Both (in fact every internal user — `base.group_user`); reference content is read-only, Managers can edit articles.
**Menu path / URL:** Help & Training → Getting Started (`menu_wms_getting_started`, sequence 1 — appears first). Action `action_wms_getting_started` opens the `wms.help.article` list filtered to `domain=[('is_onboarding','=',True)]`, i.e. only the curated onboarding articles.
**Answers:** "I'm new — where do I start, and which short guides walk me through the basics in order?"
**Key columns/metrics:** Same list as Help Center (Category, Title, Audience, "Getting Started" flag) but restricted to onboarding articles (`is_onboarding = True`). The seeded onboarding set includes a **Training Library — Start Here** index plus four guided tours: a **First-Login Tour** (everyone), and role-specific **Store Keeper**, **Admin / Manager**, and **Read-only Viewer** tours. Each tour article is a click-through that links to the relevant screens (the tour action links are placeholders resolved to live actions by a post-init hook). Opening an article shows its **Content** (`body`, beginner-friendly HTML) and, if present, an inline training **video** player.

A related onboarding control lives in user **Preferences**: **WMS Beginner Mode** (`res.users.wms_beginner_mode`, Boolean, default True), added by `wms_training/models/res_users.py` under a "Warehouse (WMS)" group on the preferences form. When on, the WMS shows extra guidance and beginner hints; each user can toggle their own flag from Preferences without manager rights (it is in the self-readable/writeable field lists). This is distinct from the onboarding articles — one is persistent in-app guidance, the other is curated reading.
**Views & filters:** list / form (the shared help search view is available, but the action is pre-scoped to onboarding articles).
**How to use:**
1. Open Help & Training → Getting Started (first menu item).
2. Open each onboarding guide in order (start with "Training Library — Start Here" or the First-Login Tour), then follow the role-specific tour for your job.
3. Once comfortable, optionally turn off **WMS Beginner Mode** in your user Preferences to hide the extra hints.
**Role notes:** Visible to every internal user. Articles are read-only; only WMS Managers can create/edit them.

### Help Center
**Role:** Both (every internal user — `base.group_user`); read-only knowledge base, Managers can edit/add articles and upload videos.
**Menu path / URL:** Help & Training → Help Center (`menu_wms_help_center`, sequence 2). Action `action_wms_help_center` opens the full `wms.help.article` list, defaulting to **group by Category** (`search_default_group_category`).
**Answers:** "What does this term mean / how do I do this / why is this blocked?" — a searchable, browsable reference for the whole WMS.
**Key columns/metrics:** List columns **Category, Title, Audience**, and a hidden "Getting Started" (onboarding) flag — the list is `create=0 edit=0 delete=0` (read-only). Each article carries: **Title** (`name`); **Category** (one of: What is this? (terminology), Role training, Workflow tutorial, FAQ, Troubleshooting, Safety warning); **Audience** (Everyone / Admin · Manager / Store Keeper / Read-only viewer); **Content** (`body`, plain-language HTML with real warehouse examples); optional **training video** (uploaded clip or YouTube/Vimeo link, rendered in an inline player shown to everyone when present); plus manager-only fields **slug** (deep-link id), **sequence**, and **keywords** (extra search terms). The search box matches across Title, keywords, and body.
**Views & filters:** list / form. Search filters: **Getting Started** (onboarding), the six category filters (What is this? / Role training / Workflow tutorials / FAQ / Troubleshooting / Safety), audience filters **For Store Keepers** / **For Admins**, and **▶ Has video**. Group-bys: **Category** (default), Audience.
**How to use:**
1. Open Help & Training → Help Center (articles arrive grouped by category).
2. Type a term in the search box ("FIFO", "compartment", "why is this blocked?") or click a category/audience filter; use "▶ Has video" to find articles with a clip.
3. Open the article to read the explanation and watch any embedded training video.
**Role notes:** All internal users can read; only WMS Managers can edit existing articles, add new ones, set slug/sequence/keywords, and upload/link training videos. (Articles cannot be created from the UI list — it is create-disabled; managers edit via the form.)

---

# Appendix A — Common errors & what they mean

These are the guardrails you will actually hit. Each is intentional — the system is refusing to let you record something that doesn't make physical sense, not malfunctioning. (All verified live on the running build.)

| What you see | When it happens | What to do |
|---|---|---|
| **"quantity must be greater than zero"** (CheckViolation) | Entering a negative or zero quantity on a Damage, Dispense, or scan | Enter a positive quantity. |
| **Duplicate barcode is rejected** (ValidationError) | Creating a product/carton/packaging barcode that already exists | Barcodes are unique — reuse the existing record or pick a new code. |
| **Duplicate lot is rejected** (ValidationError) | Creating a second lot with the same name on the same product | Lot names must be unique per product. |
| **The dispense/medication log can't be edited or deleted** (UserError) | Trying to change a posted dispense record | The audit trail is immutable by design. Correct it with a compensating entry, not an edit. |
| **A slot-stock guard blocks the move** | Issuing/damaging more than the slot actually holds | Re-count the slot; you can only move what's on hand. |
| **404 / "Access Error" on a manager screen** | A Storekeeper opening a manager-only page (KPI Dashboard, Configuration, Value reports, recall/quarantine) by URL | Expected — ask an Administrator, or have them grant the needed group. |
| **Login page looks unstyled** | The web asset bundles failed to build/serve | This is an environment issue (wrong data-dir / first-run asset build), not a code defect — restart Odoo with the default filestore; see INSTALLATION-GUIDE §15. |

A note for whoever runs the test suite: an **unscoped** `--test-enable` also runs Odoo's own base/framework tests, which contain Windows-only failures unrelated to this product. Always scope with `--test-tags /wms_*`. The WMS suite itself is **619 tests, 0 failed / 0 error**.

---

# Appendix B — The security model in one picture

Permissions are enforced at three independent layers, so nothing relies on merely hiding a button:

1. **Menu layer** — a Storekeeper's WMS bar omits Configuration and Back-Up entirely, and manager-only items (e.g. the executive KPI Dashboard) don't appear.
2. **Route layer** — manager-only web pages (`/wms/intelligence`, `/wms/dashboard`) return **404** to a Storekeeper while serving the Administrator.
3. **Database (ACL) layer** — even by direct API/RPC, a Storekeeper is denied the 19 manager-only actions with a real `AccessError`; operator sub-groups (Scan Receive/Issue, File Damage, Submit Audit, Approve Issue, Repair Tech) gate the *actions within* the screens they can see.

**Quick role summary.** A Storekeeper can scan goods in/out and return, find stock, view products/lots, log damage, dispense medicine, submit audits, log cold-chain readings, and *read* nearly all analytics and operational reports. A Storekeeper cannot reach configuration and warehouse setup, product creation/onboarding, the backup/disaster-recovery suite, issue approvals, recall/quarantine/migration *initiation*, repair sign-off, the executive KPI dashboard, or the money/activity reports (Stock Value, Consumption Value, Product Lifecycle, Store-Keeper Activity). Those are the Administrator's.

---

*This manual documents build v20.0.0. If a screen differs from what you see, the build may have moved on — regenerate this manual from the then-current source, and treat the code as the source of truth. For installation and first-launch, see `docs/INSTALLATION-GUIDE.md`; for in-app help, see WMS → Help & Training.*
