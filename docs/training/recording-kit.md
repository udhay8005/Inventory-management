# WMS Video Recording Kit

This kit turns the written training library into actual screen-recorded videos and
wires each finished clip into the in-app **Help & Training** Help Center.

Everything a recorder needs is already prepared:
- **What to say** — every workflow has a word-for-word, timestamped *Narration Script* in its SOP file under `docs/training/sop/`.
- **What to click** — every SOP file ends with a *Recording Checklist* (the exact click path).
- **Where it goes** — the table below maps each video to the Help-Center article that should hold it.

---

## 1. How to record (one-time setup)

| Setting | Value |
|---|---|
| Tool | OBS Studio (free) or Windows **Xbox Game Bar** (`Win`+`G`) |
| Resolution | 1920×1080 (1080p), 30 fps |
| Audio | One mic, quiet room; read the SOP *Narration Script* aloud |
| Cursor | Enable "highlight cursor / clicks" (OBS: *Sources → Display Capture → cursor*; or a tool like Cursorcerer) |
| Pace | Slow. Pause ~1 s after each click so a beginner can follow |
| Length | 2–10 min, **one topic per video**, clear start ("In this video we will…") and end ("That's it — you've just…") |
| Browser | Chrome at `http://localhost:8069`, logged in as the relevant role |
| Zoom | For small targets (a field hint, a toggle), zoom the browser to 110–125 % before recording that beat |

Record each video against the **live app** following the SOP's *Recording Checklist*, reading
the *Narration Script*. Save as `H.264 MP4`, 720p+ is fine, keep under ~50 MB so it uploads cleanly.

> Tip: do a "dry run" of the click path once (no recording) so the take is smooth.

---

## 2. How to attach a finished video to its Help-Center article

Two ways — pick one per article. The infrastructure is already built into every article.

**A) Upload the MP4 (works offline, recommended for the trust's tablets)**
1. Open the **Help & Training** app → **Help Center**.
2. Open the target article (see the table below for which slug).
3. Field **"Training video (upload)"** → upload your `.mp4`. Set **"Video filename"**.
4. (Optional) **"Video caption"** → e.g. *"Scanning a receipt — 2 min"*.
5. Save. The video now plays inline at the top of the article.

**B) Paste a YouTube / Vimeo link (needs internet)**
1. Open the article as above.
2. Field **"Video link (YouTube / Vimeo)"** → paste the URL. Set a **"Video caption"**.
3. Save. A safe, whitelisted player embeds automatically.

> An uploaded file always wins over a link if both are set.
> The in-app guide **"How do I add a training video?"** (slug `how-to-add-a-training-video`) repeats these steps for staff.

---

## 3. Master video list → SOP script → target article

Record these in priority order (top = most useful to a new hire). "Article slug" is where to paste/upload the finished clip.

### Store Keeper (record first — daily use)
| # | Video | Length | SOP script | Article slug |
|---|---|---|---|---|
| 1 | Receiving stock (Scan Receipt) | 3–4 m | `sop/01-receiving.md` | `workflow-receiving-stock` |
| 2 | Putaway — getting stock to its slot | 2–3 m | `sop/02-putaway.md` | `workflow-putaway-moving-stock-to-its-spot` |
| 3 | Issuing stock (Scan Issue / FIFO) | 3–4 m | `sop/03-fifo-issue.md` | `workflow-fifo-issuing` |
| 4 | Returns (Scan Return) | 2–3 m | `sop/04-returns.md` | `workflow-returns` |
| 5 | Inventory count / cycle count | 3 m | `sop/05-cycle-count.md` | `workflow-cycle-count-checking` |
| 6 | Barcode scanning basics | 2 m | `sop/01-receiving.md` (§ scanning) | `keeper-path-barcodes-and-scanners` |
| 7 | Reporting damage | 2–3 m | `sop/08-damage-handling.md` | `workflow-damage-handling` |
| 8 | Repairs | 2–3 m | `sop/09-repair-orders.md` | `workflow-repairs` |

### Admin / Manager
| # | Video | Length | SOP script | Article slug |
|---|---|---|---|---|
| 9  | System overview | 4–5 m | `00-training-map.md` (intro) | `admin-path-system-overview` |
| 10 | Warehouse setup — Zones | 3 m | `sop/06-warehouse-setup.md` (§ Zone) | `workflow-creating-zones-and-floor-areas` |
| 11 | Warehouse setup — Racks | 3 m | `sop/06-warehouse-setup.md` (§ Rack) | `workflow-creating-racks` |
| 12 | Slots & floor zones | 2–3 m | `sop/06-warehouse-setup.md` (§ Floor/Slots) | `workflow-assigning-slots` |
| 13 | Onboarding products | 3 m | `sop/07-product-onboarding.md` | `workflow-receiving-stock` (§ onboarding) |
| 14 | Audit management | 3 m | `sop/05-cycle-count.md` + `10-reports-and-readonly.md` | `admin-path-audit-trail-and-roster` |
| 15 | Reports tour | 4–5 m | `sop/10-reports-and-readonly.md` | `workflow-using-reports` |
| 16 | Backup verification | 3 m | `sop/11-backup-restore-health.md` | `workflow-backup-verification` |
| 17 | Restore drill | 3–4 m | `sop/11-backup-restore-health.md` | `workflow-restore-drill` |
| 18 | Monitoring / health | 2–3 m | `sop/11-backup-restore-health.md` (§ health) | `admin-path-observability-health` |
| 19 | User management & roster | 3 m | `sop/12-user-management.md` | `admin-path-users-and-permissions` |
| 23 | Cloud backup (Backup Now + settings) | 3 m | `sop/13-cloud-backup.md` | `workflow-cloud-backup-now` |

### Read-only viewer
| # | Video | Length | SOP script | Article slug |
|---|---|---|---|---|
| 20 | Using reports | 3 m | `sop/10-reports-and-readonly.md` | `readonly-path-using-reports` |
| 21 | Searching inventory | 2 m | `sop/10-reports-and-readonly.md` (§ search) | `readonly-path-searching-stock` |
| 22 | Audit history | 2 m | `sop/10-reports-and-readonly.md` (§ audit) | `readonly-path-audit-visibility` |

---

## 4. Screenshot pack

Annotated screenshots of every major screen were delivered in the chat session that produced
this kit (Slots, Zones, Racks, Compartments, all three Scan wizards, Product Onboard, Damages,
Repair, Audits, Backup & DR Audit, the three generators, Occupancy, Movement History, Oldest
Stock, Forecasts, Expiry, Store Keepers, Carton Barcodes, Help Center, Getting Started). Save the
ones you want from that transcript into `docs/training/media/<area>/` and drop them into the
matching article body (Help Center → article → edit body → insert image) if you want stills inline.

---

## 5. Done-checklist per video
- [ ] Recorded at 1080p with visible cursor, slow pace, one topic
- [ ] Narration matches the SOP script
- [ ] Uploaded/linked to the correct article slug (table above)
- [ ] Caption set
- [ ] Played back inside the Help Center to confirm it works
