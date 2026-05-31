# 13 — Operations Playbook (the 7 things)

This is the *process* layer that sits on top of the software. Each section
explains: **what the software already does**, **what your team has to do
around it**, and **the minimum bar for it to work**.

---

## 1. SKU / Item Coding

### In the software
- Every product has `Internal Reference` (technical name: `default_code`).
  This **is** the SKU.
- Visible everywhere: list views show `[SCRW-M4-20] Screw M4×20mm`.
- Searchable: typing the SKU into the global search jumps straight to the product.

### Your convention (see [docs/14-sku-naming.md](14-sku-naming.md))
- **Prefix–category–serial** pattern, e.g. `RM-ASH-001`, `PK-JAR-500`, `FL-OIL-001`.
- Lock it in once, **don't change format** mid-stream.

### Minimum bar
- Every product created has a non-blank `Internal Reference`.
- No two products share the same SKU.
- One human is the gatekeeper for new SKUs.

---

## 2. Storage Structure

### In the software
Already complete:
```
Warehouse (YourCompany)
  └─ Stock (WH/Stock)
       └─ Rack R-01 .. R-32
            └─ Level L-1 .. L-6
                 └─ Divider D-1 .. D-4
                      └─ Slot S-1 .. S-3   ← 2,304 unique stocking locations
```
- Each slot has its own auto-generated barcode like `R-12-L3-D2-S1`.
- Visual heat-map per rack at `/wms/rack/<id>/grid`.

### Physical alignment
1. Print **slot labels** in batches: open WMS → Operations → Slots →
   select up to 100 → ☰ menu → *Print > WMS Location Label*.
2. Stick them so they're visible while reaching into the slot.
3. Use the rack-grid view to walk the floor and confirm "physical = software."

### Minimum bar
- Every physical slot has its software label stuck to it.
- No stock kept "on the floor" outside a slot.

---

## 3. Barcode / Label System

### In the software
- **Product labels** (Code128 + SKU + name): list a product → ☰ *Print > WMS Product Label*.
- **Slot labels**: as above for stock.location.
- **Carton barcodes** (one barcode = N units): WMS → Configuration → *Carton Barcodes*.
- Any USB / wireless 2.4GHz / Bluetooth HID scanner works without driver install.

### Hardware (matches your starter list)
| Need | Starting choice | Upgrade later |
|---|---|---|
| Scanner | Any ₹800-₹2,000 USB HID scanner | 2.4GHz wireless or BT for tablet workflow |
| Label printer | Regular A4 + sticker sheets (Avery / Su-Kam) | Zebra GK420t or TSC TE244 thermal |
| Sticker sheet | A4 30-up / 65-up sheets | Same — both A4 templates print fine |
| Phone | Existing Android/iOS | Same |
| UPS | 600VA for the laptop running Odoo | 1KVA when you scale |
| Scale | Optional, any platform scale with PC link | Connect via Odoo IoT (later) |

### Minimum bar
- Each new product gets a barcode label printed and stuck before it's shelved.
- Barcode value is stored on `product.product.barcode`.

---

## 4. Receiving (GRN-style flow)

### In the software
**WMS → Operations → Scan Receipt** runs this flow:
1. Operator scans a product (or carton) barcode → line added with qty.
2. Optionally scans a slot barcode → destination set for that line.
3. *Validate & Print* → creates a `stock.picking` (WH/IN/NNNNN) in **Done** state.
4. Quants are atomically created/incremented at the chosen slot with `in_date = now()`.

Every receipt has a chatter log: who did it, when, what moved.

### The process around it
Stick to this order, even if it feels like overhead at first:

```
[Vendor delivery arrives]
        ↓
1. Physical count at the dock
        ↓
2. Quality check (visible damage, count match, expiry on perishables)
        ↓
3. Scan Receipt — one entry per delivery
        ↓
4. Auto-print product labels for any unlabelled items
        ↓
5. Walk to the assigned slot(s), place stock, verify label match
        ↓
6. Sign the supplier challan as "Received & Stocked"
```

### Minimum bar
- Stock is **never** placed on a shelf before it's been scanned into the system.
- Damaged or short-shipped items go through the **Damage** flow, not silently discarded.
- One nominated person ("Receiver") owns the GRN step.

---

## 5. Issue / Consumption

### In the software
**WMS → Operations → Scan Issue (FIFO)** plans the deduction from
oldest stock first across all slots holding that product:

```
Operator picks destination:
   Customers      → Sales / Dispatch (creates WH/OUT/NNNNN)
   Production     → Internal consumption
   Internal       → Slot-to-slot transfer
```

For measured products (litres / kg / etc.) the wizard **requires a photo**
of the dispensed quantity before validate — that proof attaches to the
picking's audit trail.

### The process
| Scenario | Destination to pick | Who triggers |
|---|---|---|
| Customer sale / despatch | Customers | Sales / Despatch |
| Production consumption | Production (Manufacturing Loc) | Production lead |
| Project / department use | Internal (project sub-location) | Project owner |
| Damaged / expired write-off | use Damage flow | Operator + Manager approval |
| Send for repair | use Repair flow | Maintenance lead |

