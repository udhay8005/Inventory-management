# Install / Update / Rebuild — the three commands

Everything you can do to a WMS machine is one of three things. Pick the one you
actually want, because two of them keep your data and one destroys it.

| I want to… | Command | Your data |
|---|---|---|
| Set up a **new machine** | `scripts\install-native.ps1` | n/a — new |
| **Move to the latest code** and keep everything | `scripts\upgrade-service.ps1` | **kept** |
| **Start clean** — wipe the database, keep the code | `scripts\reset-database.ps1` | **destroyed** |

All three ask for Windows admin rights and show a UAC prompt. Approve it, and
watch the elevated window that opens — that is where the output goes.

---

## A. Update to the latest code — the normal one

This is what you run after any change is merged. It backs up first, applies
database migrations, and restarts the service.

```powershell
cd D:\Udhay\projects\Inventory_mngt
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\upgrade-service.ps1
```

It upgrades all ten addons by default. Nothing is deleted; stock, history,
users and passwords all survive. A pre-upgrade backup is taken automatically —
that is your rollback point, so don't pass `-SkipBackup`.

**Check it worked.** Sign in and open **WMS → Reports → Self-Diagnostics**.
Everything should read OK or WARN; a FAIL means look before carrying on.

---

## B. Rebuild the database clean — destroys data

For when you have finished piloting and want a fresh production database on the
current code. **This deletes every product, location, stock figure, batch,
issue, return, audit, damage and repair record, user and password.**

```powershell
cd D:\Udhay\projects\Inventory_mngt
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\reset-database.ps1
```

It backs up first, then makes you **type the database name** to confirm, then
drops it, recreates it, installs all ten addons, and restarts the service.

Afterwards you sign in as `admin` / `admin`, **change that password**, and
rebuild your storage structure and stock. Nothing carries over.

> `install-native.ps1 -Reset` is **not** this. That switch wipes the cloned Odoo
> source and the Python venv and leaves the database alone.

**Changed your mind after it ran?** The backup it took is under `backups\`:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\scripts\restore-native.ps1 -BackupFile .\backups\wms-<timestamp>.dump.gpg
> ```
>
> You need `BACKUP_PASSPHRASE` from your `.env` — without it the backups cannot
> be decrypted by anyone, including you.

---

## C. Fresh machine

```powershell
# From an Administrator PowerShell:
git clone https://github.com/udhay8005/Inventory-management.git
cd Inventory-management
copy .env.example .env       # edit it: set DB_PASSWORD and BACKUP_PASSPHRASE
powershell -ExecutionPolicy Bypass -File .\scripts\install-native.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\reset-database.ps1 -Force
```

The installer sets up PostgreSQL, Python, wkhtmltopdf, the pinned Odoo source
and the venv, and creates an empty database. The second command installs the
ten WMS addons into it. Then open <http://localhost:8069>.

Needs **Python 3.11 or 3.12** — not 3.13 (Odoo's PDF library has no 3.13 build).
Odoo itself is pinned to the revision in `ODOO_REV`, so you get the same Odoo
this system was tested against rather than whatever the branch head is today.

---

## Paste-in prompt for Claude Code

If you would rather have Claude Code do it on the machine, paste this:

```text
Update the Dakshin Vrindavan WMS on this machine to the latest code.

Repo: D:\Udhay\projects\Inventory_mngt   Service: Odoo-WMS   DB: wms   Port: 8069

Do this:
1. git pull on main, and tell me what changed since the deployed version.
2. BEFORE touching the live database, dry-run the upgrade against a copy:
     CREATE DATABASE wms_dryrun WITH TEMPLATE wms;
   then run the upgrade against wms_dryrun and confirm it completes with no
   errors and no data loss (compare location count and total on-hand before
   and after).
3. Only if the dry run is clean, run scripts\upgrade-service.ps1 for real.
   It self-elevates; I will approve the UAC prompt.
4. Verify on the live system: all ten addons at their new versions, the service
   listening on 8069, and Self-Diagnostics showing no FAIL.
5. Report what changed and anything I should check in the warehouse.

Do NOT drop or recreate the live database. If you think a rebuild is needed,
stop and ask me first.
```

For a clean rebuild instead, replace steps 2–3 with:

```text
2. Take a full backup and tell me where it is.
3. Run scripts\reset-database.ps1 to drop and rebuild the database on the
   current code. I understand this destroys all stock and history.
```

---

## If something goes wrong

| Symptom | What to do |
|---|---|
| UAC prompt cancelled | Nothing happened. Re-run the command. |
| "Missing required path … run install-native.ps1 first" | The venv or Odoo source is missing — run the installer. |
| DROP DATABASE says "being accessed by other users" | The service restarted mid-run. `Stop-Service Odoo-WMS`, then re-run. |
| Service starts but nothing on 8069 | Check `.runtime\logs\odoo.log`. |
| Need yesterday's data back | `restore-native.ps1 -BackupFile .\backups\<file>.dump.gpg` — needs `BACKUP_PASSPHRASE`. |

Backups live in `backups\`, encrypted, with a copy in the off-site folder set by
`BACKUP_OFFSITE_DIR`. Fourteen are kept.
