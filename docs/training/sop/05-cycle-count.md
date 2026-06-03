# SOP 05 — Cycle Count & Inventory Audit

*Standard Operating Procedure for the Store Keeper role — Dakshin Vrindavan Cow-Care Trust WMS (Odoo 19)*

---

## Purpose

A **cycle count** is checking that what's physically on a shelf matches what the system says — done slot by slot, a little at a time, instead of one giant yearly stocktake. Counts drift over time: a missed return, a hand-grab nobody logged, a miscount at receiving. Regular counting catches small errors before they grow, so issues and orders are based on reality.

This SOP covers the keeper's three connected tools:

1. **Cycle Count Due** (*Reports*) — a read-only list of every slot that hasn't been counted in **over 30 days**, oldest first. This is your worklist.
2. **Cycle Count** (*Operations*) — Odoo's built-in Inventory Adjustments screen, where you record a counted quantity for a slot and reset its 30-day clock.
3. **Inventory audits** (*Operations*) — the structured, formal walk recorded as a `wms.audit`. The Admin creates an audit and assigns you; you walk the racks, enter a **counted** quantity next to each **expected** quantity, the system highlights **variances**, and you **Submit**. The Admin then **Accepts** (the books are adjusted to match your count) or **Rejects** (you re-walk).

> **Critical integrity rule:** once an Inventory audit is **Submitted**, it is **LOCKED** — its count lines cannot be edited or deleted, even by an Admin or a script. This is intentional: the submitted count is the record of truth. To change anything, the Admin **rejects** the audit and a **fresh** one is walked.

---

## Who Uses It (role + capability group)

- **Role:** Store Keeper (Odoo group `WMS / Store Keeper`, `group_wms_user`).
- **Cycle Count Due** (Reports): readable by any WMS user.
- **Cycle Count** (Operations, Inventory Adjustments): the everyday count screen.
- **Inventory audits** (Operations): requires the *Can submit Inventory audits* capability (`group_wms_can_submit_audit`), ticked on your roster card by the Admin. Without it, the **Inventory audits** menu doesn't appear.
- **Accepting or Rejecting** a submitted audit is **Manager-only** (`group_wms_manager`). A keeper walks and submits; the Admin reviews and applies adjustments.

---

## Prerequisites

1. You can see **WMS → Reports → Cycle Count Due** (any WMS user can).
2. For formal audits, you have the **Can submit Inventory audits** capability, and an Admin has **created an audit and assigned you** as Auditor (or you open one yourself if permitted).
3. Your **name is on the roster** so you can be picked as **On-duty Store Keeper** on the audit (required before you can Submit).
4. No **in-progress Scan Issue** is touching the slot you're about to count — finish or wait for it first, or reserved stock will skew the count.
5. A pen and the physical means to count the shelf accurately.

---

## Step-by-Step Instructions

### Part A — Find what's due (Cycle Count Due)

