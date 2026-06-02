# Visual Coverage Report (STEP 7 — Phase 1)

*Audit of the in-app Help Center against visual-learning criteria. Generated from the live `wms_help_article` table (90 articles).*

## Headline

The Help Center has a **strong written foundation** (terminology, role paths, workflow tutorials, FAQ, troubleshooting, safety) plus 12 external SOPs and a recording kit. Its gap is purely the **visual layer**: **0 of 90 articles currently embed any screenshot, diagram, GIF, or video.** STEP 7 adds that layer without touching the existing text.

## Current state by category

| Category | Articles | Has diagram | Has screenshot/annotation | Has GIF | Has video | Visual need |
|---|---|---|---|---|---|---|
| Workflow tutorial | 14 | 0 | 0 | 0 | 0 | **HIGH** — procedural, benefit most from diagrams + tours |
| Role training (incl. onboarding) | 29 | 0 | 0 | 0 | 0 | **HIGH** for the 5 onboarding paths; MED for the rest |
| Terminology ("What is this?") | 25 | 0 | 0 | 0 | 0 | MED — concept diagrams help (FIFO vs FEFO, rack→slot) |
| FAQ | 10 | 0 | 0 | 0 | 0 | LOW — short Q&A; text sufficient |
| Troubleshooting | 9 | 0 | 0 | 0 | 0 | LOW–MED — a "what the red message means" visual helps |
| Safety warning | 3 | 0 | 0 | 0 | 0 | MED — a callout/icon visual reinforces |
| **Total** | **90** | **0** | **0** | **0** | **0** | |

## Missing visual assets & improvement priority

**Priority 1 — the 19 procedural articles (14 workflow + 5 onboarding/role).** These are what a new hire follows to *do* the job. Each needs: a workflow **diagram**, an **annotated screen-map** of its main wizard, a **step-by-step** structure, a **video slot**, and (where possible) a **guided tour** entry point.

| Article (slug) | Missing | Asset plan |
|---|---|---|
| workflow-receiving-stock | diagram, screen-map, video | `diagrams/receiving.svg` + `annotated/scan-receipt.svg` + Storekeeper tour step |
| workflow-putaway-moving-stock-to-its-spot | diagram, video | `diagrams/putaway.svg` + tour step |
| workflow-fifo-issuing | diagram, screen-map, video | `diagrams/fifo-issue.svg` + `annotated/scan-issue.svg` + tour step |
| workflow-returns | diagram, screen-map, video | `diagrams/returns.svg` + `annotated/scan-return.svg` |
| workflow-cycle-count-checking | diagram, video | `diagrams/cycle-count-audit.svg` |
| workflow-creating-zones-and-floor-areas | diagram, screen-map, video | `diagrams/warehouse-structure.svg` + `annotated/generate-zone.svg` + Admin tour |
| workflow-creating-racks | diagram, screen-map, video | `annotated/create-rack.svg` + Admin tour |
| workflow-assigning-slots | diagram, video | `diagrams/warehouse-structure.svg` |
| workflow-damage-handling | diagram, video | `diagrams/damage-repair.svg` |
| workflow-repairs | diagram, video | `diagrams/damage-repair.svg` |
| workflow-backup-verification | diagram, video | `diagrams/backup-restore-health.svg` |
| workflow-restore-drill | diagram, video | `diagrams/backup-restore-health.svg` |
| workflow-using-reports | diagram, video | reports overview + Read-only tour |
| workflow-low-stock-handling | diagram, video | `diagrams/forecast-reorder.svg` |
| welcome / training-library-index | hero visual | First-Login tour entry |
| admin-path-system-overview | system map | `diagrams/roles-permissions.svg` + Admin tour |
| keeper-path-getting-started | flow | Storekeeper tour |
| readonly-path-what-you-can-do | flow | Read-only tour |

**Priority 2 — terminology (25).** Add concept diagrams to the highest-impact ones: `fifo-vs-fefo`, `what-is-a-rack/compartment/slot/zone` (the structure diagram), `what-is-an-audit-trail`.

**Priority 3 — FAQ / troubleshooting / safety (22).** Text is adequate; optionally add a single "what the blocked-action messages mean" visual to troubleshooting.

## What STEP 7 delivers against this report

- **SVG workflow diagrams** (Phase 5) → embedded into P1 + P2 articles.
- **Annotated SVG screen-maps** (Phase 3) → embedded into the wizard articles.
- **Real in-app guided tours** (Phase 8) → First-Login, Storekeeper, Admin, Read-only.
- **Article enrichment** (Phase 6) → Overview / Diagram / Steps / Video structure appended to the 19 P1 articles (existing text preserved).
- **Video Production Tracker** (Phase 7), **mobile verification** (Phase 9), **certification** (Phase 10).
