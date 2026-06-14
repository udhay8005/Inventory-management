# SOP 03 — Issuing Stock the FIFO Way (Scan Issue)

*Standard Operating Procedure for the Store Keeper role — Dakshin Vrindavan Cow-Care Trust WMS (Odoo 19)*

---

## Purpose

Use **Scan Issue** whenever stock leaves the store **for use**. Because the trust uses inventory itself and never sells, this is how feed goes to the shed, medicine goes to a calf, ghee goes to the pooja room, and a tool goes out to a job. You scan the product and say how many you need; the system **plans the pick for you** and shows the exact slot(s) to take from **before** anything moves.

The picking rule is automatic and simple — it is the **same for every product**, perishable or not:

- **FIFO — First In, First Out:** stock leaves **oldest-arrived first** (by in-date), across all slots, so nothing rots forgotten at the back. This applies to **everything** — tools, feed, medicine, fluid, pooja items, all of it.

There is no separate "expiry-sorted" picking at the Scan Issue picker. A single Scan Issue is for **one product**, and expiry is tracked **per product** (not per physical batch), so within an issue there is nothing to expiry-sort against — oldest-arrived *is* the rule.

To stop medicine or feed expiring on the shelf, you don't rely on the issue wizard — you use the **Expiry Alerts** report (WMS → Reports → Expiry alerts). It lists items by soonest expiry (red = expired, amber = within 30 days, blue = within 90 days) so you can deliberately go and issue or rotate the soonest-to-expire stock first. See SOP 10.

Issuing is the heart of the audit trail. Every issue records **who took it, who authorised it, which keeper was on duty, and why** — so usage can be checked against the monthly cow-care plan. That is also why a **photo is required** for measured items (liquids and weighed goods): proof of the amount actually dispensed.

---

## Who Uses It (role + capability group)

- **Role:** Store Keeper (Odoo group `WMS / Store Keeper`, `group_wms_user`).
- **Capability required:** *Can Scan Issue* (`group_wms_can_scan_issue`). The Admin ticks this on your roster card under **Configuration → Store Keepers**.
- Without this capability, the **Scan Issue (FIFO)** menu does not appear for you.
- **WMS Manager** (Admin) inherits the capability and can also issue.

---

## Prerequisites

