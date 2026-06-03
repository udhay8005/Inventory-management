# SOP 01 — Receiving Stock (Scan Receipt)

*Standard Operating Procedure for the Store Keeper role — Dakshin Vrindavan Cow-Care Trust WMS (Odoo 19)*

---

## Purpose

Bring newly delivered stock into the warehouse correctly, every single time. "Receiving" is the act of recording what a vendor or courier dropped off — feed, medicine, ghee, tools — so the system knows it exists, how much there is, where it sits, who took it in, and exactly when it arrived. That arrival time (the *in-date*) is what FIFO later uses to decide which batch leaves first, so a sloppy receipt poisons every later issue. Receiving is where good data begins.

The trust **buys and uses** stock; it never sells. So a receipt has no price approval, no invoice, no money gate. What it does have is a **quality check** (you confirm the count and condition with your own eyes) and an **audit trail** (your name as the on-duty keeper, plus who delivered it).

---

## Who Uses It (role + capability group)

- **Role:** Store Keeper (Odoo group `WMS / Store Keeper`, technical id `group_wms_user`).
- **Capability required:** *Can Scan Receipt / Return* (`group_wms_can_scan_receive`). The Admin ticks this on your roster card under **Configuration → Store Keepers**.
- If you do **not** have this capability, the **Scan Receipt** menu will not appear for you at all.
- A **WMS Manager** (Admin) inherits this capability automatically and can also receive.

---

## Prerequisites

Before a receipt will work:

1. You are logged in with a Store Keeper account that has the **Can Scan Receipt / Return** capability.
2. At least one **warehouse** exists (Odoo creates one on install).
3. At least one **slot** or **floor zone** exists in the warehouse — otherwise the system has nowhere to put the stock and will refuse at Validate. Racks/slots are built by the Admin under **Configuration → Create Rack** / **Generate Floor Zones**.
4. The products being delivered already exist in the catalogue with a **barcode** (the Admin onboards products under **Configuration → Onboard Products**). A brand-new product the system has never seen will scan as "Unknown barcode".
5. Your **name is on the roster** (Configuration → Store Keepers, "On the roster" ticked) so it appears in the *Store Keeper on duty* picker. Only on-roster keepers show up there.
6. A barcode **scanner** (USB or Bluetooth, acting as a keyboard) is connected — or you can type/pick lines by hand.

---

## Step-by-Step Instructions

Open the wizard: **WMS → Operations → Scan Receipt**. It opens as a pop-up form titled **Scan Receipt**.

1. **Read the blue banner.** It says: *"Scanner ready. Cursor stays in the scan field — each barcode is processed automatically. Carton barcodes auto-fill their unit count."* This is your reminder that you do **not** click a button after every scan; the cursor lives in the scan box and each beep is processed on its own.

2. **Confirm the company/warehouse.** The top-left field is the **warehouse** selector. It defaults to the trust's warehouse; leave it unless you genuinely run more than one.

3. **Leave the *Return entry* toggle OFF.** This is a plain receipt of newly bought goods. (The toggle is only ON when you opened **Scan Return** instead — see SOP 04.)

4. **Scan into the "Scan here" field.** It carries the placeholder *"Scan product, carton, or slot..."* and already has the cursor. For each item:
   - Scan the **product** barcode → a line is added to the table below with **Quantity = 1**.
   - Scan a **carton** barcode → a line is added with the carton's **preset unit count** (e.g. a 24-bottle carton adds 24 at once).
   - The grey **feedback** line under the box confirms each action, e.g. *"Added 24 × Cow Calcium Bolus"*.

5. **Watch the lines table.** It has columns **Product | Quantity | Location Dest** (plus an optional hidden Lot column). You can also click **Add a line** to enter a product and quantity by hand if a barcode won't scan.

6. **Set the destination slot (putaway) — optional.** In the **Location Dest** column you may pick the slot, or simply **scan the slot's barcode** (e.g. `R01-SH04-C01-SL01`). When you scan a slot, it is applied to the most recent line that doesn't yet have a destination, and the feedback says *"Slot … assigned"*. If you leave Location Dest empty, the system **auto-assigns** a sensible slot when you Validate (see SOP 02 — Putaway). Slot codes read **Rack / Shelf / Compartment / Slot**, e.g. `R01 / SH04 / C01 / SL01`.

7. **Complete the QUALITY CHECK block.** Tick **Quality check passed** to confirm you have physically counted the delivery and inspected its condition. This tick is **mandatory** — Validate is blocked without it. Use the free-text **QC notes** box (placeholder *"Anything unusual? (optional)"*) to record anything odd (a dented tin, a short count, a near-expiry batch).

