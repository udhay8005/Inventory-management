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
2. **Three delivery layers, one source of truth.** Everything keys off two existing facts already in the database: the user's **base role** (`group_wms_user` / `group_wms_manager` / `group_repair_tech`, plus the optional `group_buyer`) together with their **capability sub-groups** (all five in the `wms_location.*` namespace — `group_wms_can_scan_receive`, `group_wms_can_scan_issue`, `group_wms_can_file_damage`, `group_wms_can_submit_audit`, `group_wms_can_manage_catalog`) and a new **Beginner Mode** flag on `res.users`. No third notion of "skill level" is invented.
3. **Never block the expert.** Every guided element is dismissible and remembered. A two-year storekeeper sees almost nothing; a day-one helper sees everything.
4. **Build on Odoo 19 primitives, do not fight them.** Use HTML `wms.help.article` records (with the install-time link-rewriter `hooks.apply_tour_action_links`) for walkthroughs, `field help=` + view tooltips for hints, a `wms.help.article` model for the help center, a `res.users` boolean for Beginner Mode, standard `mail.thread` for "what happened" explanations. No bespoke front-end framework, no JS tour engine.

### 1.2 The four pillars (and the Odoo 19 primitive each uses)

| Pillar | What the helper experiences | Odoo 19 mechanism |
|---|---|---|
| **A. Guided Tours** | Step-by-step walkthroughs that link straight to the real screen for each step | HTML articles (`wms.help.article`) whose `<a href="/odoo/action-PENDING-…">` placeholders are rewritten at install/upgrade by `hooks.apply_tour_action_links` to point at the real backend actions. **Not** `web_tour` JS tours. |
| **B. Inline Help (tooltips & banners)** | The little hint under a field; the coloured banner at the top of a form | `field help=` attributes, `<field help="...">` view overrides, `alert` `<div>` banners (pattern already in `scan_receipt_views.xml`) |
| **C. Help Center** | A searchable list of short "How do I…?" articles inside the WMS app | New `wms.help.article` model + kanban/form views + a global search bar |
| **D. Beginner Mode safety net** | Extra explanations, bigger confirmations, dangerous buttons hidden | New `res.users.wms_beginner_mode` boolean read by views (`invisible`/`readonly`), tours, and confirmation dialogs |

### 1.3 Where it lives

A **single new addon `wms_training`** (depends on all six WMS addons + `web`, `mail`). One addon keeps install/upgrade simple for the trust's one-PC deployment and means tours/articles can reference any model across the system. All content (tours, articles, tooltip overrides) ships as data so it is versioned in git and survives `-u wms_training`.

### 1.4 Data-flow diagram (text)

```
res.users.wms_beginner_mode  ──┐
base role (group_wms_user /  ──┼──►  decides what each user sees
   _manager / _repair_tech,    │
   + optional group_buyer)     │
capability sub-groups (all 5   │
   in wms_location.*)          │
                               ├──►  (B) view tooltips & banners  (invisible="not wms_beginner_mode")
                               ├──►  (A) which tours auto-offer    (tour.groups + beginner check)
                               ├──►  (C) help articles filtered by role + capability
                               └──►  (D) confirmations / hidden danger buttons
```

---

## 2. Beginner UX Strategy

The mental model of the target user: *"I scan things in, I scan things out, I count shelves. I am scared of breaking something. I am on a tablet with one hand while holding a feed bag."* Strategy points:

