# SOP 02 — Putaway (Getting Stock to Its Slot)

*Standard Operating Procedure for the Store Keeper role — Dakshin Vrindavan Cow-Care Trust WMS (Odoo 19)*

---

## Purpose

Putaway means deciding **which slot newly received stock goes into**, and then physically placing it there so the shed and the screen agree. In this system putaway is **not a separate screen** — it happens as part of **Scan Receipt** (SOP 01). You either tell the system the slot by scanning the slot's barcode during the receipt, or you leave it blank and let the system **auto-assign** a sensible slot when you press Validate.

Good putaway keeps each product together in one findable place, makes counting easy, and stops the same item being scattered across ten random slots. It also means a brand-new helper doesn't have to memorise the whole warehouse layout — scan and validate, and the system places it well.

### Understanding slot codes

Every storage location has an address built from the rack hierarchy: **Rack → Shelf → Compartment → Slot**. On screen the slot's display name reads with slashes:

```
R01 / SH04 / C01 / SL01
└┬─┘   └┬─┘  └┬─┘  └┬─┘
Rack  Shelf  Comp  Slot
R01    04     01    01
```

- **R01** — the Rack (one shelving unit). A rack can also be themed, e.g. `PHARM01`.
- **SH04** — the Shelf coordinate (4th shelf down). A tall compartment shows a range like `SH01-03`.
- **C01** — the Compartment (the cubby on the grid). A wide one shows `C01-03`.
- **SL01** — the Slot (the exact spot that actually holds the stock).

The printed barcode for that same slot uses hyphens instead of slashes: **`R01-SH04-C01-SL01`**. That's the code your scanner reads off the shelf label. Stock can also live in a **Floor / Open area** (a pallet or yard bay) which sits outside the rack tree but behaves exactly like a slot.

---

## Who Uses It (role + capability group)

- **Role:** Store Keeper (Odoo group `WMS / Store Keeper`, `group_wms_user`).
- **Capability required:** *Can Scan Receipt / Return* (`group_wms_can_scan_receive`) — the same capability as receiving, because putaway is the tail end of a receipt.
- **WMS Manager** (Admin) can also do it and additionally builds the slots/racks that putaway targets.

---

## Prerequisites

1. You can run **Scan Receipt** (have the *Can Scan Receipt / Return* capability).
2. The warehouse has **slots and/or floor zones** built by the Admin (Configuration → Create Rack / Generate Floor Zones). If there are none, the receipt cannot finish — auto-assign fails with *"No slots or floor zones are set up …"*.
3. Slot **shelf labels are printed and stuck** where a hand can see them while reaching in (the Admin prints these from **Operations → Slots → Print → WMS Location Label**). Putaway is only safe when the physical label matches the on-screen name.
4. You have stock in hand from an in-progress receipt (see SOP 01).

---

## Step-by-Step Instructions

Putaway happens inside the **Scan Receipt** wizard (**WMS → Operations → Scan Receipt**), after you've scanned your products onto the lines.

### Option A — You choose the slot (recommended when the product has a home)

1. Add your product/carton lines as in SOP 01.
2. With the cursor in the **"Scan here"** field, **scan the slot's barcode** off the shelf label (e.g. `R01-SH04-C01-SL01`).
3. The system applies that slot to the **most recent line that has no destination yet**, and the feedback line confirms *"Slot R01 / SH04 / C01 / SL01 assigned"*. The slot now shows in that line's **Location Dest** column.
4. Repeat: scan the next product, then scan its slot, and so on. (Scan the product **first**, then the slot — scanning a slot with no pending line shows *"No pending line for slot …"*.)
5. Alternatively, click the **Location Dest** cell on a line and pick the slot from the dropdown by name. The dropdown only offers **slot** and **floor** locations — you cannot put stock onto a rack or compartment (those are containers, not storage).
6. Press **Validate & Print**. Stock lands exactly in the slots you chose.

### Option B — Let the system auto-assign (fine for routine stock)