1. Open **WMS → Reports → Cycle Count Due**.
2. The list shows overdue slots with **Slot | Rack | Last counted | Days since count | On hand | Distinct products**, oldest first. Rows are colour-coded: **blue** > 30 days, **amber** > 60, **red** > 90 days.
3. Pick a few slots to count this session (don't try to do the whole warehouse at once).

### Part B — Quick reconcile one slot (Cycle Count / Inventory Adjustments)

4. Physically go to the slot and **count the stock** there.
5. Open **WMS → Operations → Cycle Count** (this is Odoo's Inventory Adjustments view).
6. Find the slot/product line.
7. If the physical count **matches**, apply/confirm the count — this resets that slot's 30-day clock so it drops off the Due list.
8. If it **differs**, enter the **real counted quantity** so the system updates to match the shelf. Don't adjust a number just to "make the system happy" without actually counting.

### Part C — The formal walk (Inventory audit) — when the Admin asks for one

9. Open **WMS → Operations → Inventory audits** and open the audit the Admin assigned to you (or create one with **New**). It carries an auto-name like **AUDIT/00007**.
10. Check the top fields: **Auditor** (you, defaults to the logged-in user), **On-duty Store Keeper** (pick your roster name — required before Submit), plus the read-only **Started at / Submitted at / Reviewed by / Reviewed at** stamps and a **Summary** (Line Count, Variances).
11. Click **Start audit**. The status moves **Draft → In progress**, and the system **auto-populates the lines** from current stock — one row per slot+product, each showing the **Expected** quantity (what the books say) next to a fresh **Counted** column (starting at 0).
12. Walk the racks. For each line in the **Lines** tab (columns **Slot | Product | Expected | Counted | Variance | Note**): physically count and type the real number into **Counted**. The **Variance** (Counted − Expected) computes live and the row colour-codes — **amber** for any mismatch, **red** for a shortfall (counted less than expected). Use the **Note** column for context ("wrong slot", "damaged units left in place", "expired — moved to trash").
13. Use the **Summary** group to see your running **Variances** count, and the **Notes** tab for an overall comment.
14. When every line is counted, click **Submit**. The status moves **In progress → Submitted**. The system **locks the lines**, posts a variance digest to the Managers, and the audit can no longer be edited.
15. **Stop here — your part is done.** The **Admin** reviews and clicks either **Accept counts** (the system applies the variances as stock adjustments so the books match your count) or **Reject + re-open** (you walk a fresh audit).

> **Audit buttons** (in the header, by state): **Start audit** (draft), **Submit** (in progress), **Accept counts** / **Reject + re-open** (submitted — Manager-only). The status bar shows **Draft → In progress → Submitted → Reviewed**.

---

## Worked Example

The weekly reminder flags the **feed-store floor area** on **Cycle Count Due** (last counted 40 days ago, blue row), and the Admin has also opened a formal **AUDIT/00007** and assigned you.

**Quick reconcile route:**
1. **Reports → Cycle Count Due** shows the feed floor at *Days since count = 40*.
2. You walk over and count **18 sacks** of cattle feed.
3. **Operations → Cycle Count**, find the feed-floor line. The system expected **20**.
4. You enter **18**. The books drop to 18, matching the shed, and the feed floor's 30-day clock resets — it disappears from the Due list. Two sacks of error caught early.

**Formal audit route (when asked):**
1. **Operations → Inventory audits → AUDIT/00007.**
2. **On-duty Store Keeper = Suresh** (your roster name).
3. **Start audit.** Lines auto-fill. One line reads: Slot = *Feed store (floor)*, Product = *Cattle Feed*, **Expected = 20**, **Counted = 0**.
4. You count and type **Counted = 18**. **Variance = −2**, the row turns red. In **Note** you type *"2 sacks short — suspect an unlogged hand-grab."*
5. You also have a line for **Cow Calcium Bolus** in `R01 / SH04 / C01 / SL01`: Expected = 48, you count 48, Variance = 0 (no colour).
6. All lines counted → **Submit**. The audit locks; the Managers get a digest highlighting the −2 feed variance.
7. The Admin opens AUDIT/00007 and clicks **Accept counts**. The system writes the feed quant down to 18; the calcium stays 48. The trail now shows you counted and the Admin approved.

---

## Common Errors & What They Mean

| Message / symptom | What it means | What to do |
|---|---|---|
| **"Pick the on-duty Store Keeper from the roster before submitting…"** | You clicked Submit without choosing the **On-duty Store Keeper**. | Pick your name from the roster (top of the form), then Submit. |
| **"Only an in-progress audit can be submitted. Audit … is currently in …"** | You tried to Submit an audit that isn't in the *In progress* state (e.g. still Draft, or already Submitted). | If it's Draft, click **Start audit** first. If it's already Submitted, you're done. |
| **"Audit … is not in draft. Open a fresh audit to re-walk the warehouse."** | You clicked **Start audit** on an audit that has already moved past Draft. | Don't restart it. If counts are wrong, the Admin rejects it and a new audit is created. |
| **"Cannot delete audit line(s) on a submitted or reviewed audit — the count of record is immutable once submitted."** | You (or a script) tried to delete a line after Submit. | This is intentional. Ask the Admin to **Reject** the audit; you then re-walk a fresh one. |
| **"Only a submitted audit can be reviewed."** / **"Only a submitted audit can be rejected."** | An Accept/Reject was attempted on an audit that isn't Submitted. | Only act on audits in the *Submitted* state. (These are Manager actions.) |
| The **Accept counts / Reject** buttons aren't visible to you | Those are **Manager-only**. | Submit and hand off; the Admin reviews. |
| A count looks wrong because stock is **reserved** | An in-progress Scan Issue has claimed some units. | Finish/await that issue, then count. |

---

## Troubleshooting

- **I submitted with a wrong count.** You can't edit a submitted audit — that's the integrity guarantee. Ask the Admin to **Reject + re-open**; the system creates a fresh audit for you to walk again.
- **A slot is still on the Due list after I counted it.** The quick **Cycle Count** apply (Part B) resets the clock; a *formal audit* count only updates the books once the **Admin accepts** it. If you used the audit route, the slot's clock resets when the adjustment is applied on Accept.
- **The audit auto-filled hundreds of lines.** It snapshots every internal slot+product with stock. Count steadily; the Summary's Line Count tells you the total. For routine maintenance, prefer the **Cycle Count Due** list + quick reconcile rather than a full audit.
- **Variance is huge / negative on many lines.** Re-count before submitting — a systematic error (counting the wrong slot, or counting mid-issue) is more likely than the whole shed being wrong. Use the Note column to explain real discrepancies.
- **I can't find the Inventory audits menu.** You lack the *Can submit Inventory audits* capability. Ask the Admin to tick it on your roster card.
- **Should I count a slot while someone is issuing from it?** No — finish or wait for any in-progress Scan Issue first, or the reserved/in-flight units will make the count look wrong.

---

## Best Practices

- **Count a few overdue slots each week**, not the whole store at once. Each count resets that slot's 30-day clock, so the Due list stays short and manageable.
- **Count honestly, then enter the real number.** Never adjust a figure to match the system without physically counting — that hides the real problem.
- **Use the Note column.** "2 sacks short — suspect unlogged grab" tells the Admin far more than a bare variance number.
- **Don't count mid-issue.** Reserved stock skews the count; wait for in-flight issues to finish.
- **Treat Submit as final.** Re-check your counts before you click it — a submitted audit is locked and can only be undone by a Manager rejecting it.
- **Check Damage/Repair before panicking at a shortfall.** Missing units may simply be held in the Damage or Repair area, which no longer counts as usable on-hand.
- **Make it routine.** Pair the weekly cycle-count session with the weekly review of Low stock and Expiry alerts.

---

## Related Help-Center Articles (by slug)

- `workflow-cycle-count-checking` — How to do an inventory / cycle-count check
- `keeper-path-stock-adjustments-audits` — Keeper Path 9: Stock adjustments and audits
- `what-is-cycle-count` — Cycle count and Inventory audit
- `why-audit-locked-after-submit` — Why an audit is locked after Submit
- `what-is-audit-trail` — Audit trail
- `what-is-on-hand` — On-hand quantity
- `what-is-reserved-quantity` — Reserved quantity
- `why-is-this-action-blocked` — Why an action is blocked
- `safety-never-delete-archive` — Never delete, archive instead

---

## Narration Script (voiceover for a 2–4 min screen recording)

**[0:00]** "Hi. In this video we'll do a cycle count — checking that what's on the shelf matches what the system says — and then a formal Inventory audit. Counts drift over time, and regular checks keep our records honest."

**[0:18]** "I start in WMS, Reports, Cycle Count Due. This lists every slot not counted in over thirty days, oldest first. The colours show how overdue — blue, then amber, then red. Today the feed-store floor is flagged at forty days."

**[0:40]** "First, the quick route. I walk to the feed floor and physically count — eighteen sacks. Then I open WMS, Operations, Cycle Count — that's Odoo's Inventory Adjustments. I find the feed line; the system expected twenty. I enter eighteen, and now the books match the shed. That slot's thirty-day clock resets and it drops off the Due list."

**[1:10]** "Now the formal version, when the Admin asks for it. WMS, Operations, Inventory audits. The Admin created AUDIT-double-oh-seven and assigned me. First I pick myself as On-duty Store Keeper — that's required before I can submit."

**[1:32]** "I click Start audit. The status goes from Draft to In progress, and the system fills in a line for every slot and product, each showing the Expected quantity next to a Counted column."

**[1:52]** "I walk the racks. For the feed line, Expected is twenty; I counted eighteen, so I type eighteen. The Variance shows minus two and the row turns red. In the Note I write 'two sacks short, suspect an unlogged hand-grab'. For the calcium, Expected forty-eight, I count forty-eight, variance zero."

**[2:20]** "When every line is counted, I click Submit. And here's the important part: the moment I submit, this audit is locked. The lines cannot be edited or deleted by anyone — not even an Admin. That's deliberate; the submitted count is the record of truth."

**[2:42]** "The Managers get a digest of the variances. From here it's the Admin's job: they click Accept counts, and the system adjusts the books to match my count — or they Reject, and I walk a fresh audit. To fix a mistake, we never edit; we reject and re-count."

**[3:02]** "So: use the Due list to find stale slots, reconcile small ones quickly, and run a formal audit when asked — counting honestly, because Submit is final. Done."

---

## Recording Checklist (exact click path to perform on camera)

1. Open **WMS → Reports → Cycle Count Due**; point to **Days since count** and the colour-coded rows.
2. Open **WMS → Operations → Cycle Count** (Inventory Adjustments); find a slot line and enter a **counted quantity** to reconcile it.
3. Open **WMS → Operations → Inventory audits**; open the assigned audit (e.g. **AUDIT/00007**).
4. Set **On-duty Store Keeper** to your roster name.
5. Click **Start audit**; show the status bar move **Draft → In progress** and the **auto-populated lines**.
6. On a line, type a **Counted** value that differs from **Expected**; show the **Variance** turning red and add a **Note**.
7. On another line, type a matching **Counted** value (variance 0).
8. Click **Submit**; show the status move to **Submitted**.
9. Demonstrate the **lock**: try to edit/delete a submitted line and show it's blocked (the immutability message), or simply narrate that the lines are now read-only.
10. (Manager shot, if available) Show the Admin's **Accept counts** / **Reject + re-open** buttons on the submitted audit.
