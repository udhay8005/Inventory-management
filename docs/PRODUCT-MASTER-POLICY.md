# Product Master Creation Policy

**Dakshin Vrindavan Gaushala WMS** · Audience: **Admins / Managers** (the only roles
that can create Families, Brands, Forms, Categories) · Status: governance policy,
to read before creating master data.

> **Why this exists.** The system now generates enterprise SKUs automatically from
> a few master registers (Family, Brand, Form) plus per-product fields (Variant,
> Strength, Pack). The code *prevents* exact case/spacing duplicates
> (`Paracetamol` = `PARACETAMOL` = `Paracetamol  `). It **cannot** prevent *semantic*
> duplicates that are different words for the same thing —
> `Paracetamol` vs `Paracetamol 500` vs `Paracetamol Tablet` vs `Paracetamol Tablet 500`.
> Those are not duplicates to a computer, but they are the **same family** to a human,
> and they corrupt grouping, search and reporting. Avoiding them is a discipline, not
> a feature. This policy is that discipline.

---

## 1. The one golden rule

**A Family is the bare product / molecule / line — nothing else.**
Everything that describes a *specific pack* — the brand, the physical form, the
strength, the variant, the pack size — is a **separate field on the product**, never
part of the Family (or Brand, or Form) name.

> If you ever feel the urge to type a number, a unit, a form, or a brand **into a
> Family name**, stop — that detail belongs in its own field.

| You are tempted to create Family… | ❌ Wrong | ✅ Right |
|---|---|---|
| `Paracetamol 500` | strength is in the name | Family `Paracetamol`; put `500 mg` in **Strength** |
| `Paracetamol Tablet` | form is in the name | Family `Paracetamol`; pick Form `Tablet` |
| `Paracetamol Tablet 500` | form + strength in the name | Family `Paracetamol` + Form `Tablet` + Strength `500 mg` |
| `Cipla Paracetamol` | brand is in the name | Family `Paracetamol` + Brand `Cipla` |
| `Premium Feed 50kg` | variant + pack in the name | Family `Cattle Feed` + Variant `Premium` + Pack `50kg` |
| `Bosch Drill 18V` | brand + spec in the name | Family `Drill Machine` + Brand `Bosch` + Strength `18V` |

The product's **display name** can still read naturally ("Paracetamol Tablet 500mg
(Cipla)") — that's fine. The rule is only about the **Family / Brand / Form master
records**, which must stay clean and atomic.

---

## 2. What goes where — the field map

| Field | What it is | One per… | Examples |
|---|---|---|---|
| **Family** | the molecule / generic product line | molecule / line | Paracetamol, Ivermectin, Calcium, Cattle Feed, Phenyl, Drill Machine, Hand Sanitizer |
| **Brand** | the manufacturer / label | manufacturer | Cipla, Sun Pharma, VetCare, Bosch, ABC, Dettol, Local |
| **Form** | the physical form (or *Model* for tools) | dosage form | Tablet, Syrup, Injection, Bolus, Powder, Pellet, Liquid, Spray, Gel; (tools: Cordless, Corded) |
| **Variant** | a line/grade within a brand (free text, optional) | — | Premium, Standard, Citrus, Pro, Adult |
| **Strength** | potency / spec (free text, optional) | — | 500 mg, 250mg/5ml, 70%, 18V |
| **Pack size** | the pack you receive/scan (free text) | — | 10, 50kg, 60ml, 5L, Unit |

**Family / Brand / Form are shared registers** — every product reuses them, so they
must be few and atomic. **Variant / Strength / Pack are typed per product** — they
vary freely and never become master records.

---

## 3. The "one per concept" rules

- **One Family per molecule / product line.** `Paracetamol` is one family — every
  strength, form, brand and pack of paracetamol points at that single family. Do
  **not** create `Paracetamol`, `Paracetamol 500`, `Paracetamol Syrup` as three
  families.
- **One Brand per manufacturer.** `Cipla` once. Not `Cipla`, `Cipla Ltd`,
  `Cipla Pharma`. (The code blocks `Cipla`/`CIPLA`; *you* must avoid `Cipla Ltd`.)
- **One Form per dosage form.** `Tablet` once. Not `Tablet`, `Tab`, `Tablets`.
- **Never invent a new concept that already exists** under a slightly different
  wording. When unsure, it already exists — reuse it.

---

## 4. Before you create a new Family / Brand / Form — the 10-second check

1. **Open the dropdown first.** When creating a product (or in Configuration →
   Families / Brands / Forms), type the first 3–4 letters. The autocomplete shows
   what already exists.
2. **If something close appears, use it.** `Para…` already shows `Paracetamol`? Pick
   it. Do not add `Paracetamol 500`.