1. Add your product/carton lines and leave **Location Dest blank**.
2. Press **Validate & Print**. For every blank line the system picks a slot using this **priority order**:
   1. A slot or floor zone that **already holds this same product** (keep like with like — "clustering").
   2. Any **empty rack slot**.
   3. Any **empty floor zone**.
   4. As a fallback, **any rack slot** (this mixes products — avoid when you can).
   5. As a last resort, **any floor zone**.
3. Read the slot the system assigned on the finished receipt, and put the stock there.

### Then — the physical step (always)

4. Read the slot name on the finished receipt / on each line.
5. Walk each item to that **exact** slot. The shelf label matches the on-screen name.
6. Place the stock and check the label one more time.
7. If the suggested slot is physically full or clearly wrong, go back and **scan a different empty slot** during the receipt so the record matches reality. Never silently put it somewhere else.
8. To confirm afterwards, open **WMS → Reports → Where is product X?** and check the slot shown matches the real shelf.

---

## Worked Example

You've just received **48 Cow Calcium Bolus** and **1 E2E Hammer** on a Scan Receipt.

- **Calcium (has a home).** There's already calcium living in `R01 / SH04 / C01 / SL01`. You want the new bottles to join it, so during the receipt you scan that slot's label `R01-SH04-C01-SL01`. Feedback: *"Slot R01 / SH04 / C01 / SL01 assigned."* The calcium line's Location Dest now shows that slot. (Even if you'd left it blank, auto-assign rule #1 would have clustered it to the same slot, because that slot already holds calcium.)
- **Hammer (no home yet).** This is a fresh tool with no existing stock anywhere. You leave its Location Dest blank. On Validate, the system applies rule #2 and drops it into the first **empty rack slot**, say `R02 / SH01 / C01 / SL01`.
- After Validate, the receipt shows both destinations. You carry the calcium cartons to `R01 / SH04 / C01 / SL01`, slot them next to the existing bottles, and check the label. You carry the hammer to `R02 / SH01 / C01 / SL01` and check that label too. Done — screen and shed match.

---

## Common Errors & What They Mean

| Message / symptom | What it means | What to do |
|---|---|---|
| **"No pending line for slot …"** (feedback) | You scanned a slot before scanning a product, so there's no line to attach it to. | Scan the **product first**, then its slot. |
| **"No slots or floor zones are set up in warehouse … yet."** (at Validate) | The warehouse has no storage locations for auto-assign to choose. | Ask the Admin to run **Create Rack** or **Generate Floor Zones**. |
| The slot you want isn't in the **Location Dest** dropdown | The dropdown only lists **slot** and **floor** locations. You may be looking at a rack or compartment (a container), not a slot. | Pick the actual slot (its name ends in `… / SL01`), or scan its barcode. |
| Stock auto-assigned to a slot that already holds **a different product** | The warehouse had no empty slot, so the system fell back to rule #4 (any rack slot) and mixed products. | If you have an empty slot, scan it instead so products stay separate. Otherwise tell the Admin you need more slots. |
| Slot label on the shelf doesn't match the screen name | The label is wrong, missing, or on the wrong shelf. | Stop. Don't guess. Ask the Admin to reprint/restick the label, and put the stock where the **system** says. |

---

## Troubleshooting

- **Auto-assign put it somewhere awkward.** Auto-assign is sensible, not psychic. If you'd rather choose, always scan the slot during the receipt (Option A). You can re-run nothing after Validate — instead, the Admin can move stock between slots if it really must change.
- **I want to split one product across two slots.** Add two lines for the same product (scan it twice with the right quantities), and scan a different slot for each line.
- **The compartment is one big slot — where exactly does it go?** Most compartments contain a single slot (`SL01`), so the compartment *is* the slot. Just match the label.
- **It went to a Floor zone, not a rack.** That's normal for bulky items (sacks, drums) or when rack slots were full. Floor zones behave the same as slots for FIFO and counting.
- **After putaway the report shows the wrong place.** That means the stock was physically put somewhere other than the recorded slot. Move it to match the record, or ask the Admin to correct it — never leave the screen and shed disagreeing.

---

## Best Practices

