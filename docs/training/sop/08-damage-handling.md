# SOP 08 — Damage Handling (Recording Broken, Expired, or Contaminated Stock)

## Purpose
This procedure explains how to record stock that is no longer usable — broken, expired, contaminated, or otherwise spoiled — using the **Damages** screen. Filing a damage event and confirming it moves the affected quantity out of normal storage into a separate **Damage** location, so nobody issues it by mistake. The form also gives a plain-English **recommended action** (repair it, urgently buy a replacement, or just note it) based on the product's kind and how much is left elsewhere.

## Who Uses It
- **Store Keepers** with the **"File damage events"** capability (group `group_wms_can_file_damage`), and **WMS Managers** (who hold every capability).
- The **Damages** menu is hidden from any Store Keeper who has not been granted that capability.
- Read-only viewers can see damage records on reports but cannot file or confirm them.
- Creating the follow-on **Repair Order** is covered in SOP 09 (the **Create Repair Order** button appears on a confirmed damage record for repairable items).

## Prerequisites
- You are logged in as a user with the **File damage events** capability (or as a Manager).
- The stock physically exists in a known slot or floor zone, and you have counted how many units are damaged.
- You know the three audit-trail names required to *confirm*:
  - **Reported by** — the worker who found or caused the damage.
  - **Authorised by** — the Manager / cow-care lead who authorised filing it.
  - **Store Keeper on duty** — picked from the roster (the actual human at the desk).
- The warehouse has a **Damage** location configured (created automatically by the repair/damage module on install).

## Step-by-Step Instructions
1. Open **WMS → Operations → Damages**. The list shows columns: **Name** (e.g. `DMG/00001`), **Product**, **Quantity**, **Source Slot**, **Other units on hand**, **Recommended Action**, **State**, and **Created on**.
2. Click **New**. A blank damage form opens; the **Name** fills automatically as `DMG/0000x` on save.
3. In the **What & where** group, fill:
   - **Product** — the damaged product.
   - **Quantity** — how many units are damaged (default `1`).
   - **Source Slot** — the slot or floor zone the stock is in. (You can only pick a slot or floor location.)
   - **Reason** — one of **Broken**, **Expired**, **Contaminated**, or **Other**. If you pick **Other**, you must write an explanatory **Note** at the bottom.
   - (**Warehouse** fills automatically from the slot and is read-only.)
4. In the **Who reported it** group, fill:
   - **Reported by** (placeholder "Worker who found / caused it").
   - **Authorised by** (placeholder "Manager / cow-care lead").
   - **Store Keeper on duty** (pick from the roster).
5. Read the **recommendation block** that appears once a product is chosen. Depending on the product's kind and remaining stock, it shows one of:
   - A red **URGENT BUY** alert — item is gone and can't be repaired.
   - A yellow **Only one — repair needed** alert.
   - A blue **Open a Repair Order** or **Assess: repair or scrap?** alert.
   - A grey **Just a note** alert.
   The **Spare-stock check** group shows **Other units on hand** and a coloured **Recommended Action** badge.
6. If you chose **Other** as the reason (or just want detail), type the explanation in the **Note** field at the bottom (placeholder "Describe what happened...").
7. Click **Confirm** (top-left, primary button). The system:
   - Re-checks that all three audit-trail fields are filled (it blocks confirm if any are missing).
   - Creates an internal transfer moving the quantity from the source slot to the warehouse **Damage** location and validates it.
   - Sets the record's state to **Confirmed**, links the picking, and writes an audit summary into the chatter.
   - If the recommendation is **Urgent buy**, it also pings every WMS Manager via Discuss.
8. If the item is repairable, a **Create Repair Order** button now appears (see SOP 09). Otherwise the damage record is complete.

To cancel a draft you filed by mistake, click **Cancel** (only works while the record is still draft).

## Worked Example
A helper finds a cracked bottle of calcium on the medicine rack.

1. **WMS → Operations → Damages → New**.
2. What & where: Product = `Calcium Bolus`; Quantity = `1`; Source Slot = `R01-SH01-C01-SL01`; Reason = **Broken**.
3. The recommendation block shows a blue **Open a Repair Order**? No — calcium is a consumable medicine, so with other bottles still on hand it shows **Just a note** (or, if it were the last unit and non-repairable, a red **URGENT BUY**). The **Other units on hand** field shows, say, `23`.
4. Who reported it: Reported by = `Ramesh`; Authorised by = `Cow-care lead`; Store Keeper on duty = `Suresh`.
5. Click **Confirm**. The one cracked bottle moves from the rack slot to the Damage location; the record becomes **Confirmed**; the chatter records "Damage confirmed. Reported by Ramesh; authorised by Cow-care lead; Store Keeper on duty: Suresh."

