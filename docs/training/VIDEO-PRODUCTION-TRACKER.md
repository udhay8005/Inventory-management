# Video Production Tracker (STEP 7 — Phase 7)

Tracks every training video from script → recording → upload → publish. The
in-app infrastructure is already complete on **every** article:

| Capability | Status | Where |
|---|---|---|
| Video **upload** slot (`video_file`, attachment) | ✅ exists | Help Center → article → *Training video (upload)* |
| Video **URL** field (`video_url`, YouTube/Vimeo) | ✅ exists | *Video link* field (whitelisted, safe-embedded) |
| Video **caption** (`video_caption`) | ✅ exists | *Video caption* field |
| **Thumbnail** | ✅ auto | the `<video>` player shows the clip's first frame as the poster automatically; a custom poster can be added later if desired |
| **Recording checklist** | ✅ ready | each `docs/training/sop/NN-*.md` → *Recording Checklist* section |
| **Narration script** | ✅ ready | each SOP → *Narration Script* (timestamped) |

**Status legend:** ⬜ not recorded · 🟡 recording-ready (script+checklist+slot done) · 🔵 uploaded · 🟢 published (plays in-app)

## Tracker

| # | Video | Target article (slug) | Script | Status |
|---|---|---|---|---|
| 1 | Receiving (Scan Receipt) | workflow-receiving-stock | sop/01 | 🟡 recording-ready |
| 2 | Putaway | workflow-putaway-moving-stock-to-its-spot | sop/02 | 🟡 recording-ready |
| 3 | Issuing (FIFO/FEFO) | workflow-fifo-issuing | sop/03 | 🟡 recording-ready |
| 4 | Returns | workflow-returns | sop/04 | 🟡 recording-ready |
| 5 | Cycle count / audit | workflow-cycle-count-checking | sop/05 | 🟡 recording-ready |
| 6 | Barcode scanning basics | keeper-path-barcodes-and-scanners | sop/01 §scan | 🟡 recording-ready |
| 7 | Damage handling | workflow-damage-handling | sop/08 | 🟡 recording-ready |
| 8 | Repairs | workflow-repairs | sop/09 | 🟡 recording-ready |
| 9 | System overview | admin-path-system-overview | 00-training-map | 🟡 recording-ready |
| 10 | Warehouse setup — Zones | workflow-creating-zones-and-floor-areas | sop/06 | 🟡 recording-ready |
| 11 | Warehouse setup — Racks | workflow-creating-racks | sop/06 | 🟡 recording-ready |
| 12 | Slots & floor zones | workflow-assigning-slots | sop/06 | 🟡 recording-ready |
| 13 | Onboarding products | workflow-receiving-stock §onboard | sop/07 | 🟡 recording-ready |
| 14 | Audit management | admin-path-audit-trail-and-roster | sop/05 +10 | 🟡 recording-ready |
| 15 | Reports tour | workflow-using-reports | sop/10 | 🟡 recording-ready |
| 16 | Backup verification | workflow-backup-verification | sop/11 | 🟡 recording-ready |
| 17 | Restore drill | workflow-restore-drill | sop/11 | 🟡 recording-ready |
| 18 | Monitoring / health | admin-path-observability-health | sop/11 §health | 🟡 recording-ready |
| 19 | User management & roster | admin-path-users-and-permissions | sop/12 | 🟡 recording-ready |
| 20 | Using reports (viewer) | readonly-path-using-reports | sop/10 | 🟡 recording-ready |
| 21 | Searching inventory | readonly-path-searching-stock | sop/10 §search | 🟡 recording-ready |
| 22 | Audit history (viewer) | readonly-path-audit-visibility | sop/10 §audit | 🟡 recording-ready |

**Summary: 0 published · 0 uploaded · 22 recording-ready · 0 missing scripts.**

## To publish a video
1. Record per `docs/training/recording-kit.md` (1080p, narration from the SOP).
2. Help Center → open the target article → upload the MP4 (or paste a YouTube/Vimeo link) → set the caption → Save.
3. Update this tracker's Status to 🟢. The clip then plays at the top of that article and in any Guided Tour that references it.
