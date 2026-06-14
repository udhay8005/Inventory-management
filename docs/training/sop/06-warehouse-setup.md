# SOP 06 — Warehouse Setup (Zones, Racks, Compartments, Slots, Floor Zones)

## Purpose
This procedure explains how an Admin builds the physical storage map of the warehouse inside the WMS, so every item ends up with a precise, scannable address (Rack → Compartment → Slot, or an open Floor zone). You do this with three "generator" wizards:

- **Generate Zone** — creates a named umbrella area (e.g. "1st Floor") and can create racks and/or floor zones inside it in one click.
- **Create Rack** — creates a single shelving unit laid out as a grid of shelves × columns, with compartments and slots underneath.
- **Generate Floor Zones** — creates open / pallet / yard storage areas that behave like a slot for receiving, FIFO issue, and reports.

Getting this right once means every later step — receiving, issuing, counting, damage, and reports — points to the correct shelf.

## Who Uses It
- **WMS / Manager (Admin) only.** All three generators live under **WMS → Configuration**, which is hidden from Store Keepers (the Configuration menu is gated by the `group_wms_manager` group).
- Read-only viewers and Store Keepers cannot run these wizards; they only see the resulting locations on reports and scan screens.

## Prerequisites
- You are logged in as a user in the **WMS / Manager** group.
- At least one **Warehouse** exists (Odoo creates a default one on install; its stock location is usually `WH/Stock`).
- Decide your naming and counts before you start:
  - Zone names (e.g. "1st Floor", "Ground Floor / East", "Outside Yard").
  - Rack codes (convention is zero-padded: `R01`, `R02`, …).
  - For each rack: number of shelves (rows), columns, and slots per compartment.
  - For floor zones: a prefix (e.g. `F`), a start number, and a count.
- A label printer ready, so you can print and stick location barcodes after generation (covered in the rack/slot-label SOP and the help article `admin-path-rack-compartment-slot-logic`).

## Step-by-Step Instructions

### A. Generate a Zone (and optionally fill it with racks/floor zones)
1. Open **WMS → Configuration → Generate Zone**. A dialog titled **Generate Zone** opens with a blue banner explaining: *"A Zone groups racks and floor areas under a single named umbrella — e.g. '1st Floor', 'Ground Floor / East', 'Outside Yard'. Use this wizard once per zone; counts can be 0 if the zone is a pure container."*
2. Set **Warehouse** (defaults to your only warehouse).
3. Set **Parent location** — the location the zone will live under. Usually `WH/Stock` (only "view"-type locations are selectable).
4. Type the **Zone Name** (the field shows the placeholder `1st Floor`).
5. Under the **Racks** section, set **Rack Count**. If you leave it `0`, no racks are created and the zone is a pure container. If you set it above 0, extra fields appear:
   - **Rack start number** (default `1`) — use `33` if you already have `R01`…`R32` elsewhere.
   - **Rack prefix** (default `R`).
   - **Shelves per rack** (default `6`).
   - **Columns per rack** (default `3`).
   - **Slots per compartment** (default `1`).
   - **Rack capacity per slot** (optional soft cap).
   Every rack created here uses the same shelves × columns layout (quick-grid mode).
6. Under the **Floor zones (no rack)** section, set **Floor Count** (default `0`). If above 0, extra fields appear: **Floor start number**, **Floor prefix** (default `F`), and **Floor capacity**.
7. Click **Generate**. The wizard creates the zone, then any racks and floor zones inside it, and opens the new zone's form. Re-running with the same zone name and rack codes is safe — existing racks/zones are skipped, not duplicated.

### B. Create a single Rack
1. Open **WMS → Configuration → Create Rack**. A dialog titled **Create Rack** opens.
2. Under **Rack identity**, set:
   - **Warehouse**.
   - **Parent location** — usually a Zone (e.g. "Pharmacy") or `WH/Stock`.
   - **Rack Code** (placeholder `R01`; zero-pad by convention).
   - **Display name** (optional human label, e.g. "Pharmacy bottles").
   - **Capacity Per Slot** (optional soft cap).
3. Choose a layout tab:
   - **Quick grid** (the simple option). Set **Shelves** (e.g. `6`), **Columns** (e.g. `3`), and **Slots per compartment** (e.g. `1`). A note reminds you: *"Quick grid creates one compartment per (shelf × column) cell with the same slot count. Switch to Visual builder if you need merged compartments (e.g. one tall compartment spanning shelves 1–3)."*
   - **Visual builder** (advanced). Click cells in the preview to select them, then use **Merge up** / **Merge down** / **Split** to build spanning compartments, and set the slot count per compartment in the side panel. The JSON box below is generated for you — do not hand-edit it unless you really mean to. When the Visual builder has produced a layout, it overrides whatever is in Quick grid.
4. Click **Create rack**. The system builds the hierarchy Rack (view) → Compartment (view) → Slot (internal). Each slot gets an auto barcode like `R01-SH01-C01-SL01` (the segments are zero-padded; spanning compartments read like `R01-SH01-03-C01-SL01`). The new rack's form opens.