1. **One primary action per screen.** The scan wizards already do this well (big scan field + one blue *Validate* button). Extend it: in Beginner Mode every form gets a one-line plain-English "What this screen is for" banner at the very top.
2. **Progressive disclosure.** Advanced fields (lot numbers, overuse caps, FIFO internals) stay collapsed/optional for beginners and only surface for Managers or when Beginner Mode is off. Use `optional="hide"` on list columns (already used for `lot_id`) and `invisible="context.get('wms_beginner_mode')"` on advanced notebook pages.
3. **Show the consequence before the action, not after.** This is *already* the design of Scan Issue (the FIFO plan table shows which slot the stock will leave *before* Validate). Make this a stated principle and apply it to Damage and Audit too.
4. **Explain in terms of the physical world.** "Scan the **shelf label**" not "set `location_dest_id`". "The system takes the **oldest stock first** so nothing expires on the shelf" not "FIFO removal strategy".
5. **Forgiveness over prevention where data is recoverable; hard stops only where it is not.** A wrong scan is fixable (remove the line). Stock walking out unscanned is not. Beginner Mode therefore adds *confirmations* (reversible-but-annoying) rather than *blocks*, except on the genuinely destructive actions (delete location, scrap, accept audit, download/restore backup).
6. **The empty state is a teacher.** Every list action gets a friendly `help=""` empty-state message (Odoo 19 renders the action's `help` as the no-records placeholder) that says what the screen is and links the matching tour. Example for the Audits list: *"No stock counts yet. A stock count is where you walk the racks and check the real amount against the computer. Press **New** to start one, or open **Help & Training → Getting Started** for a walk-through."* (Adding these action-level empty states is roadmap — see §13 Phase 2.)
7. **Always a way out and a way to ask.** A persistent **Help (?)** entry in the WMS menu and a floating "Need help?" affordance (see §13) so a stuck helper is never more than one tap from the relevant article or from "call the Admin" contact info.

---

## 3. Role-Based Training Design

The security model is **three base roles** (`group_wms_user` = Store Keeper, `group_wms_manager` = Manager, `group_repair_tech` = Repair Tech) plus an **optional fourth** (`group_buyer` = Buyer), layered with **five capability sub-groups** that live entirely in the `wms_location.*` namespace (`group_wms_can_scan_receive`, `group_wms_can_scan_issue`, `group_wms_can_file_damage`, `group_wms_can_submit_audit`, `group_wms_can_manage_catalog`). Training audiences map **exactly** onto those groups — no new roles invented.

### 3.1 Admin / Manager — `group_wms_manager`
- **Knows or must learn:** the whole system, plus setup-only tasks: onboarding products, generating racks/zones, reviewing & accepting audits, authorising repairs, reading reports/forecasts, **and the dangerous ops** (delete location, scrap, backup download, restore).
- **Training surface:** a one-time **"Set up your warehouse"** master tour offered on first login, then task tours available on demand. Manager sees *all* help articles including an **Admin-only** category (backup/restore, security, rack generation).
- **Beginner Mode default:** **OFF** for Managers (they are few and trained), but available — a brand-new Admin can switch it on.

### 3.2 Store Keeper — `group_wms_user` + capability sub-groups
This is the core training audience. Crucially, **what a keeper is *trained on* must match the capabilities they actually hold**, because menus are gated by the five sub-groups (`group_wms_can_scan_receive`, `…_scan_issue`, `…_file_damage`, `…_submit_audit`, `…_manage_catalog`). A keeper without "Scan Issue" never sees that menu, so they must never be shown that tour either.

- **Design:** tours and articles are tagged with the capability they require and **only offered when the user holds it** (tour `groups` field + article domain on the same sub-groups). A keeper with only Receive+Issue sees exactly two scan tours, the "find product" tour, and the count tour if they can submit audits.
- **Beginner Mode default:** **ON** for any newly created Store Keeper login (set in `wms.storekeeper.action_create_login`, see §10), because most are new/temporary.
- **Tone:** maximum simplicity and reassurance; heavy use of the "your name is recorded, mistakes are easy to fix, just ask" message already in the onboarding script (`docs/15`).

### 3.3 Repair Tech — `group_repair_tech`
A first-class base role for the bench technician who works damage triage and repair orders. The Repair Tech is **not** a storekeeper — by default they do not hold Scan Receipt or Scan Issue capabilities, and the daily put-away / give-out scan menus are not their job.
- **Knows or must learn:** the **Repair Orders** workflow (assess → repair → return-to-stock or scrap-recommend), the **damage triage** flows (reading a Damage record raised by a keeper, attaching parts/labour, recording outcome), and how to hand a repaired item back to a keeper for re-shelving.
- **Training surface:** a dedicated **"Repair Tech daily rhythm"** tour covering the Repair Orders list, the damage queue, and the "what to do when an item can't be saved" path (which routes through a Manager — Repair Techs never scrap directly). Help-Center filter shows repair/damage articles plus the orientation set; receive/issue/audit recipes are hidden.
- **Beginner Mode default:** **ON** for newly created Repair Tech logins (same factory hook as keepers), **OFF** once the tech is trained.

### 3.4 Buyer — `group_buyer` (optional)
An optional purchasing role for a trust member who needs to read forecasts and reorder reports without touching stock. May or may not be installed depending on the deployment.
- **Training surface:** the orientation tour, the forecast / reorder articles, and the "Where is product X?" recipe — nothing that requires write access to stock. If `group_buyer` is not installed, this row simply does not apply.
- **Beginner Mode default:** **ON** initially (low-frequency users benefit from the guard-rails).

### 3.5 Read-only viewer — `group_wms_user` with **no** capability sub-groups
The security model explicitly supports this: a user in `group_wms_user` alone "can log in and browse, but the Scan Receipt menu / Damage form / Audit list never appear." This is the natural **read-only / trainee-observer** role (e.g. a trustee who only wants to *see* stock, or a brand-new helper on day zero before capabilities are granted).
- **Training surface:** a short **"Find your way around"** orientation tour (open the app, read the Warehouse Map, use "Where is product X?", read a report) — nothing that requires write access. Help articles filtered to read-only/"understanding the system" topics. A clear banner on the dashboard: *"You can look but not change things yet. When you're ready to start receiving or issuing stock, ask your Admin to switch on those buttons for you."*

### 3.6 Role → content matrix

| Content | Read-only (`group_wms_user` only) | Store Keeper (with caps) | Repair Tech (`group_repair_tech`) | Buyer (`group_buyer`, optional) | Manager |
|---|---|---|---|---|---|
| Orientation tour ("Find your way around") | Yes (auto) | Yes | Yes | Yes | Yes |
| Scan Receipt / Return tour | — | If `can_scan_receive` | — (not their job) | — | Yes |
| Scan Issue (FIFO) tour | — | If `can_scan_issue` | — (not their job) | — | Yes |
| File Damage tour | — | If `can_file_damage` | Yes (reads the damage queue) | — | Yes |
| Stock Count (Audit) tour | — | If `can_submit_audit` | — | — | Yes |
| Repair Orders / bench workflow tour | — | — | Yes (primary tour) | — | Yes |
| "Where is product X?" / reports tour | Yes | Yes | Yes | Yes | Yes |
| Forecast / reorder articles | — | — | — | Yes | Yes |
| Set-up tours (racks, zones, onboard product) | — | — | — | — | Yes |
| Backup/restore, security articles | — | — | — | — | Yes |
| Beginner Mode default | ON | ON | ON | ON | OFF |

---

## 4. Interactive Help Design (Guided Tours — pillar A)

### 4.1 Technology
"Guided tour" is the user-facing name, but the **shipped mechanism is HTML, not JavaScript**. Each tour is a record of `wms.help.article` whose `body_html` contains a numbered list of steps; each step is a link of the form `<a href="/odoo/action-PENDING-&lt;xmlid&gt;">…</a>`. At install/upgrade the post-init / migration hook `wms_training.hooks.apply_tour_action_links` rewrites every `action-PENDING-<xmlid>` placeholder to the resolved numeric action id, so each step jumps straight to the right backend screen. There are **no `web_tour` JS tours, no `registry.category("web_tour.tours")` entries, no CSS-selector `trigger` steps, and no `assets` bundle** in this addon.

The shipped tours are reached from **Help & Training → Getting Started** (a top-level Odoo app menu — see §12); each step is a hyperlink the helper clicks to land on the real screen, then they return to the article for the next step.

### 4.2 Tours shipped in this release

Four HTML-article tours ship today, each gated by article record rules so the helper only sees the ones relevant to their role:

| Article xmlid | Title (helper-facing) | Steps | Gated for |
|---|---|---|---|
| `wms_training.help_tour_first_login` | "Your first login — what to do" | 4 | every WMS user (first thing they read) |
| `wms_training.help_tour_storekeeper` | "Daily storekeeper rhythm" | 5 | `group_wms_user` (with any capability sub-group) |
| `wms_training.help_tour_admin` | "Admin walk-through — set things up" | 6 | `group_wms_manager` |
| `wms_training.help_tour_readonly` | "Find your way around (look only)" | 5 | `group_wms_user` with no capability sub-groups |

Each step is one `<a href="/odoo/action-PENDING-&lt;xmlid&gt;">` link inside the article body; `hooks.apply_tour_action_links` rewrites those placeholders at install. Adding a new tour = adding a `wms.help.article` data record with PENDING links and re-running `-u wms_training`. Future-roadmap tours (per-capability scan tours, find-product, admin-review) are tracked under §13 Phase 3 and not in this release.

### 4.3 Step content style (example, storekeeper rhythm)
> Step linking to Scan Issue: *"This screen is the computer telling you **which shelves to take from**. It always picks the **oldest stock first**. Take from the shelves shown — even if a fuller shelf is closer. (For medicine and feed, check **Reports → Expiry alerts** so you deliberately use up the soonest-to-expire batch before it goes bad.)"*

Each tour's source: the verbatim human script in `docs/15-onboarding-script.md` is the content seed — the four shipped tours turn that proven 30-minute script into linked HTML steps, keeping its exact phrasing and "3 rules of scanning".

### 4.4 Re-launch & tracking
- Tours are plain articles, so re-launching is just opening the article again from **Help & Training → Getting Started** or **Help & Training → Help Center**. There is no "Show me how" button widget, no client-side launcher, and no auto-offer-once nagging in this release — those are roadmap items (see §13 Phase 3).
- There is no "Reset my tours" action either. Because tours are articles, "resetting" just means re-opening the article; there is no per-user consumed-tour state to clear.

---

## 5. Tooltip Design (pillar B)

### 5.1 Three tooltip tiers
1. **Field help (`help=`)** — the standard Odoo "i" hint shown on hover/tap of a field label. The codebase already uses this heavily and well (e.g. `wms.scan.issue.usage_note`, `storekeeper_id`, `wms.audit.line.variance`). **Audit and complete it**: every user-facing field on every WMS-owned model and wizard must have a `help=` written in plain language with a concrete example. Where a field lives on a standard Odoo model we override it in the view: `<field name="x" help="..."/>`.
2. **Banner tooltips (alert `<div>`)** — the top-of-form coloured explainer. Pattern already in `scan_receipt_views.xml` ("Scanner ready" info banner, "Return entry mode" warning banner). Standardise: **info (blue)** = "what this screen is for"; **warning (orange)** = "be careful / special mode"; **success (green)** = "ready / done". In Beginner Mode an extra, longer info banner appears; with Beginner Mode off only the short one (or none) shows.
3. **Field placeholders** — the faint in-field example text (`placeholder="Scan product, carton, or slot..."`, already used). Every free-text and scan field gets a concrete placeholder.

### 5.2 Tooltip writing rules
- One short sentence + one concrete example. Example for `taken_by`: *"Who is physically taking these items — e.g. the worker, a department lead, or a visitor."* (already this good in code).
- Never reference Odoo internals. Replace any remaining "picking", "quant", "UoM" wording in help strings with "delivery / receipt note", "shelf stock", "unit (kg, litre, piece)".
- For FIFO fields, always restate *why*: "oldest leaves first, so stock keeps rotating." (To avoid spoilage, point operators at the Expiry Alerts report, which lists items by soonest expiry.)
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
The four shipped tours already cross screens — each step is a hyperlink to a different backend action, resolved at install by `hooks.apply_tour_action_links`. The pattern is naturally cross-screen because the helper navigates step-by-step via the link instead of being driven by a JS engine. Future cross-workflow tours considered:
- **"Receive → store → find it again"** (Receipt wizard → Warehouse Map → Where is product X?) — would prove to a beginner that what they scanned really landed somewhere they can find. Roadmap.
- **"Count → Admin review"** would split across two role-tours because they are done by different people; the keeper article would end with "your Admin now checks it." Roadmap.

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
  tour_id         Char     (optional roadmap field — would render a "Show me how" button; not in this release)
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
- **Form** = the article reader: rendered `body_html` with inline step links resolved by `hooks.apply_tour_action_links` (the tours articles use this; recipe articles can mix step links and prose). A "Was this helpful?" thumbs widget is a planned addition (see §13 Phase 4); it is not in this release.
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
- The Help & Training menu link is surfaced more prominently (roadmap; today the menu is always present at the top level).
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
| Override a FIFO plan line | Discouraged: show the line read-only-ish with a warning; full override needs Beginner Mode off or Manager |

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

1. **Tap targets ≥ 48px.** Help cards and confirm buttons use Odoo's `btn-lg` / large kanban cards. Help Center landing is a kanban of big cards (§7.2).
2. **Tours must work on touch.** Because the shipped tours are HTML articles with link steps, "tapping a step" is just tapping a hyperlink — already touch-native. Tooltip "i" hints are reachable by tap (Odoo handles this) — but because hover is unreliable on touch, **critical guidance goes in banners/placeholders, not hover-only `help=`**. `help=` is the *secondary* layer on mobile.
3. **Camera-first flows.** The Scan Issue photo field already renders as a single "Take photo" button opening the OS camera on mobile (`widget="image"`, `capture`). The tour explicitly teaches this and the help article notes the **HTTPS requirement** for the camera (from `docs/12`): "If the photo button doesn't open the camera, you're on plain http — ask the Admin for the secure (https) address."
4. **Scanner-aware copy.** The barcode wizards inherit `barcodes.barcode_events_mixin` (HID scanner ENTER auto-fires). Mobile help covers both a hardware scanner *and* the on-screen field; the "scan won't register — tap the field once" tip from the onboarding FAQ becomes a pinned banner in Beginner Mode.
5. **Vertical, single-column forms.** The scan wizards already use Bootstrap `col-12 col-md-*` responsive grids — keep every training-added banner/field in that pattern so it stacks cleanly on a phone.
6. **Offline/again-later reality.** A mobile help article "When the screen won't load" covers the LAN/tunnel troubleshooting table from `docs/12` in plain words, and reminds: "Never put stock on a shelf before it's scanned, even if the tablet is being slow — write it on paper and scan when it's back."
7. **Beginner Mode is doubly valuable on mobile** (fat-finger protection): the stronger confirmations (§9.4) specifically guard against an accidental tap on Validate while walking.

---

## 11. Files / Modules — live addon shape

A single addon **`wms_training`**. The shipped layout is intentionally minimal — no assets bundle, no JavaScript, no OWL widgets, no client actions. Tours are HTML articles and the only "code" that touches them at install time is `hooks.apply_tour_action_links`.

```
addons/wms_training/
├── __init__.py
├── __manifest__.py                       # depends on wms_location/_barcode/_repair_damage/_reports/_ai_forecast/_fifo + web + mail; application=False (no Apps-grid tile); LGPL-3
├── hooks.py                              # apply_tour_action_links: rewrites <a href="/odoo/action-PENDING-<xmlid>"> to /odoo/action-<resolved-id> across every wms.help.article body_html; runs from post_init_hook and migrations
├── models/
│   ├── __init__.py
│   ├── res_users.py                      # wms_beginner_mode boolean (extends res.users)
│   ├── wms_help_article.py               # wms.help.article model (kanban + form reader)
│   └── wms_repair_order.py               # repair-order touch-up so Scrap/Repair links resolve in tours
├── views/
│   ├── wms_help_article_views.xml        # article kanban + form views + actions; ALSO declares the top-level "Help & Training" menu inline (no separate menus.xml — see lines 110-125)
│   ├── res_users_views.xml               # Beginner-mode toggle in Preferences + Settings → Users
│   └── wms_repair_scrap_views.xml        # adjusts the Scrap action so the admin tour step lands cleanly
├── data/
│   ├── help_articles.xml                 # seeded recipe / how-to articles (noupdate="1")
│   ├── guided_tours.xml                  # the 4 tour articles: help_tour_first_login (4 steps), help_tour_storekeeper (5), help_tour_admin (6), help_tour_readonly (5) — each step is one /odoo/action-PENDING-<xmlid> link
│   └── training_index.xml                # category / landing index records
├── security/
│   └── ir.model.access.csv               # article read for WMS users, write for managers
├── static/
│   └── img/
│       ├── annotated/                    # annotated UI screenshots embedded in article bodies
│       └── diagrams/                     # flow diagrams embedded in article bodies
├── migrations/
│   ├── 19.0.1.5.0/                       # earlier migration step
│   └── 19.0.1.6.0/post-migrate.py        # re-runs apply_tour_action_links so existing installs pick up new tour links
└── tests/
    ├── __init__.py
    ├── test_beginner_mode.py             # toggle persists; default ON path
    ├── test_help_video.py                # rendered article body smoke test
    └── test_tour_links.py                # every /odoo/action-PENDING-<xmlid> resolves to a live ir.actions record after hooks run
```

Notes:
- **No `static/description/icon.png`** ships. The manifest is `application=False`, so the addon installs without an Apps-grid tile; it surfaces only via the top-level "Help & Training" Odoo app menu its views declare.
- **No `assets` registration** in the manifest. There is no `web.assets_backend` block — nothing to bundle, because there is no JS/SCSS.
- **No `menus.xml`, no `wms_help_category_views.xml`, no `wms_training_dashboard.xml`, no `tooltip_overrides_*.xml`, no `wizards/`.** Those are roadmap (§13 Phase 2-3); the live release relies on the existing addons' tooltips/banners.
- **The "Help & Training" menu and its two children (Getting Started, Help Center) are declared inline at the bottom of `views/wms_help_article_views.xml` (lines 110-125)** — top-level Odoo app menu, `sequence=6`, `groups="base.group_user"`. It is NOT a submenu under WMS (see §12).

---

## 12. UI Placement — what ships today vs. roadmap

### 12.1 Shipped placement

| Piece | Placement | Why there |
|---|---|---|
| **Help & Training (root menu)** | **Top-level Odoo app menu**, `sequence=6`, `groups="base.group_user"` — sits next to WMS in the apps bar, not under it. Declared inline in `views/wms_help_article_views.xml` lines 110-125. | One predictable home for help, visible to every internal user; deliberately separate from WMS so non-warehouse users (trustees, helpers in training) can still reach it |
| ↳ **Help & Training → Getting Started** | Article action; the four shipped guided tours (`help_tour_first_login`, `help_tour_storekeeper`, `help_tour_admin`, `help_tour_readonly`) are the headline content here | First thing a new helper opens |
| ↳ **Help & Training → Help Center** | Kanban over `wms.help.article` recipe / how-to articles | Searchable landing |
| **Beginner-mode toggle** | **Preferences** dialog (top-right user menu) and **Settings → Users** form for Admins, via `views/res_users_views.xml` | Self-service + admin control |

### 12.2 Roadmap placement (not in this release)

These were considered and may ship in later phases (see §13); they are **not** present in the live addon today:

| Piece | Planned placement | Phase |
|---|---|---|
| Welcome / training dashboard client action | Default action when a beginner opens the WMS app | Phase 3 |
| In-form "What this screen is for" beginner banner | Top of each WMS form, beginner-gated | Phase 2 |
| Floating "Need help?" launcher | Bottom-right widget on WMS backend screens | Phase 3 |
| Inline "See: …" / "Learn more" links wired into errors | Beginner-mode error dialogs | Phase 2 |
| Auto-offer-once on first login | Manager and keeper first-login prompts | Phase 3 |
| Command palette (Ctrl/Cmd-K) article entries | Power-user shortcut | Phase 4 |

---

## 13. Rollout Strategy (phased)

Ship in four phases so value lands early and risk stays low on the trust's single-PC deployment.

**Phase 0 — Foundations (no user-visible behaviour change yet)**
- Create the `wms_training` addon skeleton, the `res.users.wms_beginner_mode` field, and the `wms.help.article`/`category` models + ACLs.
- Audit and complete every `help=` tooltip across the six addons (pure content, low risk, immediately useful even before the rest ships).
- Acceptance: install/upgrade clean; tooltip coverage checklist 100%; existing tests still green.

**Phase 1 — Help Center + tooltips live**
- Seed the help categories and the first ~10 articles (from `docs/15`, `docs/03`, `docs/20`, `docs/12`).
- Add the top-level Help & Training menu, the article kanban/reader, the empty-state placeholders, and the standardised banners (beginner-gated).
- Acceptance: a keeper can find and read "how to take stock out" in ≤ 3 taps; access tests pass (keeper read-only, manager curates).

**Phase 2 — Beginner Mode + confirmations + danger-hiding**
- Wire the boolean into view context; add the confirm dialog and the danger-button `invisible` rules; default new storekeeper logins to ON; add the self-service toggle.
- Acceptance: `test_beginner_mode` green; manual check on a tablet that Validate asks for confirmation in beginner mode and goes straight through otherwise; no dangerous button visible to a beginner.

**Phase 3 — Guided tours + welcome dashboard**
- Extend the four shipped tour articles with per-capability scan tours and find-product / admin-review tours; optionally add a "Show me how" launcher widget and the beginner welcome dashboard with auto-offer-once. (If JS tours are introduced for any of these, they would be add-ons to the HTML pattern, not a replacement.)
- Acceptance: `test_tour_links.py` resolves every tour step link for its seeded role; on-duty pilot with 1–2 real helpers in the shed.

**Phase 4 — Pilot, measure, translate**
- Two-week supervised pilot with real temporary helpers; collect "Was this helpful?" data and watch which errors still cause "ask the Admin" interruptions.
- Add a regional-language (`.po`) translation of articles/tooltips if the workforce needs it.
- Acceptance: a brand-new helper completes one receipt + one issue + one count *unaided* using only in-app help, matching the goal of the `docs/15` 30-minute script — but self-served.

---

## 14. Long-Term Maintainability Strategy

1. **Content is data, versioned in git.** Articles, categories, and tour definitions live in the addon (`noupdate="1"` for seeded articles so Admin edits survive upgrades). Editing copy = a normal PR, reviewed like code; no separate CMS to drift.
2. **Single source of truth per fact.** Tooltips/`help=` describe the field; articles describe the *task*; tours *show* the task. A behaviour change in a workflow updates one tour article (xmlid pattern `help_tour_<role>`) + one recipe article, found via a naming convention. The mapping is kept in the tour article body itself, which links to the relevant screen.
3. **Tour links are tested, so they break loudly.** `tests/test_tour_links.py` walks every `<a href="/odoo/action-PENDING-<xmlid>">` placeholder across the four tour articles and asserts that `hooks.apply_tour_action_links` resolves each xmlid to a live `ir.actions` record. If a developer renames or removes an action xmlid the tours point at, the test fails in CI (the project already runs tests per `docs/10`/`docs/17`) — turning silent doc-rot into a red build. **This is the key anti-staleness mechanism.**
4. **Tooltip coverage is a gate.** The coverage checklist (§5.3) is part of `code-review`/CI: a new user-facing field without `help=` fails review. New capability sub-groups automatically need a matching gated tour/article (documented in `res_users._CAPABILITY_XMLIDS`'s neighbourhood + the README).
5. **Feedback loop drives pruning.** The "Was this helpful?" counter + a simple "articles read this month" report (reuse the `wms_reports` pattern) tells Admins which help is unused (delete/merge) or unhelpful (rewrite). Errors that still trigger "ask the Admin" are candidates for a new article or a friendlier message.
6. **Decouple from Odoo churn.** All tours/help use *public* Odoo 19 primitives (`wms.help.article` model, `ir.actions` xmlids resolved by a tiny post-install hook, `field help`, action `help`, `res.users` context). No monkey-patching of core controllers, no dependency on the JS tour-service internals. When upgrading Odoo, `test_tour_links.py` is the migration tripwire; a renamed action xmlid is the only likely fix.
7. **Keep the docs/ and in-app help in sync deliberately.** The `docs/*.md` files remain the *engineering* source; in-app articles are their plain-language derivative. A short note in `docs/11-maintenance.md` (or a new `docs/21-training-maintenance.md`) records the mapping so future maintainers know that editing the onboarding flow means touching both. Consider a CI check that flags an article whose source doc changed since the article's last edit.
8. **Low operational cost.** No extra services, no enterprise modules, no external SaaS — fits the trust's volunteer-run, single-PC, offline-friendly reality. Everything ships in one installable addon and is removed cleanly by uninstalling it.

---

### Appendix — Alignment notes for implementers
- The terminology is **Rack → Compartment → Slot** (+ Zone, Floor); the older `docs/15` onboarding script still says "Levels → Dividers". The current security model is **three base roles** (`group_wms_user`, `group_wms_manager`, `group_repair_tech`) **plus the optional `group_buyer`**, layered with **five capability sub-groups** all in the `wms_location.*` namespace (`group_wms_can_scan_receive`, `…_scan_issue`, `…_file_damage`, `…_submit_audit`, `…_manage_catalog`) — Repair Tech and Buyer are **first-class roles**, not orphan references. **Rewrite article copy to the current model**, not the stale "Levels → Dividers" / two-role script wording.
- Reuse, don't reinvent, the existing friendly assets: the `scan_receipt`/`scan_issue` alert banners, the rich `help=` strings, the chatter audit lines, and the `wms.keeper.warning.mixin` are the established voice — the training layer extends them consistently.
- The Store Keeper login factory (`wms_barcode/models/wms_storekeeper.py → action_create_login`) is the natural hook to default `wms_beginner_mode = True` for new helpers; add that one line there when Phase 2 lands.
