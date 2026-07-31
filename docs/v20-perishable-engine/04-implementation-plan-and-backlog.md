# v20 Implementation Plan + Backlog

> **Wave split tightened by the owner (2026-06-24).** Wave 1 = **inventory correctness + safety
> only** — including the recall-freeze and quarantine *exclusion* mechanisms (recalled/quarantined
> stock must be un-issuable from day one) but **not** their dashboards or analytics. Everything
> analytical, visual, or advanced moves to Wave 2. Plus three owner-added Wave-1 features:
> **duplicate-lot detection, lot barcode, lot timeline.** Every phase ends green (lint + full
> suite + CI) before the next. Commits small and logically separated.

## WAVE 1 — MVP (inventory correctness + safety). Ship → pilot → only then Wave 2.

**Wave 1 contents (locked):** per-lot tracking · batch+expiry capture · FEFO engine · lot-aware
receipt · lot-aware issue · auto-split across lots · expired block · FEFO-bypass approval ·
lot-aware issue reversal · recall freeze · quarantine location · unreserve recalled/quarantined
lots · per-lot expiry reports · migration tooling · complete automated test suite · **+
duplicate-lot detection · lot barcode · lot timeline · near-expiry receiving guard · **per-product
shelf-life policy · FEFO reservation · lot lock during edits** · extension hooks.** Nothing
analytical/visual — all dashboards/analytics → Wave 2.

| Phase | Delivers | Gate |
|-------|----------|------|
| **P0 Scaffold** | `wms_perishable` addon + `product_expiry` dep + post-init stub | installs clean; suite green |
| **P1 Lot + receipt** | perishable-kinds extension; `tracking='lot'`+`use_expiration_date` auto-enable; receipt batch/expiry/supplier fields; find/create lot, **never merge**, tracking guard; `stock.lot` lifecycle state + supplier meta; **duplicate-lot detection** (V20-006) | 3 receipts → 3 lots; dup batch detected; suite green |
| **P2 FEFO** | `stock.quant.wms_effective_expiry` (stored, indexed); override `_wms_sorted_for_removal`; `idx_quant_fefo`; **auto-split** across lots | earliest-expiry first, auto-splits; non-perishables still FIFO (regression); suite green |
| **P3 Issue safety** | per-lot expiry + FEFO-order + **resulting-balance preview**; **shortfall breakdown** (excluded expired/quarantined/recalled); expired **block** + manager override (reuse gate); FEFO-bypass warn+confirm; **lot-aware reversal** | expired blocked + override audited; bypass warns; reversal restores to original lot; suite green |
| **P4 Recall + Quarantine exclusion** | `wms.lot.recall` **freeze** (lot state + picker exclusion); Quarantine/Recall **location flags** + auto-create + picker-domain exclusion; **unreserve** a lot on freeze; minimal "hold/release lot" + "locate this lot" actions | recalled/quarantined stock un-issuable; open reservations cancelled on freeze; suite green |
| **P5 Reports + barcode + timeline** | per-lot Expiry-Alert re-key + configurable thresholds + digest + 2 self-diagnostics probes + settings; **lot barcode** (per-lot label + scan→full context); **lot timeline** (per-lot move-history view) | per-batch report + working thresholds; scan a lot barcode → product/batch/expiry/location/remaining; timeline lists full lot history; suite green |
| **P6 Migration** | paths 1 (fresh)/2 (zero-stock)/3 (legacy-lot bulk) + rollback runbook | fresh-DB + upgrade verified; suite green |
| **P7 Hardening** | `WmsLotTestBase` + **100+ tests**; browser validation; warehouse simulation; **CI green, 0 skips** | tag Wave-1 build → re-certify in warehouse → **pilot 2–4 weeks** before Wave 2 |

## WAVE 2 — Analytics, dashboards, advanced (only after the pilot + operator feedback)

