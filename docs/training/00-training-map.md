# WMS Training Feature Map

*A beginner's guide to the Dakshin Vrindavan Warehouse Management System (Odoo 19)*

## How to read this document

This is the master "feature map" for the trust's warehouse software. The trust **buys and uses** inventory (feed, medicine, ghee for pooja, tools, construction material, cloth) for cow-care work — it **never sells** anything. Everything below reflects that: there are no customers, no invoices, no sales prices that matter, and no money changes hands.

Every feature is described in the same shape so you always know where to look:

- **Feature Name**
- **Purpose** — what it is for, in plain words.
- **Who Uses It** — Admin/Manager, Store Keeper, or Read-only viewer, and what each can do.
- **Prerequisites** — what must already exist before the feature works.
- **Common Mistakes** — beginner errors and how to avoid them.
- **Best Practices** — habits that keep the warehouse data clean.
- **Related Workflows** — other features that connect to this one.

### The three roles (read this first)

The whole system has only two real Odoo groups, plus a set of "capability" tick-boxes:

1. **Admin / Manager** — group `WMS / Manager` (`group_wms_manager`). Full control: create/edit/delete products, racks, zones, slots; run and approve audits; authorise repairs; manage users; download backups. The built-in `admin` login is put in this group automatically on first install. A Manager automatically inherits **all five** capabilities below.
2. **Store Keeper** — group `WMS / Store Keeper` (`group_wms_user`). The everyday desk operator. On its own it is a read-only baseline (can log in, see the WMS app, read inventory and reports). What a keeper can actually *do* is controlled by five capability sub-groups the Admin ticks on the keeper's roster card:
   - **Can Scan Receipt + Scan Return** (`can_scan_receive`)
   - **Can Scan Issue** (`can_scan_issue`)
   - **Can file Damage events** (`can_file_damage`)
   - **Can submit Inventory audits** (`can_submit_audit`)
   - **Can manage Carton aliases + Labels** (`can_manage_catalog`)
   A menu (e.g. *Scan Receipt*, *Damages*, *Inventory audits*) only appears for a keeper who has the matching capability. A keeper with `group_wms_user` and no sub-groups can browse but cannot move any stock.
3. **Read-only viewer** — a user in `group_wms_user` with **no** capability sub-groups ticked. They can open the WMS app and read reports for weekly review, but the action menus (Scan, Damage, Audit) never appear and they cannot change data.

> The standard Odoo **Inventory**, **Apps**, and **Dashboards** apps are deliberately hidden from Store Keepers. The WMS scan wizards are the *only* path a keeper has to move stock — this is by design so nothing bypasses the audit trail.

### The two apps in the menu

- **WMS** (main app): Operations, Forecast / Reorder, Reports, Configuration.
- **Help & Training** (separate app, visible to every internal user): Getting Started + Help Center.

---

## 1. Warehouse Structure (Racks, Compartments, Slots, Zones, Floor areas)

### 1a. The location hierarchy

**Purpose.** Model the physical warehouse as data so the system always knows *exactly* where each item sits. The structure is a strict tree built on top of Odoo's `stock.location`:

```
Warehouse view
└── Zone            (building / floor / area, e.g. "Pharmacy", "1st Floor")
    └── Rack        (a physical shelving unit, usage = view)
        └── Compartment   (a 2D rectangle on the rack grid, usage = view)
            └── Slot       (the unit that actually holds stock, usage = internal)
```

A **Floor / Open area** location (`floor`) is a fifth type that sits outside the rack tree — a pallet area, a yard bay, a single slab, a staging dock. It holds stock directly (`usage = internal`) and behaves exactly like a slot for receiving, FIFO, and reports.

Shelves and columns are **grid coordinates**, not separate records. Each rack carries a shelf count and column count; each compartment records the rectangle it covers (shelf top→bottom, column left→right). A compartment can be one cell, several shelves tall (bottles), several columns wide (a drawer), a full corner block, or even an L/T/U polyomino shape from the visual builder. Display names are self-describing, e.g. `R12 / SH01-03 / C01` (a 3-shelf-tall compartment in rack R12).

**Who Uses It.**
- **Admin** — creates, edits, and (rarely) archives the whole structure. Lives under **Configuration → Zones / Racks / Compartments**, and **Operations → Slots / Floor Zones**.
- **Store Keeper** — reads it; puts stock into slots by scanning. Cannot create or edit locations.
- **Read-only** — can browse Slots and the Warehouse Map.

**Prerequisites.**
- An Odoo **warehouse** must exist (Odoo creates one by default on install).
- Decide on a naming convention for rack codes (zero-padded: `R01`, `R02`, …; or themed: `PHARM01`).

**Common Mistakes.**
- Trying to put stock into a **rack** or **compartment** directly — only **slots** and **floor areas** hold stock (they have `usage = internal`). Racks and compartments are containers/views.
- Deleting a rack/slot that still has stock or history. The system **refuses** this and tells you to empty it first, then **archive** (deactivate) instead of delete — this protects the audit trail.
- Building one giant compartment with one slot for everything. You lose the benefit of knowing precisely where things are.
- Forgetting that a brand-new slot has no barcode unless it was created by a generator (generators auto-create barcodes; see below).

**Best Practices.**
- Create the structure top-down: Zone first, then Racks inside it, then let the generator make compartments and slots.
- Keep rack codes short and printed on a sticker on the physical rack.
- Use **Floor areas** for genuinely open storage (sand pile, pallet of bagged feed) instead of forcing it into a rack grid.
- Archive, never delete, anything that has ever held stock.

