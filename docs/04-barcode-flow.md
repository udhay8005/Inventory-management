# 04 — Barcode flow

## Barcode kinds

| Kind | Stored on | Example | Notes |
|---|---|---|---|
| Product (unit) | `product.product.barcode` | `8901234567890` | Odoo native EAN-13 |
| Product (carton / bulk) | `wms.barcode.alias` (new) | `CTN-0001-COKE350ML` | Maps to product + units/carton |
| Slot | `stock.location.barcode` | `S-R01-D2-S3` | Odoo native (already on stock.location) |
| Rack | `stock.location.barcode` | `R-01` | Same |

`wms.barcode.alias` lets one product have many "physical" codes (vendor carton
labels, supplier batch labels), each with `units_per_scan` so a single scan can
add e.g. 24 units.

## Inbound scan flow

```
[Scan barcode]
      │
      ▼
[lookup product]  ← product.barcode or wms.barcode.alias
      │
      ├─ found product  → ask quantity (default = alias.units_per_scan or 1)
      │
      ├─ found slot     → set destination
      │
      └─ unknown        → "Create new product?" wizard step
```

Lines accumulate on the wizard. **Validate** posts the picking; quants land
in chosen slots with `in_date = now()`.

## Outbound scan flow (FIFO)

```
[Scan product barcode] → product P
[Enter qty Q]
[Engine queries stock.quant where product=P AND quantity>0
                ORDER BY in_date ASC]
[Loop quants, deduct min(remaining_need, quant.qty) until Q satisfied]
[Generate stock.move.line per quant with location_id = quant.location_id]
[Operator confirms → picking done]
```

If a chosen slot is physically empty (mis-count), the operator overrides; the
override is logged and triggers a cycle-count suggestion for that slot.

## Label printing (ReportLab + python-barcode)

- Server action **Print Barcode Labels** on `product.product`, `stock.location`,
  and any picking → triggers `report.wms_barcode.label_template`.
- Renders Code128 by default (URL-safe, dense, alphanumeric).
- Templates configurable (label width/height) via `wms.label.template`.

## Hardware

### Barcode scanners

All three common form factors are supported out of the box. They all enumerate
as **HID keyboards** to the OS, so no driver install is needed:

| Form factor | Examples | Notes |
|---|---|---|
| **Wired USB** | Honeywell Voyager, Zebra DS2208 | Plug in → it types into the focused field. |
| **2.4 GHz wireless (USB dongle)** | typical Amazon "rechargeable wireless scanner" | Same as wired — the dongle presents as a USB keyboard. |
| **Bluetooth (BT/BLE HID)** | most modern handhelds | Pair once via OS, then identical behaviour. |

Our scan wizards inherit `barcodes.barcode_events_mixin`, so every scan
is processed automatically (no button click). Cursor stays in the scan
field between scans for rapid-fire receiving.

**Scanner configuration tip:** make sure your scanner is set to append
**CR/LF (Enter)** as the suffix — this is the factory default for most
2.4 GHz wireless models. If scans land in the field but never process,
print the "Enable Enter Suffix" config barcode from the scanner's manual.

### Thermal label printer

Any printer the **host OS** can see. Odoo generates a PDF via the
report engine; the browser prints to the user's local printer through the
standard browser print dialog. Tested with Zebra GK420t and TSC TE244.
