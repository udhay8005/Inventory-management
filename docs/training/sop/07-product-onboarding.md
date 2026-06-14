# SOP 07 — Product Onboarding (Bulk Catalog + Initial Stock + Labels)

## Purpose
This procedure explains how an Admin adds new products to the WMS catalog using the **Onboard Products** wizard. In one screen you can:

- Create one product or two hundred (paste a column of names straight from Excel/Google Sheets).
- Get an automatic SKU per product (e.g. `TOOL-00001`), an automatic Code128 barcode, and an EAN-13 alias.
- Optionally place the initial stock into a slot or floor zone on submit.
- Optionally print one combined thermal-label PDF for every new product.

It replaces the old three-step routine (create product → scan receipt → print label) with a single table.

## Who Uses It
- **WMS / Manager (Admin) only.** The wizard lives under **WMS → Configuration → Onboard Products** and is gated by the `group_wms_manager` group. It is a *setup* task, not daily warehouse work.
- Store Keepers and read-only viewers cannot onboard products. Day-to-day stock arrivals are handled by Store Keepers through **Scan Receipt** instead.

## Prerequisites
- You are logged in as a **WMS / Manager**.
- The storage map exists (at least one slot or floor zone) — see SOP 06. You need a slot to place initial stock; products with no starting quantity can be created without one.
- Know each product's **WMS Kind** (Tool, Consumable, Medicine, Feed, etc.) — this drives the SKU prefix and which extra fields are required.
- For **Medicine** and **Feed** products you must have the **expiry date** from the supplier's label ready (the wizard blocks submit without it).
- A thermal label printer connected if you want labels printed immediately.

