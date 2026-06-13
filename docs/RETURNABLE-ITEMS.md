# Returnable items — expected return, overdue alert, Returns-due report

Some things you issue are meant to **come back** — tools, spares, equipment
lent out for a job. The WMS can mark a product **returnable**, stamp an
**expected return date** when it is issued, **alert managers** when it is
overdue and still out, list everything outstanding in a **Returns-due report**,
and clear the item the moment **Scan Return** brings it back.

This is an **advisory** track, not a hard lock: issuing a returnable item is
never blocked, and a missing return raises a notice rather than stopping work.

For the return flow itself see [docs/03-workflows.md](03-workflows.md) and
[docs/13-operations-playbook.md § 4](13-operations-playbook.md).

---

## 1. Marking an item returnable

Returnability is a product setting on the **WMS Classification** page of the
product form (and an optional column on the **Onboard Products** wizard):

- **Returnable** — the on/off flag. It is **seeded from the product's Kind**
  (tools and spares come in returnable; consumables and feed do not), and you
  can override it per product.
- **Expected return (days)** — how many days a returnable item is expected back
  in. Also Kind-seeded — **tools and spares default to 14 days**, textile and
  safety items to 7 — and editable per product. Leave it at 0 to fall back to
  the global default.

The expected-return field only shows when the product is returnable.

> The **global default** expected-return period is a System Parameter
> (`wms_reports.default_return_days`, default **7** days). It is used for
> any returnable product whose own expected-return is left at 0.

---

## 2. Issuing a returnable item stamps a return date

When **Scan Issue** issues a plan that includes a returnable product, the
resulting picking gets an **Expected return** date:

```
expected return date = issue date + the product's expected-return days
                       (or the global default when the product's is 0)
```

The keeper sees the proposed return date in the Scan Issue audit block before
validating (it only appears when a returnable product is on the plan). Issuing
the item is **not** blocked — the date simply drives the overdue alert and the
report below.

---

## 3. The overdue alert (daily)

A **daily background job** checks for returnable issues that are **past their
expected return date and not yet returned**, and notifies every WMS Manager in
their **Discuss inbox** (and by email when `wms_reports.alert_email` is set —
the same alert path used by the low-stock and backup alerts).

- The notice lists each overdue picking, the product(s), the department, and
  how many days overdue.
- It is **quiet when healthy** — if nothing is overdue, the job posts nothing.
- An issue that was **undone / reversed** never counts as overdue.

This means an item that goes out and never comes back surfaces on its own,
rather than being forgotten.

---

## 4. The Returns-due report

**WMS → Reports → Returns due / overdue** lists every returnable issue that is
still outstanding — both **due soon** and **already overdue** — with:

- the picking and the product,
- the **department** it went to and the **store keeper** who issued it,
- the **expected return date** and the **days overdue**.

The report is **read-only for keepers** and managers alike, so a keeper can see
what is still out without being able to edit it. An item drops off the report
as soon as it is returned (§ 5) or once the issue is reversed.

---

## 5. Scan Return clears a returnable item

When a returnable item comes back, run **WMS → Operations → Scan Return** as
usual. On a successful return, the WMS finds the matching open issue (by
product and department, newest expected-return first) and marks it
**returned** — which:

- takes it off the **Returns-due report**, and
- stops it being flagged by the **overdue alert**.

If no confident match is found, the return still succeeds and the item simply
stays listed as due — which is the safe outcome: nothing is silently
reconciled. This is advisory matching, not strict one-to-one accounting; the
report always errs toward *still showing it* rather than wrongly clearing it.

---

## 6. References

- [docs/03-workflows.md](03-workflows.md) — inbound / outbound / return flows.
- [docs/13-operations-playbook.md](13-operations-playbook.md) — receiving and
  issuing process.
- [docs/UOM-BY-KIND.md](UOM-BY-KIND.md) — Kind also seeds the returnable flag
  and the expected-return period.
- [docs/06-reports.md](06-reports.md) — every dashboard and report.
- [docs/22-gdrive-backup.md § 4.3](22-gdrive-backup.md) — the shared
  manager-notification path the overdue alert uses.