- **Put away immediately after receiving**, one item at a time, scanning the slot as you place it. Don't pile new stock "temporarily" in a corner.
- **Keep like with like.** Send a product to the slot that already holds it. The system tries to do this for you; help it by scanning the home slot.
- **Heavy and liquid items go on lower shelves.** Choose the slot with that in mind.
- **Trust the label, not your memory.** The shelf label is the truth. If it doesn't match the screen, fix the mismatch the same day — never work around it.
- **Don't mix two products in one slot** when an empty slot is available; mixed slots make counting and picking error-prone.
- **Never move stock between slots without telling the system.** Use the slot scan during a receipt, or ask the Admin. Silent moves break every future search and FIFO pick.

---

## Related Help-Center Articles (by slug)

- `workflow-putaway-moving-stock-to-its-spot` — How to do putaway
- `keeper-path-putaway-finding-slots` — Keeper Path 4: Putaway and finding the right slot
- `what-is-putaway` — Putaway (where new stock goes)
- `what-is-a-slot` — Slot
- `what-is-a-compartment` — Compartment
- `what-is-a-rack` — Rack
- `what-is-a-floor-location` — Floor / Open area location
- `workflow-assigning-slots` — How to assign slots
- `faq-where-is-product` — Where is a product?

---

## Narration Script (voiceover for a 2–4 min screen recording)

**[0:00]** "Welcome. This video is about putaway — getting newly received stock into the right slot, and making sure the shelf and the screen agree. In this system there's no separate putaway screen; it happens right inside Scan Receipt."

**[0:18]** "First, let's read a slot code. On screen a slot looks like this: R01 slash SH04 slash C01 slash SL01. That's Rack R01, Shelf 04, Compartment 01, Slot 01 — the exact spot the stock sits. The shelf label uses hyphens for the same address, and that's what your scanner reads."

**[0:45]** "I'm in Scan Receipt with my products already scanned onto the lines. I have two choices for putaway: I can pick the slot myself, or let the system choose."

**[1:00]** "Let's pick it ourselves. The calcium has a home already, so with the cursor in the scan field I scan the shelf label of that slot. The feedback confirms: 'Slot R01 slash SH04 slash C01 slash SL01 assigned.' See the Location Dest column on that line — it's now filled."

**[1:25]** "For the hammer, this is a brand-new tool with no home. I'll leave its Location Dest blank and let the system choose. When I validate, it follows a priority: first, a slot already holding this product; then any empty rack slot; then an empty floor zone; and only as a last resort, a slot that mixes products."

**[1:55]** "I press Validate and Print. The calcium goes exactly where I scanned. The hammer gets auto-assigned to the first empty rack slot. The finished receipt shows both destinations."

**[2:15]** "Now the part people forget — the physical step. I read the slot name, carry the calcium to that exact shelf, place it next to the existing bottles, and check the label matches. Then the hammer to its slot, label checked."

**[2:40]** "If a suggested slot were full or wrong, I'd go back and scan a different empty slot so the record matches reality — never just dump it elsewhere. To double-check, I can open Reports, Where is product X, and confirm the slot. Screen and shed agree. That's putaway."

---

## Recording Checklist (exact click path to perform on camera)

1. Open **WMS → Operations → Scan Receipt** (with one or two product lines already scanned, or scan them live).
2. On screen, point out a **slot display name** like `R01 / SH04 / C01 / SL01` and name each part (Rack / Shelf / Compartment / Slot).
3. **Option A:** click into **"Scan here"**, scan the slot barcode `R01-SH04-C01-SL01`, and show the feedback *"Slot … assigned"* plus the filled **Location Dest** cell.
4. **Option B:** on a second line, leave **Location Dest blank** to demonstrate auto-assign.
5. Click **Validate & Print**.
6. On the finished receipt, point to the **destination slot** of each line (one chosen by you, one auto-assigned).
7. (Physical shot) Walk an item to its slot; show the **shelf label matching** the on-screen name.
8. Open **WMS → Reports → Where is product X?**, search the product, and show it sitting in the expected slot.
