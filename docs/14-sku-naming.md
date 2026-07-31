# 14 — SKU & Product-Code Policy

The Product Master uses **two identifiers** per product. The system builds and
protects both — you mostly choose the identity fields and let it compose the SKU.

| Identifier | Field | Example | Who reads it |
|---|---|---|---|
| **Business SKU** | Internal Reference (`default_code`) | `MED-PARA-CIP-TAB-500MG-10` | people: search, print, recognise |
| **Internal Product Code** | Internal product code (`wms_product_code`) | `PRD-000017` | the system: audits, imports, history, integrations — **permanent** |

> **Why two?** The SKU is *readable* but composed from attributes; the PRD code is
> a *permanent* handle that never changes even if the SKU is regenerated before
> stock. Together you get clean labels **and** rock-solid data integrity. This is
> how SAP / ERPNext / Dynamics separate "item number" from "internal id".

---

## The Business SKU

### Format (composed automatically)

```
<KIND>-<FAMILY>-<BRAND>-[VARIANT]-<FORM>-[STRENGTH]-[PACK]
```

- All uppercase, **A–Z 0–9 hyphen** only — the system enforces it.
- Optional segments (Variant, Strength, Pack) **collapse** when empty — no blank
  dashes, no `000` filler.
- You do **not** type the SKU. You pick the identity fields and the system
  composes it. (A manager can fix it before stock via **Regenerate SKU**.)

### Where each segment comes from

| Segment | Source | How |
|---|---|---|
| KIND | WMS Kind | fixed prefix (`MED`, `FEED`, `TOOL`, `SAN`, …) |
| FAMILY | **Families** register | the family's stable **code** (Paracetamol → `PARA`) |
| BRAND | **Brands** register | the brand's stable **code** (Cipla → `CIP`) |
| VARIANT | Variant text | squeezed (Premium → `PREM`) |
| FORM | **Forms** register | the form's stable **code** (Tablet → `TAB`) |
| STRENGTH | Strength / dosage text | squeezed (`500 mg` → `500MG`) |
| PACK | Pack size text | squeezed (`50kg` → `50KG`, `10` → `10`) |

The codes for Family / Brand / Form are set **once** in their registers
(Configuration → Families / Brands / Forms) and reused forever — so abbreviations
never drift. Enter a pack size as just the quantity + unit (`10`, `50kg`, `5L`)
for a clean segment.

### Examples

| Identity | Business SKU |
|---|---|
| Medicine · Paracetamol · Cipla · Tablet · 500 mg · 10 | `MED-PARA-CIP-TAB-500MG-10` |
| Feed · Cow Feed · ABC · Premium · Pellet · 50 kg | `FEED-COWFD-ABC-PREM-PEL-50KG` |
| Sanitation · Phenyl · Local · — · Liquid · — · 1 L | `SAN-PHEN-LOCAL-LIQ-1L` |
| Tool · Drill · Bosch · — · Cordless (model) · 18 V | `TOOL-DRILL-BOSCH-CORD-18V` |

### Fallback

If you create a product **without** a Family + Brand (e.g. quick entry or the bulk
onboard list), the SKU falls back to the legacy auto sequence `KIND-NNNNN`
(`CONS-00042`). Every product still gets a permanent `PRD-` code.

---

## Collision: the system BLOCKS, it never auto-numbers

If the identity you entered would compose a SKU that already exists, **creation is
blocked** with a message naming the existing product:

```
SKU 'MED-PARA-CIP-TAB-500MG-10' already exists.
Existing product: Paracetamol Tablet 500mg (PRD-000017)
Adjust the Brand, Variant, Pack size or Strength to make it distinct.
```

The system will **never** create `…-10-2` or `…-10-0002`. Fix the catalogue
instead — a true duplicate identity *is* the same product.

---

## Freeze: once it's in circulation, the code locks

The moment a product has **stock or movement**, its Business SKU and Code128
barcode **freeze** (the PRD code is permanent from creation):

- the SKU / barcode can no longer be edited;
- to change a frozen item, **archive it and create a new product** — never rename
  a code that is already in stock history (and likely on a printed sticker).
- *Filling a blank* barcode still works on a stocked product (so the system can
  back-fill a missing Code128); only **renaming** an existing code is locked.

Before freeze (no stock yet) a manager can still correct identity fields and click
**Regenerate SKU from identity**.

---

## How to add a new product

1. Confirm it doesn't already exist (search by name / family / brand / SKU).
2. On the product form, set **WMS Kind**, then **Family**, **Brand**, **Form**,
   and (as needed) **Variant**, **Strength**, **Pack size**. Pick existing
   register entries; add new Families/Brands/Forms (with a short code) under
   Configuration if missing.
3. Save — the system stamps the **PRD code**, composes the **Business SKU**, sets
   the Code128 barcode (= SKU) and a numeric EAN-13, and applies the form's
   suggested unit.
4. Print the label and stick it on the item.

---

## Why this matters

- **Readable + stable**: `MED-PARA-CIP-…` tells a human what it is; `PRD-000017`
  never changes underneath it.
- **No drift**: family/brand/form codes are set once and reused.
- **No duplicates**: collisions are blocked, not silently suffixed.
- **Audit-safe**: the PRD code means the same physical thing for the life of the
  trust, regardless of renames or recategorisation.

---

## One-page wall print version

```
TWO CODES per product:
  • Business SKU   = KIND-FAMILY-BRAND-[VARIANT]-FORM-[STRENGTH]-[PACK]
                     (auto-built, readable, on the label)
  • Internal code  = PRD-000123  (permanent, never changes)

SET the identity fields; the system builds the SKU:
  Kind → Family → Brand → [Variant] → Form → [Strength] → [Pack]

RULES:
  • Codes are UPPERCASE A-Z 0-9; family/brand/form codes set once in their register.
  • Duplicate SKU? The system BLOCKS it — adjust Brand/Variant/Pack/Strength.
  • After stock/movement, the SKU + barcode FREEZE — archive + recreate
    instead of renaming.
  • No Family/Brand entered → SKU falls back to KIND-00001.
```