### Minimum bar
- Nothing leaves the warehouse without going through one of these flows.
- The "Take material later, log it later" habit is the #1 killer — ban it.
- Issues > a certain ₹ threshold need Manager-group user to validate (add a
  domain on the action if you want it enforced in code).

---

## 6. Periodic Stock Counting

### In the software (just added)
**WMS → Operations → Cycle Count** opens Odoo's native inventory
adjustment screen filtered to your slots:
1. Filter by Rack / Product / Last-counted-before-date.
2. Walk the floor, type the physical count next to the system count.
3. Apply → creates correcting `stock.move`s with full audit.

You can also add a cron that emails the WMS Manager every Monday with
"Slots not counted in 30 days." (Ask if you want this — 10 lines of code.)

### Recommended cadence

| Frequency | What to count | Who |
|---|---|---|
| **Daily** | High-value spot checks (3-5 slots randomly) | Operator |
| **Weekly** | All fast-moving SKUs (forecast `velocity_class='fast'`) | Operator |
| **Monthly** | One full rack rotation (rack 1 in Jan-W1, rack 2 in Jan-W2, …) | Operator + supervisor |
| **Yearly** | Full physical count, all 2,304 slots, system frozen | Whole team |

### Minimum bar
- Any operator-found mismatch is logged immediately, not "fixed quietly".
- Discrepancies > 5% trigger a manager review of the slot's last 30 days
  of movements.

---

## 7. Responsibility System

### In the software
Four built-in groups (Settings → Users & Companies → Groups, filtered by WMS):

| Group | Can | Cannot |
|---|---|---|
| **WMS / Store Keeper** | Scan receipt, issue, internal transfer; view stock | Approve damage, edit racks |
| **WMS / Manager** | Everything WMS User can + cancel pickings, edit racks, run cycle count, see all reports | — |
| **WMS / Repair Tech** | Start / finish repair, scrap from repair | Manage stock outside repair |
| **WMS / Buyer** | View forecasts, create draft POs, see vendor data | Move stock |

### Assign real names

| Role | Software group | Name in your org |
|---|---|---|
| Inventory In-charge | WMS / Manager | _______________ |
| Receiver | WMS / Store Keeper | _______________ |
| Issuer / Despatcher | WMS / Store Keeper | _______________ |
| Repair Tech | WMS / Repair Tech | _______________ |
| Buyer / Procurement | WMS / Buyer | _______________ |
| Auditor | WMS / Manager (read-only sub-group if needed) | _______________ |

Print this filled-in table and stick it in the warehouse office.

### Audit trail (free, automatic)
- Every `stock.picking`, `wms.damage`, `wms.repair.order`, and inventory
  adjustment carries a chatter entry with the user's name and timestamp.
- Click any record → chatter at the bottom → full history of who did what
  and when. Immutable for non-admins.

### Minimum bar
- One person ultimately owns inventory accuracy. They don't have to do
  every count, but they own the number.
- Disagreements have a documented escalation path (Operator → Manager →
  Inventory In-charge).

---

## Starter checklist (Stage 1, "70% solved")

Before you onboard anyone:

- [ ] Write the SKU convention (one A4 page, see next doc).
- [ ] Print and stick all 2,304 slot labels.
- [ ] Print product labels for every existing SKU and put them on the items.
- [ ] Create users for at least: Receiver, Issuer, Manager.
- [ ] Train the Receiver: complete one Scan Receipt end-to-end.
- [ ] Train the Issuer: complete one Scan Issue end-to-end with FIFO.
- [ ] Run one mock damage + repair cycle so the team has muscle memory.
- [ ] Set a daily 9am calendar reminder: "Yesterday's stock moves match physical?"
- [ ] Schedule `scripts\backup-native.ps1` in Windows Task Scheduler — 02:00 daily.
- [ ] Print the responsibility table.

That's the bar. Everything beyond is optimisation.

---

## Stage 2 upgrades (when basics are humming)

- **Batch / Lot tracking**: enable `lot_id` on the scan wizards — already
  there as an optional field; turn on Odoo's "Lots & Serial Numbers" setting
  in Inventory → Configuration → Settings.
- **Reorder rules**: each row in WMS → Forecast already shows a *Create PO*
  button — wire it to a default vendor per product, and the AI will queue
  drafts you only have to confirm.
- **Mobile photo capture**: requires HTTPS — once you're ready, named
  Cloudflare Tunnel gives a permanent URL. See `docs/12-mobile-access.md`.
- **Inventory valuation**: enable `stock.valuation.layer` reports (already
  installed via `stock_account`). Useful for accounting hand-off.
- **IoT scale**: integrates with `weight` field on `stock.quant`. Useful
  once you handle weight-based products consistently.

---

## What kills small-warehouse inventory systems (and how to avoid each)

| Failure mode | How software helps | Process needed |
|---|---|---|
| Multiple names for the same item | SKU is the primary key — duplicates rejected | Discipline + SKU gatekeeper |
| Unlabelled shelves | All 2,304 slots have a barcode | Stick the labels |
| Updating stock "later" | Scan wizards are 30-second flows; no excuse | Manager enforces same-day rule |
| Over-engineering on day 1 | We already shipped the minimum + room to grow | Don't enable features you don't need yet |
| No one accountable | Audit log captures every action with user | Name the person in the role table |
