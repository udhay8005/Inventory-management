# Annotated Screen-Maps

Beginner-friendly, **annotated screen-maps** of the WMS barcode scan wizards for
the Warehouse Training Academy (Odoo 19 WMS for a cow-care trust that buys and
uses stock — never sells).

These are **not screenshots**. Each file is a clean, stylized vector recreation
of a wizard's layout — a labelled diagram — with **numbered orange callout
circles** pointing at the important fields and buttons. The numbers run `1, 2,
3…` in the order a user fills the form, so a trainee can follow the wizard
top-to-bottom while reading what each control does.

They are recreated from the live wizard views, so the titles, banners, field
labels, placeholders, and button names match what the operator actually sees:

- `scan-receipt.svg` / `scan-return.svg` — `addons/wms_barcode/wizards/scan_receipt_views.xml`
- `scan-issue.svg` — `addons/wms_barcode/wizards/scan_issue_views.xml`

## Shared style

| Element | Look |
| --- | --- |
| Dialog window | outer rounded rect, white fill, `#cbd5e1` stroke |
| Title bar | `#f1f5f9` fill, shows the wizard title |
| Field row | light rounded rect, `#f8fafc` fill, `#e2e8f0` stroke, with a label (`#334155`, 13px, 600) and a placeholder line |
| Info banner | tinted rounded rect, `#eff6ff` fill, `#3b82f6` stroke |
| Primary button | `#f59e0b` fill, white text (Validate) |
| Secondary button | `#e2e8f0` fill, `#334155` text (Process scan / Plan FIFO / Cancel) |
| Callout | orange circle (`#f59e0b`, white bold number, r=13) + short label (`#7c2d12`, 12px) |

All three share `width=640`, `font-family="Segoe UI, Arial, sans-serif"`, and a
red asterisk (`*`) on required fields. A red sticky note inside `scan-issue.svg`
reminds the trainee that **Validate hides when stock is short — you can't
over-issue.**

## Files

| File | Wizard | Callouts |
| --- | --- | --- |
| `scan-receipt.svg` | **Scan Receipt** — receiving a delivery | 1 Scan here · 2 Lines table · 3 Quality check · 4 Store Keeper on duty · 5 Delivered by · 6 Validate &amp; Print |
| `scan-issue.svg` | **Scan Issue (FIFO)** — issuing stock for trust use | 1 Requested Qty · 2 Last Scan · 3 Plan table · 4 Item photo · 5 Audit trail (Taken by / Ordered by / Store Keeper / Reason) · 6 Validate |
| `scan-return.svg` | **Scan Return** — booking an item back into stock | 1 Scan here · 2 Lines table · 3 Quality check · 4 Store Keeper on duty · 5 Validate &amp; Print |

## Notes for each wizard

- **Scan Receipt** — the cursor stays in the scan field; every barcode is
  processed automatically and carton barcodes auto-fill their unit count. QC
  must be ticked and an on-duty Store Keeper chosen before Validate works.
- **Scan Issue (FIFO)** — set the quantity **first**, then scan. FIFO pulls the
  oldest stock; FEFO is used for items with an expiry (the **Expires** column is
  highlighted when a batch is near its date). A photo is required for measured
  items (liquids / weighed goods), and all four audit fields are mandatory.
- **Scan Return** — the same receipt wizard with return mode pre-set. Only
  products flagged **Returnable** are accepted; fluids and consumables are
  refused at Validate.
