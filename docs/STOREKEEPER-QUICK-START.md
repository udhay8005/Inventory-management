# Store Keeper Quick Start (≈10 minutes)

For the people working the store desk. You scan goods in and out; the system
records **who did what**. Works on a PC, phone, or tablet on the same WiFi.

> Stuck on any screen? Tap the top-level **Help & Training** app menu — it has a short
> guided tour and step-by-step articles for everything below. **Beginner Mode**
> (on by default) adds hints and an extra "are you sure?" on risky actions.

---

## 1. Log in
1. Open the WMS in your browser (ask your admin for the address, e.g.
   `http://<office-pc>:8069`).
2. Sign in with the shared **store-keeper login**.
3. You'll work entirely from the **WMS** menu. (The raw Inventory app is hidden —
   that's normal; the scan wizards are the only path.)

**Every stock action asks for the same three things — the audit trail:**
- **Store Keeper on duty** → pick *your own name* from the roster.
- **Taken/Received/Delivered by** → who physically handled the goods.
- **Ordered/Authorised by** → who approved it.

You can't finish a damage/repair with these blank — that's by design.

### Find where something is
**WMS → Operations → Find / Where is it?** Type a product name, SKU, or scan its
barcode — the page tells you **which slot(s)** it's in and **how much** is on
hand. Or tap a chip (**low stock**, **expiring**, **dead stock**, **damaged**,
**under repair**) for an instant list. Works great on a phone.

> **Find / Where is it? vs Where is product X?** — *Find / Where is it?*
> (Operations menu, `/wms/find`) is your quick all-purpose search by barcode,
> SKU, or product name. *Where is product X?* (Reports menu) is the drill-down
> report that lists slot-by-slot stock for one specific product. Use Find for
> day-to-day lookups; use the report when you need the full picture for one item.

## 2. Scan Receipt (goods coming IN)
**WMS → Operations → Scan Receipt**
1. Pick your name + fill the audit fields.
2. **Scan the product barcode** (or pick it) → type the **quantity**.
3. **Scan the destination slot** label (e.g. `R01-SH02-C01-SL01`).
4. Tap **Validate**. Stock is now in that slot.

## 3. Putaway (where it goes)
Putaway just *is* the slot you scanned in step 2 — the goods live wherever you
placed them. For loose/bulk items, scan a **Floor Zone** (`F-01`) instead of a
rack slot.

## 4. Scan Issue (goods going OUT)
**WMS → Operations → Scan Issue (FIFO)**
1. Fill the **four mandatory audit fields**: *Taken by*, *Ordered by*,
   *Store Keeper on duty* (your roster name), and *Reason / usage note*
   (why). The wizard won't validate with any of these blank.
2. Optionally pick **Issued for** (Cows / Pooja / Maintenance / …) — this is
   a separate category dropdown that defaults to *Other*. It's not required,
   but setting it correctly lets managers see "how much did Cows cost vs
   Pooja" in the Consumption Value report.
3. **Scan the product** → quantity to give out.
4. The system picks the **oldest stock first (FIFO)** / **earliest-expiry first
   (FEFO)** automatically and shows the plan.
5. Tap **Validate**. Stock leaves the slot.
> If you hit a **daily limit** or **stock-out** message, stop and tell a manager —
> don't force it.

### Made a mistake? Undo it
If you just issued the wrong item or quantity, open the transfer that opened
after you validated and tap the orange **Undo this transfer** button. The system puts the stock straight back —
no manual return needed. The button only shows for a short window (15 minutes by
default) and only while the stock is still where you put it. After that, use
**Scan Return** instead.

## 5. Scan Return (goods coming BACK)
**WMS → Operations → Scan Return** — for returnable items (tools, spares) coming
back to the shelf. Pick your name, scan the item, scan the slot, **Validate**. (The product's
*Kind* decides whether returns are allowed.)

## 6. Damage (something is broken/spoiled)
**WMS → Operations → Damages**
1. Pick your name; enter **Reported by** and **Authorised by**.
2. Scan the product + the slot it's in + the damaged quantity.
3. **Confirm** → the stock moves to the **Damage** location (out of normal stock).
> Can't repair it yourself — a manager decides repair vs. write-off.

## 7. Audit (count a slot)
**WMS → Operations → Inventory audits** (if you have the *Submit audits* permission)
1. Start an audit; the system lists what it *thinks* is in each slot.
2. **Count the shelf** and enter the real numbers.
3. **Submit** for a manager to review and accept — accepting fixes the books to
   match reality (it keeps any receipts/issues that happened while you counted).

## 8. Backup Now (only if you've been given it)
Some keepers are granted the **WMS / Can Run Backup Now** permission. If you
have it, a **Back Up Now** entry appears in the WMS menu.
1. Open **WMS → Back Up Now** and tap the big **Back Up Now** button.
2. It takes a few minutes — tap **Refresh** to check on it.
3. When it's done, the screen shows the backup's **filename**, its **size**,
   and the **upload time**. That's your confirmation it worked.
> No Back Up Now menu? You don't have the permission — that's normal. The
> system still backs itself up automatically every day.

---

## Everyday tips
- A **USB/Bluetooth scanner** just types into the focused box — tap the field,
  then scan.
- For **liquids / by-weight items**, the receipt asks for a **photo** — your
  phone camera opens automatically.
- **Check stock fast:** **WMS → Operations → Find / Where is it?** (smart search
  page — type a product name, SKU, or scan a barcode → see its slot and qty,
  or tap a chip for "low stock" / "expiring" / "damaged" / "under repair").
- Always pick **your own name** as the on-duty keeper — that's how the trust
  knows who handled what.

## FAQ

**A menu like Damages or Inventory audits isn't showing up — why?** Your user
account is missing the corresponding capability sub-group
(`group_wms_can_file_damage`, `group_wms_can_submit_audit`). Ask the Manager
to tick the right capability under your user profile.

That's the whole job. Full picture for managers:
**[ADMIN-QUICK-START.md](ADMIN-QUICK-START.md)** · **[INSTALLATION-GUIDE.md](INSTALLATION-GUIDE.md)**.
