# 14 — SKU Naming Policy

Pin this on the wall. **Every** product gets a SKU that follows this rule
before it's saved.

## Format

```
<CATEGORY>-<ITEM>-<VARIANT>
```

- All uppercase, **A–Z 0–9 hyphen only**. No spaces, no other punctuation.
- Total length ≤ 20 characters (fits on a 25 mm thermal sticker).
- Three segments. If a segment doesn't apply, use `000` not blank.

## Segment rules

### 1. CATEGORY (2–3 letters)

| Prefix | Meaning | Examples |
|---|---|---|
| `RM` | Raw Material | `RM-ASH-001`, `RM-COTTON-50K` |
| `PK` | Packaging | `PK-JAR-500`, `PK-BOX-S` |
| `FL` | Fluids / Liquids / Oils | `FL-OIL-001`, `FL-PETROL-95` |
| `FG` | Finished Goods | `FG-SOAP-100G` |
| `WIP` | Work in Progress | `WIP-MIX-A1` |
| `CONS` | Consumables (office, cleaning) | `CONS-PEN-BLUE` |
| `TOOL` | Reusable tools / equipment | `TOOL-DRILL-18V` |
| `SPARE` | Spare parts | `SPARE-BLT-M4` |

Add categories only when you actually have items in them. Don't pre-declare.

### 2. ITEM (3–6 letters or short word)

Strict rule: pick **one** abbreviation per item and stick to it forever.
A change here ruins history.

- Good: `ASH`, `JAR`, `OIL`, `SOAP`, `COTTON`
- Bad: `ASH-RAW`, `RAW-ASH`, `aShN` (case / dash inconsistency)

### 3. VARIANT (3 chars, digits or short tag)

- Size, capacity, model, colour, grade — whichever is the **primary**
  attribute that differentiates the variant.
- For sequential items with no real variant: `001`, `002`…
- Examples:
  - `500` (ml) → `PK-JAR-500`
  - `M4` (thread) → `SPARE-BLT-M4`
  - `RED` (colour) → `PK-CAP-RED`
  - `001` (no variant axis) → `RM-ASH-001`

## Examples (real-world)

| SKU | Item | Reasoning |
|---|---|---|
| `RM-ASH-001` | Ash, raw material | Single variant for now |
| `RM-ASH-FINE` | Ash, fine grade | Same item, finer variant |
| `PK-JAR-500` | 500 ml glass jar | Capacity is the primary axis |
| `PK-JAR-1000` | 1 L glass jar | Same family, different size |
| `FL-OIL-001` | Gingelly oil | Could later add `FL-OIL-COCO`, `FL-OIL-NEEM` |
| `FG-SOAP-100G` | 100 g finished soap bar | Weight as variant |
| `TOOL-DRILL-18V` | Cordless drill 18V | Voltage as variant |
| `SPARE-BLT-M4` | M4 bolt | Thread as variant |

## What's banned

| Anti-pattern | Why it's banned |
|---|---|
| `SOAP-NEW` | "NEW" stops being new in three months |
| `temp-001` | Lowercase + meaningless "temp" |
| `Ash Raw Material` | Spaces, mixed case, too long |
| `BOX1`, `BOX2` | No category prefix, no variant rule |
| Renaming an existing SKU | Breaks audit trail — create a new one and archive the old |

## How to add a new SKU

1. Inventory In-charge confirms the item doesn't already exist (search the
   product list by name + by SKU prefix).
2. Pick the right CATEGORY from the table above. If none fit, propose
   a new prefix to the In-charge — add to this doc *before* creating any
   product with it.
3. Pick the ITEM abbreviation. Re-use existing if it's the same item.
4. Pick the VARIANT — primary differentiator only.
5. Create the product in Odoo (**WMS Manager** group required):
   - **Internal Reference** = the SKU
   - **Barcode** = the same SKU (so scanning the SKU sticker also finds the product)
   - **Name** = the human name
   - **Unit of Measure** = correct unit (Units / Litre / kg / m / …)
6. Print the product label and stick it on the item.

## Why this matters

- **Search**: `SCRW-` instantly lists every screw variant.
- **Counting**: ordered list, no "which Ash is this?" confusion.
- **Purchase**: vendor sees a stable code on every order, not changing names.
- **Barcode**: the SKU *is* the barcode by default — one printable string.
- **Audit**: 5 years from now the SKU still means the same physical thing.

## Migration tip (if you have existing items)

Don't bulk-rename. Instead:

1. Pick a **cutover date**.
2. From that date, every new product follows this policy.
3. Existing products: rename only when you next touch them anyway (price
   change, vendor change, etc.).
4. Within 3 months you'll have ~80% of active inventory on the new scheme.
   The other 20% (dead stock) doesn't matter.

## One-page wall print version

```
SKU = CATEGORY-ITEM-VARIANT

CATEGORY:
  RM     Raw Material
  PK     Packaging
  FL     Fluid / Oil
  FG     Finished Good
  WIP    Work in Progress
  CONS   Consumable
  TOOL   Tool / Equipment
  SPARE  Spare part

Rules:
  • UPPERCASE, A-Z 0-9 hyphen only
  • ≤ 20 characters
  • If no variant axis: use 001, 002, ...
  • NEVER rename an existing SKU.
  • Always add Internal Reference + Barcode (same value).
```