### C. Generate Floor Zones (open / pallet / yard storage)
1. Open **WMS → Configuration → Generate Floor Zones**. A dialog titled **Generate Floor Zones** opens with a banner: *"Use floor zones for items not stored in a multi-tier rack — pallet areas, single-shelf slabs, outside yard bays, receiving/staging benches. Each zone gets a unique barcode and behaves like a slot for receiving, FIFO issue, and reports."*
2. Set **Warehouse**.
3. Set **Parent area** — usually `WH/Stock`, or a building/zone underneath it (only "view"-type locations are selectable).
4. Set **Zone Prefix** (e.g. `F`).
5. Set **Start Number** (default `1`) — bump this if you already used `F-01`…`F-05`.
6. Set **Count** (how many to create, default `1`).
7. Set **Capacity Units** (optional soft cap per zone).
8. Click **Generate**. Resulting names look like `WH/Stock/F-01`, each with a unique barcode (prefixed with a compressed parent code so two warehouses' `F-01`s don't collide on a scanner). The new floor zones open in a list so you can print labels immediately. If every requested zone already exists, you get a "Nothing to do" notice.

### D. After generating: review and label
1. Browse what you created: **Configuration → Zones**, **Configuration → Racks**, **Configuration → Compartments**, **Operations → Slots**, **Operations → Floor Zones**.
2. Print and stick the location barcodes (see the rack/slot label workflow). Place each label where a hand can see it while reaching in.
3. Walk the floor with the rack grid open and confirm the **physical shelves match the software**.

## Worked Example
The trust is setting up its medicine room as a zone with two racks.

1. **WMS → Configuration → Generate Zone**.
2. Warehouse = the default warehouse; Parent location = `WH/Stock`; Zone Name = `Pharmacy`.
3. Racks section: Rack Count = `2`; Rack prefix = `R`; Rack start number = `1`; Shelves per rack = `6`; Columns per rack = `3`; Slots per compartment = `1`.
4. Floor zones section: Floor Count = `0` (the pharmacy is all shelving).
5. Click **Generate**. The system creates the `Pharmacy` zone, then racks `R01` and `R02` inside it, each with 6 × 3 = 18 compartments and 18 slots (one slot each). Slot barcodes look like `R01-SH01-C01-SL01` through `R02-SH06-C03-SL01`.
6. Now the trust needs a pallet bay for bulk feed sacks near the same room. **WMS → Configuration → Generate Floor Zones**: Parent area = `WH/Stock`, Zone Prefix = `F`, Start Number = `1`, Count = `3`. Click **Generate** → creates `F-01`, `F-02`, `F-03` (names like `WH/Stock/F-01`), each behaving like a slot for receiving and FIFO.
7. Print labels for the 36 rack slots and the 3 floor zones; stick them on the shelves and pallet positions.

## Common Errors & What They Mean
- **"A rack with code R01 already exists under <location>."** — You tried to create a rack whose code is already taken under that parent. Use a different code or a higher start number. (The Zone generator silently skips a duplicate rack code instead of erroring.)
- **"You must have at least 1 shelf and 1 column on the rack. Enter numbers like 6 shelves x 3 columns (the usual setup)."** — Shelves or columns was 0 or blank in Quick grid.
- **"Slots per compartment must be at least 1."** — Slots-per-compartment was 0.
- **"The custom layout file isn't formatted correctly… Ask a Manager to re-generate the layout using the Visual builder…"** — The Visual builder's JSON is malformed (only happens if it was hand-edited). Re-open the Visual builder tab to regenerate it.
- **"Cell (shelf X, column Y) is covered by two compartments (#a and #b). Compartments cannot overlap."** — A Visual-builder layout has overlapping compartments. Adjust the merges so each cell belongs to exactly one compartment.
- **"Compartment #N references shelf/column … which is out of range 1..M."** — A Visual-builder compartment spills outside the rack's grid. Increase the rack's shelves/columns, or shrink the compartment.
- **"Count must be at least 1."** (Floor Zone generator) — You set Count to 0.
- **"Nothing to do — Every requested zone already exists."** (Floor Zone generator) — Idempotent re-run; the floor zones you asked for were already created.

## Troubleshooting
- **Parent location dropdown is empty or missing the place I want.** The Zone and Floor Zone parent fields only list "view"-type locations (containers, not slots). `WH/Stock` is a view location and should appear. If a custom area doesn't appear, it may have been created as "internal" rather than "view".
- **The wizard created the zone but no racks/floor zones.** Check you set Rack Count / Floor Count above 0 — they default to 0, which makes the zone a pure container.
- **I generated racks under WH/Stock but wanted them in a zone.** Select the racks (or floor zones) in any list, then use the list's **Action → Move to Zone** server action, pick the target zone, and confirm. (This action is Manager-only; Store Keepers get a clear "Only WMS Managers can move racks or zones" message.)
- **Barcodes look different for spanning compartments.** That's expected: a single cell reads `R01-SH01-C01-SL01`; a compartment spanning shelves 1–3 reads `R01-SH01-03-C01-SL01`; an L/T/U shape gets a `-P<n>` shape tag so two same-bounding-box compartments don't clash.
- **Two floor zones in different warehouses both want `F-01`.** That's fine — the barcode is prefixed with a compressed parent code, so the scanner sees distinct codes.