**Related Workflows.** Rack/Zone/Floor Generators (1b–1d); Putaway (§3); Warehouse Map and Slot Occupancy reports (§10); Cycle Count (§7).

---

### 1b. Create Rack (Rack Generator + Visual Rack Builder)

**Purpose.** Build a whole rack — with all its compartments and slots, each with an auto-generated barcode — in one click, instead of creating dozens of locations by hand. Menu: **Configuration → Create Rack**.

Two modes:
1. **Quick grid** — type shelves, columns, and slots-per-compartment; the wizard makes one compartment per (shelf × column) cell.
2. **Visual builder** — an interactive grid where you click cells to merge them into tall/wide/odd-shaped compartments; it writes a custom layout that overrides the quick grid.

Slots get barcodes shaped like `R01-SH01-C01-SL01` (rack-shelf-column-slot, zero-padded), so the printed slot sticker is the same string the scanner reads.

**Who Uses It.** **Admin only** (whole Configuration menu is Manager-gated). Store Keepers and Read-only users never see it.

**Prerequisites.**
- A **parent location** to hang the rack under — usually a Zone or the warehouse stock location.
- A **unique rack code** within that parent (the wizard rejects duplicates).

**Common Mistakes.**
- Re-using a rack code that already exists under the same parent → blocked with an error.
- Setting shelves or columns to 0 → must be at least 1 each.
- Hand-editing the custom-layout JSON and breaking it → the wizard shows a parse error; just re-generate from the Visual builder.
- Expecting overlapping compartments — the builder forbids two compartments covering the same cell.

**Best Practices.**
- Use Quick grid for ordinary uniform racks; reserve the Visual builder for racks with genuinely irregular bays.
- Generate the rack, then immediately print slot labels from the Slots list (Action → Print thermal label).
- Set a soft **capacity per slot** if you want the Occupancy report to show a meaningful percentage.

**Related Workflows.** Location hierarchy (1a); Zone Generator (1c); Label printing (§2c); Slot Occupancy (§10).

---

### 1c. Generate Zone (Zone Generator)

**Purpose.** Create a Zone (a building / floor / area) and, in the same step, generate many racks and/or floor areas inside it. Menu: **Configuration → Generate Zone**. Example: "1st Floor" with 32 identical racks, or "Outside Yard" with 10 floor bays.

**Who Uses It.** **Admin only.**

**Prerequisites.** A parent **view** location (usually the warehouse stock location). For racks, decide the shelves/columns/slots that every generated rack will share.

**Common Mistakes.**
- Expecting per-rack custom layouts here — the Zone Generator makes **uniform** racks only (same shelves × columns). For one-off shapes, use the Visual Rack Builder afterward.
- Re-running with the same rack numbers — existing rack codes are skipped, so you may get fewer racks than the count you typed.
- Setting the rack start-number wrong and clashing with racks elsewhere (use a start number above your highest existing rack).

**Best Practices.**
- Plan rack numbering across the whole building before generating (e.g. floor 1 = R01–R32, floor 2 = R33–R64).
- Generate floor areas with a clear prefix (`F` → `F-01`, `F-02`) so their barcodes don't collide.

**Related Workflows.** Create Rack (1b); Generate Floor Zones (1d); Warehouse Map (§10).

---

### 1d. Generate Floor Zones (Floor Zone Generator)

**Purpose.** Create one or many **open-area** stocking locations (pallet areas, yard bays, staging docks, a damaged-goods bench) that hold stock directly without a rack/shelf/slot hierarchy. Menu: **Configuration → Generate Floor Zones** (and they appear under **Operations → Floor Zones**).

**Who Uses It.** **Admin only.**

**Prerequisites.** A parent **view** location.

**Common Mistakes.**
- Using a floor area where a rack would be better (you lose shelf/column precision) — only use floor areas for genuinely unstructured storage.
- Re-running and expecting duplicates — existing zone names under the same parent are skipped (the run is idempotent).

**Best Practices.**
- Give each floor area a soft **capacity** if you want occupancy tracking.
- Print and stick the auto-generated barcode on the physical spot so receiving can scan it.

**Related Workflows.** Receiving auto-putaway (§3); Damage (§5, the Damage bench can be a floor area conceptually); Occupancy report (§10).

---

## 2. Receiving (Scan Receipt) and supporting catalog/labels

### 2a. Scan Receipt

**Purpose.** Record stock coming **into** the warehouse from a vendor or supplier by scanning, then validate to create a real inbound transfer. Menu: **Operations → Scan Receipt**. Works with any USB/wireless barcode scanner — keep the cursor in the scan box and each beep is processed automatically.

You scan a product (or a carton alias, or a lot barcode), the line is added with a quantity; optionally scan a **slot barcode** to place it, or leave it for auto-putaway. Then you fill the audit trail and click **Validate & Print**.

**Who Uses It.** **Store Keeper** with the **Scan Receipt + Scan Return** capability, and **Admin** (who has it by default). Read-only users cannot.

**Prerequisites.**
- Products must already exist in the catalog with barcodes (created via Onboard Products or the product form).
- At least one **slot or floor area** must exist (auto-putaway needs somewhere to put stock).
- The on-duty keeper must be on the **Store Keeper roster** (Configuration → Storekeeper).
- The warehouse must have incoming receipts enabled (Odoo default).

