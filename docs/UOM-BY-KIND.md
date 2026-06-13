# Unit of Measure by Kind

A product's base **Unit of Measure (UoM)** is now set automatically from its
**Kind** when it is created, so a fluid comes in as **Litre**, a feed as
**kg**, and everything else as **Units** — without anyone having to remember to
change the unit by hand. The UoM stays fully editable afterwards, and
**existing products are never touched**.

This removes the old trap where every onboarded product defaulted to *Units*
and a litre of oil or a kilo of feed had to be corrected manually (and often
was not).

For onboarding itself see [docs/13-operations-playbook.md § 1](13-operations-playbook.md)
and the [Admin Quick Start § 4](ADMIN-QUICK-START.md); for the product Kind
list see [docs/02-data-model.md](02-data-model.md).

---

## 1. How the default is chosen

When you onboard a product (or create one on the product form) **and leave the
UoM blank**, the Kind decides the base unit:

| Kind | Default UoM | Why |
|---|---|---|
| **Fluid** | **Litre** | Liquids are dispensed by volume |
| **Feed** | **kg** | Feed is weighed |
| **Everything else** | **Units** | Counted items (see note on Medicine below) |

So a *Fluid* product onboards as Litre, a *Feed* product as kg, and a Tool,
Spare, Sanitation item, Construction material, Stationery, Packaging, Pooja
item, Raw material, etc. all onboard as **Units**.

### 1.1 Medicine is Units on purpose

**Medicine onboards as Units, not millilitres.** Vials, strips and bottles are
counted, and the dose is recorded separately on the product. Defaulting
medicine to a volume unit would also wrongly trip the measured-item photo gate
on Scan Issue (see § 3), so medicine stays counted by default. Switch an
individual bulk-liquid medicine to mL by hand if you genuinely stock it by
volume.

---

## 2. Switching pipe / rope / cable / cloth to Metre

Some items are stocked or issued **by length** rather than by the piece. These
default to **Units** but are commonly switched to **Metre** per product:

- **Pipe / plumbing** — cut pipe sold by the metre.
- **Cable / wire (electrical)** — spools issued by length.
- **Rope** — sold by length.
- **Cloth / textile** — fabric issued by the metre.

There is **no special "length" Kind**. You pick **Metre** per product wherever
it makes sense:

- During onboarding, set the row's **UoM** column to **Metre** (the column is
  shown so you can override the kind default).
- Or open the product later and change its **UoM** to Metre.

If an item is **stocked as whole pieces but recorded by length**, keep the UoM
at **Units** and record the length in the product's length field instead.

---

## 3. The UoM stays editable

The kind only sets the **default** at create time. After that:

- The UoM is a normal, editable product field — change it any time the product
  has no stock yet.
- Choosing **Metre** for a measured item makes Scan Issue **require a photo**
  of the dispensed quantity (the same photo gate that already applies to Litre
  and kg). Counted **Units** items do not need a photo.

> Once a product has stock, Odoo blocks changing the UoM's *category*
> (e.g. Units → Litre) because it would invalidate the on-hand quantity. Set
> the right unit **before** you receive stock; that is exactly why the kind now
> seeds it at onboarding.

---

## 4. Existing products are untouched

This is a **create-time default only**. Products that already exist in the
catalogue are **never retrofitted** — their current UoM is left exactly as it
is, whatever it was set to before. There is no migration that rewrites unit on
existing products, by design: silently flipping the unit on a stocked product
would corrupt its on-hand figure.

In short:

- **New** product, blank UoM → Kind sets it (fluid → Litre, feed → kg, else
  Units).
- **New** product, UoM picked by the operator → the operator's choice wins.
- **Existing** product → unchanged.

---

## 5. References

- [docs/13-operations-playbook.md](13-operations-playbook.md) — SKU / item
  coding and the onboarding flow.
- [docs/02-data-model.md](02-data-model.md) — the product Kind model.
- [docs/RETURNABLE-ITEMS.md](RETURNABLE-ITEMS.md) — kind also seeds the
  returnable flag and expected-return period.
- [docs/ISSUE-DIMENSIONS.md](ISSUE-DIMENSIONS.md) — the issue dimensions
  captured at Scan Issue.