## Step-by-Step Instructions
1. Open **WMS → Configuration → Onboard Products**. A dialog titled **Onboard new products** opens with a blue tip: *"paste a column of names from Excel/Google Sheets directly into the table to add many rows at once. Each row gets an auto-SKU (e.g. TOOL-00001), an auto Code128 barcode, and an EAN-13 alias. If you set the quantity and slot, the initial stock is placed on submit."*
2. Add rows to the editable table. Either click into the empty row and type, or **paste a column of product names** copied from a spreadsheet (Odoo's list import handles the clipboard paste).
3. For each row, fill the columns:
   - **Product name** (required).
   - **WMS Kind** (required) — pick from the dropdown. The label shows the SKU prefix in parentheses, e.g. *Tool / Equipment (TOOL)*, *Consumable (CONS)*, *Medicine - veterinary (MED)*, *Feed / Grass / Bran (FEED)*, *Stationery (STAT)*, *Fluid / Liquid / Oil (FL)*, *Pooja items (POOJA)*, and so on.
   - **Initial qty** (default `1`) — units to place on submit. Set to `0` for a catalog-only entry (no stock yet).
   - **Slot** — where the initial stock goes. Required when Initial qty is greater than 0. The dropdown only lists internal slots and floor zones.
   - **Scan slot** — instead of picking from the dropdown, scan the slot's barcode here (e.g. `R01-SH01-C01-SL01`); the system auto-fills the Slot field and clears the scan box for the next scan.
   - **Expiry** (shown by default) — **required for Medicine and Feed**; useful for Fluid and Pooja. The Expiry Alert report uses this date.
   - Optional hidden columns you can switch on via the list's column picker: **Batch** (supplier batch/lot), **Litres** (volume for fluids), **Supplier** (default vendor), **Unit price**.
4. Review every row for typos — the wizard validates all rows *before* writing anything, so a 50th-row mistake won't leave 49 half-saved products behind.
5. Click one of the footer buttons:
   - **Onboard + Print labels** — creates the products, places initial stock, and opens a combined thermal-label PDF (one label per product).
   - **Onboard only** — creates the products and places stock, shows a success toast, and closes the dialog. (Print labels later from the product list via **Action → Print thermal label**.)
   - **Cancel** — discards the wizard.
6. After submit, find the new products under **Inventory → WMS Products** (or wherever your product list lives). The SKU, Code128 barcode, and EAN-13 alias are already filled. The wizard also shows a summary line like *"3 products onboarded with 30 units of stock placed."*

## Worked Example
The trust just received a delivery and wants to onboard three items at once, two with stock and one catalog-only.

1. **WMS → Configuration → Onboard Products**.
2. Paste three names into the table: `Calcium Bolus`, `Cattle Feed 50kg`, `Cordless Drill 18V`.
3. Fill the rows:
   - Row 1: Name `Calcium Bolus`; WMS Kind **Medicine - veterinary (MED)**; Initial qty `24`; Slot — scan `R01-SH01-C01-SL01` (auto-fills the slot); **Expiry** `2026-12-31` (required for medicine).
   - Row 2: Name `Cattle Feed 50kg`; WMS Kind **Feed / Grass / Bran (FEED)**; Initial qty `20`; Slot — pick `F-01` from the dropdown; **Expiry** `2026-09-30` (required for feed).
   - Row 3: Name `Cordless Drill 18V`; WMS Kind **Tool / Equipment (TOOL)**; Initial qty `0` (catalog only — no slot needed).
4. Click **Onboard + Print labels**.
5. Result: three products created with SKUs `MED-00001`, `FEED-00001`, `TOOL-00001`; 44 units of stock placed (24 medicine in the rack slot, 20 feed sacks on floor zone `F-01`); the drill exists in the catalog with no stock yet. A PDF opens with one thermal label per product. The summary reads "3 products onboarded with 44 units of stock placed."

## Common Errors & What They Mean
- **"You haven't added any products yet. Add at least one product row…"** — The table is empty. Add a row before submitting.
- **"Row N: product name is required."** — A row has a blank name.
- **"Row '<name>' is missing a WMS Kind. Pick one (Tool, Consumable, Feed, Medicine, Pooja, Fluid)…"** — A row has no WMS Kind. The Kind is what generates the SKU prefix.
- **"Row '<name>' has a starting quantity, so it needs a slot to live in. Scan the slot barcode, or pick it from the list. If you only want this product in the catalog (no stock yet), set the quantity to 0."** — Initial qty is greater than 0 but no Slot is set.
- **"Row '<name>' is a <Kind> product, and you must enter an expiry date from the supplier's label…"** — A Medicine or Feed row has no Expiry date. This is mandatory so the **Expiry Alerts report** can track the product and warn you before it spoils.
- **"Row '<name>': initial quantity cannot be negative."** — A negative number was entered for Initial qty.
- **"No internal location matches barcode '<code>'. Check the slot sticker, or pick from the dropdown."** — The barcode you scanned into **Scan slot** doesn't match any internal location. Verify the sticker or choose the slot from the dropdown.
- **SKU prefix mismatch (`SKU '<code>' does not match WMS Kind '<kind>'…`)** — This appears if a product code is typed that contradicts its Kind. In the onboard wizard the SKU is auto-generated, so you normally won't see this; it can appear later when editing a product code by hand. Fix: start the code with the expected prefix (e.g. `TOOL-`), or clear it so the system regenerates it.

## Troubleshooting
- **Paste from Excel didn't split into rows.** Copy a single *column* (one product name per cell, vertically) and paste into the first cell of the editable list. Pasting a horizontal row or a block with extra columns can misalign.
- **I clicked Onboard only and the dialog stayed open.** It should close after the success toast. If you double-clicked, the wizard guards against re-submitting (which would create duplicate SKUs) by chaining a close action — wait for the toast rather than clicking twice.
- **The Expiry column isn't visible.** It is shown by default. If someone hid it, open the list's column picker (the toggle on the header row) and re-enable **Expiry**. It auto-requires itself for Medicine/Feed rows.
- **A product shows no barcode afterwards.** The wizard stamps Code128 (= the SKU) and an EAN-13 alias automatically. If a clash prevented the Code128 (another product already owns that string), select the products in the list and run **Action → Generate missing barcodes**, then reprint labels.
- **I need a supplier or price on the product.** Switch on the optional **Supplier** and **Unit price** columns via the column picker before submitting, or edit the product afterwards.
- **Kind-specific details (dosage, volume, serial number) aren't on the wizard.** The wizard captures name, kind, qty, slot, expiry, batch, litres, supplier, and price. Other kind-specific fields (dosage, container size, serial number, weight, voltage, etc.) are entered later on the product's **WMS Classification** tab.

## Best Practices
- **Classify correctly the first time.** The WMS Kind sets the SKU prefix permanently and controls returnability and whether the product is treated as **expiry-sensitive**. Medicine/Feed/Fluid/Pooja are expiry-sensitive, which means an expiry date is required (Medicine/Feed) and the product is tracked on the Expiry Alerts report for spoilage. (Issuing itself is plain FIFO — oldest-arrived first — for every Kind.)
- **Always enter expiry for perishables.** Even where it isn't strictly required (Fluid, Pooja), entering expiry lets the Expiry Alert report protect the trust from spoilage.
- **Never rename an existing SKU.** It breaks the history trail. If something genuinely changes, create a new product (new SKU) and archive the old one. See `what-is-a-sku`.
- **Use Initial qty = 0 for catalog-only items.** Create the product now, receive stock later via Scan Receipt — no fake slot needed.
- **Onboard in batches that match a delivery.** Paste the delivery's item list, set quantities and the receiving slot/floor zone, and print labels in one pass.
- **Let the system place stock; don't double-receive.** Stock placed by the onboard wizard is real on-hand stock — do not also run a Scan Receipt for the same units, or you'll double-count.

## Related Help-Center Articles
- `admin-path-system-overview`
- `what-is-a-sku`
- `what-is-a-barcode`
- `what-is-scan-receipt`
- `what-is-fefo`
- `faq-where-is-product`
- `safety-never-delete-archive`

## Narration Script
*(Target length ~3 minutes.)*

- **[0:00]** "In this video we'll onboard new products into the warehouse system. Onboarding creates the product, gives it an automatic code and barcode, and can place its first stock — all in one screen. This is a Manager task."
- **[0:18]** "Open WMS, Configuration, Onboard Products. Notice the tip at the top: you can paste a column of product names straight from Excel to add many rows at once."
- **[0:35]** "Let's add three items. I'll paste three names: Calcium Bolus, Cattle Feed fifty kg, and Cordless Drill eighteen volt."
- **[0:50]** "For each row I set the WMS Kind. Calcium Bolus is Medicine, so I choose 'Medicine - veterinary, M-E-D'. The Kind decides the product code prefix automatically."
- **[1:08]** "Calcium has twenty-four units arriving, so I set Initial qty to twenty-four and scan the slot barcode into the Scan slot box — the Slot field fills itself. Because medicine can expire, I must enter the expiry date from the box: December thirty-first, twenty twenty-six."
- **[1:30]** "Cattle Feed is a Feed product, twenty sacks, going onto floor zone F-zero-one, with its own expiry date. The Cordless Drill is a Tool — I'll leave its quantity at zero, so it's catalog-only with no slot needed yet."
- **[1:52]** "I'll double-check every row, because the wizard validates all rows before saving anything — so one typo can't half-save the batch."
- **[2:05]** "Now I click Onboard plus Print labels. The system creates all three products with codes M-E-D dash zero-zero-zero-zero-one, F-E-E-D dash zero-zero-zero-zero-one, and T-O-O-L dash zero-zero-zero-zero-one, places the stock, and opens one P-D-F with a thermal label for each product."
- **[2:30]** "If I didn't want labels right now, I'd click Onboard only instead, and print later from the product list using Action, Print thermal label."
- **[2:45]** "The new products are now in the catalog, ready to scan, issue, and report on. Remember: classify correctly, always set expiry for perishables, and never rename a code once it's created. Thank you."

## Recording Checklist
1. Log in as a WMS Manager.
2. Click **WMS → Configuration → Onboard Products**.
3. Show the blue tip banner.
4. Paste three names into the editable table.
5. Set WMS Kind on each row (Medicine, Feed, Tool).
6. On row 1, set Initial qty `24`, **scan** a slot barcode into **Scan slot**, set **Expiry**.
7. On row 2, set Initial qty `20`, pick `F-01` from **Slot**, set **Expiry**.
8. On row 3, set Initial qty `0` (no slot).
9. Click **Onboard + Print labels**; show the generated label PDF.
10. Open the product list and show the new SKUs and barcodes; finish on the summary line.
