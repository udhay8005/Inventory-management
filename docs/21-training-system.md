# Design — In-App Beginner Training & Help System (`wms_training`)

**Project:** Dakshin Vrindavan Cow-Care Trust WMS — Odoo 19 CE
**Audience for this doc:** the development + admin team who will build and maintain the training layer.
**Audience for the *product*:** brand-new, often temporary, low-technical warehouse helpers using tablets in a cow shed / store room, plus a couple of Admins.
**Design rule that governs every decision below:** *Write everything a brand-new helper sees in simple, friendly, jargon-free language. No Odoo words ("picking", "quant", "wizard", "m2o"). Say "delivery note", "stock count", "form".*

This system is **additive**: it wraps the existing six addons (`wms_location`, `wms_fifo`, `wms_barcode`, `wms_repair_damage`, `wms_ai_forecast`, `wms_reports`) without changing their behaviour. The existing code already has an excellent friendly voice — chatty `help=` strings, alert banners in the scan wizards, multi-line `UserError` messages. The job here is to **systematise and complete** that voice, add guided walkthroughs, a searchable help center, and a "Beginner Mode" safety net.

---

## 1. Training System Architecture

### 1.1 Guiding principles

1. **Learn in the real app, not a separate course.** A temporary helper will not read a PDF. Training must appear *on the screen where the work happens* — a tip beside the field, a guided tour over the real button, an example in the empty-list placeholder.
2. **Three delivery layers, one source of truth.** Everything keys off two existing facts already in the database: the user's **group** (`group_wms_manager` / `group_wms_user` + capability sub-groups) and a new **Beginner Mode** flag on `res.users`. No third notion of "skill level" is invented.
3. **Never block the expert.** Every guided element is dismissible and remembered. A two-year storekeeper sees almost nothing; a day-one helper sees everything.
4. **Build on Odoo 19 primitives, do not fight them.** Use `web_tour` for walkthroughs, `field help=` + view tooltips for hints, a small `help.article` model for the help center, `res.users` boolean for Beginner Mode, standard `mail.thread` for "what happened" explanations. No bespoke front-end framework.

### 1.2 The four pillars (and the Odoo 19 primitive each uses)

| Pillar | What the helper experiences | Odoo 19 mechanism |
|---|---|---|
| **A. Guided Tours** | "Show me how" walkthroughs that point at the real buttons and make you do each step | `web_tour` JS tours in `registry.category("web_tour.tours")`, launched from a help menu / button |
| **B. Inline Help (tooltips & banners)** | The little hint under a field; the coloured banner at the top of a form | `field help=` attributes, `<field help="...">` view overrides, `alert` `<div>` banners (pattern already in `scan_receipt_views.xml`) |
| **C. Help Center** | A searchable list of short "How do I…?" articles inside the WMS app | New `wms.help.article` model + kanban/form views + a global search bar |
| **D. Beginner Mode safety net** | Extra explanations, bigger confirmations, dangerous buttons hidden | New `res.users.wms_beginner_mode` boolean read by views (`invisible`/`readonly`), tours, and confirmation dialogs |

### 1.3 Where it lives

A **single new addon `wms_training`** (depends on all six WMS addons + `web`, `mail`). One addon keeps install/upgrade simple for the trust's one-PC deployment and means tours/articles can reference any model across the system. All content (tours, articles, tooltip overrides) ships as data so it is versioned in git and survives `-u wms_training`.

### 1.4 Data-flow diagram (text)

```
res.users.wms_beginner_mode  ──┐
group_wms_manager / _user / ───┼──►  decides what each user sees
   capability sub-groups       │
                               ├──►  (B) view tooltips & banners  (invisible="not wms_beginner_mode")
                               ├──►  (A) which tours auto-offer    (tour.groups + beginner check)
                               ├──►  (C) help articles filtered by role
                               └──►  (D) confirmations / hidden danger buttons
```

---

## 2. Beginner UX Strategy

The mental model of the target user: *"I scan things in, I scan things out, I count shelves. I am scared of breaking something. I am on a tablet with one hand while holding a feed bag."* Strategy points:

