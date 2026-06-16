# Product Master Expansion — Phased Build Spec

**Dakshin Vrindavan Gaushala WMS (Odoo 19 CE)** · Status: **approved, phased build in progress** · Date: 2026-06-16

> Output of the second design sprint (6 grounded analysts → architecture-lead
> synthesis → adversarial review). It implements the **owner's expanded
> enterprise model**, which deliberately overrides the minimalist deferrals in
> [PRODUCT-MASTER-ARCHITECTURE.md](PRODUCT-MASTER-ARCHITECTURE.md) §0/§5/§12 (the
> owner chose structured SKUs + brand-as-master + assisted migration + an
> editable tree). That earlier doc remains the record of *why the variant engine
> is rejected*; this doc is the *build plan* for everything layered on the flat
> model.

**Programme invariant (every phase):** *additive only* — never UPDATE/rewrite an
existing `product.template`/`product.product` row, its `default_code`, its
Code128 `barcode`, its `wms.barcode.alias`, `stock.quant`, `stock.move.line`, or
`wms.audit`. New behaviour applies to **new products** and **opt-in admin
actions** only.

---

## 1. Executive build decision

1. **Flat one-`product.template`-per-stockable-identity stays.** Each owner "row"
   (Family × Brand × Variant × Form × Strength × Pack) = one template, one
   auto-variant, one SKU, one Code128, one EAN-13. The variant engine stays
   rejected (Form drives template-level UoM; `create()`/`_wms_ensure_barcodes()`
   assume one variant).
2. **Family, Brand, Form become small MASTER models with a stable `code`**
   (`wms.family`, `wms.brand`, `wms.form`), cloning the `wms.department` pattern.
   The `code` is the **drift-proof SKU abbreviation**, entered once and reused by
   deterministic lookup — this is what defuses the earlier review's
   "abbreviation drift" objection to structured SKUs.
3. **Variant, Strength, Pack-Size stay Char on the template.** Strength **reuses
   the existing `wms_dosage`** field; Size **reuses the existing `wms_size`**.
   Only `wms_variant` and `wms_pack_size` are net-new Char.
4. **kind-vs-Category — BOTH coexist, never merge.** `wms_product_kind`
   (18-value Selection) stays the code-governed engine driving the SKU prefix,
   the per-kind `ir.sequence`, the default UoM, and the returnable/expiry maps.
   Native `product.category` becomes the admin-editable enterprise tree + home of
   the per-category required-field matrix. The only coupling is a **one-way**
   `wms_default_kind` on `product.category` (category → suggested kind in the
   wizard). Seeding the tree **never reparents** existing `categ_id`.
   *(Critic: correct. Plus a hard rule — every category leaf carries a kind, and
   the wizard falls back to `consumable` if one is somehow missing.)*
5. **Structured SKU = the human string IS `default_code`, with the per-kind
   sequence number as the immutable trailing uniquifier:**
   `KINDPREFIX-FAMILY-BRAND-[VARIANT]-FORM-[STRENGTH]-[PACK]-NNNNN`. One sequence
   draw (reuse the `NNNNN` the existing `next_by_code` already returns), so
   `UNIQUE(default_code)` can never collide and `_check_sku_prefix` passes
   unchanged. SKU is **frozen** once stock exists or a label is printed.

---

## 2. Final data model

### New models (`wms.coded.master` abstract base → 3 registers)

| Model | Purpose | Key fields |
|---|---|---|
| `wms.family` | Generic group (Paracetamol, Cow Feed, Liv52) | `name`; `code` UNIQUE ≤6; `sequence`; `active` |
| `wms.brand` | Manufacturer/label (Cipla, Himalaya, Local) | `name`; `code` UNIQUE ≤6; `sequence`; `active` |
| `wms.form` | Form / =Model for tools (Tablet, Syrup, Drill12V) | `name`; `code` UNIQUE ≤4; `default_uom_id`; `sequence`; `active` |