3. **Only create new if it is genuinely a new concept** (a molecule/brand/form not
   in the list at all).
4. **Give it an atomic name + a short stable code** (see §5). The code becomes part
   of every SKU — choose it once, carefully, and never change it after products use
   it.

---

## 5. Naming + code conventions

- **Name:** the plain, full, singular concept — `Paracetamol`, `Cipla`, `Tablet`.
  No numbers, units, forms, or brands mixed in. Title Case.
- **Code:** SHORT, UPPER-CASE, letters/digits only — Family/Brand ≤ 6 chars, Form
  ≤ 4 chars. It is the SKU segment, so make it recognisable: `PARA`, `CIP`, `TAB`,
  `BOSCH`, `CATFD`, `CORD`. Set it **once** — changing a code after products exist
  would make new SKUs diverge from old ones.
- The system stores codes UPPER-case and rejects exact case/space-duplicate names
  automatically — but it is on **you** to avoid synonyms and granularity drift.

---

## 6. What the system enforces vs what it trusts you for

| Risk | Caught by the system? |
|---|---|
| `Paracetamol` vs `PARACETAMOL` vs `Paracetamol ` (case / spaces) | ✅ **Blocked** automatically |
| Duplicate `code` (two brands both `CIP`) | ✅ **Blocked** (unique code) |
| Duplicate product identity (same family+brand+form+strength+pack) | ✅ **Blocked** at product creation |
| Category with same name under the same parent | ✅ **Blocked** |
| `Paracetamol` vs `Paracetamol 500` vs `Paracetamol Tablet` (granularity) | ❌ **Your discipline** (this policy) |
| `Bosch` vs `Bosche` vs `Bosch Ltd` (typos / synonyms) | ❌ **Your discipline** (check the dropdown) |

---

## 7. Worked examples (the right decomposition)

```
Paracetamol (Family PARA)
 ├─ Cipla (CIP) · Tablet (TAB) · 500 mg · pack 10  → MED-PARA-CIP-TAB-500MG-10
 ├─ Cipla (CIP) · Tablet (TAB) · 650 mg · pack 10  → MED-PARA-CIP-TAB-650MG-10
 ├─ Sun  (SUN) · Tablet (TAB) · 500 mg · pack 10   → MED-PARA-SUN-TAB-500MG-10
 └─ Cipla (CIP) · Syrup (SYR) · 60 ml              → MED-PARA-CIP-SYR-60ML

Cattle Feed (Family CATFD)
 ├─ ABC (ABC) · Premium · Pellet (PEL) · 25kg      → FEED-CATFD-ABC-PREM-PEL-25KG
 ├─ ABC (ABC) · Premium · Pellet (PEL) · 50kg      → FEED-CATFD-ABC-PREM-PEL-50KG
 └─ ABC (ABC) · Premium · Pellet (PEL) · 100kg     → FEED-CATFD-ABC-PREM-PEL-100KG

Drill Machine (Family DRILL)   [tools: Form = "Model"]
 ├─ Bosch (BOSCH) · Cordless (CORD) · 12V          → TOOL-DRILL-BOSCH-CORD-12V
 ├─ Bosch (BOSCH) · Cordless (CORD) · 18V          → TOOL-DRILL-BOSCH-CORD-18V
 └─ Bosch (BOSCH) · Cordless (CORD) · 24V          → TOOL-DRILL-BOSCH-CORD-24V

Hand Sanitizer (Family — e.g. SANI)
 ├─ Dettol · Liquid (LIQ) · 500ml                  → SAN-SANI-DETTOL-LIQ-500ML
 ├─ Dettol · Liquid (LIQ) · 1L                     → SAN-SANI-DETTOL-LIQ-1L
 └─ Dettol · Liquid (LIQ) · 5L                     → SAN-SANI-DETTOL-LIQ-5L
```

In every block there is **one Family**, **one Brand**, **one Form** — and the rows
differ only by Strength / Pack, which are per-product fields. That is the whole
policy in one picture.

---

## 8. Who can do this

- **Managers / Admins** create and edit Families, Brands, Forms and Categories
  (Configuration menu). They own catalogue governance.
- **Storekeepers** can read these but **cannot create or edit** them (enforced) — so
  master data only ever grows through a manager who has read this policy.

---

## 9. Quick reference (pin this)

```
NEW PRODUCT?  →  reuse an existing Family + Brand + Form (check the dropdown!)
              →  type the Variant / Strength / Pack for THIS pack
              →  let the system build the SKU + PRD code + barcode

NEW FAMILY/BRAND/FORM?  →  only if the concept is genuinely missing
                        →  atomic name, short stable CODE, set once
                        →  NEVER put a brand / form / strength / pack in the name

GOLDEN RULE:  Family = the molecule.  Everything else is a field, not a family.
```
