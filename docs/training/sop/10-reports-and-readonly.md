# SOP 10 — Reports and the Read-Only Viewer

## Purpose
This procedure explains the WMS reporting screens — what each one shows and how to read it — for two audiences: the **read-only viewer** (someone who needs to look but not touch) and the **Manager** who reviews the warehouse. It covers Slot occupancy, Movement history, Oldest stock (FIFO), Expiry alerts, Forecasts/Reorder, and the Manager-only Store Keeper Activity audit.

All of these are *read-only outputs* — they reflect live data (scans update them immediately; the AI forecasts are retrained daily by a cron). Looking at a report never changes stock.

## Who Uses It
- **Read-only viewer / Store Keeper** — can open every report under **WMS → Reports** and read it. They cannot edit the underlying data. (Store Keepers get the same read access for their weekly audits.)
- **WMS Manager** — sees everything, plus the **Store Keeper Activity** audit screens and the **Backup & DR Audit** screen (the latter is covered in SOP 11), which are gated by `group_wms_manager`.
- A true "read-only" person is a user in **WMS / Store Keeper** with **no capability switches** ticked: they can log in, browse, and read reports, but the Scan/Damage/Audit menus stay hidden.

## Prerequisites
- You are logged in to the WMS (any WMS role can read reports; the Store Keeper Activity screen needs the Manager role).
- There is stock and history to look at (receipts, issues, products with expiry dates, etc.).
- For Forecasts to be meaningful, the daily retrain cron has run at least once (or you've clicked **Retrain now** on a row).

## Step-by-Step Instructions

### Where the reports live
Open the **WMS** app, then **Reports**. You'll see (Manager view; a read-only viewer sees the same minus the Manager-only items):
- **Warehouse Map**, **Where is product X?**, **Oldest stock (FIFO)**, **Slot occupancy**, **Cycle Count Due**, **Movement history**, **Expiry alerts**, **Low stock alerts**, **Dead stock**, **Reorder summary**, **Tool / Spare fleet**, **Store Keeper Activity** *(Manager-only)* with **Weekly / Monthly / Yearly** shortcuts, and **Backup & DR Audit** *(Manager-only)*.
- **Forecasts** live under a separate top-level menu: **WMS → Forecast / Reorder → Forecasts**.

### A. Slot occupancy (Reports → Slot occupancy)
1. Open **Reports → Slot occupancy**. One row per stocking location.
2. Read the columns: **Location**, **Location Kind** (Floor zone / Rack slot), **Compartment**, **Rack**, **Capacity**, **On Hand**, **Occupancy Pct**, **Distinct** (number of different products in that location).
3. Rows are colour-coded: red over 90% full, amber over 75%, greyed when empty (On Hand = 0). Capacity is the soft hint set when the slot/floor was created; Occupancy Pct is On Hand ÷ Capacity.

### B. Movement history (Reports → Movement history)
1. Open **Reports → Movement history**. It lists validated stock moves (state = Done), grouped by product by default.
2. Read the columns: **Source Document** (the picking/origin), **Product**, **Demand** (the quantity), and **Status** (Done). Use it to answer "what moved, and when".

### C. Oldest stock / FIFO (Reports → Oldest stock (FIFO))
1. Open **Reports → Oldest stock (FIFO)**. Every live quant in a rack slot, sorted oldest-first.
2. Read the columns: **Product**, **Quantity**, **Slot**, **Compartment**, **Rack**, **In Date** (when it arrived), and **Age Days**. Older stock should be issued first.
3. Rows colour by age: red over 365 days, amber over 180, blue over 90. There's also a **Pivot** view (rack × product) for a roll-up.

### D. Expiry alerts (Reports → Expiry alerts)
1. Open **Reports → Expiry alerts**. Products that have an expiry date set, sorted by soonest expiry. By default the view pre-applies the **Expired**, **Within 30 days**, and **Within 90 days** filters.
2. Read the columns: **Product**, **Kind**, **Expiry date**, **Days to expiry** (negative = already expired), **On hand**, **Batch**, and **Status** (e.g. "Expires within 90 days").
3. Rows colour by urgency: red = Expired, amber = within 30 days, blue = within 90 days, grey = more than 90 days left. Use the search filters **Expired / Within 30 days / Within 90 days** and group by Kind or Status. **This report is how you rotate perishables by expiry** — the Scan Issue picker always pulls oldest-arrived (FIFO), so you read this list to spot what's nearing expiry and deliberately issue or rotate it first.

### E. Forecasts / Reorder (Forecast / Reorder → Forecasts)
1. Open **WMS → Forecast / Reorder → Forecasts**. By default it shows products that need reordering now.
2. Read the columns: **Product**, **Velocity Class** (Fast / Normal / Slow / Dead), **Monthly Avg**, **On Hand**, **Reorder Qty** (with a total at the foot), **Reorder Date**, **Model Name** (the AI model used), **RMSE** (error metric — lower is better), and **Last Trained**.
3. The figures are produced by an AI engine (Holt-Winters / SES) retrained automatically every day by a cron. A Manager/Buyer can click **Create PO** on a row (or **Retrain now** / **Create draft PO** on the form) — read-only viewers just read the numbers.
4. Related shortcuts: **Reports → Low stock alerts** (products whose forecast will drop stock below the reorder point) and **Reports → Dead stock** (no outflow in 90 days). The **Reorder summary** report is a separate roll-up.

### F. Store Keeper Activity (Reports → Store Keeper Activity) — Manager only
1. Open **Reports → Store Keeper Activity**. A timeline of everything each keeper has done. By default it groups by Day and Store Keeper for the last 30 days.
2. Read the columns: **When** (date/time), **Store Keeper**, **Activity** (Scan Receipt / Scan Return / Scan Issue / Internal move / Damage filed / Repair order), **Reference**, **Product**, **Quantity**, and **Counterparty**.
3. Switch views: **List** (audit timeline), **Pivot** (day-by-keeper matrix), **Graph** (stacked bars). Use the **Weekly / Monthly / Yearly summary** shortcuts under the same menu for pre-filtered views, and the search filters (Receipts / Issues / Returns / Damages, plus Today / This week / This month / This year).

### G. Inventory Audits results (Operations → Inventory audits)
Although audits are *performed* under Operations, their results are read-only after submission. The list shows: **Name** (`AUDIT/0000x`), **Auditor**, **On-duty Store Keeper**, **Started At**, **Submitted At**, **Line Count**, **Variances**, and **State**. A **Submitted** audit's count lines are locked (immutable) until a Manager accepts or rejects it.

## Worked Example
A Manager runs the Monday morning review.

1. **Reports → Expiry alerts.** Two medicine batches show red (Expired) and three amber (within 30 days). The Manager notes the expired ones for disposal (via a Damage event, reason Expired) and flags the amber ones to be issued first.
2. **Reports → Oldest stock (FIFO).** A sack of feed in rack `R02` shows Age Days = 200 (amber). The Manager tells the desk to issue that sack next.
3. **Reports → Slot occupancy.** Slot `R01-SH02-C01-SL01` is red at 96% — nearly full. The Manager plans to spread the next delivery to a different slot.
4. **Forecast / Reorder → Forecasts.** Three Fast-moving products have a positive Reorder Qty with a near Reorder Date. The Manager (acting as Buyer) clicks **Create PO** on each to draft purchase orders.
5. **Reports → Store Keeper Activity** (Monthly summary). The pivot shows Suresh did most receipts and Ramesh most issues last month — useful for balancing the roster.

A read-only viewer (e.g. a trustee) opens the same Expiry, Oldest stock, and Slot occupancy reports to satisfy themselves the store is healthy — without any ability to change data.

## Common Errors & What They Mean
- **"No backup events recorded yet." / empty report placeholders.** Several reports show a friendly empty-state when there's nothing to display (e.g. nothing expiring, no dead stock). It's informational, not an error.
- **A report menu is missing.** **Store Keeper Activity** and **Backup & DR Audit** are Manager-only — a read-only viewer won't see them. That's by design, not a fault.
- **AccessError when trying to edit a value on a report.** Reports are read-only views; you can't edit cells. (Forecasts allow the Create PO / Retrain actions only for users with the right role.)
- **Forecast row shows blank Model Name / Last Trained.** The daily retrain cron hasn't run for that product yet. Click **Retrain now** on the form, or wait for the next daily run.

## Troubleshooting
- **Occupancy Pct shows 0 even though there's stock.** Occupancy needs a **Capacity** set on the slot/floor. With no capacity hint, Pct stays 0 (only On Hand is meaningful there).
- **A product isn't on the Oldest stock report.** That report only includes quants in **rack slots**. Stock sitting directly in a **floor zone** appears on Slot occupancy but not on the rack-only FIFO report. (FIFO at issue time still considers floor stock — the report view is just rack-scoped.)
- **A perishable product isn't on Expiry alerts.** The report only lists products with an **Expiry date** set. Set the expiry on the product (or during onboarding) so it appears.
- **Movement history seems to show too much/too little.** It's filtered to **Done** moves and grouped by product by default. Clear or change the grouping and add date filters via the search bar to narrow it.
- **Store Keeper Activity is empty for a period.** It only includes actions that recorded an on-duty Store Keeper. Adjust the date filter (default is last 30 days) and check the keeper was selected on those actions.
- **Forecast numbers look stale.** Confirm the "WMS — Retrain forecasts" daily cron is active, or click **Retrain now** to refresh a specific product immediately.

## Best Practices
- **Make report-reading a routine.** A weekly pass over Expiry, Oldest stock, Slot occupancy, and Forecasts catches spoilage, stagnation, congestion, and shortages early.
- **Act on Expiry and FIFO together.** Every product issues oldest-arrived first (FIFO) at the picker. For medicine/feed/fluid/pooja, also work the **Expiry alerts** report: it surfaces what's nearing expiry so you can deliberately rotate or issue the soonest-to-expire stock before it spoils.
- **Use the right view for the question.** List for a timeline, Pivot for "how much per keeper per day", Graph for a quick visual.
- **Read-only viewers should rely on reports, not the raw Inventory app.** The reports are the safe, curated window into the data.
- **Trust the live numbers.** Scans update reports instantly; you don't need to refresh or recompute (except Forecasts, which are a daily AI job).
- **Treat submitted audits as the count of record.** Don't try to edit a submitted audit's lines — reject and re-walk if a count is wrong.

## Related Help-Center Articles
- `readonly-path-what-you-can-do`
- `readonly-path-using-reports`
- `readonly-path-searching-stock`
- `readonly-path-audit-visibility`
- `readonly-path-safe-viewing`
- `admin-path-reports-overview`
- `workflow-using-reports`
- `faq-where-is-product`
- `faq-fifo-vs-fefo`
- `what-is-cycle-count`

## Narration Script
*(Target length ~4 minutes.)*

- **[0:00]** "In this video we'll tour the warehouse reports — the read-only screens that tell you the health of the store. Looking at a report never changes any stock."
- **[0:15]** "Open the WMS app and click Reports. A read-only viewer sees the same screens a Manager sees, minus the two Manager-only audit screens."
- **[0:32]** "First, Slot occupancy. One row per location — rack slot or floor zone — showing capacity, on-hand, and how full it is as a percentage. Red means over ninety percent full; grey means empty. The Distinct column tells you how many different products share that spot."
- **[0:58]** "Next, Oldest stock, F-I-F-O. Every quant sorted oldest-first, with its in-date and age in days. Older stock should leave first. Red rows are over a year old — investigate those."
- **[1:22]** "Expiry alerts shows anything with an expiry date, soonest first. Days to expiry goes negative when something's already expired. Red is expired, amber within thirty days, blue within ninety. This is the report you use to rotate perishables — the issue picker always pulls the oldest-arrived stock, so you check this list to see what's getting close and deliberately issue or move that stock first, before it spoils."
- **[1:50]** "Movement history lists every completed stock move — source document, product, quantity, and a Done status. It answers 'what moved and when'."
- **[2:12]** "Now Forecast and Reorder, under its own menu. For each product you get a velocity class — Fast, Normal, Slow, or Dead — a monthly average, current on-hand, a suggested reorder quantity and date, and the AI model details with an error score. These are retrained automatically every day. A Buyer can click Create P-O to draft a purchase order; a read-only viewer just reads the numbers."
- **[2:45]** "Managers also get Store Keeper Activity — a timeline of who did what. Switch to the Pivot view for a day-by-keeper matrix, or use the Weekly, Monthly, and Yearly shortcuts. It's the answer to 'who was on the desk when this happened'."
- **[3:12]** "And under Operations, Inventory audits show their results read-only: who counted, when, how many lines, and how many variances. Once an audit is submitted, its counts are locked."
- **[3:35]** "So: occupancy for congestion, oldest-stock and expiry for rotation, movement history for the trail, forecasts for buying, and activity for accountability. Make a weekly pass through them and you'll catch problems early. Thank you."

## Recording Checklist
1. Log in (as a Manager to show all screens; optionally repeat as a read-only Store Keeper to show the trimmed menu).
2. Click **WMS → Reports**.
3. Open **Slot occupancy**; point out Location, Location Kind, Compartment, Rack, Capacity, On Hand, Occupancy Pct, Distinct; note the colour coding.
4. Open **Oldest stock (FIFO)**; point out In Date and Age Days; show the **Pivot** view.
5. Open **Expiry alerts**; point out Days to expiry and Status; toggle the **Expired / Within 30 days / Within 90 days** filters.
6. Open **Movement history**; point out Source Document, Product, Demand, Status.
7. Open **WMS → Forecast / Reorder → Forecasts**; point out Velocity Class, Monthly Avg, On Hand, Reorder Qty, Model Name, RMSE, Last Trained.
8. Open **Reports → Store Keeper Activity** (Manager); switch **List → Pivot → Graph**; show the Monthly summary shortcut.
9. Open **Operations → Inventory audits**; show the list columns and a Submitted (locked) audit.
10. End on the Reports menu.