8. **Complete the AUDIT TRAIL block.**
   - **Store Keeper on duty** — **required**. Pick *your* name from the roster (the on-duty human at the desk). You cannot create a name here; if yours is missing, ask the Admin to add it first.
   - **Delivered by** — optional but helpful. Type the driver / vendor / courier who handed the goods over.

9. **Press "Validate & Print".** The system:
   - auto-assigns slots for any line you left blank,
   - creates the incoming receipt and lands the stock in its slot,
   - stamps today's date/time as the **in-date**,
   - writes an audit message into the receipt's history,
   - and opens the finished receipt record.

10. **Walk the stock to its slot.** Read the slot name on the finished receipt (or on each line). Carry each item to that exact shelf, place it, and check the shelf label matches the name on screen.

> **Buttons on this form:** **Process scan** (manually push whatever is in the scan box — rarely needed, scans auto-process), **Validate & Print** (finish the receipt), **Cancel** (discard).

> **Double-click safety:** once a receipt is validated, the wizard remembers it. Clicking Validate again (or refreshing) just **re-opens the receipt already made** — it will **not** receive the delivery twice.

---

## Worked Example

A vendor drops off **2 cartons of Cow Calcium Bolus** (each carton = 24 bottles, kind MED, batch BATCH-B with an expiry) and **1 E2E Hammer** (kind TOOL).

1. At the door you count: 2 sealed cartons + 1 hammer. The carton seals are intact; the hammer is fine. Quality looks good.
2. **WMS → Operations → Scan Receipt.**
3. Warehouse defaults correctly; *Return entry* is OFF.
4. You scan the first **carton barcode** → feedback: *"Added 24 × Cow Calcium Bolus"*. You scan the second carton → another *"Added 24 × Cow Calcium Bolus"* line.
5. You scan the **E2E Hammer** product barcode → *"Added 1 × E2E Hammer"*.
6. You scan the medicine slot label `R01-SH04-C01-SL01` to send the calcium there (feedback: *"Slot R01 / SH04 / C01 / SL01 assigned"*). You leave the hammer's Location Dest blank and let auto-putaway handle it.
7. QUALITY CHECK: tick **Quality check passed**; in QC notes you type *"BATCH-B, expiry on box, all seals intact."*
8. AUDIT TRAIL: **Store Keeper on duty = Suresh** (your roster name); **Delivered by = "Ravi (vendor driver)"**.
9. **Validate & Print.** The 48 calcium bottles land in `R01 / SH04 / C01 / SL01`; the hammer is auto-assigned to a tool slot; both get today as their in-date; the receipt opens showing the moves.
10. You carry the cartons to the medicine rack slot, the hammer to its tool slot, and confirm the shelf labels match.

---

## Common Errors & What They Mean

| Message / symptom | What it means | What to do |
|---|---|---|
| **"No lines to receive."** | You clicked Validate with an empty table. | Scan at least one product/carton first. |
| **"Mark 'Quality check passed' first…"** | You tried to Validate without ticking the QC box. | Physically count and inspect, then tick **Quality check passed**. |
| *Store Keeper on duty* shows a red "required" outline | You left the on-duty keeper blank. | Pick your name from the roster. If it's missing, ask the Admin to add you. |
| **"Unknown barcode: …"** (in feedback) | The scanned code isn't linked to any product. | Check you scanned the right label. If it's a genuinely new item, the Admin must onboard it first. |
| **"No pending line for slot …"** (in feedback) | You scanned a slot before scanning any product. | Scan the product first, *then* its slot. |
| **"No slots or floor zones are set up in warehouse … yet."** | The warehouse has no storage locations. | Ask the Admin to run **Create Rack** or **Generate Floor Zones**. |
| **"Warehouse … isn't configured to receive incoming stock."** | The warehouse's Receipts operation type is missing. | Ask an Administrator to enable Receipts in Inventory settings. |

---

## Troubleshooting