Recall **dashboards** · value-at-risk analytics · **disposal** mechanics + analytics (the
`destroyed`-state workflow + value write-off) · supplier-quality analytics · shelf-life analytics
· wastage trends · KPI dashboards · **cycle-count** enhancements (lot-aware) · **cold-chain**
workflows (manual quality-hold UX; sensors stay out of scope) · advanced reporting (lot ledger,
traceability) · **polished visual lot timeline** · full inbound-QC workflow. Built only against
real-use evidence; nothing speculative.

> Note: expired stock is **safe** in Wave 1 (blocked at issue + flagged on the report); the formal
> **disposal/destroy + write-off** workflow is Wave 2 — managers dispose manually during the pilot.
>
> **Discovered during the V20-003→005 flip (must be handled in V20-009/011):** once a perishable is
> lot-tracked, the removal engine will not *reserve* an already-expired lot — so an expired lot is
> currently unmovable even for a manual Damage/scrap. The expired-handling work must therefore
> **block expired stock at issue but keep it movable for disposal** (a removal carve-out for
> damage/scrap moves), otherwise expired stock gets stuck on the shelf with no way to clear it.
> The exact mechanism is Odoo `product_expiry`: `stock.move` injects a `with_expiration` context and
> `stock.quant._get_gather_domain` then hard-filters `removal_date >= with_expiration OR removal_date
> IS NULL` at the DB level (not a sort artifact). The carve-out = suppress that context on disposal
> moves (V20-011), plus an explicit issue-time expired filter in the planner (which does NOT go
> through that context) so expired lots are *visibly* excluded with a shortfall reason.
>
> **Discovered during V20-008 (handle in V20-004 / V20-022):** `product_expiry` AUTO-FILLS a new
> lot's `expiration_date = now + product.expiration_time` on creation. With `expiration_time = 0`
> (no shelf-life configured), a perishable received with **no explicit expiry** gets a lot that
> **expires today** → instantly un-issuable. V20-004 must therefore make expiry effectively required
> for perishable receipt lines (or V20-022's per-kind shelf-life must set a sane `expiration_time`),
> so a blank-expiry receipt cannot silently create dead-on-arrival stock.
>
> **From the V20-011c adversarial safety review (non-blocking, → Wave 2):** (1) **Scrap cannot
> dispose expired stock.** The disposal carve-out (`wms_allow_expired_removal`) covers only
> `wms.damage.action_confirm`; `stock.scrap` reads `product.qty_available`, which product_expiry
> zeroes for expired lots — so expired stock can be cleared via Damage (the designated, tested
> path) but not via Scrap. Add a scrap carve-out in Wave 2 if scrap is wanted as a disposal route.
> (2) **A non-perishable product carrying a template `wms_expiry_date` is not hard-blocked at issue
> even past that date** — the entire product_expiry exclusion is gated on `use_expiration_date`, so
> this is pre-existing v19 behaviour (the template date drives FEFO ordering + alerts, not a block),
> NOT a regression and NOT a perishable-stock path. Optional consistency hardening: have the issue
> planner's non-perishable delegate also consider `product_tmpl_id.wms_expiry_date`.

---

## Backlog (re-cut, ordered, ticket-level)

Effort: **S** ≤½ day · **M** ~1–2 days · **L** ~3–5 days.

### Wave 1
| ID | Ticket | Touch | Effort |
|----|--------|-------|--------|
| V20-001 | Scaffold `wms_perishable` + `product_expiry` dep + post-init | — | S |
| V20-002 | Extend perishable kinds (+vaccine/supplement/chemical/fertilizer/food) + dicts + SKU sequences | E1 | M |
| V20-003 | `product.template.create()` auto-enable lot+expiry for perishables | E2 | S |
| V20-004 | Receipt line batch/expiry/supplier fields + view columns | C1,C4 | M |
| V20-005 | Receipt validate: find/create lot, **never merge**, tracking guard | C2,C3 | M |
| **V20-006** | **Duplicate-lot detection** on key (company,product,batch,expiry [+supplier? OWNER-8]) → *add-to-existing* / *cancel* / *new-lot (manager-only)* | C2/C3 | M |
| V20-007 | `stock.lot` lifecycle state + supplier meta | 3.1 | S |
| V20-008 | `stock.quant.wms_effective_expiry` (stored, indexed, computed) | A2 | M |
| V20-009 | FEFO override + `idx_quant_fefo` + auto-split | A1,A5 | M |
| V20-010 | Issue plan: per-lot expiry + FEFO-order + resulting-balance preview + **shortfall breakdown** | D1,D2,A9 | L |
| V20-011 | Issue: expired block + manager override + FEFO-bypass warn (reuse gate) | D3,D4 | L |
| V20-012 | **Lot-aware issue reversal** (restore to original lot) | G/A8 | M |
| V20-013 | Recall: `wms.lot.recall` freeze + exclusion + **unreserve** + manual/supplier mode + notice number + 🔴 RECALL-ACTIVE visibility | 3.4,A3,B4 | M |
| V20-014 | Quarantine/Recall location flags + auto-create + picker exclusion + minimal hold/release | B1,B2,A3 | M |
| V20-015 | Re-key per-lot Expiry-Alert + thresholds/settings + digest + 2 probes | F1,F6,3.5 | M |
| **V20-016** | **Lot barcode + label**: label prints product/batch/expiry/mfg/supplier/QR; scan → product/batch/expiry/location/remaining | label engine + `resolve()` | M |
| **V20-017** | **Lot timeline**: per-lot full move history view (supplier→receipt→…→destroy) | move-line history | M |
| **V20-018** | **Near-expiry receiving guard** (warn + manager approval; optional reject) | 3.7 | M |
| **V20-019** | **Extension hooks** (receipt/issue/recall/quarantine; disposal stub) | spec §16 | M |
| **V20-022** | **Per-product shelf-life policy** (per-kind/product min-receive + min-issue) + **short-dated-issue** guard; feeds V20-018 | 2.8,3.7,7.3 | M |
| **V20-023** | **Lot lock** during manager edits (expiry/recall/quarantine) | 4.7 | S |
| V20-020 | Migration paths 1/2/3 + rollback runbook | 03 | M |
| V20-021 | `WmsLotTestBase` + 100+ tests + CI tags + browser + warehouse sim | H2 | L |

### Wave 2 (after pilot)
| ID | Ticket | Effort |
|----|--------|--------|
| V20-030 | Recall dashboard | M |
| V20-031 | Value-at-risk + disposal analytics; disposal/destroy workflow + value write-off | L |
| V20-032 | Supplier-quality + shelf-life + wastage-trend analytics | L |
| V20-033 | KPI dashboards (perishable overview) | L |
| V20-034 | Cycle-count enhancements (lot-aware) | M |
| V20-035 | Cold-chain quality-hold workflow + full inbound-QC | L |
| V20-036 | Advanced reporting: lot ledger + traceability + polished visual timeline | L |
| V20-037 | **Stock Health Score** KPI (% healthy / near-expiry / expired / recalled / quarantined) | M |
| **V20-039** | **Expiry Risk Engine** — consumption (via `wms_ai_forecast`) vs remaining shelf-life → HIGH/MED/LOW (flagship) | L |
| V20-040 | Expiry Calendar (what expires by month) | M |
| V20-041 | Supplier Performance analytics (recalls/rejects/expiry-loss/quality per supplier) | M |
| V20-042 | Lot Audit Score (batch/supplier/mfg/expiry/barcode/timeline completeness) | S |
| V20-043 | Bulk lot operations (multi-select quarantine / recall / approve) | M |
| V20-038 | Wave-2 hardening + final v20 production-readiness report | M |

> **Folded into existing Wave-1 tickets (not separate):** FEFO *reservation* → V20-009 (the
> `_gather` override already FEFO-orders reservations; add a test + note); FEFO *explanation* in the
> preview → V20-010; automatic lot naming → V20-005; hook *versioning* (`v20 Hook API 1.0`) → V20-019.

**Rough effort:** Wave 1 ≈ 18–22 dev-days (the owner's additions add ~5–6); Wave 2 ≈ 14–20 (after
the mandatory 2–4-week pilot). Highest-uncertainty W1 tickets: V20-010/011 (issue-safety UX),
V20-020 (migration on a populated DB), V20-006 (duplicate-detection UX).