1. You can run **Scan Issue** (have the *Can Scan Issue* capability).
2. The product exists with a **barcode**, and there is **stock on hand** somewhere in the warehouse. (If not, you'll see a STOCK OUT message and cannot issue.)
3. Your **name is on the roster** so it appears in *Store Keeper on duty*.
4. You know **who is taking** the stock and **who authorised** it — both are required.
5. You have a **camera/phone** ready **if** the product is measured by weight or volume (e.g. litres of ghee, kilograms of feed) — a photo is mandatory for those.
6. A destination is set. By default it is the trust's **"Trust internal use"** location (the trust consumes stock internally). The Admin can pick another internal location (Cow Shed, Pooja Room, etc.) for the day.

---

## Step-by-Step Instructions

Open the wizard: **WMS → Operations → Scan Issue (FIFO)**. It opens as a pop-up titled **Scan Issue (FIFO)**.

1. **Read the blue banner:** *"Set qty, then scan. FIFO pulls the oldest stock first across all slots. Scan a carton barcode to use its preset count."* The order matters: set the quantity **first**, then scan.

2. **Confirm warehouse and destination.** Top row: the **warehouse** (defaults correctly) and the **destination** location. The destination defaults to **Trust internal use**. Change it only if this issue genuinely goes somewhere specific the Admin has set up.

3. **Set "Requested Qty".** This field defaults to **1.00**. Type how many you need (e.g. `5`). If you then scan a **carton** barcode, the requested quantity is multiplied by the carton's preset count.

4. **Scan into "Last Scan".** This input carries the placeholder *"Scan product / carton..."* and holds the cursor. Scan the product (or carton). The system immediately builds a **plan**.

5. **Read the plan in the lines table.** Columns are **Product | Slot | In Date | Expires | Available | Take**:
   - **Slot** — the exact location to pick from.
   - **In Date** — when that stock arrived (the FIFO key — this is what the pick order is based on).
   - **Expires** — the product's expiry date, shown **for awareness only**; it is **colour-flagged** (red within ~30 days, amber within ~90) so near-expiry stock stands out. It does **not** change the pick order — that's always oldest-arrived first. Use the Expiry Alerts report to act on it.
   - **Available** — free quantity in that slot (on-hand minus reserved).
   - **Take** — how many the plan will pull from that slot.
   The grey **feedback** line summarises the plan, e.g. *"Planned 5 × Cow Calcium Bolus across 1 slot(s) — oldest stock first."* The plan may cross **several slots** for one product when the oldest slot can't cover the whole quantity — that's correct.

6. **Check the "Short qty" field.** If the warehouse can't fully supply your request, this shows the shortfall and the feedback warns **"STOCK OUT"** or **"only N on hand"**. **The Validate button disappears while there is a shortfall** — you cannot over-issue. Reduce the quantity, or stop and tell the Admin to buy/await a return.

7. **Attach the "Item photo" if required.** The label shows a red **"* required"** marker when the product is **measured by weight or volume** (its unit isn't a simple count — litres, kg, m³, etc.). On a phone/tablet the upload opens the camera directly. For plain counted items (a hammer, a bottle) the photo is optional but still allowed.

8. **Fill the AUDIT TRAIL block — all four are mandatory:**
   - **Taken by** — name of the person physically carrying the items away (worker, department lead, visitor).
   - **Ordered by** — name of the person who authorised the issue (Manager / cow-care lead / project owner).
   - **Store Keeper on duty** — pick *your* name from the roster (the human at the desk now). You cannot create one here; if it's missing, ask the Admin.
   - **Reason / usage note** — a short free-text explanation of **why**, e.g. *"morning feed for shed B"*, *"replacing broken pump"*, *"monthly vaccination round for calves"*. This is **required** — there is no issue without an explanation.

   **Optionally, also pick "Issued for"** — a separate category dropdown (Cows / Gaushala, Pooja / Temple, Maintenance / Repairs, Project / Construction, Administration / Office, Other). It defaults to **Other** and is **not required**, but setting it correctly lets the Consumption Value report break spend down by purpose (e.g. "how much did Cows cost vs Pooja last month").

9. **Press "Validate".** The system reserves the planned stock, double-checks nobody else grabbed it first, removes it from the slots, records the audit details (and attaches the photo if present), and opens the resulting delivery record. The reason is also written to the delivery's note and history.

> **Buttons on this form:** **Plan FIFO** (re-run the plan for whatever is in the scan box — normally the scan does this automatically), **Validate** (finish the issue; hidden when short), **Cancel** (discard).

> **Double-click safety:** once an issue is validated, clicking Validate again (or refreshing) just **re-opens the delivery already made** — it will **not** issue the stock twice.

> **Overuse limits:** some products have an Admin-set **Max per issue** and/or a **24-hour daily cap**. If your request would breach one, Validate is blocked with a clear message naming the limit (see Common Errors).

---

## Worked Example

A vet needs **5 Cow Calcium Bolus** for a calf vaccination round.

**First, a quick rotation check (do this before you issue perishables).** Open **WMS → Reports → Expiry alerts**. Cow Calcium Bolus shows up with the **soonest-expiring stock at the top** — say it's the stock that arrived earliest and is now closest to its expiry date, flagged amber (within 90 days). That tells you the stock to clear first. Good news: because that's also the **oldest-arrived** stock, plain FIFO at the issue picker will pull it for you. (If the report ever showed a *newer* arrival expiring sooner than an older one, you'd issue the soonest-to-expire deliberately — but for one product tracked at one expiry date, oldest-arrived and soonest-to-expire are the same stock.)

Now the issue:

1. **WMS → Operations → Scan Issue (FIFO).**
2. Warehouse defaults; destination stays **Trust internal use**.
3. **Requested Qty = 5.**
4. Scan the **Cow Calcium Bolus** barcode.
5. The system plans the pick **oldest-arrived first (FIFO)**. The plan shows it pulling from the slot holding the oldest calcium stock — say `R01 / SH04 / C01 / SL01`. The **Expires** cell on that row is colour-flagged (amber/red) **for awareness**, but it isn't what chose the slot — the **In Date** is. Feedback: *"Planned 5 × Cow Calcium Bolus across 1 slot(s) — oldest stock first."* **Short qty = 0**, so the **Validate** button is showing.
6. Calcium boluses are counted in **units**, so **no photo is required** (the "* required" marker is absent). (Contrast: if this were 5 litres of ghee, the photo would be mandatory.)
7. AUDIT TRAIL: **Taken by = "Dr Rao"**; **Ordered by = "Farm lead"**; **Store Keeper on duty = Suresh** (your roster name); **Reason = "monthly vaccination round for calves"**. Optional **Issued for = "Cows / Gaushala"** so the Consumption Value report attributes this spend to the herd.
8. **Validate.** Five bottles leave the oldest slot; the delivery opens showing the move and your audit note.
9. You hand Dr Rao exactly the five bottles the plan named — from the oldest slot, not whichever was nearest. Because you checked the Expiry Alerts report first, you also know this is the stock that most needed clearing.

*Tool example:* issuing **1 E2E Hammer** for a fence repair works exactly the same way — plain **FIFO** (a hammer has no expiry, and there's no Expiry Alerts entry to check), needs **no photo** (it's a counted item), and you'd type a reason like *"fence repair, north paddock"*. Remember a hammer is **returnable** — when the job is done, bring it back via Scan Return (SOP 04).

---

## Common Errors & What They Mean

| Message / symptom | What it means | What to do |
|---|---|---|
| **"Scan a product barcode before planning the issue."** | You pressed Plan/Validate with nothing scanned. | Set the qty, then scan the product. |
| **"That barcode isn't linked to any product…"** | The scanned code isn't a known product/carton/lot. | Check the label; if it's genuinely new, ask the Admin to set it up. |
| Feedback: **"⚠ STOCK OUT — no … available anywhere"** and **Validate is hidden** | There is none of this product on hand in the whole warehouse. | Don't part-issue. Tell the Admin to receive more, or wait for a Scan Return. |
| Feedback: **"⚠ Only N × … on hand … that's M less than you asked for"**; **Short qty > 0**; Validate hidden | The warehouse can't fully cover your request. | Reduce **Requested Qty** to what's available and re-scan, or wait for stock. |
| **"This product is measured by weight or volume. Take a photo…"** | You tried to Validate a measured item without a photo. | Snap the **Item photo** of what you're dispensing, then Validate. |
| **"You asked for more … than is allowed in a single issue…"** | Your quantity exceeds the product's **Max per issue** cap. | Ask for less, split into separate issues, or ask a Manager to change the cap. |
| **"You've reached the daily limit for …"** | The rolling 24-hour total for this product would exceed its **Daily cap**. | Wait a few hours, or ask a Manager to raise the daily cap. |
| **"Another keeper took some of this stock while you were finishing up…"** | Someone else issued the same stock between your plan and your Validate. **Nothing was issued.** | Re-scan to plan against what's actually left, then Validate. |
| *Taken by / Ordered by / Reason* show required outlines | One of the mandatory audit fields is blank. | Fill all four: Taken by, Ordered by, Store Keeper on duty, and the Reason. |

---

## Troubleshooting

- **The plan pulled from a slot that isn't the closest / isn't the one I expected.** That's deliberate — it's the **oldest-arrived** stock (FIFO). Pick from the slot the plan names, not the convenient one, or you break rotation.
- **The plan crossed two different slots for one product.** Normal under FIFO when the oldest slot can't cover the whole quantity — it tops up from the next-oldest slot. Pick from each slot the plan lists, in order.
- **I can't see the Validate button.** There's a shortfall (**Short qty > 0**) — the button is intentionally hidden. Reduce the quantity to what's available, or wait for more stock.
- **A slot the plan named is actually empty on the shelf.** Don't force it. Cancel, do a quick count, and if the shelf truly differs from the system, flag it for a cycle count (SOP 05). Issuing against phantom stock corrupts the records.
- **The camera didn't open on my phone.** Use the file picker that appears and select a photo; or take the photo in your camera app first and upload it.
- **I clicked Validate twice.** No harm — the second click just re-opens the delivery already made; stock isn't doubled.
- **I issued the wrong amount / wrong item.** You cannot "un-issue" from this wizard. If it was a returnable item, it can come back via **Scan Return**. Otherwise tell the Admin so it can be corrected through a proper adjustment.

---

## Best Practices

- **Issue at the moment of handover**, never "log it later from memory". Memory issues are how counts drift.
- **Trust the plan.** The system already knows the oldest-arrived stock. Don't second-guess it by grabbing from another slot.
- **Never part-issue during a stock-out.** The system refuses on purpose so you escalate to the Admin instead of quietly half-filling a request.
- **Write a real reason.** "morning feed for shed B" is useful; "stuff" is not. The reason is what reconciles usage against the cow-care plan.
- **Pick your own name** as Store Keeper on duty — the human actually at the desk.
- **For medicine and perishables, run the Expiry Alerts report regularly** (WMS → Reports → Expiry alerts) and rotate the soonest-to-expire stock to the front. The Scan Issue picker always pulls oldest-arrived; the report is what tells you *which* perishables are getting close, so you can clear them before they spoil. The **Expires** column on the issue plan is just an at-a-glance flag, not the picking rule.
- **Photograph measured items honestly** — frame the actual amount dispensed (the jug, the weighed bag). It's the trust's proof.

---

## Related Help-Center Articles (by slug)

- `workflow-fifo-issuing` — How to issue stock (Scan Issue, FIFO)
- `keeper-path-issuing-fifo` — Keeper Path 5: Issuing stock the FIFO way
- `what-is-scan-issue` — Scan Issue (taking stock out)
- `what-is-fifo` — FIFO — First In, First Out (the issue picking rule)
- `what-is-fefo` — FEFO — First Expiry, First Out (the principle; at this trust it's applied via the Expiry Alerts report, not the issue picker)
- `faq-fifo-vs-fefo` — FIFO vs FEFO
- `stock-out-message` — What the STOCK OUT message means
- `why-photo-required-on-issue` — Why a photo is required on issue
- `issue-blocked-daily-limit` — Issue blocked by the daily limit
- `why-record-who-took-stock` — Why we record who took stock
- `safety-double-check-fefo-medicine` — Rotate medicine by expiry: use the Expiry Alerts report

---

## Narration Script (voiceover for a 2–4 min screen recording)

**[0:00]** "Hi. In this video we'll take stock out of the store using Scan Issue. Since the trust uses its inventory and never sells, this is how feed, medicine, and tools leave for the cows, the pooja room, or a job — with full accountability."

**[0:18]** "From the WMS menu I open Operations, then Scan Issue, FIFO. Read the blue banner: set the quantity first, then scan. FIFO pulls the oldest stock first across all slots."

**[0:35]** "Our vet needs five calcium boluses for a vaccination round. Because calcium is a perishable, I first take a quick look at Reports, Expiry alerts — it lists products by soonest expiry, so I can see which stock to clear first. The calcium that arrived earliest is closest to expiry. That's good: it's also the oldest stock, so plain FIFO at the issue picker will pull exactly that for me."

**[0:48]** "Back to Operations, Scan Issue. The warehouse defaults are fine, and the destination is Trust internal use. I set Requested Qty to five."

**[0:55]** "Now I scan the calcium barcode. Instantly the system builds a plan in the table — Product, Slot, In Date, Expires, Available, and Take. The pick is oldest-arrived first — that's FIFO, and it's the same rule for every product. The In Date column is what chose the slot. The Expires cell is colour-flagged so near-expiry stock stands out, but it's just for awareness — it isn't what picked the slot."

**[1:25]** "I check the Short qty field — it's zero, so there's enough, and the Validate button is showing. If we were short, that button would disappear on purpose, so I could never over-issue."

**[1:45]** "Calcium is counted in units, so no photo is required — there's no 'required' marker on Item photo. If this were litres of ghee or kilos of feed, a photo would be mandatory, and on a phone the camera would open right here."

**[2:05]** "Now the audit trail, and all four are required. Taken by — Doctor Rao. Ordered by — the farm lead. Store Keeper on duty — that's me, I pick my name from the roster. And the Reason — 'monthly vaccination round for calves'. No issue goes through without that explanation. I'll also pick 'Issued for — Cows / Gaushala' from the optional category dropdown so the Consumption Value report attributes this to the herd."

**[2:35]** "I press Validate. The five bottles leave the oldest slot, the delivery record opens, and my audit note is saved. I hand over exactly the five bottles the plan named — from the oldest slot, not whichever was nearest. And because I checked Expiry alerts first, I know this is the stock that most needed clearing."

**[2:55]** "And that's a FIFO issue. The system pulled the oldest stock, blocked any over-issue, and recorded who, why, and which keeper. For perishables, remember the rhythm: check Expiry alerts to see what's getting close, then issue — the picker handles the oldest-first part. And if this had been a tool, remember to bring it back later with Scan Return."

---

## Recording Checklist (exact click path to perform on camera)

1. (Perishable preliminary) Open **WMS → Reports → Expiry alerts**; show calcium near the top, soonest-expiry first; note this is the stock to clear, and that it's also the oldest-arrived.
2. Open **WMS → Operations → Scan Issue (FIFO)**.
3. Point at the **blue banner**; read "set qty, then scan".
4. Show **warehouse** and **destination** (Trust internal use).
5. Set **Requested Qty = 5**.
6. Click into **"Last Scan"** and scan **Cow Calcium Bolus**.
7. On the plan table, point to **Slot**, **In Date** (the pick key), the colour-flagged **Expires** cell (awareness only), **Available**, and **Take**; read the **"oldest stock first"** feedback line.
8. Show **Short qty = 0** and that the **Validate** button is present.
9. Note the **Item photo** label has **no "* required"** marker (counted item).
10. Fill **Taken by**, **Ordered by**, **Store Keeper on duty** (roster name), and the **Reason / usage note**. Optionally set **Issued for** (e.g. *Cows / Gaushala*) so the Consumption Value report can break spend down by purpose.
11. Click **Validate**.
12. Show the resulting **delivery form** with the move and the audit note in its history.
13. (Optional contrast shot) Scan a measured item (e.g. ghee in litres) to show the **"* required"** photo marker appearing; or attempt an over-quantity to show the **Validate** button vanishing with a STOCK OUT message.
