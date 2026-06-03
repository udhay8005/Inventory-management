# SOP 09 — Repair Orders (Fixing a Damaged Item and Returning It to Service)

## Purpose
This procedure explains how to track a damaged-but-fixable item through repair using the **Repair Orders** screen. A repair order walks an item through these states: **Draft → In repair → Done** (or **Scrapped** if it can't be fixed; **Cancelled** while still draft). It generates the internal stock moves automatically:

- **Start Repair** moves the item from the **Damage** location to the **Repair-Out** location.
- **Mark Done** moves it from **Repair-Out** back to a slot (the original, or a chosen return slot) and makes it issuable again.
- **Scrap** writes the item off from Repair-Out using Odoo's native scrap.

Repair orders are for **returnable** things — tools and equipment that survive use.

## Who Uses It
- **Repair Order records** can be *created* from a confirmed damage event by a Store Keeper or a Manager.
- **State transitions** (Start Repair, Mark Done, Scrap, Cancel) require write access and are restricted to the **WMS / Repair Tech** group and **WMS / Manager**. A plain Store Keeper can create and read repair orders but cannot drive them through the stages (those buttons are hidden for them).
- The **Repair Orders** menu itself is **Manager-only** (`group_wms_manager`). A Repair Tech reaches an order via the **Repair** smart button on a damage record, or via a direct link.
- Read-only viewers can see repair orders on reports but cannot change them.

## Prerequisites
- A **confirmed** damage event exists for the item (see SOP 08), or you are a Manager creating a repair order directly.
- The warehouse has both a **Damage** location and a **Repair** (Repair-Out) location configured (created on install by the repair/damage module).
- The three audit-trail names are known (they pre-fill from the linked damage event):
  - **Reported by** — who flagged the item for repair.
  - **Authorised by** — the Manager / cow-care lead who authorised the repair.
  - **Store Keeper on duty** — from the roster.
- A **Technician** (an Odoo user) to assign, if you track who does the work.

## Step-by-Step Instructions

### A. Create the repair order (usually from the damage record)
1. Open the confirmed damage event (**WMS → Operations → Damages**, open the `DMG/0000x` record).
2. Click **Create Repair Order**. A new repair order opens, pre-filled with the product, quantity, original slot, return slot (defaulting to the original), and the three audit-trail names copied from the damage. The damage record now shows a **Repair / Order** smart button linking to it.
   - *(A Manager can also create one directly, but starting from the damage keeps the two records linked.)*

### B. Review the repair order form
The form's **Name** is `REP/0000x`. In the **What & where** group, check/fill:
- **Product** and **Quantity**.
- **Original slot** — where the item came from (default destination after repair).
- **Return slot** — where it goes after repair completes (placeholder "Defaults to original slot").
- **Technician** — the Odoo user doing the work (optional).
- **Damage** — the linked damage event (shown if present).
In the **Who reported it** group, confirm **Reported by**, **Authorised by**, and **Store Keeper on duty** (pre-filled from the damage). Add **Repair notes** at the bottom (placeholder "What was wrong, what was done, parts used...").

### C. Start the repair
3. Click **Start Repair** (visible only in Draft, only to Repair Tech / Manager). The system checks the audit triplet is complete, then moves the item from the **Damage** location to the **Repair-Out** location and validates the transfer. State becomes **In repair**, and the chatter records "Repair started."

### D. Finish or scrap
4a. When the item is fixed, click **Mark Done** (visible only In repair). The system moves it from **Repair-Out** back to the **return slot** (or original slot) and validates. State becomes **Done**; the item is available to issue again; the chatter records "Repair done … Item returned to slot <slot>."
4b. If the item cannot be saved, click **Scrap** (visible only In repair). The system runs a native scrap from Repair-Out, state becomes **Scrapped**, and the chatter records "Scrapped."

### E. Cancel (draft only)
5. To abandon a repair order before any stock has moved, click **Cancel** (visible only in Draft). State becomes **Cancelled**.

You can monitor all orders in **WMS → Operations → Repair Orders**, whose list shows: **Name** (`REP/0000x`), **Product**, **Quantity**, **State**, **Technician**, **Store Keeper on duty**, and **Created on**.

## Worked Example
The cordless drill from SOP 08 needs a new battery.

1. Open the confirmed damage `DMG/00002` for `Cordless Drill 18V`.
2. Click **Create Repair Order** → `REP/00001` opens, pre-filled: Product `Cordless Drill 18V`, Quantity `1`, Original slot = the drill's slot, Return slot = same, and the audit names from the damage.
3. Assign **Technician** = `Workshop User`. Add a repair note: "Battery pack dead; replacing with spare 18V pack."
4. As a Repair Tech (or Manager), click **Start Repair**. The drill moves from the Damage location to Repair-Out; state → **In repair**.
5. The technician swaps the battery. Click **Mark Done**. The drill moves from Repair-Out back to its slot; state → **Done**; the chatter says "Item returned to slot <slot> and is available for issue again."
6. (If the drill had been beyond repair, the tech would have clicked **Scrap** instead, and state would be **Scrapped**.)

## Common Errors & What They Mean
- **"Fill in the audit-trail field(s) before moving this repair order: <list>."** — One of Reported by / Authorised by / Store Keeper on duty is blank. Repair orders can be *drafted* with placeholders but can't move past draft without the triplet.
- **"Damage / Repair locations missing for <warehouse>."** — The warehouse lacks a Damage or Repair-Out location. Ask an Admin to check the repair/damage setup.
- **"No destination slot."** — On Mark Done, neither a return slot nor an original slot is set. Set the return slot.
- **"Only in-repair items can be scrapped."** — You tried to Scrap an order that isn't In repair.
- **"This repair order is already <done/scrapped> — cancelling would orphan the stock moves it generated. Open a new damage event if the item needs to leave service again."** — You can't cancel a finished or scrapped order.
- **"Item is currently at the Repair-Out location. Either finish the repair (Mark Done) or scrap it before cancelling — otherwise the unit stays stuck in Repair-Out with no owner."** — You can't cancel an In-repair order; resolve it via Mark Done or Scrap.
- **The state buttons are missing entirely.** You're a plain Store Keeper (create/read only). Start/Mark Done/Scrap/Cancel are restricted to Repair Tech and Manager.

## Troubleshooting
- **I can see the order but no action buttons.** You lack the **Repair Tech** role (or Manager). Ask an Admin to add you to **WMS / Repair Tech**, or have a Tech/Manager drive the stages.
- **The Repair Orders menu isn't in my WMS app.** The menu is Manager-only. A Repair Tech opens repair orders via the **Repair** smart button on the related damage record.
- **Create Repair Order didn't appear on the damage.** That button only shows on a **confirmed** damage for a repairable item (returnable, or tool/spare with the matching recommendation), and only if no repair order is already linked. If one is linked, click the **Repair / Order** smart button instead.
- **The item didn't come back to the right slot.** Mark Done sends it to the **Return slot** if set, otherwise the **Original slot**. Set the Return slot before clicking Mark Done if it should land somewhere new.
- **I need to re-damage an item after it was repaired.** A Done/Scrapped order can't be reopened. File a fresh damage event (SOP 08) and create a new repair order from it.

## Best Practices
- **Always create the repair order from the confirmed damage**, so the damage and repair records stay linked and the audit names carry across.
- **Record what was done.** Use the **Repair notes** field for the fault and the fix (parts used) — it's the maintenance history for an expensive, donation-funded asset.
- **Assign a Technician** when you track who does the work; it shows on the Repair Orders list and Store Keeper Activity report.
- **Don't leave items stuck In repair.** An item at Repair-Out has no owner until you Mark Done or Scrap it; resolve orders promptly so counts stay honest.
- **Scrap honestly.** If it can't be fixed, scrap it rather than leaving it in limbo — the scrap is recorded and the books stay accurate. See `safety-confirm-before-scrapping`.
- **Repair returnable items, not consumables.** Consumables/fluids that are damaged are written off via the Damage workflow, not repaired.

## Related Help-Center Articles
- `what-is-repair`
- `what-is-damage`
- `workflow-repairs`
- `admin-path-damage-repair-oversight`
- `faq-cannot-cancel-repair`
- `safety-confirm-before-scrapping`
- `why-record-who-took-stock`

## Narration Script
*(Target length ~3 minutes.)*

- **[0:00]** "In this video we'll take a damaged tool through repair and back into service using a Repair Order."
- **[0:14]** "Repair orders are for returnable things — tools and equipment that survive use. We usually start from a confirmed damage record, so the two stay linked."
- **[0:30]** "Here's the confirmed damage for a cordless drill with a dead battery. Because a drill is repairable, there's a Create Repair Order button. I click it."
- **[0:48]** "A new repair order, R-E-P dash zero-zero-zero-zero-one, opens — already filled in with the product, quantity, the slot it came from, the slot it'll return to, and the audit names copied from the damage. I'll assign a Technician and add a note: battery pack dead, replacing with a spare."
- **[1:15]** "Now, as a Repair Tech or Manager, I click Start Repair. The system moves the drill from the Damage location to the Repair-Out location, and the state changes to In repair. The chatter logs that the repair started."
- **[1:40]** "The technician swaps the battery. When it's fixed, I click Mark Done. The system moves the drill from Repair-Out back to its slot, marks the order Done, and notes that it's available to issue again."
- **[2:05]** "If the drill couldn't be saved, I'd click Scrap instead — that writes it off from Repair-Out, and the state becomes Scrapped."
- **[2:25]** "A few rules to remember: you can't move an order past draft until the three audit names are filled; you can't cancel an order once it's In repair, Done, or Scrapped — finish or scrap it instead; and only a Repair Tech or Manager sees these action buttons."
- **[2:48]** "Record what you fixed, return it to the right slot, and resolve orders promptly. Thank you."

## Recording Checklist
1. Open a confirmed damage record for a repairable item (e.g. `Cordless Drill 18V`).
2. Click **Create Repair Order**; show the pre-filled `REP/0000x` form.
3. Point out **Product**, **Quantity**, **Original slot**, **Return slot**, **Technician**, and the audit names.
4. Add a **Repair note**.
5. As Repair Tech / Manager, click **Start Repair**; show state → **In repair** and the chatter entry.
6. Click **Mark Done**; show state → **Done** and the "returned to slot" chatter entry.
7. (Optional, on a separate order) show **Scrap** producing state → **Scrapped**.
8. Open **WMS → Operations → Repair Orders**; show the list columns (Name, Product, Quantity, State, Technician, Store Keeper on duty, Created on).
9. (Optional) Log in as a plain Store Keeper to show the action buttons are hidden.
10. End on the Repair Orders list.