1. **One primary action per screen.** The scan wizards already do this well (big scan field + one blue *Validate* button). Extend it: in Beginner Mode every form gets a one-line plain-English "What this screen is for" banner at the very top.
2. **Progressive disclosure.** Advanced fields (lot numbers, overuse caps, FEFO internals) stay collapsed/optional for beginners and only surface for Managers or when Beginner Mode is off. Use `optional="hide"` on list columns (already used for `lot_id`) and `invisible="context.get('wms_beginner_mode')"` on advanced notebook pages.
3. **Show the consequence before the action, not after.** This is *already* the design of Scan Issue (the FIFO/FEFO plan table shows which slot the stock will leave *before* Validate). Make this a stated principle and apply it to Damage and Audit too.
4. **Explain in terms of the physical world.** "Scan the **shelf label**" not "set `location_dest_id`". "The system takes the **oldest stock first** so nothing expires on the shelf" not "FIFO removal strategy".
5. **Forgiveness over prevention where data is recoverable; hard stops only where it is not.** A wrong scan is fixable (remove the line). Stock walking out unscanned is not. Beginner Mode therefore adds *confirmations* (reversible-but-annoying) rather than *blocks*, except on the genuinely destructive actions (delete location, scrap, accept audit, download/restore backup).
6. **The empty state is a teacher.** Every list action gets a friendly `help=""` empty-state message (Odoo 19 renders the action's `help` as the no-records placeholder) that says what the screen is and links the matching tour. Example for the Audits list: *"No stock counts yet. A stock count is where you walk the racks and check the real amount against the computer. Press **New** to start one, or click **Show me how**."*
7. **Always a way out and a way to ask.** A persistent **Help (?)** entry in the WMS menu and a floating "Need help?" affordance (see §13) so a stuck helper is never more than one tap from the relevant article or from "call the Admin" contact info.

---

## 3. Role-Based Training Design

Three audiences map **exactly** onto groups that already exist — no new roles invented.

### 3.1 Admin / Manager — `group_wms_manager`
- **Knows or must learn:** the whole system, plus setup-only tasks: onboarding products, generating racks/zones, reviewing & accepting audits, authorising repairs, reading reports/forecasts, **and the dangerous ops** (delete location, scrap, backup download, restore).
- **Training surface:** a one-time **"Set up your warehouse"** master tour offered on first login, then task tours available on demand. Manager sees *all* help articles including an **Admin-only** category (backup/restore, security, rack generation).
- **Beginner Mode default:** **OFF** for Managers (they are few and trained), but available — a brand-new Admin can switch it on.

### 3.2 Store Keeper — `group_wms_user` + capability sub-groups
This is the core training audience. Crucially, **what a keeper is *trained on* must match the capabilities they actually hold**, because menus are gated by the five sub-groups (`group_wms_can_scan_receive`, `…_scan_issue`, `…_file_damage`, `…_submit_audit`, `…_manage_catalog`). A keeper without "Scan Issue" never sees that menu, so they must never be shown that tour either.

- **Design:** tours and articles are tagged with the capability they require and **only offered when the user holds it** (tour `groups` field + article domain on the same sub-groups). A keeper with only Receive+Issue sees exactly two scan tours, the "find product" tour, and the count tour if they can submit audits.
- **Beginner Mode default:** **ON** for any newly created Store Keeper login (set in `wms.storekeeper.action_create_login`, see §10), because most are new/temporary.
- **Tone:** maximum simplicity and reassurance; heavy use of the "your name is recorded, mistakes are easy to fix, just ask" message already in the onboarding script (`docs/15`).

### 3.3 Read-only viewer — `group_wms_user` with **no** capability sub-groups
The security model explicitly supports this: a user in `group_wms_user` alone "can log in and browse, but the Scan Receipt menu / Damage form / Audit list never appear." This is the natural **read-only / trainee-observer** role (e.g. a trustee who only wants to *see* stock, or a brand-new helper on day zero before capabilities are granted).
- **Training surface:** a short **"Find your way around"** orientation tour (open the app, read the Warehouse Map, use "Where is product X?", read a report) — nothing that requires write access. Help articles filtered to read-only/"understanding the system" topics. A clear banner on the dashboard: *"You can look but not change things yet. When you're ready to start receiving or issuing stock, ask your Admin to switch on those buttons for you."*

### 3.4 Role → content matrix

| Content | Read-only (`group_wms_user` only) | Store Keeper (with caps) | Manager |
|---|---|---|---|
| Orientation tour ("Find your way around") | Yes (auto) | Yes | Yes |
| Scan Receipt / Return tour | — | If `can_scan_receive` | Yes |
| Scan Issue (FIFO/FEFO) tour | — | If `can_scan_issue` | Yes |
| File Damage tour | — | If `can_file_damage` | Yes |
| Stock Count (Audit) tour | — | If `can_submit_audit` | Yes |
| "Where is product X?" / reports tour | Yes | Yes | Yes |
| Set-up tours (racks, zones, onboard product) | — | — | Yes |
| Repair, backup/restore, forecast articles | — | — | Yes |
| Beginner Mode default | ON | ON | OFF |

---

## 4. Interactive Help Design (Guided Tours — pillar A)

### 4.1 Technology
Odoo 19 ships the **`web_tour`** system. A tour is JS registered in `registry.category("web_tour.tours")` with an ordered `steps` array; each step has a `trigger` (CSS selector of the real element), `content` (the bubble text — **simple language**), `position`, and optional `run` (`"click"`, `text "50"`, etc.). Tours can be:
- **Onboarding tours** (`url` + auto-start) that run once for a user, OR
- **On-demand tours** launched from a button/menu via the tour service.

We use the **on-demand + once-only-auto** pattern: a beginner is *offered* the tour (a dismissible prompt) the first time they open a screen; thereafter they relaunch it from **WMS → Help → Show me how**.

### 4.2 Tours to ship (initial set)

| Tour key | Title (helper-facing) | Steps cover | Gated by |
|---|---|---|---|
| `wms_tour_orientation` | "Find your way around" | App home, the WMS menu sections, Warehouse Map, "Where is product X?" | all WMS users |
| `wms_tour_scan_receipt` | "Put stock in (Scan Receipt)" | Open wizard → read the green "Scanner ready" banner → scan a product → check qty → scan a shelf → tick Quality check → pick on-duty keeper → Validate & Print | `can_scan_receive` |
| `wms_tour_scan_return` | "Take a tool back in (Scan Return)" | Same wizard, return mode banner, returnable-only caveat | `can_scan_receive` |
| `wms_tour_scan_issue` | "Take stock out (oldest first)" | Pick destination → set quantity → scan → **read the plan table (this is the oldest stock, take from these shelves)** → fill Taken by / Ordered by / Reason → photo if asked → Validate | `can_scan_issue` |
| `wms_tour_damage` | "Report a broken or expired item" | New → product, qty, source slot, reason, photo → Confirm | `can_file_damage` |
| `wms_tour_audit` | "Do a stock count" | New → Start → walk and type counted qty per line → Submit to Admin | `can_submit_audit` |
| `wms_tour_find_product` | "Where is something stored?" | Reports → Where is product X? → search → read "Next to pick" row → open visual grid | all |
| `wms_tour_admin_setup` | "Set up your warehouse (Admin)" | Onboard a product → generate a rack → generate a zone → print labels → create a storekeeper login | `group_wms_manager` |
| `wms_tour_admin_review` | "Review a submitted stock count (Admin)" | Open submitted audit → read variances → Accept or Reject | `group_wms_manager` |
| `wms_tour_beginner_intro` | "Welcome — 90-second tour" | What WMS is, the 3 rules of scanning, where Help lives, how to turn Beginner Mode on/off | auto on first login |

### 4.3 Step content style (example, Scan Issue)
> Step on the plan table: *"This list is the computer telling you **which shelves to take from**. It always picks the **oldest stock first** (for medicine and feed, the **soonest-to-expire** first) so nothing goes bad on the shelf. Take from the shelves shown here — even if a fuller shelf is closer."*

Each tour's source: the verbatim human script in `docs/15-onboarding-script.md` is the content seed — we are turning that proven 30-minute script into clickable tours, keeping its exact phrasing and "3 rules of scanning".

### 4.4 Re-launch & tracking
- A **"Show me how"** button appears in the header of each major wizard/list (a `<button>` in the view that calls a small server action / client action starting the matching tour). In Beginner Mode the button is shown prominently; otherwise it is tucked in the cog/Help menu.
- "Tour completed" is tracked by Odoo's own consumed-tour mechanism so an auto-offered tour does not nag after completion. A **"Reset my tours"** action under Help lets a returning seasonal helper re-enable the prompts.

---

## 5. Tooltip Design (pillar B)

### 5.1 Three tooltip tiers
1. **Field help (`help=`)** — the standard Odoo "i" hint shown on hover/tap of a field label. The codebase already uses this heavily and well (e.g. `wms.scan.issue.usage_note`, `storekeeper_id`, `wms.audit.line.variance`). **Audit and complete it**: every user-facing field on every WMS-owned model and wizard must have a `help=` written in plain language with a concrete example. Where a field lives on a standard Odoo model we override it in the view: `<field name="x" help="..."/>`.
2. **Banner tooltips (alert `<div>`)** — the top-of-form coloured explainer. Pattern already in `scan_receipt_views.xml` ("Scanner ready" info banner, "Return entry mode" warning banner). Standardise: **info (blue)** = "what this screen is for"; **warning (orange)** = "be careful / special mode"; **success (green)** = "ready / done". In Beginner Mode an extra, longer info banner appears; with Beginner Mode off only the short one (or none) shows.
3. **Field placeholders** — the faint in-field example text (`placeholder="Scan product, carton, or slot..."`, already used). Every free-text and scan field gets a concrete placeholder.

### 5.2 Tooltip writing rules
- One short sentence + one concrete example. Example for `taken_by`: *"Who is physically taking these items — e.g. the worker, a department lead, or a visitor."* (already this good in code).
- Never reference Odoo internals. Replace any remaining "picking", "quant", "UoM" wording in help strings with "delivery / receipt note", "shelf stock", "unit (kg, litre, piece)".
- For FIFO/FEFO fields, always restate *why*: "oldest leaves first so nothing expires."
- Beginner-only deep tooltips: where a one-liner isn't enough for a novice, attach a **"Learn more"** link in the banner that opens the matching help article (see §7) instead of bloating the `help=` string.

### 5.3 Coverage checklist (delivered as part of the addon)
A short markdown checklist in the addon listing every WMS field and whether it has `help=`, used as the acceptance gate. Focus areas with the highest novice confusion (from the model code): product **Kind** dropdown, **Returnable** toggle, **Max per issue / Daily cap**, **expiry date**, **on-duty Store Keeper**, **QC passed**, audit **expected vs counted vs variance**.

---

## 6. Workflow Tutorial Design

Tours (§4) teach a *single* screen. **Workflow tutorials** teach an *end-to-end task that spans screens* and the *why* between them. Two formats:

### 6.1 "Recipe" articles (in the Help Center)
Short, numbered, screenshot-light "How do I …?" recipes for each real job. Each maps to a chapter of `docs/20-end-to-end-flow.md` and `docs/13-operations-playbook.md`, rewritten at a 6th-grade reading level. Initial set:
- "Receive a delivery from start to finish"
- "Give stock to the cow shed / pooja room"
- "A bottle broke — what do I do?"
- "Do my Monday stock count"
- "Find where something is stored"
- "A scan won't register — fixes to try"
- "(Admin) Add a brand-new item and print its label"
- "(Admin) Make a login for a new helper"
- "(Admin) Generate a new rack"

### 6.2 Multi-screen guided tours
For the two workflows that genuinely cross screens, ship `web_tour` tours that navigate between menus mid-tour (web_tour supports steps that click menu items and wait for the next view):
- **"Receive → store → find it again"** (Receipt wizard → Warehouse Map → Where is product X?) — proves to a beginner that what they scanned really landed somewhere they can find.
- **"Count → Admin review"** is split across two role-tours (`wms_tour_audit` for the keeper, `wms_tour_admin_review` for the Admin) because they are done by different people; the keeper article ends with "your Admin now checks it."

### 6.3 The "what just happened" explainer
A recurring novice fear is *"did it work?"*. Every successful Validate already lands the user on the created record whose **chatter** logs a plain-English audit line (see `scan_issue.action_validate`'s "Issued. Taken by … ordered by … Store Keeper on duty …"). In Beginner Mode, add a **success toast + a one-line banner on the result record**: *"Done! Stock was taken from the shelves shown. This is now recorded with your name. You can close this."* This closes the loop the tour opened.

---

## 7. Help Center Structure (pillar C)

### 7.1 Model: `wms.help.article`
A lightweight knowledge-base model (we deliberately do **not** depend on Odoo's `knowledge` enterprise module — CE only).

```
wms.help.article
  name            Char     (the question, e.g. "How do I take stock out?")
  sequence        Integer  (ordering inside a category)
  category_id     m2o → wms.help.category
  body            Html     (the answer; QWeb-renderable, supports images/steps)
  keywords        Char     (extra search terms: "issue, give, FIFO, remove")
  group_ids       m2m → res.groups  (who may see it; defaults to group_wms_user)
  capability_id   m2o → res.groups  (optional: only show if user holds this cap)
  tour_id         Char     (optional web_tour key → renders a "Show me how" button)
  related_action  Reference (optional: "Take me to this screen" button)
  is_admin_only   Boolean  (shortcut for category gating)
  active          Boolean
wms.help.category
  name            Char  ("Getting started", "Putting stock in", "Taking stock out",
                          "Counting", "Finding things", "When something is wrong",
                          "Admin & setup")
  sequence, icon
```

### 7.2 Views & access
- **Kanban** grouped by category (big tap-friendly cards) as the landing view — ideal on tablets.
- **Form** = the article reader: rendered `body`, a **"Show me how"** button if `tour_id` set, a **"Open this screen"** button if `related_action` set, and a **"Was this helpful?"** thumbs widget writing to a tiny `helpful_count` (drives §15 maintenance).
- **ACL:** read for `group_wms_user` (so everyone sees help); create/write/unlink for `group_wms_manager` only (Admins curate content). Record rules hide `is_admin_only` / capability-gated articles from keepers who lack the capability — so a Receive-only keeper is never shown the Issue article.
- **Search:** the standard Odoo search bar over `name`, `body`, `keywords`. Articles are also exposed to the global **command palette** (Ctrl/Cmd-K) so a literate user can jump straight to an answer.

### 7.3 Content authoring
- Articles ship as **XML data records** (`noupdate="1"` so an Admin's later edits aren't overwritten on upgrade) seeded from the existing `docs/` set, rewritten in plain language. Source mapping: `docs/15` → getting-started recipes; `docs/03-workflows.md` + `docs/20-end-to-end-flow.md` → task recipes; `docs/12-mobile-access.md` → "Using a phone/tablet"; `docs/16-hardware-guide.md` → "Scanner & label printer help".
- Bilingual-ready: `name`/`body` are translatable fields, so a Hindi/regional translation can be loaded later via `.po` without code change (matches the trust's likely workforce).

---

## 8. Error Message Improvements (principles)

The codebase already sets a high bar (`scan_issue` and `wms_audit` raise multi-line, explain-and-fix `UserError`s). Codify it as a **house style** and apply it everywhere, including standard-Odoo errors the helper might hit.

**The 4-part error formula** (every WMS `UserError` / `ValidationError` follows it):
1. **What happened**, in plain words — "Stock out." not "Insufficient quantity for move id 41."
2. **Why** — "The warehouse is 5 short of what you asked for."
3. **What to do now** — "Wait for the missing units to come back through Scan Return, or reduce the quantity and try again."
4. **Who to ask if stuck** — "If you think this is wrong, ask the Admin to check the count." (added for beginner-facing errors).

Additional principles:
- **Never expose internals**: no model names, no field technical names, no Python tracebacks to keepers. (Sanitise the few remaining raw messages.)
- **Name the fix location precisely**: the overuse-cap error already does this well — "ask the Admin to adjust the 'Max per issue' field on the product (WMS Classification tab)." Keep that specificity everywhere.
- **Validation should pre-empt, not punish**: where possible, disable/grey the Validate button with a tooltip *before* the click rather than throwing after. Use `invisible`/`readonly`/required-field highlighting so a beginner sees the blocker inline (the wizards already require `taken_by`, `ordered_by`, `usage_note`, on-duty keeper — surface these as obvious "still needed" markers in Beginner Mode).
- **Catch the standard-Odoo cliffs**: the three or four places a keeper can hit a raw Odoo error (e.g. a UNIQUE clash, an access-rights denial when they wander into a manager-only record) get a friendlier wrapper or a record-rule that simply hides the screen instead.
- **Errors link to help**: in Beginner Mode, long error dialogs end with a "See: <article>" pointer (the help article slug) so the fix is one tap away.

---

## 9. Beginner Mode Design

The centrepiece safety net. **One boolean toggles three behaviours: more guidance, fewer dangerous actions, stronger confirmations.**

### 9.1 The flag
Add to `res.users` (extend the existing `wms_location/models/res_users.py`, which already inherits `res.users`):

```python
wms_beginner_mode = fields.Boolean(
    string="Beginner mode (extra help & guard-rails)",
    default=False,
    help="When on, the WMS shows extra plain-language explanations, "
         "asks you to confirm before anything risky, and hides the "
         "expert-only buttons. Turn it off once you're confident.")
```
- **Where it's set:**
  - **By the user themselves:** a toggle in their user preferences *and* a one-click switch in the WMS dashboard header ("I'm new here — show me extra help" / "I'm confident — hide the extra help"). Self-service is essential because helpers are temporary and proud.
  - **By the Admin:** defaulted **ON** automatically when a Store Keeper login is created via `wms.storekeeper.action_create_login` (§10), and editable from the storekeeper roster form.
- **Exposed to views via context:** the web client already puts `res.users` context keys within reach; we add `wms_beginner_mode` to the user's context (via `_get_user_context`/`context_get` override or a computed `ir.filters`-style key) so view `invisible`/`readonly` expressions and tours can read `context.get("wms_beginner_mode")` without an extra RPC.

### 9.2 Behaviour 1 — extra guidance (ON)
- The long "what this screen is for" banners (§5.2) render only when beginner.
- "Show me how" tour buttons are prominent.
- Success explainer toast/banner after each Validate (§6.3).
- Empty-state placeholders show the fuller, friendlier copy.
- Advanced fields/notebook pages stay collapsed.

### 9.3 Behaviour 2 — hide dangerous actions (ON)
Dangerous = irreversible **or** stock-affecting at scale. In Beginner Mode these are **hidden or disabled** via `invisible="context.get('wms_beginner_mode')"` (for keepers they're often already group-gated; this is defence-in-depth and also applies to a Manager who self-enables Beginner Mode):

| Action | Beginner Mode treatment |
|---|---|
| Delete a Rack / Compartment / Slot / Zone | Hidden (delete already guarded by `test_location_delete`; also hide the button) |
| Scrap (in Repair) / permanent write-off | Hidden — route them to "ask Admin" |
| Accept/Apply a stock-count audit (creates adjustments) | Hidden for keepers (already manager-gated); confirmation-wrapped for managers in beginner mode |
| Download encrypted backup / Restore | Hidden (already manager-only; extra-hidden in beginner mode) |
| Inventory adjustment power-edits, bulk delete on lists | Hidden / list `delete="0"` while beginner |
| Override a FIFO/FEFO plan line | Discouraged: show the line read-only-ish with a warning; full override needs Beginner Mode off or Manager |

### 9.4 Behaviour 3 — stronger confirmations (ON)
For reversible-but-consequential actions, Beginner Mode inserts an **explicit confirm step** the expert doesn't get:
- Implement via a tiny **confirmation wizard** (`wms.confirm.dialog` transient) or the OWL `Dialog`/`confirm` service, shown only when `wms_beginner_mode`. Copy is reassuring and specific: *"You're about to record that 50 kg of cattle feed left the store, taken by Ramesh. This will update the stock counts. Press Yes to confirm, or Back to change it."*
- Applies to: **Validate** on Scan Issue (large qty), **Confirm** on Damage, **Submit** on Audit. For experts (mode off) these go straight through, preserving speed.
- Reuse the existing `wms.keeper.warning.mixin` banner idea (orange "X edited this 4 min ago — review before saving") — in Beginner Mode raise it from a passive banner to a confirm prompt so a novice can't blindly overwrite a colleague.

### 9.5 Interaction with roles
Beginner Mode is **orthogonal** to group: a Manager *can* turn it on (useful for a brand-new trustee-admin), a confident keeper *can* turn it off. The defaults (ON for new keepers, OFF for managers) just set the starting point. This keeps the model to exactly two inputs — group + one boolean — as the architecture demands.

---

## 10. Mobile / Tablet UX Guidance

The real deployment is tablets in a shed, sometimes one-handed, sometimes on a flaky LAN/HTTPS tunnel (`docs/12`). The training layer must be *more* helpful, not less, on small screens.

1. **Tap targets ≥ 48px.** Tour bubbles, "Show me how", help cards, and confirm buttons use Odoo's `btn-lg` / large kanban cards. Help Center landing is a kanban of big cards (§7.2).
2. **Tours must work on touch.** `web_tour` steps use `run: "click"`/`text` which map to taps; avoid hover-only triggers. Tooltip "i" hints are reachable by tap (Odoo handles this) — but because hover is unreliable on touch, **critical guidance goes in banners/placeholders, not hover-only `help=`**. `help=` is the *secondary* layer on mobile.
3. **Camera-first flows.** The Scan Issue photo field already renders as a single "Take photo" button opening the OS camera on mobile (`widget="image"`, `capture`). The tour explicitly teaches this and the help article notes the **HTTPS requirement** for the camera (from `docs/12`): "If the photo button doesn't open the camera, you're on plain http — ask the Admin for the secure (https) address."
4. **Scanner-aware copy.** The barcode wizards inherit `barcodes.barcode_events_mixin` (HID scanner ENTER auto-fires). Mobile help covers both a hardware scanner *and* the on-screen field; the "scan won't register — tap the field once" tip from the onboarding FAQ becomes a pinned banner in Beginner Mode.
5. **Vertical, single-column forms.** The scan wizards already use Bootstrap `col-12 col-md-*` responsive grids — keep every training-added banner/field in that pattern so it stacks cleanly on a phone.
6. **Offline/again-later reality.** A mobile help article "When the screen won't load" covers the LAN/tunnel troubleshooting table from `docs/12` in plain words, and reminds: "Never put stock on a shelf before it's scanned, even if the tablet is being slow — write it on paper and scan when it's back."
7. **Beginner Mode is doubly valuable on mobile** (fat-finger protection): the stronger confirmations (§9.4) specifically guard against an accidental tap on Validate while walking.

---

## 11. Files / Modules to Create

A single new addon **`wms_training`**. Proposed manifest dependencies: `["wms_location", "wms_barcode", "wms_repair_damage", "wms_reports", "wms_ai_forecast", "wms_fifo", "web", "mail"]`. Concrete file list:

```
addons/wms_training/
├── __init__.py
├── __manifest__.py                      # name, depends (above), data+assets bundles, license LGPL-3
├── models/
│   ├── __init__.py
│   ├── res_users.py                     # add wms_beginner_mode boolean + inject into user context
│   ├── wms_help_article.py              # wms.help.article + wms.help.category models
│   └── wms_training_mixin.py            # optional: helper to compute beginner banners / "show me how" availability
├── wizards/
│   ├── __init__.py
│   ├── wms_confirm_dialog.py            # transient model powering Beginner-Mode confirmations
│   └── wms_confirm_dialog_views.xml
├── views/
│   ├── menus.xml                        # WMS → Help (root help menu + dashboard action); "Reset my tours"
│   ├── wms_help_article_views.xml       # kanban (landing), form (reader), search; actions
│   ├── wms_help_category_views.xml
│   ├── res_users_views.xml              # Beginner-mode toggle in Preferences + Settings→Users
│   ├── wms_training_dashboard.xml       # client-action / OWL dashboard: "Welcome", tour launcher, beginner toggle
│   ├── tooltip_overrides_location.xml   # <field help=...> + banners injected into wms_location forms
│   ├── tooltip_overrides_barcode.xml    # banners/help on scan wizards (extends existing alert divs, beginner-gated)
│   ├── tooltip_overrides_repair.xml     # Damage/Repair form guidance
│   ├── tooltip_overrides_reports.xml    # report list help= empty-states
│   └── empty_state_help.xml             # action help="" placeholders across the WMS actions
├── data/
│   ├── wms_help_category_data.xml       # the 7 categories (noupdate="1")
│   ├── wms_help_article_data.xml        # seeded articles from docs/ (noupdate="1")
│   └── wms_training_settings.xml        # default: new storekeeper logins → beginner_mode = True hook wiring
├── security/
│   ├── ir.model.access.csv              # article read=all WMS users, write=manager; category same
│   └── wms_training_rules.xml           # record rules: hide admin-only / capability-gated articles
├── static/
│   ├── description/
│   │   └── icon.png
│   └── src/
│       ├── js/
│       │   ├── tours/
│       │   │   ├── tour_orientation.js
│       │   │   ├── tour_scan_receipt.js
│       │   │   ├── tour_scan_return.js
│       │   │   ├── tour_scan_issue.js
│       │   │   ├── tour_damage.js
│       │   │   ├── tour_audit.js
│       │   │   ├── tour_find_product.js
│       │   │   ├── tour_admin_setup.js
│       │   │   ├── tour_admin_review.js
│       │   │   └── tour_beginner_intro.js
│       │   ├── help_launcher/             # OWL widget: floating "Need help?" button + "Show me how"
│       │   │   ├── help_launcher.js
│       │   │   ├── help_launcher.xml
│       │   │   └── help_launcher.scss
│       │   └── beginner_confirm/          # OWL hook wiring the confirm dialog to Validate in beginner mode
│       │       └── beginner_confirm.js
│       └── scss/
│           └── wms_training.scss
├── tests/
│   ├── __init__.py
│   ├── test_help_article_access.py       # keeper can read, not write; capability gating hides Issue article
│   ├── test_beginner_mode.py             # toggle persists; new storekeeper login defaults ON
│   └── test_tours.py                     # HttpCase: each tour runs end-to-end for a seeded user/role
└── README.md                             # how to add a new article/tour; the tooltip coverage checklist
```

Manifest `assets` registration (Odoo 19 pattern, mirrors `wms_location`):
```python
"assets": {
    "web.assets_backend": [
        "wms_training/static/src/scss/wms_training.scss",
        "wms_training/static/src/js/tours/*.js",
        "wms_training/static/src/js/help_launcher/**/*",
        "wms_training/static/src/js/beginner_confirm/beginner_confirm.js",
    ],
},
```

---

## 12. Recommended UI Placement

Where each piece lives in the existing WMS menu/UX (menu root `wms_location.menu_wms_root`, sections Operations / Configuration / Reports / Forecot / Backup):

| Piece | Placement | Why there |
|---|---|---|
| **Help menu (root)** | New top-level child of **WMS** menu, label **"Help"**, low sequence so it sits last, `web_icon` "?" — visible to **all** WMS users (`group_wms_user`) | One predictable home for help; mirrors how Reports is its own section |
| ↳ **Help Center** (article kanban) | Under WMS → Help → **"How-to guides"** | Searchable landing |
| ↳ **Guided tours list** ("Show me how") | Under WMS → Help → **"Show me how"** → opens the dashboard/launcher | Re-launch any tour |
| ↳ **Reset my tours** | WMS → Help → **"Reset my tours"** | Seasonal returners |
| **Welcome / training dashboard** | The **default action** when a *beginner* opens the WMS app (client action), replacing the bare menu landing; experts land on the normal Operations menu | First thing a new helper sees is orientation, not a blank screen |
| **"Show me how" button** | In the **header** of each scan wizard, Damage form, Audit form, and the "Where is product X?" list | Contextual relaunch right where the task is |
| **"What this screen is for" banner** | Top of each form, **above** the existing alert banners (beginner-gated) | Consistent first-read line |
| **Floating "Need help?" launcher** | Bottom-right OWL widget on WMS backend screens (beginner-gated; collapsible) | Always-available escape hatch, tablet-friendly |
| **Beginner-mode toggle** | (a) the WMS dashboard header; (b) standard **Preferences** dialog (top-right user menu); (c) **Settings → Users** form for Admins; (d) the **Store Keeper roster** form | Self-service + admin control |
| **Help article links from errors/banners** | Inline "See: …" / "Learn more" links rendered inside Beginner-Mode banners and long error dialogs | Connects the moment-of-confusion to the answer |
| **Admin setup tour prompt** | Auto-offered on a Manager's first login after install | Drives initial warehouse setup |
| **Command palette (Ctrl/Cmd-K)** entries | Articles registered as commands | Power-user shortcut, no menu hunting |

---

## 13. Rollout Strategy (phased)

Ship in four phases so value lands early and risk stays low on the trust's single-PC deployment.

**Phase 0 — Foundations (no user-visible behaviour change yet)**
- Create the `wms_training` addon skeleton, the `res.users.wms_beginner_mode` field, and the `wms.help.article`/`category` models + ACLs.
- Audit and complete every `help=` tooltip across the six addons (pure content, low risk, immediately useful even before the rest ships).
- Acceptance: install/upgrade clean; tooltip coverage checklist 100%; existing tests still green.

**Phase 1 — Help Center + tooltips live**
- Seed the help categories and the first ~10 articles (from `docs/15`, `docs/03`, `docs/20`, `docs/12`).
- Add the WMS → Help menu, the article kanban/reader, the empty-state placeholders, and the standardised banners (beginner-gated).
- Acceptance: a keeper can find and read "how to take stock out" in ≤ 3 taps; access tests pass (keeper read-only, manager curates).

**Phase 2 — Beginner Mode + confirmations + danger-hiding**
- Wire the boolean into view context; add the confirm dialog and the danger-button `invisible` rules; default new storekeeper logins to ON; add the self-service toggle.
- Acceptance: `test_beginner_mode` green; manual check on a tablet that Validate asks for confirmation in beginner mode and goes straight through otherwise; no dangerous button visible to a beginner.

**Phase 3 — Guided tours + welcome dashboard**
- Ship the role/capability-gated `web_tour` tours, the "Show me how" buttons, the floating launcher, and the beginner welcome dashboard with auto-offer-once.
- Acceptance: `test_tours.py` HttpCase runs every tour for its seeded role; on-duty pilot with 1–2 real helpers in the shed.

**Phase 4 — Pilot, measure, translate**
- Two-week supervised pilot with real temporary helpers; collect "Was this helpful?" data and watch which errors still cause "ask the Admin" interruptions.
- Add a regional-language (`.po`) translation of articles/tooltips if the workforce needs it.
- Acceptance: a brand-new helper completes one receipt + one issue + one count *unaided* using only in-app help, matching the goal of the `docs/15` 30-minute script — but self-served.

---

## 14. Long-Term Maintainability Strategy

1. **Content is data, versioned in git.** Articles, categories, and tour definitions live in the addon (`noupdate="1"` for seeded articles so Admin edits survive upgrades). Editing copy = a normal PR, reviewed like code; no separate CMS to drift.
2. **Single source of truth per fact.** Tooltips/`help=` describe the field; articles describe the *task*; tours *show* the task. A behaviour change in a workflow updates one tour + one article, found via a naming convention (`wms_tour_<task>` ↔ article keyword). The README's mapping table keeps these paired.
3. **Tours are tested, so they break loudly.** Each `web_tour` is covered by an `HttpCase` in `tests/test_tours.py`. If a developer renames a button or moves a field, the tour's `trigger` selector fails in CI (the project already runs tests per `docs/10`/`docs/17`) — turning silent doc-rot into a red build. **This is the key anti-staleness mechanism.**
4. **Tooltip coverage is a gate.** The coverage checklist (§5.3) is part of `code-review`/CI: a new user-facing field without `help=` fails review. New capability sub-groups automatically need a matching gated tour/article (documented in `res_users._CAPABILITY_XMLIDS`'s neighbourhood + the README).
5. **Feedback loop drives pruning.** The "Was this helpful?" counter + a simple "articles read this month" report (reuse the `wms_reports` pattern) tells Admins which help is unused (delete/merge) or unhelpful (rewrite). Errors that still trigger "ask the Admin" are candidates for a new article or a friendlier message.
6. **Decouple from Odoo churn.** All tours/help use *public* Odoo 19 primitives (`web_tour` registry, `field help`, action `help`, `res.users` context, OWL `Dialog`/`registry`). No monkey-patching of core controllers beyond the existing benign UI patches. When upgrading Odoo, the test suite (especially tours) is the migration tripwire; selectors are the only likely fix.
7. **Keep the docs/ and in-app help in sync deliberately.** The `docs/*.md` files remain the *engineering* source; in-app articles are their plain-language derivative. A short note in `docs/11-maintenance.md` (or a new `docs/21-training-maintenance.md`) records the mapping so future maintainers know that editing the onboarding flow means touching both. Consider a CI check that flags an article whose source doc changed since the article's last edit.
8. **Low operational cost.** No extra services, no enterprise modules, no external SaaS — fits the trust's volunteer-run, single-PC, offline-friendly reality. Everything ships in one installable addon and is removed cleanly by uninstalling it.

---

### Appendix — Alignment notes for implementers
- The terminology is **Rack → Compartment → Slot** (+ Zone, Floor); the older `docs/15` onboarding script still says "Levels → Dividers" and references "Repair Tech / Buyer" roles that aren't in the current two-role + capability security model. **Rewrite article copy to the current model**, not the stale script wording.
- Reuse, don't reinvent, the existing friendly assets: the `scan_receipt`/`scan_issue` alert banners, the rich `help=` strings, the chatter audit lines, and the `wms.keeper.warning.mixin` are the established voice — the training layer extends them consistently.
- The Store Keeper login factory (`wms_barcode/models/wms_storekeeper.py → action_create_login`) is the natural hook to default `wms_beginner_mode = True` for new helpers; add that one line there when Phase 2 lands.
