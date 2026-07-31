# Issue dimensions — Department / Purpose / Animal

Every **Scan Issue** now records *where the stock went* in three structured
fields instead of the single free-form "Issued for" tag it used before:

- **Department** (required) — the cost centre / section that consumed the
  stock (Gaushala, Veterinary Hospital, Dairy, …).
- **Purpose / reason** (optional) — *why* it was issued (routine consumption,
  treatment, maintenance, …).
- **Animal / cow** (optional) — *which animal* it was for, when the issue is
  treatment for a single cow.

These ride on the resulting `stock.picking` alongside the unchanged audit
triplet (**Taken by / Ordered by / Store Keeper on duty**), so the consumption
reports can now be sliced by department instead of by the old six-way
"purpose" list. The old **Issued for** field is kept and auto-derived from the
department so every existing report and search keeps working — see § 5.

For the issue flow itself see
[docs/13-operations-playbook.md § 5](13-operations-playbook.md); for the
approval gate that can hold an issue see
[docs/ISSUE-APPROVALS.md](ISSUE-APPROVALS.md).

---

## 1. The three dimensions

| Dimension | Required | What it answers | Picked from |
|---|---|---|---|
| **Department** | **Yes** (defaults to *Other*) | Which section used the stock | The Department master |
| **Purpose / reason** | No | Why it was issued | The Purpose master |
| **Animal / cow** | No | Which animal it was for | The Animal register |

Department is the primary reporting dimension and is **always** set — the
wizard defaults it to **Other** so an issue is never blocked for want of a
department. Purpose and Animal are optional and left blank when they do not
apply (most routine consumption needs neither).

### 1.1 The Animal register

The Animal register is a deliberately **lightweight** herd list — it is not a
full livestock-management module. Each animal carries:

- **Name** — the cow's given name (required).
- **Tag** — ear-tag / token number (optional, unique when set).
- **Shed** — a free-text shed / pen label (not a storage location).
- **Age class** — Calf / Heifer / Cow / Bull / Ox / Other.

Animals are entirely optional on an issue; populate the register only if you
want per-animal treatment traceability.

---

## 2. The seeded departments

A fresh install seeds eleven departments. Ten are the trust's owner-specified
sections plus the always-present **Other** fallback:

| Department | Use it for |
|---|---|
| **Gaushala / Cowshed** | General cow-shed consumption |
| **Veterinary Hospital** | Medicines, dressings, treatment supplies |
| **R&D / Panchgavya** | Research and panchgavya production |
| **Dairy** | Milk handling, dairy operations |
| **Fodder & Agriculture** | Fodder, feed crops, farm inputs |
| **Kitchen / Bhojanalaya** | Kitchen / canteen consumption |
| **Maintenance** | Repairs and upkeep |
| **Construction / Project** | Building and project work |
| **Administration** | Office / admin use |
| **Temple / Pooja** | Ritual / pooja items |
| **Other** | Anything that fits none of the above (the default) |

A starter list of **purposes** is also seeded (routine feed, treatment,
cleaning, repair, construction, ritual, office, other). The **Animal**
register ships empty — the owner adds the herd later.

Departments and purposes are **archived, never deleted** — archiving a
department keeps it readable on every historical picking that used it, while
removing it from the picker for new issues.

---

## 3. Picking them on Scan Issue (Store Keeper)

In **WMS → Operations → Scan Issue (FIFO)**, after planning the deduction and
filling the audit triplet:

1. **Department** — pick the section the stock is for. It is pre-filled with
   **Other**; change it to the real section (e.g. *Veterinary Hospital* for a
   medicine going to treat a cow).
2. **Purpose / reason** — optionally pick why (e.g. *Animal treatment*). Leave
   blank for routine consumption.
3. **Animal / cow** — optionally pick the animal, when the issue is for one
   specific cow. Leave blank otherwise.
4. **Validate** as usual.

The validated picking records all three, and the chatter line names the
department, purpose, and animal so the audit trail reads in plain language.

> A keeper can only **pick** from the existing departments / purposes /
> animals — they cannot add new ones. Ask a manager to extend the masters
> (§ 4).

---

## 4. Configuring departments, purposes and animals (Manager)

The three masters live under **WMS → Configuration** and are **manager-only**
(gated to *WMS / Manager*, the same as the Store-Keeper roster). A keeper sees
neither menu.

| Menu | What you maintain |
|---|---|
| **WMS → Configuration → Departments** | The department list + each one's display order |
| **WMS → Configuration → Purposes** | The purpose / reason list |
| **WMS → Configuration → Animals** | The herd register (name, tag, shed, age class) |

To add a department: open **Departments → New**, type the name, set the
display **sequence** if you want it higher in the picker, and save. It is
immediately available on the next Scan Issue.

To retire one: open it and **Archive** it (do not delete) — it disappears from
the picker but stays legible on the pickings that already used it.

> **Animals** are the one master you are expected to grow over time: add each
> cow as it joins the herd so per-animal treatment issues can name it.

---

## 5. The Consumption report splits by Department

**WMS → Reports → Consumption Value** now uses **Department** as its primary
breakdown. Group or pivot the report by Department to see what each section
consumed by value, instead of the old six-way purpose split.

The legacy **Issued for** grouping is **retained as a secondary dimension** so
older saved filters and habits keep working through the transition. Both are
available in the report's group-by; Department is the one to reach for going
forward.

### 5.1 The legacy "Issued for" is auto-derived

Older issues carried a single **Issued for** tag with six values
(Cows / Pooja / Maintenance / Project / Administration / Other). That field
has **not** been removed:

- On every **new** issue, **Issued for** is **derived automatically from the
  chosen department** — each department maps to one of the six legacy codes
  (for example *Veterinary Hospital*, *Dairy* and *Fodder & Agriculture* all
  roll up to the legacy *Cows* code; *Maintenance* → *Maintenance*; *Temple /
  Pooja* → *Pooja*). You never set it by hand.
- On **existing** issues, the historical **Issued for** value is left exactly
  as it was, so no consumption history is lost.

This means any report, pivot, or search keyed off the old **Issued for** field
keeps reading correctly while the new, finer **Department** dimension carries
the detail the legacy six values could not (the new *Veterinary*, *Dairy*,
*Fodder*, *R&D / Panchgavya* and *Kitchen* departments did not exist in the old
list).

---

## 6. References

- [docs/13-operations-playbook.md](13-operations-playbook.md) — the issue /
  consumption process around the wizard.
- [docs/ISSUE-APPROVALS.md](ISSUE-APPROVALS.md) — when an issue is held for a
  manager's approval (department drives the min-life re-request guard).
- [docs/UOM-BY-KIND.md](UOM-BY-KIND.md) — how a product's unit is set.
- [docs/RETURNABLE-ITEMS.md](RETURNABLE-ITEMS.md) — returnable items and the
  overdue-returns report.
- [docs/06-reports.md](06-reports.md) — every dashboard and report.
