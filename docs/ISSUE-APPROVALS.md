# Issue approvals — min-life guard + high-value threshold

Two situations now route a Scan Issue through a **manager's approval** before
any stock actually leaves:

- **Requested too soon** — the *same department* re-requests the *same product*
  inside that product's minimum re-request window (the **min-life guard**).
- **Worth too much** — the issue's total value is over a configurable
  **high-value threshold**.

In either case the keeper types a **reason**, the request is held as a
**Pending Approval**, and a **Manager** must Approve or Reject it. The keeper
**cannot approve their own request** — by design there is no password prompt,
just a button the keeper's role cannot press. When approved, the system
**re-checks stock** and only then issues.

Everything that is below the threshold and outside the min-life window issues
**inline as before** — the gate adds nothing to the normal flow.

For the issue flow itself see
[docs/13-operations-playbook.md § 5](13-operations-playbook.md); for the
department dimension the min-life guard keys off, see
[docs/ISSUE-DIMENSIONS.md](ISSUE-DIMENSIONS.md).

---

## 1. The two triggers

### 1.1 Min-life re-request guard (too soon)

A product can carry a **minimum re-request interval** (in days). If the **same
department** asks for the **same product** again *within that window*, the
issue is held for approval.

- The interval is a product setting, in the product's "Usage limits" group on
  the WMS Classification page (and an optional onboard column). It is
  **Kind-seeded** — sanitation, textile and safety items default to **7 days**
  — and editable per product.
- When a product leaves its own interval at 0, a **global fallback** applies
  (System Parameter `wms_location.default_min_life_days`, default **0** = off).
  If both are 0, the product is never guarded.
- The guard is **per department**: *Veterinary* re-requesting the same item
  within the window is held, but a *different* department asking for the same
  item is **not** — the window is about one section over-drawing one product.

This catches a section re-drawing something it should still have, without
hard-blocking a genuine need.

### 1.2 High-value threshold (worth too much)

An issue whose **total value** (planned quantity × cost) exceeds the
**high-value threshold** is held for approval. The threshold is a System
Parameter (`wms_barcode.high_value_threshold`, default **Rs 5000**).

The issue value is **snapshotted at request time** — it is the value as it was
when the keeper submitted, not a figure that drifts later.

> These two are **softer** than the existing hard per-issue / daily caps. The
> hard caps still block outright; the approval gate instead routes the request
> to a manager with a reason.

---

## 2. What the keeper sees

When a Scan Issue trips either trigger:

1. The wizard shows a **reason** box and explains the issue needs a manager's
   approval (high value, or requested too soon).
2. The keeper **types the reason** and submits again.
3. Nothing is issued yet. The request is saved as a **Pending Approval** and a
   **manager is notified in Discuss** immediately.
4. The keeper can **open and see** the pending request (read-only) but has no
   Approve / Reject button — the keeper role simply does not carry that power.

The keeper's job is done at "submitted for approval"; the stock moves only once
a manager approves.

---

## 3. What the manager does — WMS → Operations → Approvals

Pending requests live under **WMS → Operations → Approvals** (manager-only; a keeper does
not see the menu). The list defaults to the **Pending** ones. Open a request to
see the snapshot — what, how much, which department / purpose / animal, the
value, why it was held, and the keeper's typed reason — plus the keeper's photo
if one was taken.

The manager then either:

- **Approve** — the system **re-checks live stock** (see § 5), creates the
  issue picking with the full audit trail and the carried-over photo, and marks
  the request **Approved**. The stock leaves at this point, not before.
- **Reject** — **nothing is issued**; the request is marked **Rejected** with
  the manager's note. The keeper can re-scan later if the need is genuine.

Both outcomes are written to the request's chatter (who decided, the value, the
reasons), so the decision is auditable.

> **A keeper cannot self-approve.** The Approve / Reject buttons are gated to
> the *WMS / Manager* role, the keeper has **read + create only** on the
> approval record (no edit), and the approve action **re-checks the manager
> role** when pressed. Three independent gates, no password handshake — the
> keeper literally cannot approve, even their own request.

---

## 4. The two System Parameters

Both live under **Settings → Technical → System Parameters** (Developer mode),
read with safe defaults so a missing or malformed value never crashes an issue.

| Key | Default | Effect |
|---|---|---|
| `wms_barcode.issue_approval_enabled` | `1` | **Master switch** for the whole approval gate (both triggers). Set to `0` to turn it off entirely — every issue then validates inline as before, with no approval step. |
| `wms_barcode.high_value_threshold` | `5000` | Rupee value above which an issue is held for approval. A non-numeric or missing value is treated as *disabled* (no high-value holds). |

The min-life side is configured per product (the re-request interval) plus the
global fallback `wms_location.default_min_life_days` — see § 1.1.

> Turning the master switch off is the quickest way to disable approvals
> globally without un-setting the per-product intervals; turn it back on and
> the existing intervals and threshold take effect again.

---

## 5. Approval re-checks stock before issuing

Time passes between the keeper's request and the manager's decision, and stock
can move in between. So **Approve does not blindly replay the original plan** —
it **re-plans against live stock**:

- If stock still covers the request, it issues the item (oldest stock first,
  the usual FIFO), with the original audit fields, department / purpose /
  animal, expected-return date and photo carried through.
- If stock **no longer covers it**, Approve **stops with a clear error** and
  issues **nothing** — the manager rejects and asks the keeper to scan again.
  There is never a half-issued picking.

Approval is also **idempotent**: a double-click or two managers acting at once
results in **exactly one** picking, never two.

---

## 6. References

- [docs/13-operations-playbook.md](13-operations-playbook.md) — the issue /
  consumption process, including the manager-approval note for high-value
  issues.
- [docs/ISSUE-DIMENSIONS.md](ISSUE-DIMENSIONS.md) — the department dimension
  the min-life guard keys off.
- [docs/08-security.md](08-security.md) — the role model and capability groups.
- [docs/RETURNABLE-ITEMS.md](RETURNABLE-ITEMS.md) — the returnable / overdue
  track, which shares the manager-notification path.
