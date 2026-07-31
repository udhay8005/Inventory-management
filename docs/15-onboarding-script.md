# 15 — 30-Minute Onboarding Script

Use this verbatim when training a new Receiver / Issuer / Manager.
**Total time: 30 minutes**, including the practice transaction.

Bring: the trainee's laptop or phone on the same WiFi, a real product with
a barcode (or a printed test label), a wireless or USB scanner.

---

## 0. Prep (do once before any training) — 5 min

- [ ] Trainee has a user account in Odoo (Settings → Users → Create).
- [ ] User added to the correct group:
  - Receivers, Issuers → **WMS / Store Keeper**
  - Inventory In-charge → **WMS / Manager**
  - Mechanics → **WMS / Repair Tech**
  - Procurement (optional) → **WMS / Buyer**
- [ ] Trainee can log in to `http://<host-IP>:8069` and sees the **WMS** app
  in the home menu.

---

## 1. The big picture — 3 min

> "Three things to learn today:
> 1. Where things live (Rack → Compartment → Slot).
> 2. How to put stock in (Scan Receipt).
> 3. How to take stock out (Scan Issue).
>
> The software does the maths. You do the scanning. Every action you do is
> logged with your name, so be honest — mistakes are easy to find and fix
> later, but lying creates problems that take weeks to untangle."

### Show them the rack grid

1. WMS → Configuration → **Racks** → click **R01** → top of form → **Open visual grid**.
2. Point out: the default rack is a **6 shelf × 3 column** grid; each cell is a
   compartment with 1 slot, colour-coded (grey = empty, green = OK, red = full).
3. Walk them to the physical R01 and show how the slot barcodes match.

---

## 2. Scan Receipt — receiving stock — 7 min

### Talk through the steps

> "When stock arrives, three rules:
> 1. **Count before you scan.** Physical first, software second.
> 2. **Scan in the same session.** Don't leave the wizard open and come back tomorrow.
> 3. **Never put stock on a shelf before scanning.** Even for 5 minutes."

### Demo

1. WMS → Operations → **Scan Receipt**.
2. Show: the green banner "Scanner ready".
3. Hand them the scanner. Scan one product barcode.
   - Line appears with quantity 1 — they don't have to click anything.
4. Adjust quantity if needed (click the cell, type, Tab).
5. Scan a slot barcode (or pick from the dropdown).
6. Click **Validate & Print**.

### What just happened (point out)

- A `stock.picking` was created (WH/IN/N).
- Quantity was added to that slot.
- Today's date is the FIFO `in_date` for this batch.
- The chatter at the bottom shows the trainee's name + timestamp.

### Practice

Hand them 3 different barcodes. Have them receive one at a time. Time them —
target is **under 30 seconds per item** once the scanner is in their hand.

---

## 3. Scan Issue — taking stock out (FIFO) — 7 min

### Talk through

> "When stock leaves — for sale, consumption, or transfer — it's the same
> drill, but reverse. The software picks the **oldest stock first** across
> every slot holding that product. You don't choose; FIFO does. If the
> system says take from `R01-SH03-C02-SL01` and you take from
> `R01-SH05-C01-SL01`, the stock counts go wrong."

### Demo

1. WMS → Operations → **Scan Issue (FIFO)**.
2. Choose destination:
   - **Customers** for despatch
   - **Production** for internal consumption
   - **Internal** for slot-to-slot
3. Set *Requested Qty* (e.g. 50).
4. Scan the product barcode.
5. The plan table fills in: shows oldest slots first with quantities.
6. If the product is measured (litres / kg), **take a photo** — mandatory.
   - On phone: tapping the photo field opens the camera.
   - On desktop: file picker.
7. Click **Validate**.

### What just happened

- A delivery picking (or internal transfer) was created in **Done** state.
- Quants in the oldest slots were decremented.
- Photo, if attached, is permanently in the picking's chatter.

### Practice

Have them issue 3 items, one to each destination type. Confirm they
understand: "FIFO picks for you — don't override unless the slot is
physically empty (in which case, also tell the Manager — a slot count is
off)."

---

## 4. Damage flow — 4 min

### Talk through

> "Broken on arrival, broken later, expired — anything that shouldn't be
> sold or consumed goes through Damage. **Never** silently throw it out."

### Demo

1. WMS → Operations → **Damages** → click **New** in the list view.
2. Product, quantity, source slot, reason.
3. Optional: photo + note.
4. Confirm → creates an internal transfer to the **Damage** location.

> "From Damage, an item either gets scrapped, repaired and returned, or
> sent back to the vendor. All three are recoverable from the chatter."

If they're a Repair Tech, also show:

1. WMS → Operations → **Repair Orders** → click **New** in the list view.
2. Product, qty, original slot (the one it came from before damage).
3. **Start Repair** → moves to Repair-Out location.
4. **Mark Done** → moves back to the original slot.
5. Or **Scrap** → permanent write-off.

---

## 5. "Where is product X?" — 2 min

> "If you ever need to find something, don't walk the floor. Use the report."

1. WMS → Reports → **Where is product X?**
2. Search the product name or SKU.
3. The list shows every slot holding it, with the FIFO-oldest row marked
   "Next to pick".
4. Click any row → goes to the slot record → click **Open Visual Grid** on
   the rack to see it highlighted physically.

---

## 6. Cycle Count basics — 3 min

### For everyone

> "Software trust is built by counting. You'll spot-check 3 slots a day,
> and the Manager will do a full count every Monday."

1. WMS → Operations → **Cycle Count**.
2. Filter by product or slot.
3. Type the physical count into *Counted Quantity*.
4. Click **Apply** → if there's a mismatch, system creates a correction
   and logs the difference.

### For Managers

> "Every Monday morning you'll get a Discuss notification listing slots
> not counted in 30+ days. Walk those slots that week."

Show: WMS → Reports → **Cycle Count Due**.

---

## 7. Wrap-up checklist — 4 min

Walk them through:

- [ ] You can log in to `http://<host-IP>:8069` from your phone on the WiFi.
- [ ] You know where Scan Receipt and Scan Issue live in the menu.
- [ ] You've done one Receipt + one Issue + one Damage end-to-end.
- [ ] You know the **3 rules of scanning**:
  1. Count physical first.
  2. Scan in the same session.
  3. Nothing on a shelf until it's scanned.
- [ ] You know where to find audit history (the chatter at the bottom of
  every record).
- [ ] You know who to escalate to when a count doesn't match.
- [ ] You have the SKU naming policy printed and on the wall.

> "If you're ever unsure, **stop and ask the Manager**. We can always fix
> data from the audit log. We can't fix stock that walked out a door
> without being scanned."

---

## Common first-week issues and quick answers

| What the trainee asks | Answer |
|---|---|
| "Why didn't my scan register?" | Make sure the cursor is in the scan field. Tap it once if not. Scanner ENTER suffix should fire automatically. |
| "What if I scan the wrong product?" | Click the red X on that line in the wizard before Validate. After Validate, ask the Manager to do an inventory adjustment. |
| "Where do I see what I did today?" | Click your name in the top right → My Activities → Recent. Or any picking has full chatter history. |
| "The product I want isn't here." | Go to WMS → Configuration → **Onboard Products** (Manager-only), follow the SKU naming policy, print a label, then receive it. |
| "The slot label is faded/missing." | Re-print: WMS → Operations → Slots → tick the slot → ☰ → Print > WMS Location Label (100×25mm). |

---

**Total elapsed: 30 min.**
**The trainee leaves with muscle memory for receipt + issue + damage and
knows where to look for everything else.**