`code` is uppercased + alphanumeric-checked on create/write; the length cap is a
per-model class attribute (`_code_max_len`).

### New fields on `product.template` *(P2)*

`wms_family_id` (M2o), `wms_brand_id` (M2o), `wms_form_id` (M2o), `wms_variant`
(Char), `wms_pack_size` (Char), `wms_product_code` (Char — immutable PRD-NNNNNN,
UNIQUE), `wms_sku_frozen` (Bool, **non-stored** compute — true once the product has
stock/movement). **Reuse** `wms_dosage` (Strength) — relabelled in the view only,
never a field rename. *(The `wms_identity_key` precompute from the spec draft was
dropped as unnecessary — the soft detector searches the identity fields directly.)*

### New fields on `product.category` *(P1, shipped)*

`active` (Bool — **Odoo 19 CE product.category genuinely lacks one**),
`wms_default_kind` (Selection), `wms_req_brand/form/strength/size/pack` (Bool),
`wms_form_is_model` (Bool), `wms_effective_req_*` (Bool, compute+store+recursive —
ORs each flag down the parent chain so sub-categories inherit a branch's policy).

### Retained unchanged (the engine)
`wms_product_kind`, `KIND_SKU_PREFIX`, `KIND_SEQ_CODE`, `KIND_DEFAULT_UOM`, the
returnable/expiry maps, `uom_id`, `default_code`, `barcode`, `wms.barcode.alias`,
`_check_sku_prefix`, `_sku_unique` (note: on **`product.product`**, not the
template — critic correction), `_next_ean13`, `data/wms_sku_sequences.xml`.

---

## 3. Per-category required-field config

Booleans live directly on `product.category` (no separate model/ACL — category
write already flows to `group_wms_manager` via `stock.group_stock_manager`).
`wms_effective_req_*` recursively OR a node's flag with its ancestors. Enforcement
is **P3, two layers**: (A) a **guarded** `@api.constrains` on `product.template`
that only fires for products **without stock/barcode** (so it never breaks
edits to the legacy catalogue), and (B) dynamic `required=` on the wizard line.
The seed sets the owner's matrix (Medicine/Supplement = all required; Feed =
Brand/Size/Pack; Tools/Spares = Brand/Form; Chemicals/Cleaning = Brand/Form/Size/
Pack; Consumables = optional) as tunable defaults — **inert until P3**.

---

## 4. Editable category tree

Seeded as brand-new `product.category` records (`noupdate="1"`) writing
`categ_id` on **no** existing product. Admin CRUD is native (add via quick-create,
rename, move via `parent_id`, reorder via `sequence`) plus **disable** via the new
`active`. A future, separately-gated `merge` action (reassign + archive) is the
one sanctioned `categ_id`-rewriting path — **deferred out of P1** (critic: it
violates the additive invariant and must ship gated/logged/tested on its own).

---

## 5. Structured SKU — TWO IDENTIFIERS *(P2)* — owner decision 2026-06-16

The owner rejected both a trailing sequence number *and* collision auto-suffixing
in favour of the genuine enterprise pattern: **separate the immutable internal id
from the readable item number.**

1. **Business SKU = `default_code`** = `KINDPREFIX-FAMILY-BRAND-[VARIANT]-FORM-
   [STRENGTH]-[PACK]` — **no trailing number**. Charset `[A-Z0-9]` per segment;
   Family/Brand/Form from the stored `code`; Variant/Strength/Pack are
   deterministic squeezes of the typed text; optional segments collapse (never
   `--`); Family+Brand are required for the structured path. This is what
   operators search, print and recognise.
2. **Internal Product Code = new `wms_product_code`** = `PRD-NNNNNN` from a new
   global `ir.sequence` (`wms.product.code`, padding 6). **Always** stamped at
   create, **immutable forever** (blocked from any write), `index`, UNIQUE,
   `copy=False`. This is the stable reference that guarantees uniqueness
   regardless of how the readable SKU is composed or edited.
