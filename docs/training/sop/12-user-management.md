# SOP 12 — User Management (Roles, Capabilities, and the Store Keeper Roster)

## Purpose
This procedure explains how an Admin manages who can do what in the WMS:

- The **two main roles**: **WMS / Manager** (Admin — full control) and **WMS / Store Keeper** (everyday operator).
- The **five capability switches** layered on top of Store Keeper: Scan Receipt + Scan Return, Scan Issue, File damage events, Submit inventory audits, Manage carton aliases + labels.
- The **Store Keeper roster** — the list of real human names picked as "Store Keeper on duty", and how to give a roster entry its own Odoo login with the right capabilities in a few clicks.
- The optional sub-roles **Repair Tech** and **Buyer**.

The goal is least access: each person gets exactly the abilities their job needs, and every stock move records a real human.

## Who Uses It
- **WMS / Manager (Admin) only.** The **Store Keepers** roster lives under **WMS → Configuration** (Manager-gated), and the capability toggles / "Create Odoo login" buttons on the roster form are Manager-only. Full user administration (groups, passwords) is under **Settings → Users**, also Admin-only.
- Store Keepers and read-only viewers cannot manage users or grant themselves abilities.

## Prerequisites
- You are logged in as a **WMS / Manager**. (The built-in `admin` user is added to this group on first install.)
- You know each person's job: which scan/damage/audit abilities they need, and whether they're a Repair Tech or Buyer.
- For an individual login: a short lowercase username (e.g. `suresh`, `ramesh_a` — no spaces) and a temporary initial password.

## Step-by-Step Instructions

### Background: how the roles fit together (read first)
- **WMS / Store Keeper** (`group_wms_user`) is the baseline: log in, see the WMS app, read every report. By itself it shows **no** scan/damage/audit menus.
- **Five capability sub-groups** each turn on one ability (and each implies the baseline):
  - **Scan Receipt + Scan Return** (`group_wms_can_scan_receive`)
  - **Scan Issue (outbound)** (`group_wms_can_scan_issue`)
  - **File damage events** (`group_wms_can_file_damage`)
  - **Submit inventory audits** (`group_wms_can_submit_audit`)
  - **Manage carton aliases + labels** (`group_wms_can_manage_catalog`)
- **WMS / Manager** (`group_wms_manager`) implies all five capabilities plus stock-manager rights — the Admin sees and does everything.
- The Inventory app, Apps, and Dashboards menus are hidden from Store Keepers on purpose, so the WMS scan flows are the *only* way they move stock.
- The **roster** (`wms.storekeeper`) is separate from logins: even on a shared desk login, the on-duty human is picked from the roster so the audit trail names a real person. A roster entry can *optionally* be linked to its own Odoo login.

### A. Add a Store Keeper to the roster
1. Open **WMS → Configuration → Store Keepers**. The list shows **Name**, **Phone**, **Odoo login**, capability toggles (hidden by default), and **On the roster**.
2. Click **New**. Type the **Name** (placeholder "e.g. Ramesh"); optionally **Phone**, **Email**, and **Notes**.
3. Leave **On the roster** ticked (untick later to retire them without deleting history).
4. Save. The keeper now appears in the "Store Keeper on duty" dropdown on Scan Issue, Scan Receipt, Damage, Repair, and Audit screens — no login required.

