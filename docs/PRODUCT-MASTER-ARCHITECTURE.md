# Product-Master & Inventory Architecture

**Dakshin Vrindavan Gaushala WMS (Odoo 19 CE)** · Status: **approved direction, phased build** · Date: 2026-06-16

> This document is the output of the Enterprise Product-Master design sprint
> (multi-agent ERP research → architecture design → adversarial review). It
> records *the decision and why*, so the variant-engine question is never
> reopened by accident. Read §0 first — it is the decision after the critique.
> §1–§12 are the full design; the appendix is the adversarial critique that
> trimmed it.

---

## 0. Decision (post-critique) — what we are actually building

The design below recommends a **"thin enterprise" flat model**: one
`product.template` per stockable identity (brand × form × strength × pack),
plus lightweight grouping fields and a guided wizard — and it explicitly
**rejects Odoo's `product.attribute` / multi-variant engine**. The adversarial
review **agreed with the core** ("SOUND_WITH_CHANGES") and rejected roughly half
the *additions* as over-engineering for a single-site trust. The build plan is
the design **as trimmed by the review**:

**Build now (no-regrets, additive, zero stock/audit data touched):**

| # | Change | Why it's safe / valuable | Status |
|---|---|---|---|
| **P0** | **EAN-13 internal-range fix** — sequence prefix `89011110`→`02`, padding `4`→`10` (body stays **12 digits**, so `_next_ean13`'s 12-digit precondition holds). | Moves off the GS1-India *registered* range (`890…`) onto the GS1 **restricted-circulation** range (`02…`, reserved for in-house codes). Padding 10 keeps the body 12 digits — the **naive "prefix `2`" fix the design first proposed would have silently stopped all EAN-13 generation** (the review caught this). Capacity grows to 10-digit. `noupdate` keeps existing aliases; a migration repoints the live sequence. | **shipped v19.0.31.0.0** |
| **P-dup** | **Live duplicate-name warning** in the onboard wizard — soft, non-blocking onchange on the product name. | The single highest-value, lowest-risk anti-sprawl control. No schema change, no new model, no new operator step, never blocks the save — just warns "a product named X already exists" so the keeper opens it instead of making a near-duplicate. | **shipped v19.0.31.0.0** |

**Deferred until identity fields are proven necessary (and made mandatory-for-medicine):**

- `wms_brand` **as a Many2one model** → start as a normalized **Char** if/when added; a brand is a label, not an entity with a lifecycle.
- **Structured SKU composition** (`KIND-ITEM-BRAND-FORM-PACK`) → keep the existing `KIND-NNNNN` auto-sequence as the real, immutable key. Human disambiguation comes from the brand/form/strength **fields on the label and in search**, not from encoding them into the primary key (which needs a fragile abbreviation map and is harder to read aloud/hand-key).
- **11-step stepper wizard** → keep the flat editable list (paste-200-rows) as the primary path; a guided single-item mode is optional later.
- **P4 Purchase-UoM conversion**, **P5 reprint/replace-on-damage** → real but not urgent; each has a concrete correctness gotcha (see appendix) to design carefully before building.
- **Per-lot FEFO (W8)** → genuine value, but it touches `stock.quant`/`stock.lot` history and deserves its own approval + test cycle.

**The First Principle that gates every line above** (the owner's own rule):
> *Keep it SIMPLE for daily operators; only add enterprise concepts that beat their complexity cost. Is it maintainable for 10+ years? Is it simple enough for a non-technical storekeeper?*

---

## 1. Executive Recommendation

Adopt a "thin enterprise" model: keep ONE flat `product.template` per stockable
identity (brand × form × strength × pack), add three lightweight
grouping/identity fields (`wms_brand`, `wms_form`, `wms_strength`) plus a real
`product.category` family tree, route ALL creation through the onboard wizard —
and explicitly REJECT Odoo's `product.attribute` / multi-variant engine.

The research is unanimous that "same item, many brands/forms/sizes" is correctly
modeled as a unique SKU + unique barcode per pack (GS1, ERPNext, Zoho, inFlow all
agree). But two hard, Odoo-19-CE-specific facts make the native variant engine
fail the First-Principle test here:

1. **UoM is template-level** — a single template cannot hold a syrup (L), a
   tablet (Units) and a powder (kg), so "Form" *cannot* be a variant axis without
   splitting templates anyway.
2. The current `create()`/`_wms_ensure_barcodes()` stamping (verified at
   `product_template.py:549-587` and `:589-635`) assumes one variant per template
   and would **silently leave multi-variant templates with no SKU and colliding
   blank barcodes**.

The flat model already delivers the hard requirement (unique SKU + unique barcode
per pack) and integrates cleanly with `stock.quant`, FIFO, audit, forecasting and
the TSPL printer with **zero new models and near-zero migration risk**. We invest
the complexity budget where it pays: a guided wizard with a duplicate detector
(kills master sprawl), a brand/form/strength identity (makes the family
searchable), a Purchase-UoM conversion for genuine buy-bulk items, and a
barcode-prefix correctness fix.

---

## 2. Comparative ERP / WMS Feature Matrix (consolidated)

| Dimension | Odoo 19 CE | ERPNext | SAP B1 | Zoho | Fishbowl | inFlow | Unleashed | iDempiere | **Decision** |
|---|---|---|---|---|---|---|---|---|---|
| Hierarchy | 2-level template→variant | 2-level | 1-level | 2-level group→item | 1-level | 2-level | 1-level | 1-level + attr-set | **1-level flat template** + `product.category` family tree |
| Variant engine | `product.attribute` Cartesian | attribute combos | none | multi-attr | descriptive | variant options | descriptive | attr-set | **REJECT** — Form drives UoM (template-level), can't be a variant axis |
| SKU gen | per-variant `default_code`, no auto-seq | `PN-V1-V2` | manual | auto + pattern | auto | Prefix+Num+Suffix | manual | manual | **KEEP** kind-prefix + sequence |
| Barcode | one per variant; `product.uom` per-pack; EAN-13 check | multi-barcode child | per UoM | one field | scan-driven | auto internal | per UoM | UPC/EAN | **KEEP** Code128(=SKU)+EAN-13 alias; **FIX** EAN prefix |
| UoM | reference-tree (`relative_uom_id`), **no `uom.category`** | factors | UoM Groups | UoM+conv | flexible | purchase≠sales | per-UoM rows | direct rate | **KEEP** kind→base-UoM; **ADD** Purchase-UoM for buy-bulk |
| Pack-size | `product.uom`/packaging OR variant | attr/UoM | UoM-group | attr | UoM | variant/UoM | UoM row | UoM conv | **Pack-as-template** (own SKU+barcode) for the hard req; alias only for "N eaches in a carton" |
| Creation UX | full attribute tab | item form | item form | group form | form | form | form | form | **Guided wizard only** |

> Verified Odoo-19-CE internals: `uom.category` **does not exist** in 19
> (conversion is the `relative_uom_id` reference-tree); `product.packaging` is
> replaced by `product.uom` (per-variant, own *required* barcode);
> `product.template.uom_po_id` was **removed** (purchase UoM lives on
> `product.supplierinfo` as `product_uom_id` + `min_qty`).

---

## 3. Current Architecture & Weaknesses (with file refs)

**What exists today (correct — do NOT rip out):** flat `product.template`, one
per item, Odoo auto-creates exactly one variant; `wms_product_kind` (16 values)
drives SKU prefix / default UoM / returnability / expiry; auto SKU
`<PREFIX>-<NNNNN>` via `ir.sequence`; auto Code128 (=SKU) + auto EAN-13 alias;
carton aliases with `units_per_scan`; onboard wizard with pre-save dup checks;
UoM seeded create-time from kind.

| # | Weakness | Verdict |
|---|---|---|
| W1 | No brand/form/strength identity → same molecule across brands is unrelated rows | **FIX (cheap)** — deferred to P1 |
| W2 | No curated `product.category` family tree | **FIX (cheap)** — deferred to P1 |
| W3 | Master sprawl: same item typed two ways, no dup detector at create | **FIX (high value)** — **name-dup warning shipped; semantic detector needs P1 fields** |
| W4 | EAN-13 prefix `89011110` in GS1-India `890` range | **FIXED (P0)** |
| W5 | `create()` stamps SKU into *template* vals; breaks under multi-variant | **Avoided by rejecting variants** |
| W6 | `_wms_ensure_barcodes()` stamps every variant the same `default_code` | **Avoided by rejecting variants** |
| W7 | No reprint/replace-on-damage flow | **FIX (thin wizard)** — deferred (see appendix gotcha: alias needs an `active` field + `resolve()` change) |
| W8 | Expiry template-level, not per-lot | **DEFER** — separate approval |
| W9 | No Purchase-UoM conversion for buy-bulk/consume-small | **FIX (targeted)** — deferred (maps to `product.supplierinfo.product_uom_id` + `min_qty`) |

W5/W6 are the proof that adopting variants is *more* work AND *more* risk than
the flat model — they vanish entirely if we don't adopt variants.

---

## 4. Proposed Product-Master Design

### 4.1 The identity rule (state once, operators internalize it)
- **Different brand, form, OR strength → a NEW product** (new template, new SKU,
  new barcode).
- **Different size/pack of a product you already stock in its base unit → a
  packaging line** (`wms.barcode.alias`) on the existing product.
- **A distinct purchase pack you receive and scan as a unit (10-tab strip, 50 kg
  sack) → a NEW product** (own SKU + barcode).

> ⚠ The review flags 4.1 as the biggest daily-operator hazard: the sack/can
> examples sit on the boundary between "new product" and "packaging line." Before
> building the wizard step, replace the judgement call with a mechanical rule the
> keeper can apply without thinking — e.g. *"if the box has its own barcode, scan
> it and let the system classify."*

### 4.2 Data model (additive only — zero new master models)
On `product.template`, add (deferred to P1): `wms_brand` (normalized **Char**, per
the review — not a new model until brand-level reporting is requested), `wms_form`
(Selection: tablet/syrup/gel/spray/liquid/powder/ointment/other — *suggests* base
UoM), `wms_strength` (Char), and wire `categ_id` to a curated `product.category`
tree. These three are the **family key**: searching `wms_brand` / `categ_id` /
SKU-prefix returns the whole family without any variant tree.

> ⚠ For the duplicate detector to actually prevent sprawl, the identity fields
> must be **mandatory at least for medicine** — otherwise blank fields give the
> detector nothing to match on (review). Make them required-for-medicine when P1
> lands.

### 4.3 The gaushala examples — exact mapping

Each row is **one `product.template`** with its single auto-variant carrying the
SKU + Code128 + EAN-13.

| Real item | template name | kind | categ_id | brand | form | strength | base uom | SKU | Code128 | EAN-13 alias |
|---|---|---|---|---|---|---|---|---|---|---|
| Paracetamol BrandA Tablet 500mg 10-pack | Paracetamol 500mg Tablet 10s (BrandA) | medicine | Medicine▸Analgesic | BrandA | tablet | 500 mg | Units | `MED-00001` | same | `02…` (auto) |
| Paracetamol BrandA Syrup 100ml | Paracetamol Syrup 100ml (BrandA) | medicine | Medicine▸Analgesic | BrandA | syrup | 250mg/5ml | L | `MED-00002` | same | `02…` |
| Paracetamol BrandB Gel 50g | Paracetamol Gel 50g (BrandB) | medicine | Medicine▸Analgesic | BrandB | gel | — | kg | `MED-00003` | same | `02…` |
| Cow Feed Premium 5kg | Cow Feed Premium 5kg | feed | Feed▸Concentrate | — | powder | — | kg | `FEED-00001` | same | `02…` |
| Phenyl BrandX 1L | White Phenyl 1L (BrandX) | sanitation | Sanitation▸Disinfectant | BrandX | liquid | — | L | `SAN-00001` | same | `02…` |

> **Note (review):** the auto SKU is `KIND-NNNNN`, which does *not* encode
> brand/form/pack — uniqueness of the *key* is guaranteed, but two genuinely
> different packs both just get the next number. Human disambiguation is delivered
> by the brand/form/strength **fields** (on the label, in search), not the SKU.
> The structured-SKU scheme in §5 is **deferred** as cosmetic.

**Why NOT `product.attribute`/variants (REJECTED so it's never reopened):**
(a) Form changes the UoM and UoM is template-level → the variant grid is
structurally impossible for the gaushala's #1 axis. (b) Verified
`create()`/`_wms_ensure_barcodes()` logic assumes one variant and would leave
multi-variant templates SKU-less with colliding blank barcodes. (c) The
attribute-config UI is exactly the DB-concept exposure the First Principle forbids
for non-technical storekeepers. (d) Cartesian generation is the documented cause
of "exploded unmanaged duplicates." **Value < complexity → REJECT.**

---

## 5. SKU Strategy

**Today (kept as the real key):** `<KIND>-<NNNNN>` from the per-kind
`ir.sequence` (RM-, MED-, FEED-, SAN-…). A non-technical operator never invents a
code; the key is short, immutable, easy to read aloud and hand-key.

**Structured composition** (`KIND-ITEM-BRAND-FORM-PACK`) is **deferred /
cosmetic** (review): it manufactures an abbreviation-map problem the trust does
not have, and the human-readability win is largely illusory while the keying-error
cost is real. If ever added, it is an optional *display* string, not the key.
`_check_sku_prefix` (`product_template.py:756-792`) already permits a structured
form (it only enforces the kind prefix) — but note it does **not** enforce the
charset/length grammar §5 once described; those would need new validation if they
ever matter.

No volatile data (price/supplier) is ever encoded in a SKU — those live in
`standard_price` / `product.supplierinfo`.

---

## 6. Barcode Strategy

- **One Code128 per template's variant, equal to the SKU** — human and scanner
  read the same string. Code128 carries its own mod-103 check.
- **One EAN-13 alias per product** for pure-numeric scanners — auto-minted with
  GS1 checksum (`_ean13_checksum`).
- **Uniqueness:** Odoo `barcode_uniq` (product) + `_barcode_unique` (alias) +
  alias collision check against product/location/lot. One unique barcode per
  stockable unit.
- **Carton/multi-pack:** `wms.barcode.alias` with `units_per_scan = N`. Keep it
  canonical (already integrated with scan wizards). Native `product.uom` is
  *stricter* not equivalent (its `barcode` field is required+unique in 19), so the
  decision to keep the alias stands; migration is value-neutral, not done now.
- **P0 FIX (shipped):** EAN-13 sequence prefix `89011110`→`02`, padding `4`→`10`
  (body stays 12 digits → +check = 13). Off the GS1-India registered range onto
  the restricted-circulation range. `noupdate` isolates existing aliases; a
  post-migration repoints the live sequence. A test asserts every new product
  gets a valid 13-digit EAN-13 (guards the silent-no-barcode regression the naive
  fix would have caused).
- **Reprint/replace (W7, deferred):** mint a *new* alias for the same product and
  mark the old inactive. **Gotcha (review):** `wms.barcode.alias` has **no
  `active` field** today and `resolve()` does a plain (active-only) search — so
  "both old and new scans still resolve" requires adding an `active` column AND
  changing `resolve()` to `active_test=False`. It is a small subsystem change, not
  a pure wizard. Design carefully before building. Gate on
  `group_wms_can_manage_catalog` and write a `wms.audit` line.

---

## 7. UoM Strategy (Odoo 19 CE-accurate)

- **Base/stock UoM** = `product.template.uom_id`, seeded create-time from kind
  (fluid→L, feed→kg, else Units), to also be *suggested* by `wms_form`. Locked
  once stock exists (Odoo guards `uom_id` against change when quants/moves exist —
  *that* is the lock, distinct from how conversions are structured via
  `relative_uom_id`). Create-time-only seed is correct; keep it.
- **Conversions** are valid only within a shared reference tree: g↔kg and ml↔L
  convert; kg↔L does not. Never a reason to split a master.
- **Purchase UoM ≠ Stock UoM (W9, deferred):** for buy-bulk/consume-small (feed
  by 50 kg sack, issued by kg; phenyl by 5 L can, issued by L). In Odoo 19 CE this
  lives on **`product.supplierinfo.product_uom_id`** (+ `min_qty`, price in that
  UoM) — *not* a generic "pack qty + UoM" pair, and `uom_po_id` was removed. The
  chosen purchase UoM must share the stock UoM's `relative_uom_id` tree or the
  write is rejected.

---

## 8. Guided Product-Creation Wizard Flow

> **Review verdict:** keep the **flat editable list** (paste-200-rows) as the
> primary path; do NOT force an 11-step stepper on a shared-PC keeper (it destroys
> bulk onboarding and adds abandonment risk). Put the high-value controls
> (duplicate warning, label preview) on the existing single screen, and offer a
> guided single-item mode only as an *alternative*.

The genuinely valuable controls, in priority order: **(1) duplicate detector**
(shipped: name-dup warning; semantic version needs P1 fields), **(2) live SKU +
barcode + label preview**, **(3)** brand/form/strength capture (P1). The current
`_do_onboard` already does ~90% of creation (auto SKU/barcode/UoM, alias rows,
initial stock, label print).

---

## 9. Label + Search Strategy Deltas

- **Direct TSPL printing** (`wms.label.printer`) — extend the label to print
  `wms_brand` / `wms_form` / `wms_strength` so a shelf label disambiguates
  BrandA-Tablet from BrandA-Syrup. ⚠ Define a **truncation priority** (drop
  strength first, then form) so three extra fields don't overflow the 100×25 mm
  label and make it *less* scannable (review).
- **`/wms/find`** — already searches barcode / default_code / name and resolves
  aliases; add brand + category filter chips and show brand/form/strength on the
  result card.
- **Product list** — add `wms_brand`, `wms_form`, `categ_id` as search/group-by
  facets so "all paracetamol" or "all BrandX" is one click. ⚠ Confirm seeding the
  category tree does **not** reparent existing products' `categ_id` (would silently
  move history under new nodes) and check `wms_ai_forecast` / `wms_reports`
  rollups (review).

---

## 10. Value-Gated GAP Analysis

| Problem | Impact | Effort | Verdict |
|---|---|---|---|
| Brand/Form/Strength identity (W1) | Family searchable; brand on label | Low | **KEEP** (P1) |
| Curated `product.category` tree (W2) | Reporting + reorder by family | Low | **KEEP** (P1) |
| Duplicate detector (W3) | Prevents master sprawl | Low-Med | **KEEP (highest value)** — name-warning shipped; semantic needs P1 |
| EAN-13 internal-prefix fix (W4) | No vendor-barcode range overlap | Trivial | **DONE (P0)** |
| Purchase-UoM, buy-bulk (W9) | Accurate on-hand for sacks/cans | Med | **KEEP** (deferred) |
| Reprint/replace-on-damage (W7) | Damaged-label recovery + audit | Low-Med | **KEEP** (deferred — needs alias `active` + resolve change) |
| `product.attribute` variant engine | "industry standard" | High | **SKIP** — impossible UoM axis; breaks stamping; DB-UI exposure; sprawl |
| Per-UoM barcode matrix | carton≠each barcodes | Med | **SKIP** — alias already covers it |
| Composite/kit items | assemblies | Med | **SKIP** — gaushala never assembles/sells |
| Numeric-range attr generators | auto size ranges | Med | **SKIP** — spawns dead SKUs |
| `wms.brand` as a model | brand entity | Low | **SKIP for now** — use normalized Char (review) |
| Structured SKU composition | cosmetic readability | Med | **SKIP for now** — keep `KIND-NNNNN` key (review) |
| Migrate alias → `product.uom` | one fewer model | Med | **DEFER** — value-neutral |
| Per-lot FEFO (W8) | FEFO for medicine/feed | Med-High | **DEFER** — separate approval |

---

## 11. Phased, Backward-Compatible, Data-Safe Plan

**Invariant across ALL phases:** existing templates, SKUs, Code128 barcodes,
EAN-13 aliases, `stock.quant`, `stock.move.line` history and `wms.audit` lines are
**never rewritten**. Every phase is additive and ships test → CI → main.

| Phase | Scope | Migration | Risk | Status |
|---|---|---|---|---|
| **P0** | EAN-13 prefix `89011110`→`02`, padding 4→10 (+test) | `noupdate` record; post-migration repoints live sequence; existing aliases untouched | Low | **shipped v19.0.31.0.0** |
| **P-dup** | live duplicate-name warning in onboard | none (onchange) | Low | **shipped v19.0.31.0.0** |
| **P1** | identity fields (Char brand, form, strength) + curated category tree + search/group facets; required-for-medicine | additive columns, NULL default | Low | next |
| **P2** | duplicate *detector* (semantic, keyed on identity) on the existing single screen | UI/logic only | Low-Med | after P1 |
| **P4** | Purchase-UoM → `product.supplierinfo.product_uom_id` + `min_qty`, buy-bulk kinds | additive supplierinfo rows | Med | later |
| **P5** | reprint/replace-on-damage (needs alias `active` + `resolve(active_test=False)` + audit + ACL) | additive column + resolve change | Low-Med | later |
| **P6** | brand/form/strength on TSPL label (+ truncation priority) + `/wms/find` chips | view/report/controller | Low | later |
| **DEFER** | per-lot FEFO (W8) | separate approval | Med-High | out of scope |

Each data-touching phase ships with its own assertions (review): P0 → "every new
product gets a valid 13-digit EAN-13" (shipped); P4 → conversion correctness;
P5 → "a deactivated alias still resolves."

---

## 12. Open Decisions for the Owner

1. **`wms_brand`: Char (recommended now) vs Many2one model** — start Char; promote
   to a model only when brand-level reporting is actually requested.
2. **Carton model: keep `wms.barcode.alias` (recommended)** vs migrate to
   `product.uom` — keep; revisit only if a native-integration need appears.
3. **Per-lot FEFO (W8): approve as a separate future release?** — recommended
   yes-but-later (touches stock history; own approval + test cycle).
4. **Back-fill brand/form/strength on the existing catalog: lazy vs one-time pass?**
   — ⚠ lazy means "all paracetamol" search misses pre-existing items until each is
   edited; if family-search-from-day-one matters, commit to a one-time guided pass
   (review). Recommendation: a one-time pass when P1 lands, since the live catalog
   is still small.

---

## Appendix — Adversarial Review (verbatim findings that shaped §0)

**Overall verdict: SOUND_WITH_CHANGES.** The core (flat model + grouping fields +
reject variants) is correct; the *additions* were over-built.

**Over-engineering (cut/deferred):**
- `wms.brand` as a new model — a brand is a label, not an entity; use a normalized
  Char (95% of the value, zero new model/menu/ACL/view).
- **Structured SKU composition** — the single most over-engineered piece;
  manufactures an abbreviation problem; keep `KIND-NNNNN` as the key.
- **11-step stepper** — worse than the current one-screen paste-200-rows flow;
  keep the flat list, add the dup detector to it.
- **9-cell ERP matrix** — decision-theater; the First Principle alone justifies
  the conclusion.

**Data-migration risks (the important one is first):**
- **The naive P0 was BROKEN.** `_next_ean13` hard-requires `len(twelve)==12` and
  returns `''` otherwise (→ no alias minted). Prefix `2`/`02` with the *old*
  padding 4 → 5–6 digit body → guard fails → **every future product gets a Code128
  but NO EAN-13**, a silent regression surfacing only on a numeric-only scanner.
  **Fix: prefix `02` + padding 10 (=12), with a unit test asserting len==13.**
  *(This is exactly what shipped.)*
- W4 collision premise is overstated — DB constraints already reject duplicate
  barcodes at insert; the `02…` range is best-practice **hygiene**, not a
  safety-critical fix.
- Lazy back-fill → split-brain catalog; family search misses old items until
  back-filled (scope the claim honestly or commit to a one-time pass).
- P5 reprint needs an `active` field on the alias + `resolve(active_test=False)` —
  not the "thin wizard" it was billed as.

**Operator-simplicity risks:** the "new product vs add-a-pack" call is the biggest
daily hazard (make it mechanical); the stepper adds friction; label crowding needs
a truncation rule; structured SKUs are harder to read aloud/hand-key.

**Odoo accuracy fixes folded into the design:** purchase UoM field is
`product.supplierinfo.product_uom_id` (+ `min_qty`), not a generic pair;
`product.uom.barcode` is required+unique (alias is stricter-not-equivalent
rationale); the UoM **lock** is the quant/move guard on `uom_id`, distinct from the
`relative_uom_id` conversion tree; `_check_sku_prefix` enforces only the prefix,
not the structured grammar.

**Missing considerations to honor when P1+ land:** identity fields must be
**mandatory-for-medicine** or the detector has nothing to match; state the final
EAN-13 digit budget + rollover plan (now: `02` + 10 digits); ship per-phase tests
for data-touching changes; confirm the category seed does not reparent existing
`categ_id` (forecast/report rollups); gate the reprint wizard on
`group_wms_can_manage_catalog` + write a `wms.audit` line; define a cutover/removal
for the old onboard path so two creation paths don't diverge.

**Recommended first release (adopted verbatim as §0):** ship ONLY a corrected P0 +
the duplicate warning; defer the brand model, structured SKU, stepper, P4 and P5
until the identity fields are proven necessary and made mandatory-for-medicine.