**Common Mistakes.**
- Forgetting to tick **Quality check passed** → Validate is blocked. This box confirms you physically counted and inspected the delivery.
- Not selecting the **Store Keeper on duty** → required; Validate fails without it.
- Double-clicking Validate, or refreshing and re-submitting — harmless: the wizard remembers the receipt it made and just re-opens it (it will not receive the delivery twice).
- Scanning a slot barcode *before* scanning the product — the slot attaches to the most recent line that has no slot yet, so scan the product first.

**Best Practices.**
- Scan everything first, eyeball the line list, then do the QC tick and audit fields last.
- Fill **Delivered by** (driver/vendor name) even though it's optional — it makes the Store Keeper Activity report far more useful.
- Let auto-putaway place stock unless you have a specific slot in mind; it clusters with existing stock of the same product.

**Related Workflows.** Putaway (§3); Onboard Products (§2b); Carton aliases & Labels (§2c); Store Keeper roster (§12); Movement History / Storekeeper Activity (§10).

---

### 2b. Onboard Products (bulk catalog + stock + labels)

**Purpose.** A single screen to create new products, place their starting stock, and print labels — instead of three separate trips (create product → scan receipt → print label). Menu: **Configuration → Onboard Products**. Each row = a product name, a WMS Kind, an initial quantity, and a slot; paste-from-Excel works for big initial loads.

On submit it creates the product (auto-generating its SKU, Code128 barcode, and an EAN-13 alias), drops the initial quantity into the chosen slot, and opens a combined thermal-label PDF.

**Who Uses It.** **Admin only** (Configuration menu). This is a setup wizard, not daily work.

**Prerequisites.**
- Slots/floor areas must exist for rows with a starting quantity.
- Know each product's **WMS Kind** (it drives the SKU prefix, returnability default, and FEFO behaviour — see §1 of product kinds in §4/§5).

**Common Mistakes.**
- Leaving the **WMS Kind** blank → blocked; the system needs it to build the right SKU.
- A row with a starting quantity but no slot → blocked. (Set quantity to 0 for a catalog-only row with no stock yet.)
- Onboarding **Medicine** or **Feed** without an **expiry date** → blocked, because these drive FEFO and spoilage tracking.
- Double-submitting the no-print version → the wizard closes itself after success specifically to stop a double-click from creating duplicate SKUs.

**Best Practices.**
- Do the whole initial inventory load through this wizard rather than one product at a time.
- Fill expiry/batch for perishables and volume for fluids right here, so the product form is complete from day one.
- Use catalog-only rows (qty 0) to pre-register products you'll receive later.

**Related Workflows.** Scan Receipt (§2a); product SKU/barcode rules (§4); Expiry Alert (§10); Label config (§2c).

---

### 2c. Carton Barcodes (aliases) and Thermal Label Config

**Purpose.**
- **Carton Barcodes** (Configuration → Carton Barcodes): map a vendor's *carton* sticker (e.g. `CTN-COKE-24`) to one product with a units-per-scan multiplier (24), so one scan of a case counts as 24 units. Each product also auto-gets a Code128 (= its SKU) and an EAN-13 alias.
- **Label Config** (Configuration → Label settings): the layout for the trust's thermal sticker labels — paper size (default 100 × 25 mm), logo position, title/SKU/barcode placement, all in millimetres.