A second example: a cordless drill's battery has failed.
1. New damage: Product = `Cordless Drill 18V`, Quantity = `1`, Source Slot = its slot, Reason = **Broken**.
2. Because a drill is a returnable tool, the recommendation reads **Schedule repair (returnable item, spare available)** (or **…no spare!** if it's the only one). Fill the three audit fields and **Confirm**.
3. The **Create Repair Order** button appears — proceed with SOP 09.

## Common Errors & What They Mean
- **"Fill in the audit-trail field(s) before confirming this damage event: <list>. The trust requires every stock-moving action to record who reported it, who authorised it, and which keeper was on the desk."** — One or more of Reported by / Authorised by / Store Keeper on duty is blank. Fill them and confirm again.
- **"If the damage reason is 'Other', you must write a quick note explaining what happened…"** — Reason is **Other** but the Note is empty. Add the note (or pick a specific reason).
- **"You're trying to file N × <product> as damaged at slot <slot>, but only M unit(s) are actually there. Re-count the slot or fix the quantity before confirming."** — The quantity exceeds what's free in that slot. Recount and correct.
- **"Slot <slot> has T × <product>, but R unit(s) are already spoken for by a pending issue that hasn't finished yet. Only F are really free to mark as damaged…"** — Another in-flight Scan Issue has reserved some units. Wait for it to finish or cancel it, or mark fewer units.
- **"No Damage location for warehouse <warehouse>."** — The warehouse has no Damage location configured. Ask an Admin to check the repair/damage setup.
- **"Warehouse <warehouse> is not configured for internal stock transfers. Ask an Administrator to enable internal transfers in the Inventory settings."** — The internal-transfer picking type is missing. An Admin must enable internal transfers.
- **"Cancel the stock transfer that was created for this damage event before cancelling the record."** — You tried to cancel an already-confirmed damage (which moved stock). You must reverse the stock transfer first; a confirmed damage can't simply be cancelled.

## Troubleshooting
- **The Damages menu isn't visible.** You don't have the **File damage events** capability. Ask an Admin to tick it on your Store Keeper roster entry (or your user).
- **"Other units on hand" looks wrong.** It deliberately *excludes* stock already in the Damage and Repair areas, so it shows what's still usable. For a draft record it also subtracts the quantity you're about to damage, so you see what will be left after you confirm.
- **No "Create Repair Order" button after confirming.** That button only appears for repairable items (returnable, or tool/spare with the right recommendation) and only after the damage is confirmed. Consumables that are simply written off won't show it.
- **I confirmed by mistake.** A confirmed damage has already moved stock to the Damage location. Don't try to cancel the record — reverse the stock movement first (ask an Admin), or use the repair/scrap workflow if appropriate.
- **Managers got an alert I didn't expect.** When the recommendation is **Urgent buy** (the last unit of a non-repairable item), every Manager is pinged via Discuss on confirm. That's intentional.

## Best Practices
- **File damage the moment you find it.** Broken or expired stock left on the shelf causes wrong counts and dangerous mistakes (e.g. issuing expired medicine).
- **Count before you type.** Enter the exact damaged quantity; the system blocks over-filing, but accurate counts keep the books clean.
- **Use the right reason.** Broken / Expired / Contaminated are self-explanatory in the audit trail; reserve **Other** for genuinely unusual cases and always add a note.
- **Read the recommendation before acting.** It tells you whether to open a repair, buy urgently, or just note it — and reflects how much usable stock remains.
- **Always name a real on-duty keeper.** Even on a shared login, picking the roster name makes the audit trail point to the actual person.
- **For repairable tools, create the Repair Order from the confirmed damage** (don't start a fresh, unlinked repair) so the two records stay connected.

## Related Help-Center Articles
- `what-is-damage`
- `what-is-repair`
- `workflow-damage-handling`
- `admin-path-damage-repair-oversight`
- `why-is-this-action-blocked`
- `why-is-this-stock-reserved`
- `why-record-who-took-stock`
- `safety-confirm-before-scrapping`

## Narration Script
*(Target length ~3 minutes.)*

- **[0:00]** "In this video we'll record damaged stock — something broken, expired, or contaminated — so it's moved off the shelf and nobody issues it by accident."
- **[0:15]** "Open WMS, Operations, Damages. You'll only see this menu if you've been given the 'File damage events' permission. Click New."
- **[0:30]** "Under What and where, I pick the product — a cracked bottle of Calcium Bolus. Quantity is one. I choose the Source Slot it's sitting in, and a Reason: Broken. If I picked 'Other', I'd have to write a note explaining what happened."
- **[0:55]** "As soon as I pick the product, a recommendation appears. The system checks the product's type and how many other units are on hand, then suggests what to do — repair it, buy urgently, or just note it. Here it tells me there's plenty of calcium left, so it's just a note."
- **[1:20]** "Now the important part — the audit trail. Under Who reported it, I fill Reported by, the worker who found it; Authorised by, the cow-care lead; and Store Keeper on duty, picked from the roster. The system will not let me confirm until all three are filled."
- **[1:45]** "I click Confirm. The system moves that one bottle from the rack slot into the Damage location, marks the record Confirmed, and writes a summary into the chatter at the bottom — who reported it, who authorised it, and which keeper was on duty."
- **[2:10]** "Let's see a repairable example. If this were a cordless drill with a dead battery, the recommendation would say 'Schedule repair', and after I confirm, a 'Create Repair Order' button would appear so I can send it for repair — that's covered in the next video."
- **[2:35]** "One safety note: if I damage the very last unit of something that can't be repaired, the system flags an Urgent Buy and pings every Manager automatically. And once a damage is confirmed, the stock has already moved — you can't just cancel it."
- **[2:55]** "File damage promptly, count carefully, and always name a real keeper. Thank you."

## Recording Checklist
1. Log in as a Store Keeper with the **File damage events** capability (or a Manager).
2. Click **WMS → Operations → Damages**.
3. Show the list columns (Name, Product, Quantity, Source Slot, Other units in stock, Recommended Action, State, Created on).
4. Click **New**.
5. Fill **Product**, **Quantity**, **Source Slot**, **Reason = Broken**.
6. Point out the auto-computed recommendation block and the **Other units on hand** / **Recommended Action** badge.
7. Fill **Reported by**, **Authorised by**, **Store Keeper on duty**.
8. Click **Confirm**; show the state change to **Confirmed** and the chatter audit summary.
9. (Optional) On a repairable product, show the **Create Repair Order** button appearing.
10. Return to the Damages list to show the new `DMG/0000x` row.