3. **Collision policy = BLOCK, never suffix.** Before create, if the composed
   Business SKU already exists on another product, raise a friendly `UserError`
   naming the existing product + its `PRD-` code and asking the operator to adjust
   Brand / Variant / Pack Size / Strength. No `-2`/`-3` auto-append (the owner:
   "force the catalog to be corrected"). This is the hard form of the dup
   detector; the soft onchange warning (§7) is the early heads-up.
4. **Fallback:** when Family or Brand is absent (legacy-style quick entry / bulk
   paste without identity), `default_code` falls back to the existing
   `KIND-NNNNN` per-kind sequence exactly as today — so the per-kind sequences are
   retained. `wms_product_code` (PRD) is stamped on **every** product regardless.

**Mechanics:** compose inside `create()`; `_check_sku_prefix` already accepts the
structured form (it only checks the leading kind segment). `_sku_unique` is on
**`product.product`** (not the template) — the UNIQUE(default_code) there backs the
block. Code128 `variant.barcode = default_code` (Business SKU) unchanged; the v31
EAN-13 numeric alias (the daily scan) is fully independent → zero risk.

**Freeze (as built, post adversarial review):** a **live** `_wms_in_circulation()`
check (queries `stock.quant` / `stock.move.line`) — NOT a stored compute. A stored
compute on `stock_quant_ids` was unreliable (its invalidation doesn't fire on
`stock.quant._update_available_quantity`, so it let a stale "not frozen" value
through — which is why an unmodified `test_fpat_fx3` passed by accident). The
write-guards call the live check directly; `wms_sku_frozen` is a non-stored UI
mirror. Freeze is **stock-only** (the owner's stated trigger) — the design-phase
"label-printed" leg was dropped as dead code. Once in circulation, `default_code` and
Code128 **renames** are blocked (clearing / filling a blank stays allowed, so
`_wms_ensure_barcodes` + back-fill still work); `wms_product_code` is *always*
immutable. **Behaviour change:** renaming a barcode/SKU after stock is now blocked
(the only collateral was `test_fpat_fx3`, reordered to set its barcode pre-stock; no
production flow renames after stock). The collision gate is archive-inclusive, covers
the manual-`default_code` path, and blocks in-batch duplicates in one `create()`; M2o
vals are resolved via `_wms_vals_id` against command-style values. Existing products
get a `PRD-` code via an additive back-fill migration (new column only).
`docs/14-sku-naming.md` rewritten for the two-identifier model.

---

## 6. Assisted migration *(P4)*

An **opt-in transient wizard** `wms.product.backfill` (NOT a `migrations/` script —
a parser bug in `-u all` would fail every upgrade; a wizard cannot). Deterministic
offline parser (no AI), 4 ordered passes per `product.name` (name never mutated):
Strength regex → Pack+Unit regex (unit advisory only, never retrofit `uom_id`) →
Brand+Form dictionary lookup (word-boundary, longest-match, explicit precedence) →
Family = residual (with a floor below which Family is left NULL, not guessed —
critic). Confidence tiers ≥95% auto / 70–95% suggest / <70% review; define
behaviour when a category's required set is empty (critic). Review wizard: dry-run
preview → editable list with per-row Accept → additive `write()` of identity
fields only. Reversibility needs a provenance marker per pass (critic). Idempotent
(NULL-only candidate filter). Never recomposes existing SKUs.

---

## 7. Guided wizard + bulk + dup detector + search/label *(P3/P5)*

Bulk paste-200-rows list stays the primary path; add a separate single-item
**stepper** (`wms.product.create`) sharing **one** create helper factored out of
`_do_onboard()` so they cannot diverge. Upgrade the v31 `_onchange_name_dup_warning`
into an **identity-tuple** detector (Category+Family+Brand+Variant+Form+Strength+
Pack), non-blocking, with an "open the existing one" affordance — and reconcile so
it doesn't double-fire with the shipped name-warning (critic). Search facets +
`/wms/find` chips (`brand:`/`family:`/`form:`/`cat:`). Label: add Brand·Form·
Strength to the subtitle with a **truncation priority** (drop strength → form →
brand) *before* the `[:48]` clips — and the barcode payload (`= default_code`)
must never change so printed labels keep scanning (note: both subtitle `:280`
**and** code `:288` are clipped).

---

## 8. Phased build plan

| Phase | Scope | Risk | Status |
|---|---|---|---|
| **P1** | 3 master models + `product.category` extension (active, default-kind, req matrix, recursive effective-req) + editable tree seed + masters seed + ACL + manager menus/views | Low (additive tables + noupdate seeds) | **shipped v19.0.32.0.0** |
| **P2** | identity fields on template + structured-SKU builder + freeze (live check) + collision block + soft dup detector | Med | **shipped v19.0.33.0.0** |
| **P3** | guided stepper + shared create helper + guarded required-matrix enforcement | Med | next |
| **P4** | assisted-migration wizard (opt-in, reviewable, reversible) | Low | after P3 |
| **P5** | label + `/wms/find` + search deltas | Low–Med | after P4 |
| **later** | category `merge` action (gated/logged); per-lot FEFO (separate approval) | Med | deferred |

**CI note (critic correction):** do **not** set `PREV_TAG` to the current
release (that makes prev→HEAD a no-op). It currently sits at `v19.0.20.0.0`, which
gives a *wider* upgrade test — left as-is. Each phase must keep `prev-tag → HEAD
-u all` green and carry non-skipped `@tagged('wms')` tests. Cross-addon: the
onboard/label/backfill wizards live in `wms_barcode`, the find controller in
`wms_reports`, the masters + SKU builder in `wms_location` — P3/P5 will bump those
manifests too.

---

## 9. Open decisions for the owner

1. **SKU uniqueness — RESOLVED (owner, 2026-06-16):** two identifiers — a readable
   `default_code` Business SKU (no tail) + an immutable `wms_product_code`
   (`PRD-NNNNNN`); Business-SKU collisions **block** creation (no auto-suffix).
   See §5.
2. **Code length caps** — Family/Brand ≤6, Form ≤4. *(Built; confirm.)*
3. **Freeze trigger — RESOLVED:** stock/movement only (a live `_wms_in_circulation`
   check). The "label-printed" leg was dropped as dead code.
4. **Starter `code` dictionary** — P1 seeds common forms/brands/a few families;
   the owner supplies/edits the rest (esp. families).
5. **Required-matrix tuning** — seeded per the owner's branch matrix; refine
   per-leaf before P3 turns enforcement on (e.g. First-Aid has no strength).

---

## 10. P1 as-built (v19.0.32.0.0 — `wms_location` 19.0.3.20.0)

New: `models/wms_product_master.py` (`wms.coded.master` base + `wms.family`/
`wms.brand`/`wms.form`), `models/product_category.py` (the extension),
`views/wms_product_masters_views.xml` (lists/forms/actions, the category-form
WMS-classification group, 4 manager-gated menus under Configuration),
`data/wms_product_masters_data.xml` (14 forms with suggested units, 5 brands, 4
example families), `data/wms_category_tree.xml` (the enterprise tree, create-only),
`tests/test_category_config.py` (13 tests). Edited: `models/__init__.py`,
`security/ir.model.access.csv` (+6 rows), `__manifest__.py`.

**Critique items deferred to later phases** (recorded so they aren't lost):
`_sku_unique` is on `product.product`; the freeze field must be a stored compute
on `stock_quant_ids`; re-syncing Code128 on rename needs new code (current
`_wms_ensure_barcodes` only fills a blank); reconcile the dup detector with the
v31 name-warning; label clips at both `:280` and `:288`; assisted-migration needs
a Family-confidence floor + a provenance marker for reversibility.