- **Scans aren't appearing.** Click once **inside the "Scan here" box** so the cursor is there, then scan. Most scanners send an "Enter" after each code (the factory default) — if yours doesn't, set it to do so, or press Enter / click **Process scan** after each scan.
- **The wrong quantity appeared.** You probably scanned a *carton* barcode (which adds the carton's full count) when you meant a single unit, or vice-versa. Fix the **Quantity** cell on the line directly, or delete the line (the trash icon) and re-scan the correct label.
- **Wrong slot.** Scan the correct slot barcode again — it reassigns the most recent line without a destination — or pick the slot in the **Location Dest** column. To correct a line that already has a slot, edit the Location Dest cell.
- **I clicked Validate twice.** No harm done. The second click just re-opens the receipt that was already created; the stock is not doubled.
- **A barcode genuinely won't scan.** Use **Add a line** and choose the product and quantity by hand. Tell the Admin the label is unreadable so it can be reprinted.
- **Two separate deliveries arrived together.** Do **one receipt per delivery** so each vendor's audit trail stays clean.

---

## Best Practices

- **Scan first, shelve second.** Never place stock on the shelf before scanning it in. If it's on the shelf but not in the system, FIFO and every report are wrong.
- **One delivery = one receipt.** Don't batch several vendors' goods into a single Scan Receipt.
- **Count at the door.** Tick *Quality check passed* only after you've physically counted and eyeballed the goods. Note anything odd in QC notes — a near-expiry batch, a dented tin.
- **Record who delivered it.** *Delivered by* is optional, but a name now saves an investigation later.
- **Cluster like with like.** If you know a product already has a home slot, scan that slot so the new stock joins it instead of scattering.
- **Damaged or short on arrival?** Receive only what's good, and send the bad units through the **Damages** workflow — never quietly bin them.
- **Pick your own name** as Store Keeper on duty, not whoever was here this morning. The audit trail must name the human who actually took the goods.

---

## Related Help-Center Articles (by slug)

- `workflow-receiving-stock` — How to receive stock (Scan Receipt)
- `keeper-path-receiving` — Keeper Path 3: Receiving a delivery
- `what-is-scan-receipt` — Scan Receipt (receiving stock)
- `what-is-putaway` — Putaway (where new stock goes)
- `what-is-in-date` — In-date (arrival date)
- `what-is-a-barcode` — Barcode (Code128 and EAN-13)
- `what-is-audit-trail` — Audit trail
- `what-is-a-storekeeper` — Store Keeper
- `keeper-path-barcodes-and-scanners` — Keeper Path 2: Barcodes and scanners

---

## Narration Script (voiceover for a 2–4 min screen recording)

**[0:00]** "Hello. In this short video we'll receive a delivery into the warehouse using Scan Receipt. Receiving is how new stock — feed, medicine, tools — officially enters the system, with your name on it and today's date stamped as the arrival time."

**[0:15]** "First, before we touch the computer, we count the delivery at the door and check its condition. Here we have two cartons of Cow Calcium Bolus and one E2E Hammer. Seals intact, hammer's fine."

**[0:30]** "Now, from the WMS menu, I open Operations, then Scan Receipt. Notice the blue banner: the cursor stays in the scan field and every barcode is processed automatically — I don't click after each one."

**[0:45]** "I leave the Return entry toggle off — this is brand-new stock, not something coming back. The warehouse is already correct."

**[1:00]** "I scan the first calcium carton. See the feedback line: 'Added 24 times Cow Calcium Bolus'. The carton barcode filled in twenty-four automatically. I scan the second carton — another twenty-four. Then the hammer — 'Added 1 times E2E Hammer'."

**[1:25]** "I want the calcium in its medicine slot, so I scan the slot label. The feedback says the slot is assigned. For the hammer I'll leave the destination blank and let the system auto-pick a tool slot when I validate."

**[1:45]** "Down here is the Quality Check block. Because I've counted and inspected everything, I tick 'Quality check passed' — the system won't let me finish without this. In QC notes I jot 'BATCH-B, expiry on box, seals intact'."

**[2:10]** "In the Audit Trail block, I pick myself — Suresh — as Store Keeper on duty. This is required: it records the real human at the desk. Under 'Delivered by' I type the driver's name. That's optional, but it's good practice."

**[2:35]** "Now I press Validate and Print. The stock lands in its slots, today's date becomes the in-date that FIFO will use later, and the system writes an audit note. The finished receipt opens so I can see exactly where everything went."

**[2:55]** "Last step — and it's a real step — I carry the cartons to the medicine slot and the hammer to its tool slot, and I check the shelf labels match the screen. Scan first, shelve second. That's receiving. Done."

---

## Recording Checklist (exact click path to perform on camera)

1. Show the **WMS** top menu.
2. Click **Operations → Scan Receipt**.
3. Point the cursor at the **blue banner**; read it.
4. Show the **warehouse** field (default) and the **Return entry** toggle (OFF).
5. Click into **"Scan here"**; scan carton #1 of Cow Calcium Bolus → show feedback *"Added 24 × …"*.
6. Scan carton #2 → second line.
7. Scan **E2E Hammer** → *"Added 1 × E2E Hammer"*.
8. Scan slot label `R01-SH04-C01-SL01` for the calcium → show *"Slot … assigned"* in feedback and the **Location Dest** cell filled.
9. Leave the hammer's **Location Dest** blank.
10. Tick **Quality check passed**; type a line in **QC notes**.
11. Set **Store Keeper on duty** to your roster name; type a **Delivered by** name.
12. Click **Validate & Print**.
13. Show the resulting **receipt form** that opens, with the moves and slots.
14. (Optional closing shot) Open the slot / **Reports → Where is product X?** to confirm the calcium is now in `R01 / SH04 / C01 / SL01`.
