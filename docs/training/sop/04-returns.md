# SOP 04 — Taking Reusable Items Back (Scan Return)

*Standard Operating Procedure for the Store Keeper role — Dakshin Vrindavan Cow-Care Trust WMS (Odoo 19)*

---

## Purpose

Use **Scan Return** when something that left the store comes back **unused and reusable** — a tool borrowed for a job, a spare part that wasn't needed, raw material or cloth brought back. It puts the stock back on a shelf and makes it available to the next person.

Scan Return is **the same screen as Scan Receipt**, opened with **Return entry** already switched on (you'll see an **amber** banner instead of the blue one). The one big difference: **only products flagged as *Returnable* can be received this way.** Things that get used up — fluids, consumables, feed, medicine, ghee/pooja items, cement, soap — are **not** returnable and the system will **refuse them at Validate**. Once those leave the gate they are spent, contaminated, or impossible to reseal; if such an item is spoiled, it goes through the **Damages** workflow, not Return.

Returns keep your counts truthful. If a tool leaves and comes back but nobody records the return, the system still thinks it's out and may tell people it's unavailable.

---

## Who Uses It (role + capability group)

- **Role:** Store Keeper (Odoo group `WMS / Store Keeper`, `group_wms_user`).
- **Capability required:** *Can Scan Receipt / Return* (`group_wms_can_scan_receive`) — the same capability as receiving. (Scan Return is the Scan Receipt wizard in return mode.)
- Without this capability, the **Scan Return** menu does not appear.
- **WMS Manager** (Admin) inherits the capability and can also process returns.

---

## Prerequisites

1. You can run **Scan Return** (have the *Can Scan Receipt / Return* capability).
2. The item is **physically back** and **in good condition** (inspect it — if it's broken, use Damages instead).
3. The item is a **Returnable** kind. Returnable by default: **tools, spares, raw materials, packaging, finished goods, work-in-progress, textiles/cloth, safety gear**. NOT returnable by default: **fluids, consumables, medicine, feed, sanitation/soap, construction, plumbing, electrical, stationery, pooja items**. (The Admin sets the *Returnable* flag from a product's **WMS Kind**; they can override it per product.)
4. Your **name is on the roster** so it appears in *Store Keeper on duty*.
5. A slot exists to receive it back into (usually its original home slot).

---

## Step-by-Step Instructions

Open the wizard: **WMS → Operations → Scan Return**. It opens as a pop-up titled **Scan Receipt** with **Return entry** turned on.

1. **Read the amber banner:** *"Return entry mode. Stock is being received back from production / a customer / an internal location. Only products flagged as Returnable can be received this way; fluids and consumables will be refused at Validate."* The amber colour is your cue you're in return mode, not a normal receipt.

2. **Confirm the *Return entry* toggle is ON.** It is pre-set because you opened the **Scan Return** menu. (If it's off, you're in a normal receipt — close and reopen via Scan Return, or switch the toggle on.)

3. **Confirm warehouse.** Top-left; defaults correctly.

4. **Scan into the "Scan here" field** (placeholder *"Scan product, carton, or slot..."*; cursor is already there). Scan each item coming back. A line is added to the **Product | Quantity | Location Dest** table, and the grey **feedback** confirms it (e.g. *"Added 1 × E2E Hammer"*).

5. **Choose where it goes back (optional).** In **Location Dest**, pick the slot, or **scan the slot barcode** (e.g. `R02-SH01-C01-SL01`) — ideally the item's original home so the next person finds it where they expect. Leave it blank to let the system auto-assign.

6. **Complete the QUALITY CHECK block.** Tick **Quality check passed** only after you've confirmed the returning item is in good condition. This tick is **mandatory** — Validate is blocked without it. Note anything in **QC notes** (placeholder *"Anything unusual? (optional)"*).

7. **Complete the AUDIT TRAIL block.**
   - **Store Keeper on duty** — **required**. Pick your name from the roster.
   - **Delivered by** — optional; the person bringing the item back.

8. **Press "Validate & Print".** The system checks every line is a **Returnable** product. If all pass, the stock is added back into its slot and the return is logged with your audit details, then the record opens.

> **If any line is NOT returnable**, Validate is **rejected** with a message listing exactly which products failed and their kind — nothing is received. See Common Errors.

> **Buttons on this form:** **Process scan**, **Validate & Print**, **Cancel** — identical to Scan Receipt.

> **Double-click safety:** once validated, clicking again just re-opens the return already made; stock isn't doubled.

---

## Worked Example

A helper borrowed an **E2E Hammer** (kind TOOL — returnable) for a fence repair and brings it back clean and undamaged.

1. **WMS → Operations → Scan Return.**
2. The **amber** banner is showing; **Return entry** is ON.
3. Warehouse defaults correctly.
4. You scan the **E2E Hammer** barcode → feedback: *"Added 1 × E2E Hammer"*.
5. You scan the hammer's home slot label `R02-SH01-C01-SL01` so it goes back where the next person looks → *"Slot R02 / SH01 / C01 / SL01 assigned"*.
6. You inspect the hammer — no damage — and tick **Quality check passed**. QC notes: *"Returned clean, no damage."*
7. AUDIT TRAIL: **Store Keeper on duty = Suresh**; **Delivered by = "Mani (fencing helper)"**.
8. **Validate & Print.** The hammer is back in stock in `R02 / SH01 / C01 / SL01`; the next person can issue it.

*Counter-example (refused):* a helper tries to "return" 2 litres of leftover **ghee** (kind POOJA — not returnable). They scan it, tick QC, and click Validate. The system **refuses**: *"These products cannot be received as a return — they are flagged not-returnable on the product form (fluids, consumables, single-use items): • Ghee (kind: Pooja items …)."* Nothing is received. Because the ghee is genuinely spoiled, they file it through **Damages** instead.

---

## Common Errors & What They Mean

| Message / symptom | What it means | What to do |
|---|---|---|
| **"These products cannot be received as a return — they are flagged not-returnable…"** (lists the products + kind) | One or more scanned items are non-returnable (fluid, consumable, medicine, feed, pooja, etc.). **Nothing was received.** | Remove those lines and return only returnable items. For spoiled/used non-returnables, use **Damages**. Or ask the Admin to change the product's WMS Kind / Returnable flag if it really is reusable. |
| **"Mark 'Quality check passed' first…"** | You clicked Validate without ticking QC. | Inspect the item, then tick **Quality check passed**. |
| **"No lines to receive."** | You clicked Validate with an empty table. | Scan the returning item first. |
| *Store Keeper on duty* shows a required outline | The on-duty keeper is blank. | Pick your name from the roster. |
| **"Unknown barcode: …"** (feedback) | The scanned code isn't a known product. | Check the label; ask the Admin if the item isn't set up. |
| Banner is **blue**, not amber | You're in a normal receipt, not return mode. | Switch **Return entry** ON, or close and reopen via **Scan Return**. |

---

## Troubleshooting

- **The wizard refused my whole return.** It only blocks the **non-returnable** lines — but it refuses the *entire* Validate until they're gone, so remove those lines (trash icon) and Validate the returnable ones. The message names exactly which products failed.
- **An item I think is reusable was refused.** Its WMS Kind defaults to non-returnable (e.g. a raw material the supplier actually takes back). Only the **Admin** can flip the *Returnable* flag on that product. Ask them; don't force it.
- **The returned item is actually damaged.** Stop. Don't return it as if it were fine. Close Scan Return and file a **Damage** (SOP — Damages) so it's pulled out of usable stock.
- **Wrong return slot.** Scan the correct slot barcode again (it reassigns the most recent line without a destination), or set the **Location Dest** cell before validating.
- **I returned it to the wrong slot and already validated.** Tell the Admin so the stock can be moved to its proper slot; don't physically move it without recording the change.
- **It's the same screen as receiving — am I in the right mode?** Check the **banner colour**: amber = return, blue = receipt. The toggle at the top also shows Return entry on/off.

---

## Best Practices

- **Inspect before you tick Quality check passed.** A return is a statement that the item is good to reuse. If it isn't, it's a Damage, not a return.
- **Return to the home slot.** Send tools and spares back to the slot they came from so the next person finds them instantly.
- **Scan it back in before shelving it.** Putting a returned item on the shelf without recording the return leaves the system thinking it's still out.
- **Don't try to return consumables.** Feed, medicine, fluids, ghee, soap, cement — once issued, they're gone. The system will refuse them; don't fight it.
- **Record who brought it back** in *Delivered by* — it closes the loop on who had the item.
- **One return entry per genuine return event** keeps the history readable.

---

## Related Help-Center Articles (by slug)

- `workflow-returns` — How to handle returns (Scan Return)
- `keeper-path-returns` — Keeper Path 6: Taking reusable items back
- `what-is-scan-return` — Scan Return (bringing stock back)
- `why-cant-receive-as-return` — Why an item can't be received as a return
- `what-is-damage` — Damage (recording broken or spoiled stock)
- `what-is-scan-receipt` — Scan Receipt (the same screen, receipt mode)
- `what-is-audit-trail` — Audit trail
- `what-is-a-storekeeper` — Store Keeper

---

## Narration Script (voiceover for a 2–4 min screen recording)

**[0:00]** "Hello. This video covers Scan Return — putting a reusable item back into the store after it was taken out. Think of a borrowed tool coming home. It's the same screen as Scan Receipt, but in return mode."

**[0:18]** "A helper borrowed this E2E Hammer for a fence repair and has brought it back. First thing I do — physically — is check it's undamaged. It's fine."

**[0:32]** "From the WMS menu I open Operations, then Scan Return. Notice the banner is amber, not blue. That's my signal I'm in return mode, and the Return entry toggle is already on. The amber banner reminds me only Returnable items work here — fluids and consumables get refused."

**[0:55]** "The warehouse is correct. With the cursor in the scan field, I scan the hammer. The feedback says 'Added 1 times E2E Hammer'."

**[1:12]** "I want it back in its home slot so the next person finds it, so I scan that slot's label. The feedback confirms the slot is assigned."

**[1:28]** "Down in the Quality Check block, because I've inspected the hammer and it's in good shape, I tick 'Quality check passed' — the system won't finish without it. In QC notes I write 'returned clean, no damage'."

**[1:48]** "In the Audit Trail block I pick myself as Store Keeper on duty, and under Delivered by I type the helper's name. Then I press Validate and Print. The hammer is back on the shelf and available to issue again."

**[2:10]** "Now let me show what happens with something that can't come back. Suppose someone tries to return leftover ghee — a pooja item, which is consumed. I scan it, tick the box, and press Validate."

**[2:28]** "The system refuses, and it lists exactly which product failed and why — ghee is flagged not-returnable. Nothing is received. Because the ghee is spoiled, it belongs in the Damages workflow, not here."

**[2:48]** "So: tools and spares come back through Scan Return, inspected and scanned to their slot; consumables never do. That keeps the counts honest. Done."

---

## Recording Checklist (exact click path to perform on camera)

1. Open **WMS → Operations → Scan Return**.
2. Point to the **amber banner** and the **Return entry** toggle (ON).
3. Show the **warehouse** field (default).
4. Click into **"Scan here"** and scan the **E2E Hammer** → show *"Added 1 × E2E Hammer"* feedback.
5. Scan the home slot label `R02-SH01-C01-SL01` → show *"Slot … assigned"* and the **Location Dest** cell filled.
6. Tick **Quality check passed**; type a line in **QC notes**.
7. Set **Store Keeper on duty** (roster name) and a **Delivered by** name.
8. Click **Validate & Print**; show the resulting record.
9. **Refusal demo:** start a new Scan Return, scan a **non-returnable** item (e.g. ghee / a fluid), tick QC, set the keeper, click **Validate**, and show the **rejection message** listing the product and its kind. Point out that nothing was received.