## Best Practices
- **Plan codes before generating.** Decide rack prefixes and start numbers so you never have to renumber later. Renumbering means re-labelling shelves.
- **Use the Zone generator for bulk builds, Create Rack for one-offs.** The Zone generator makes every rack identical (same shelves × columns). For a single rack with a custom layout (e.g. one tall compartment for bottles), use **Create Rack → Visual builder**.
- **Keep one slot per compartment unless you genuinely subdivide.** It keeps addresses simple. Add more slots only when a compartment physically holds separable sub-piles.
- **Set capacity hints sparingly.** Capacity is a *soft* hint shown on the Slot Occupancy report; it is not a hard limit and won't block over-filling.
- **Label immediately and verify against the real shed.** The system's value comes from the screen matching the shelves. Fix any mismatch the same day.
- **Use Floor zones for anything that can't sit on a tiered rack** — sacks, drums, pallets, yard items. They still support FIFO issue and all reports (and their stock shows on the Expiry Alerts report just like rack stock).

## Related Help-Center Articles
- `admin-path-warehouse-structure`
- `admin-path-rack-compartment-slot-logic`
- `workflow-creating-racks`
- `workflow-creating-zones-and-floor-areas`
- `what-is-a-rack`
- `what-is-a-compartment`
- `what-is-a-slot`
- `what-is-a-zone`
- `what-is-a-floor-location`
- `why-cant-i-move-racks-into-zone`

## Narration Script
*(Target length ~3 minutes. Read at a calm pace.)*

- **[0:00]** "Welcome. In this short video, an Admin will build the warehouse's storage map using the three generator wizards. Everything here is under WMS, then Configuration — a menu only Managers can see."
- **[0:15]** "Let's start with a Zone. A Zone is a big named area, like a room or a floor, that groups racks and floor areas together. Open WMS, Configuration, Generate Zone."
- **[0:30]** "Notice the blue banner: a Zone groups racks and floor areas under a single named umbrella. I'll set the Warehouse, leave the Parent location as WH/Stock, and type a Zone Name — let's call it 'Pharmacy'."
- **[0:50]** "Under Racks, I'll set Rack Count to two. More fields appear: the prefix 'R', a start number of one, six shelves, three columns, and one slot per compartment. I'll leave Floor Count at zero — this room is all shelving."
- **[1:12]** "Click Generate. The system creates the Pharmacy zone, then racks R-zero-one and R-zero-two inside it. Each rack now has eighteen compartments and eighteen slots, and every slot has its own barcode, like R-zero-one, dash, S-H-zero-one, dash, C-zero-one, dash, S-L-zero-one."
- **[1:35]** "Need a single rack with a custom shape? Use Configuration, Create Rack. Fill in the Rack identity, then either use the Quick grid tab for a simple shelves-by-columns layout, or the Visual builder to merge cells into a tall compartment — for example one compartment spanning shelves one to three for tall bottles. Then click Create rack."
- **[2:00]** "For sacks, drums, or pallet areas that don't fit on shelving, use Configuration, Generate Floor Zones. Set the Parent area, a prefix like F, a start number, and a count. Click Generate, and you get F-zero-one, F-zero-two, and so on. Floor zones behave just like slots for receiving, F-I-F-O issue, and reports — including the Expiry Alerts report."
- **[2:25]** "After generating, review your locations under Zones, Racks, Compartments, Slots, and Floor Zones. Print the barcodes, stick them where a hand can see them, and walk the floor to confirm the shelves match the screen."
- **[2:45]** "And that's it. Plan your codes once, generate, label, and verify. Your warehouse now has a precise address for every item. Thank you."

## Recording Checklist
1. Log in as a WMS Manager.
2. Click the **WMS** app icon.
3. Click **Configuration → Generate Zone**.
4. Show the banner; fill Warehouse, Parent location (`WH/Stock`), Zone Name (`Pharmacy`).
5. Set **Rack Count = 2**; show the revealed fields (prefix `R`, start `1`, shelves `6`, columns `3`, slots `1`).
6. Click **Generate**; show the resulting zone form.
7. Go back to **Configuration → Create Rack**; fill Rack identity; show **Quick grid** then click the **Visual builder** tab and merge two cells; click **Create rack**.
8. Go to **Configuration → Generate Floor Zones**; fill Parent area (`WH/Stock`), prefix `F`, start `1`, count `3`; click **Generate**; show the resulting list (`F-01`, `F-02`, `F-03`).
9. Open **Configuration → Racks** and **Operations → Slots** to show the generated hierarchy and barcodes.
10. End on the Slots list with the auto barcodes visible.