### B. Give a roster entry its own Odoo login (optional)
1. Open the roster entry. While it has no login, a **Set up individual Odoo login** group is shown.
2. Fill **Login** (placeholder "e.g. suresh (lowercase, no spaces)") and **Initial password** (temporary — the keeper changes it on first login).
3. Click **Create Odoo login** (header button, Manager-only). The system creates a real `res.users` linked to this roster entry and grants the **four default capabilities**: Scan Receipt + Return, Scan Issue, File damage, Submit audit. (**Manage carton aliases + labels** stays OFF — that's usually Admin work.) The initial password is cleared from the form immediately (only the hash lives on the user).
4. The **Capabilities (advantages)** toggles now appear. Tick or untick each to grant/revoke that ability — each toggle writes the matching group onto the user. **Untick anything the keeper shouldn't do.**
5. Use **Open login record** to jump to the `res.users` form for password resets ("Send Reset Password Email"), archiving, or adding finer permissions under Settings → Users → Permissions.

### C. Create or manage a user directly (Settings → Users)
1. Open **Settings → Users → New**. Set the name, login, and email; set/invite a password.
2. Under the user's permissions, add them to **WMS / Store Keeper** for the baseline, then tick the specific **capability** groups they need — or add them to **WMS / Manager** to give full control.
3. Grant **WMS / Repair Tech** only to people who start/finish/scrap repairs, and the **Buyer** role only to people who manage forecasts and draft purchase orders.
4. Save. (If you also want this user to appear as a roster name, link them from a Store Keeper roster entry.)

### D. Retire a Store Keeper
1. Open the roster entry and untick **On the roster** (the `active` flag), then save.
2. Historical issues, damages, and audits that mention them are preserved. If a linked Odoo login exists, it is archived too (so a retired keeper can't sneak past the lockdown).

## Worked Example
The trust is onboarding two helpers: Suresh (full daily operator with his own login) and Lakshmi (shared desk, roster name only for now).

1. **WMS → Configuration → Store Keepers → New.** Name `Suresh`, Phone filled. Save.
2. On Suresh's entry, fill **Login** `suresh` and an **Initial password**, then click **Create Odoo login**. He gets the four default capabilities. The trust doesn't want him editing carton aliases, so **Manage carton aliases + labels** stays OFF (it already is). They also decide he shouldn't issue stock yet, so they untick **Can Scan Issue**. Now Suresh can receive, return, file damage, and submit audits, but the Scan Issue menu won't appear for him.
3. **Store Keepers → New.** Name `Lakshmi`. Save. No login — Lakshmi works on the shared desk tablet and simply picks "Lakshmi" as the on-duty keeper.
4. Later, a third helper becomes the workshop technician. The Admin opens **Settings → Users**, opens that user, and adds **WMS / Repair Tech** so they can drive repair orders.
5. When Lakshmi leaves, the Admin opens her roster entry and unticks **On the roster** — her past actions stay on record.

## Common Errors & What They Mean
- **"Pick a Login for '<name>' before creating the user. Use a short lowercase name (e.g. 'suresh', 'ramesh')."** — You clicked Create Odoo login with the Login field empty.
- **"Set an Initial password so '<name>' has something to type on first login…"** — The Initial password field is empty.
- **"Login '<x>' is already taken (by <name>). Pick another."** — That username already exists. Choose a different one.
- **"'<name>' already has an Odoo login (<login>). Edit the capability check-boxes directly; the login itself can be managed from Settings → Users."** — You tried to create a login for an entry that already has one. Use the toggles / Open login record instead.
- **"Login '<x>' contains whitespace. Use a short, lowercase, single-word handle — e.g. 'suresh', 'ramesh_a'."** — Remove spaces from the login.
- **"Each Store Keeper name must be unique on the roster."** — A roster entry with that name already exists.
- **"An Odoo login can be tied to only one roster entry."** — That `res.users` is already linked to another roster row.
- **"Only WMS Managers can move racks or zones. Ask an admin."** — A non-Manager tried a Manager-only action; relevant if you're testing access levels.

## Troubleshooting
- **A keeper logs in but the Scan / Damage / Audit menus are missing.** They have the baseline role but not the matching capability. Open their roster entry (or Settings → Users) and tick the capability they need — the menu appears after they reload.
- **I ticked a capability on a roster entry but nothing changed.** The toggles only take effect once the entry has a **linked Odoo login**. Create the login first (or set the group directly on the user in Settings → Users).
- **The "Store Keeper on duty" dropdown is empty on scan forms.** The roster has no active entries. Add names under **Store Keepers** (and keep **On the roster** ticked).
- **I need to change someone's password.** Use **Open login record** on the roster entry (or Settings → Users) and "Send Reset Password Email", or set a new password there. Passwords are never stored on the roster.
- **A Store Keeper can see Odoo's raw Inventory app.** They shouldn't — the Inventory, Apps, and Dashboards menus are restricted to Managers. If a keeper sees Inventory, they were probably also added to a stock-manager group manually; remove that.
- **I want a true read-only viewer.** Add the user to **WMS / Store Keeper** and tick **no** capability switches. They can log in, browse, and read every report, but no scan/damage/audit menus appear.
- **Repair Tech can't see the Repair Orders menu.** That menu is Manager-only by design; a Repair Tech reaches repair orders via the **Repair** smart button on a damage record. Their role lets them drive the repair stages, not see the standalone menu.

## Best Practices
- **Grant least access.** Don't make everyone a Manager "to save time" — that removes every guardrail. Start from Store Keeper and add only the needed capabilities.
- **Keep the roster complete.** Add one row per real person so keepers can always name themselves on every action — this is what makes the audit trail meaningful.
- **Prefer the roster's "Create Odoo login" for keepers.** It grants a sensible default capability set in one click; then untick what they shouldn't do.
- **Reserve "Manage carton aliases + labels" for Admin/catalog work.** It's OFF by default for new logins — leave it OFF unless the person genuinely manages barcodes.
- **Grant Repair Tech and Buyer only to the people who do those jobs.**
- **Retire, don't delete.** Untick "On the roster" to retire a keeper; deleting would orphan history. The linked login is archived automatically.
- **Review access periodically.** When roles change, update capabilities the same day so menus match responsibilities.

## Related Help-Center Articles
- `admin-path-users-and-permissions`
- `what-is-a-storekeeper`
- `admin-path-audit-trail-and-roster`
- `faq-who-are-storekeepers-on-duty`
- `why-record-who-took-stock`
- `readonly-path-what-you-can-do`
- `safety-never-delete-archive`

## Narration Script
*(Target length ~4 minutes.)*

- **[0:00]** "In this video we'll manage users — the two roles, the capability switches, and the Store Keeper roster. The aim is least access: each person gets exactly the abilities their job needs."
- **[0:18]** "There are two main roles. WMS Manager is the Admin — full control. WMS Store Keeper is the everyday operator. On its own, Store Keeper lets someone log in and read reports, but it shows no scan, damage, or audit menus."
- **[0:40]** "On top of Store Keeper there are five capability switches you tick per person: Scan Receipt and Return, Scan Issue, File damage events, Submit inventory audits, and Manage carton aliases and labels."
- **[1:02]** "Now the roster. Open WMS, Configuration, Store Keepers. This is the list of real human names. Even on a shared desk tablet, every action asks who's on duty, and they pick a name from here — so the audit trail always points to a real person."
- **[1:25]** "Let's add Suresh. Click New, type his name, save. He's now selectable as on-duty keeper — no login needed."
- **[1:42]** "To give Suresh his own login, I fill the Login field — lowercase, no spaces — and an initial password, then click Create Odoo login. The system creates his user and grants four default capabilities: receive, issue, file damage, submit audit. Manage carton aliases stays off, because that's usually Admin work."
- **[2:10]** "Now the capability toggles appear. Suppose Suresh shouldn't issue stock yet — I untick Can Scan Issue, and the Scan Issue menu disappears for him. Each toggle maps to one permission group."
- **[2:35]** "For Lakshmi, who works only on the shared tablet, I just add her name to the roster with no login. She picks 'Lakshmi' as on-duty keeper when she works."
- **[2:55]** "For finer roles, go to Settings, Users. There you can add someone to WMS Repair Tech — so they can start, finish, and scrap repairs — or to the Buyer role for forecasts and purchase orders. Grant these only to the people who do those jobs."
- **[3:20]** "Need a true read-only viewer — say a trustee? Add them to Store Keeper and tick no capabilities. They can browse and read every report, but no scan or damage menus show."
- **[3:40]** "And when someone leaves, don't delete them — open their roster entry and untick 'On the roster'. Their history is preserved, and any linked login is archived automatically."
- **[3:58]** "Least access, a complete roster, and retire instead of delete. Thank you."

## Recording Checklist
1. Log in as a WMS Manager.
2. Open **WMS → Configuration → Store Keepers**; show the list columns (Name, Phone, Odoo login, On the roster).
3. Click **New**; type a name; save (roster-only entry).
4. On the entry, fill **Login** and **Initial password**; click **Create Odoo login**.
5. Show the **Capabilities (advantages)** toggles appearing; untick one (e.g. **Can Scan Issue**).
6. Click **Open login record** to show the linked `res.users`.
7. Open **Settings → Users → New**; add to **WMS / Store Keeper**; tick selected capabilities (and show **WMS / Manager**, **WMS / Repair Tech**, **Buyer** options).
8. Demonstrate a read-only viewer: a Store Keeper with no capabilities ticked.
9. Untick **On the roster** on a test entry to show retiring a keeper.
10. End on the Store Keepers list.