**Who Uses It.** **Admin** always; a **Store Keeper** only if granted the **Manage Catalog** capability (off by default — it's usually Admin work). Read-only users cannot.

**Prerequisites.** Products must exist to attach aliases to. For labels, a thermal printer (the trust uses a TSC TE244, 203 DPI) and the right roll.

**Common Mistakes.**
- Re-using a carton barcode that's already mapped → each carton barcode must be unique.
- Setting label width wider than the actual sticker → the right edge clips or mis-feeds (default 100 mm matches the trust's roll).
- Setting `units_per_scan` to 1 on a real carton → the case scan would only add one unit.

**Best Practices.**
- Add a carton alias the first time a new case size arrives, so future receipts scan the whole case in one beep.
- Leave the label defaults alone unless you change rolls; use size 0 on an element to hide it.
- After bulk-generating barcodes, re-print labels via product list Action → Print → WMS thermal label.

**Related Workflows.** Scan Receipt/Issue (resolve scans through these aliases); Onboard Products (auto-creates barcodes); product barcode back-fill action.

---

## 3. Putaway (where received stock goes)

**Purpose.** Decide which slot/floor area received stock lands in. There is no separate menu — putaway happens **inside Scan Receipt**: either the keeper scans a destination slot, or the system **auto-assigns** one at Validate.

Auto-assign priority order:
1. A slot/floor that **already holds this product** (cluster it together).
2. Any **empty rack slot**.
3. Any **empty floor area**.
4. Any rack slot (will mix products — last resort).
5. Any floor area.
If nothing exists at all, it errors and tells you to create racks/floor zones first.

**Who Uses It.** **Store Keeper** (during receiving) and **Admin**. Read-only users cannot.

**Prerequisites.** At least one slot or floor area must exist in the warehouse.

**Common Mistakes.**
- Receiving before any slots exist → auto-putaway fails with a clear message; build racks/floor zones first.
- Manually scanning the wrong slot and only noticing later — fix it with an internal move or the next audit.
- Assuming auto-assign always uses an empty slot — it prefers to **cluster** with existing stock of the same product first.

**Best Practices.**
- For perishables, let clustering keep batches of the same product together so FEFO and counting are simpler.
- Keep a few empty slots free so auto-assign never has to mix products into an occupied slot.
- Scan the destination slot deliberately when an item has a "home" location.

**Related Workflows.** Scan Receipt (§2a); FIFO/FEFO issuing (§4); Slot Occupancy (§10).

---

## 4. Issuing / FIFO (Scan Issue)

**Purpose.** Record stock going **out** for internal use (cow shed, pooja room, a repair job) by scanning, with the system automatically planning which slots to pull from — **oldest first**. Menu: **Operations → Scan Issue (FIFO)**.

The destination defaults to the trust's **"Trust internal use"** location (because the trust uses, not sells). You scan a product and a quantity; the wizard shows a **plan** (which slot, how much, arrival date, expiry) *before* you commit, so a miscount can be fixed first. Then fill the required audit fields and Validate.

**Picking rule:**
- **FEFO (First-Expiry-First-Out)** for perishables — kinds **medicine, feed, fluid, pooja**, or any product with an expiry date. It pulls the soonest-to-expire batch first and even crosses to sibling batches of the same product so a fresh long-dated batch never ships ahead of an older one.
- **FIFO (First-In-First-Out)** for everything else — oldest arrival date first.

**Guard rails at Validate:**
- **Stock-out / shortfall** is shown plainly ("⚠ STOCK OUT" or "only X on hand"); you can't validate while short.
- **Photo required** for items measured by weight/volume (litres, kg) — snap a photo before finishing.
- **Per-issue cap** (`Max per issue`) and **24-hour rolling daily cap** (`Daily cap`) per product, if the Admin set them (0 = no cap) — e.g. one tool at a time, 50 kg feed per day across everyone.
- **Concurrency-safe**: if another keeper grabbed the same stock between planning and validating, nothing is issued and you're asked to re-scan.
- Double-click/refresh-safe: it never issues the same stock twice.

**Who Uses It.** **Store Keeper** with the **Scan Issue** capability, and **Admin**. Read-only users cannot.

**Prerequisites.**
- Stock on hand in slots/floor areas.
- The on-duty keeper on the roster.
- (Optional) per-product caps configured on the product's WMS Classification tab.

**Common Mistakes.**
- Trying to validate while **short** → blocked; reduce the quantity or wait for a Scan Return.
- Leaving **Taken by**, **Ordered by**, or the **Reason / usage note** blank → all are required; no issue goes through without accountability.
- Forgetting the **photo** for a measured (kg/L) item → blocked.
- Thinking the wizard "misread" you when FEFO pulls from a *different* batch — that's intentional; the feedback line tells you which batch it crossed to.
- Hitting a **daily cap** and retrying immediately — wait a few hours or ask a Manager to raise the cap.

**Best Practices.**
- Always read the plan before validating — it's your chance to catch a miscount.
- Write a real reason ("morning feed for shed B"), not "stuff" — it's what monthly reconciliation reads.
- For tools, set a per-issue cap of 1 so only one leaves at a time.
- If stock is out, raise it with the Admin (buy) or wait for a return rather than forcing it.

**Related Workflows.** Global FIFO engine (§4 below); Scan Return (§5); Damage (§6); Oldest Stock & Expiry reports (§10); product caps (§4 prerequisites); Store Keeper Activity (§10).

### Global FIFO engine (background behaviour)

**Purpose.** Even outside the Scan Issue wizard (e.g. any standard Odoo stock move), the system re-orders candidate stock so the **oldest arrival is consumed first across every slot** under the warehouse. This is automatic and has no UI — it just makes FIFO the default everywhere. A database index keeps it fast on large stock tables.

**Who Uses It.** Everyone benefits; nobody operates it directly.

**Common Mistakes.** Assuming you must pick the oldest slot manually — you don't; the system already orders oldest-first.

**Best Practices.** Trust the plan; if a specific batch must go first for a non-perishable, do it via a deliberate move and note why.

---

## 5. Returns (Scan Return)

**Purpose.** Bring **returnable** stock back into the warehouse — a tool or spare that went out to a job and came back. Menu: **Operations → Scan Return**. It is the *same* Scan Receipt wizard with "Return entry" pre-ticked.

The key difference: at Validate it **refuses** any product flagged **not returnable**. Returnability is set per product (defaulted from its WMS Kind): tools, spares, raw materials, textiles, safety gear default to **returnable**; medicine, feed, fluids, consumables, sanitation, construction, plumbing, electrical, stationery, pooja default to **not returnable** (once issued they're spent, injected, burned, or installed and can't re-enter the shelf).

**Who Uses It.** **Store Keeper** with the **Scan Receipt + Scan Return** capability, and **Admin**. Read-only users cannot.

**Prerequisites.**
- The product must be marked **Returnable** (Admin can flip this per product on the product form).
- The on-duty keeper on the roster; QC tick as with any receipt.

**Common Mistakes.**
- Trying to return a consumable/fluid → blocked with a message telling you to scrap it via Damage instead, or ask the Admin to change the product's Returnable flag.
- Using Scan Receipt instead of Scan Return for genuinely returned goods — the returnability gate won't run, and reports won't tag it as a return.
- Forgetting the QC tick (same requirement as a normal receipt).

**Best Practices.**
- Use Scan Return (not Scan Receipt) for anything coming back, so the audit trail records it correctly.
- If a returnable tool came back broken, file a **Damage** instead of returning it to a normal slot.
- Ask the Admin to adjust the Returnable flag for genuine one-off exceptions rather than forcing a workaround.

**Related Workflows.** Scan Receipt (§2a); product Kind & returnability (§4); Damage (§6); Repair (§7).

---

## 6. Damage (recording broken / spoiled / contaminated stock)

**Purpose.** Record that stock is broken, expired, contaminated, or otherwise unusable, and move it out of its slot into the warehouse **Damage** location so it no longer counts as available. Menu: **Operations → Damages**. Confirming a damage event creates a real internal transfer; until confirmed it's just a draft.

Each damage event records the product, quantity, source slot, a **reason** (Broken / Expired / Contaminated / Other), and the audit trail. The form also shows a **smart recommendation** based on the product kind and how much is left elsewhere — e.g. "URGENT — buy now, zero on hand and not repairable", "Open a Repair Order (returnable item)", or "plenty on hand, just note it". When an **urgent buy** is confirmed, every Manager gets a Discuss notification.

**Who Uses It.** **Store Keeper** with the **File Damage events** capability, and **Admin**. Read-only users cannot.

**Prerequisites.**
- A **Damage location** exists per warehouse (created automatically when the module is installed).
- Stock physically present in the source slot.
- The on-duty keeper on the roster; reporter and authoriser names.

**Common Mistakes.**
- Filing more units than the slot actually has **free** (total minus reserved) → blocked; recount, or wait for an in-flight issue to release reserved stock.
- Choosing reason **Other** without a note → blocked; you must explain what happened.
- Confirming without **Reported by / Authorised by / Store Keeper on duty** → blocked.
- Trying to cancel a **confirmed** damage → blocked; you'd have to reverse the stock transfer it created first.

**Best Practices.**
- File damage the moment you find it, while the count is fresh.
- Read the smart recommendation — it tells you whether to repair, buy, or just note.
- For a returnable tool, use Damage → then **Create Repair Order** rather than scrapping outright.
- Use the specific reason (Broken/Expired/Contaminated) so reports stay meaningful.

**Related Workflows.** Repair (§7); Scan Return (§5); Buying recommendations / Forecast (§9); Store Keeper Activity (§10); Expiry Alert (§10).

---

## 7. Repair (fixing a damaged item)

**Purpose.** Take a damaged returnable item through a repair lifecycle and get it back on the shelf — or scrap it if it can't be saved. Menu: **Operations → Repair Orders**. A repair order is usually created from a Damage event via **Create Repair Order**.

Lifecycle: **Draft → In repair → Done** (or **Scrapped**, or **Cancelled** while still draft). Each transition generates auditable internal transfers:
- **Start repair**: Damage location → Repair-Out.
- **Finish repair (Mark Done)**: Repair-Out → the original slot (or an override slot).
- **Scrap**: writes the item off from Repair-Out using Odoo's native scrap.

**Who Uses It.** **Admin / Manager only** — the Admin authorises every repair start, finish, and scrap. (A Store Keeper can *create* a repair order from a damage event but the Repair Orders menu itself is Manager-gated.)

**Prerequisites.**
- **Damage** and **Repair-Out** locations exist per warehouse (auto-created on install).
- A damage event (or at least a product + source slot) to start from.
- Audit trail filled (Reported by / Authorised by / Store Keeper on duty) before leaving Draft.

**Common Mistakes.**
- Moving past Draft without the audit triplet → blocked.
- Trying to **cancel** an in-repair order → blocked; finish (Mark Done) or scrap it first, otherwise the unit is stuck in Repair-Out with no owner.
- Trying to cancel a Done/Scrapped order → blocked (it would orphan the stock moves); open a fresh damage event instead.
- Forgetting to set a return slot → it defaults to the original slot, which is usually what you want.

**Best Practices.**
- Drive repairs from the Damage form's **Create Repair Order** button so the audit fields pre-fill.
- Decide early: repairable → start it; not repairable → scrap from in-repair.
- Record useful **repair notes** for the next time the same tool breaks.

**Related Workflows.** Damage (§6); Tool / Spare fleet report (§10) for deciding how many spares to own; Movement History (§10).

---

## 8. Cycle Count & Inventory Audit

There are two related but distinct tools here.

### 8a. Cycle Count (inventory adjustments) + "Cycle Count Due"

**Purpose.** Periodically verify that the system's numbers match the shelf.
- **Operations → Cycle Count** opens Odoo's standard inventory-adjustments screen (exposed inside WMS so keepers don't have to dive into the Inventory app).
- **Reports → Cycle Count Due** is a read-only dashboard listing every slot/floor area not counted in **over 30 days**, with how many days stale, on-hand qty, and product count. A weekly background job pings Managers when slots are overdue.

**Who Uses It.** Cycle Count adjustments: **Admin** (and keepers via the standard screen, subject to stock permissions). Cycle Count Due dashboard: anyone who can read reports; the weekly reminder targets **Managers**.

**Prerequisites.** Slots/floor areas with stock and arrival/count dates (the system tracks "last counted" automatically).

**Common Mistakes.**
- Ignoring the "Cycle Count Due" list until it's huge — count a few slots regularly instead.
- Confusing a quick adjustment with a full structured audit (use §8b for an end-to-end walk).

**Best Practices.**
- Walk the oldest-overdue slots first (the list is sorted that way).
- Aim to keep every slot under 30 days since its last count.

### 8b. Inventory Audit (structured count-walk)

**Purpose.** A structured, reviewable count: a keeper walks the racks, records what's actually there against the expected numbers, and submits to the Admin, who accepts (applying stock adjustments) or rejects. Menu: **Operations → Inventory audits**.

Lifecycle: **Draft → In progress → Submitted → Reviewed** (or **Rejected**). On **Start**, the audit auto-fills one line per existing internal quant (expected vs counted). The keeper enters counted quantities; variances compute live. On **Submit**, a digest of the top mismatches goes to Managers. On **Accept**, variances become real stock adjustments so the books match the shelf.

**Who Uses It.**
- **Store Keeper** with the **Submit Inventory audits** capability — creates the audit, counts, submits.
- **Admin / Manager** — reviews, accepts (applies adjustments), or rejects.
- Read-only users cannot.

**Prerequisites.** Internal stock to count; the on-duty keeper picked from the roster before submitting.

**Common Mistakes.**
- Trying to submit without picking the **on-duty Store Keeper** → blocked.
- Trying to **delete audit lines** after submission → blocked; the submitted count is immutable. If a line is wrong, the Admin rejects and the keeper re-walks with a fresh audit.
- Submitting a not-yet-started (Draft) audit → you must Start it first (which loads the lines).

**Best Practices.**
- Count physically, then enter numbers — don't just confirm the expected values.
- Use the per-line **note** to explain odd variances ("expired, moved to trash").
- Admin: review variances before accepting, since acceptance rewrites stock to match.

**Related Workflows.** Cycle Count Due (§8a); Movement History (§10); Store Keeper Activity (§10); Damage (variances caused by unrecorded breakage).

---

## 9. Forecast / Reorder & Buying Recommendations

**Purpose.** Predict how much of each product will be needed and suggest what to buy and when. Menu: **Forecast / Reorder → Forecasts** (plus related views under **Reports**: Low stock alerts, Dead stock, Reorder summary).

For each storable product the engine looks at up to 2 years of outflow history, picks a model by data length (a 30-day naive average for sparse data, Simple Exponential Smoothing for short series, Holt-Winters for long seasonal series), and produces: predicted demand, daily/monthly average, a **velocity class** (Fast / Normal / Slow / Dead), a suggested **reorder quantity**, and a **reorder date**. The reorder math is deterministic (lead time × daily average + safety stock, minus on-hand and on-order). Forecasts retrain automatically every day (cron), or you can hit **Retrain now** on a row. **Create PO / Create draft PO** turns a suggestion into a draft purchase order for the product's vendor.

Supporting views:
- **Low stock alerts** — products whose forecast will push stock below the reorder point (reorder qty > 0).
- **Dead stock** — products with no outflow recently (velocity = Dead): clear slots, return, or reclassify.
- **Reorder summary** — totals the suggested quantities **per vendor** so a buyer gets one shopping list.
- Damage "urgent buy" events flag products as critical here on the next refresh.

**Who Uses It.**
- **Admin / Manager** — reads forecasts, retrains, creates draft POs, reviews the vendor shopping list.
- **Store Keeper / Read-only** — can read the lists for awareness; purchasing is an Admin task.

**Prerequisites.**
- Some movement history for predictions to mean anything (zero-history products show "monitor only / Dead").
- A **vendor** on the product to create a PO (the button warns if none is set).
- Optional: a reorder point / safety stock (orderpoint) and supplier lead time for better math.
- Requires the Python libraries `statsmodels`, `pandas`, `numpy` on the server (it degrades to a simple average if missing).

**Common Mistakes.**
- Treating a brand-new product's forecast as real — it needs history first.
- Clicking Create PO with no vendor configured → you get a warning, not a PO.
- Confusing "Dead stock" (no recent demand) with "out of stock" (none on hand) — they're different.
- Expecting the daily cron to have run on a freshly installed system — use **Retrain now** to see numbers immediately.

**Best Practices.**
- Set a vendor and lead time on every product you reorder, so suggestions and POs are accurate.
- Review the **Reorder summary** before a buying trip to consolidate per vendor.
- Investigate **Dead stock** periodically to free up slots.
- Re-check forecasts after big one-off issues (a one-time bulk pull can skew the average).

**Related Workflows.** Scan Issue (history source); Damage urgent-buy (§6); product vendor & lead time; purchase orders.

---

## 10. Reports & Dashboards

All reports live under **WMS → Reports** (unless noted). Read-only viewers and Store Keepers can read most of them; a few are Manager-only. None of them change data.

### 10a. Warehouse Map
**Purpose.** A visual map of racks and their occupancy. Menu: **Reports → Warehouse Map**. **Who:** anyone who can read reports. **Best practice:** use it to spot crowded vs empty racks at a glance.

### 10b. Where is product X? (Product Stock)
**Purpose.** Every location holding a given product, FIFO-ordered, with on-hand/reserved/available and an "is oldest" flag marking the slot the next FIFO pick draws from. Menu: **Reports → Where is product X?** (also reachable from the product form's "Where is it?" button). **Who:** all readers. **Common mistake:** forgetting to filter by the product. **Best practice:** use the "is oldest" marker to know which slot to pick from.

### 10c. Oldest stock (FIFO)
**Purpose.** Every live quant ordered by arrival age, grouped by rack/compartment. Menu: **Reports → Oldest stock (FIFO)**. **Who:** all readers. **Best practice:** rotate the oldest stock to the front of the shelf.

### 10d. Slot occupancy
**Purpose.** One row per slot/floor area: capacity, on-hand, occupancy %, distinct product count. Menu: **Reports → Slot occupancy**. **Who:** all readers. **Note:** occupancy % only shows if the slot has a soft capacity set.

### 10e. Movement history
**Purpose.** All validated stock moves (in/out/internal), grouped by product, with a pivot view. Menu: **Reports → Movement history**. **Who:** all readers. **Best practice:** use the pivot to compare receipts vs issues over time.

### 10f. Expiry alerts
**Purpose.** Perishables (anything with an expiry date) bucketed into Expired / within 30 days / within 90 days / OK, with days-to-expiry and on-hand. Menu: **Reports → Expiry alerts**. A weekly digest is emailed to Managers. **Who:** all readers. **Best practice:** clear expired stock via Damage, and move soon-to-expire stock to the front (FEFO already prefers it).

### 10g. Tool / Spare fleet
**Purpose.** For tools and spares only: the peak number simultaneously checked out over 90 days, a recommended fleet size (peak + 1 spare), and the shortage to buy. Menu: **Reports → Tool / Spare fleet**. **Who:** all readers; buying is Admin. **Best practice:** use the shortage column to decide how many of a shared tool to own. **Common mistake:** treating the peak as gospel when there are very few movements — it's a lower bound.

### 10h. Store Keeper Activity (weekly / monthly / yearly)
**Purpose.** A one-row-per-event timeline of everything each keeper did — receipts, returns, issues, internal moves, damages, repairs — sliceable by person and day. Menu: **Reports → Store Keeper Activity** (plus pre-filtered Weekly / Monthly / Yearly shortcuts). **Who:** **Admin / Manager only** (keepers don't audit each other). **Best practice:** use the period shortcuts for routine reviews; use the detail view to answer "who was on the desk when X happened?".

### 10i. Cycle Count Due
See §8a. **Who:** all readers; Managers get the weekly reminder.

### 10j. Low stock alerts / Dead stock / Reorder summary
See §9. **Who:** all readers; acting on them (buying) is Admin.

**Common Mistakes (all reports).** Assuming a report changes stock — they're read-only. Forgetting that some lists (Storekeeper Activity) are Manager-only and simply won't appear for a keeper.

**Best Practices (all reports).** Use the search filters and group-bys already built into each view. Open the relevant report before a weekly review meeting.

**Related Workflows.** Nearly every operational feature feeds a report; Audits (§8) and Forecast (§9) are the action counterparts.

---

## 11. Backup / Restore / Health

**Purpose.** Protect the trust's data and prove it's recoverable.
- **Download encrypted backup** (Configuration → Download encrypted backup): runs `pg_dump` and GPG-encrypts (AES-256) the database, streaming a `.dump.gpg` file straight to the Admin's browser. Same format the scheduled PowerShell backup script produces.
- **Restore from backup…** (Configuration → Restore from backup…): deliberately **not** a one-click web action — it opens an instructions page with the exact PowerShell command, because a bad restore would wipe live data. Restore is CLI-only (`scripts\restore-native.ps1 ... -Force`).
- **Backup & DR Audit** (Reports → Backup & DR Audit): an append-only log of every backup, restore drill, and staleness warning, written by the backup/restore scripts.
- **Health check** (`/wms/health`): a public JSON endpoint returning HEALTHY / DEGRADED / CRITICAL based on how fresh the last backup and last restore drill are (CRITICAL if no backup has ever been recorded; DEGRADED if the backup is over ~24h old or no recent restore drill). A daily job warns Managers when health slips. It also reports the Google Drive tier (`gdrive_enabled`, `drive_connected`, last upload age, storage used/limit, next backup time) — Drive problems are DEGRADED at most, never CRITICAL.
- **Back Up Now** (WMS root menu): a one-button wizard that sends a fresh encrypted copy to **Google Drive** immediately; the success screen shows the filename, size, and upload time. Gated by the capability group **"WMS / Can Run Backup Now"** (granted per keeper; Managers always have it).
- **Google Drive Backup** settings (Configuration, Manager-only): schedule (default 16:30), notifications, retention tiers, plus **Test Connection** / **Test Upload** / **Apply Schedule** buttons.
- **Google Drive Backups** restore browser (Configuration, Manager-only): a read-only catalog of the Drive sets grouped Year → Month → Day, with a copy-paste `gdrive-restore.ps1` command per set — execution stays CLI-only.

**Who Uses It.** **Admin / Manager only** for download, restore info, settings, the Drive catalog, and the DR audit dashboard. A **Store Keeper** with the **"WMS / Can Run Backup Now"** capability can use Back Up Now — and nothing else of the backup surface (keepers see no restore screens at all). The `/wms/health` endpoint is public (for an external uptime monitor) but exposes only ages and status — no secrets, filenames, or data.

**Prerequisites.**
- `pg_dump` and `gpg` installed on the server (the download page tells you if either is missing).
- A strong `BACKUP_PASSPHRASE` set in the project `.env` (the page refuses to back up with the default placeholder — without it, backups can't be restored later).

**Common Mistakes.**
- Leaving `BACKUP_PASSPHRASE` at the default → backup download is blocked; set a strong 24+ character value.
- Expecting to restore from the web → it's intentionally CLI-only; follow the on-screen steps.
- Losing the passphrase → encrypted backups become unrecoverable. Store it safely off-machine.
- Ignoring a DEGRADED/CRITICAL health status or the Manager warnings.

**Best Practices.**
- Keep the scheduled backups running and do the **weekly restore drill** so health stays HEALTHY.
- Store the passphrase in a password manager, separate from the backups.
- Point an external monitor at `/wms/health` and alert on non-200 responses.
- Periodically open the Backup & DR Audit dashboard to confirm backups are landing and verified.

**Related Workflows.** Backup & DR Audit dashboard (§10-style report); the PowerShell scripts under `scripts/`; the Health Check and Cloud backup help articles in the Help Center; the cloud-backup SOP (`docs/training/sop/13-cloud-backup.md`) and the canonical Drive guide (`docs/22-gdrive-backup.md`).

---

## 12. User Management (Store Keeper roster, logins, capabilities, Beginner Mode)

**Purpose.** Manage who can do what. Two layers:
- **Store Keeper roster** (Configuration → Storekeeper): the list of human names that appear in the "Store Keeper on duty" dropdown on every Scan/Damage/Repair/Audit. A roster entry can stay name-only (used with a shared desk login) **or** be given its own Odoo login.
- **Capabilities & logins**: from a roster card, the Admin fills a login + initial password and clicks **Create login** to spin up a real Odoo user, then ticks the five capability boxes (Scan Receipt/Return, Scan Issue, File Damage, Submit Audit, Manage Catalog). New logins default to all capabilities **except** Manage Catalog. Archiving a roster entry also archives its login.
- **Beginner Mode**: a per-user toggle (default **on** for new staff) that turns on extra in-app guidance and stronger confirmations on risky actions. Each user can switch it off from their own preferences once comfortable.

**Who Uses It.** **Admin / Manager only** creates roster entries, logins, and capabilities. Each individual user can read/flip **their own** Beginner Mode.

**Prerequisites.** Decide each keeper's capabilities before creating their login. Choose short lowercase logins (`suresh`, `ramesh`).

**Common Mistakes.**
- A login with whitespace or capitals → rejected; use a single lowercase word.
- Re-using a login that's already taken → blocked with a friendly message.
- Deleting a keeper who appears in historical records — **archive** instead (untick "On the roster"), so past issues still reference them.
- Granting **Manage Catalog** to everyone — it's usually Admin work and off by default.
- Forgetting that ticking a capability on a roster entry **with no login yet** does nothing until the login is created.

**Best Practices.**
- Give each real person their own login (better audit trail than a shared desk account).
- Grant the **minimum** capabilities each role needs.
- Use **Open login** on the roster card to reset a password or manage the user later.
- Leave Beginner Mode on for new hires; let them turn it off themselves.

**Related Workflows.** Every operational feature's "Store Keeper on duty" field; Store Keeper Activity report (§10h); the capability gating that shows/hides menus (§intro).

---

## 13. Help Center & Getting Started (Help & Training app)

**Purpose.** In-app, searchable, beginner-friendly help — so staff don't need a separate manual. Separate app: **Help & Training** (visible to every internal user).
- **Getting Started**: a short, ordered set of onboarding articles for first-time users.
- **Help Center**: a searchable knowledge base grouped by category — *What is this?* (terminology), *Role training* (step-by-step Admin and Store Keeper learning paths), *Workflow tutorials*, *FAQ*, *Troubleshooting*, and *Safety warnings*. Articles are tagged by audience (Everyone / Admin / Store Keeper / Read-only). Many can carry a short **training video** (uploaded clip that works offline, or a YouTube/Vimeo link).

**Who Uses It.**
- **Everyone** (all internal users) can search and read articles and watch videos.
- **Admin / Manager** can add or edit articles and upload/link training videos (the editing controls are Manager-gated).
- **Store Keeper / Read-only** read only.

**Prerequisites.** None — content is seeded on install (terminology, FAQs, and the role learning paths) and is extendable in-app by a Manager without a code change.

**Common Mistakes.**
- Looking for help in the WMS app — it's the separate **Help & Training** app.
- A keeper expecting to edit articles — only Managers can.
- Pasting a non-YouTube/Vimeo video link and expecting it to embed — only those two hosts embed; others show as a safe outbound link.

**Best Practices.**
- New staff: start with **Getting Started**, then follow your role's learning path (Admin Path or Keeper Path).
- Search by what you'd actually type ("why is this blocked?", "FIFO", "compartment").
- Managers: when a question keeps coming up, add a short article (and a 2-minute video) so the next person self-serves.

**Related Workflows.** Beginner Mode (§12) which surfaces extra hints in the WMS app; every feature above has matching terminology/workflow articles here.

---

## Quick role cheat-sheet

| Feature | Admin / Manager | Store Keeper (with capability) | Read-only viewer |
|---|---|---|---|
| Build racks / zones / slots | Create, edit, archive | Read | Read |
| Onboard Products | Yes | No | No |
| Scan Receipt / Return | Yes | Yes (Scan Receipt+Return) | No |
| Scan Issue (FIFO/FEFO) | Yes | Yes (Scan Issue) | No |
| Damage | Yes | Yes (File Damage) | No |
| Repair Orders | Yes (authorise) | Create from damage only | No |
| Inventory Audit | Review/accept/reject | Create/count/submit (Submit Audit) | No |
| Carton aliases / Labels | Yes | Yes only if Manage Catalog | No |
| Forecast / Reorder / POs | Yes | Read | Read |
| Reports | Yes | Read (most) | Read (most) |
| Store Keeper Activity report | Yes | No (Manager-only) | No |
| Backup / Restore / DR audit | Yes | No | No |
| Back Up Now (Google Drive) | Yes | Yes (Can Run Backup Now) | No |
| User roster & logins | Yes | No | No |
| Help Center | Read + edit articles | Read | Read |
| Beginner Mode (own toggle) | Yes | Yes | Yes |

---

*Document version 1.0 — generated from the WMS source (addons: wms_location, wms_barcode, wms_fifo, wms_repair_damage, wms_reports, wms_training, wms_ai_forecast). When the software changes, update this map alongside it.*
