# Prompt: set up (or refresh) the WMS on another device

Copy the block below and paste it into Claude Code on the **other** machine — or
hand it to whoever is setting that machine up. It is self-contained: it assumes
no knowledge of this repo.

Pick **one** of the two goals in step 0 before you send it, and delete the other.

---

```text
Set up the Dakshin Vrindavan warehouse system (Odoo 19 CE) on THIS Windows
machine, using the latest code.

Repository: https://github.com/udhay8005/Inventory-management  (branch: main)

## 0. Which outcome I want  — KEEP ONE LINE, DELETE THE OTHER

GOAL A — a CLEAN system: latest code, empty database, no stock or history.
GOAL B — a COPY of the live warehouse: latest code plus the production data,
         restored from an encrypted backup file I will provide.

## 1. Safety check before anything else

This machine must NOT be the production warehouse PC (hostname GAUSHALAPC3,
which runs the live database 'wms'). Print the hostname and confirm with me
before continuing. If it IS that machine, stop — the instructions below would
destroy the trust's live inventory records.

## 2. Prerequisites

- Windows 10/11, and an Administrator PowerShell.
- Python 3.11 or 3.12. NOT 3.13 — Odoo 19 needs rl-renderPM, which has no
  3.13 build. Install with:  winget install Python.Python.3.12
- git. The installer handles PostgreSQL, wkhtmltopdf and NSSM itself.

Check the Python version first and tell me what you find before proceeding.

## 3. Clone and configure

    git clone https://github.com/udhay8005/Inventory-management.git
    cd Inventory-management
    copy .env.example .env

Then edit .env and set at minimum:
  DB_PASSWORD         a new strong password for the local PostgreSQL 'odoo' user
  ODOO_ADMIN_PASSWD   the Odoo master password for this machine
  BACKUP_PASSPHRASE   the key that encrypts backups

  IMPORTANT for GOAL B: BACKUP_PASSPHRASE must be the SAME value as on the
  machine the backup came from, or the .gpg backup cannot be decrypted. Ask me
  for it; do not invent one.

Do not commit .env — it is gitignored, and this repository is public.

## 4. Install

    powershell -ExecutionPolicy Bypass -File .\scripts\install-native.ps1

This installs PostgreSQL, Python tooling and wkhtmltopdf, clones Odoo 19 at the
exact revision pinned in the ODOO_REV file (not the moving branch head), creates
the virtualenv, and creates an empty database.

If PostgreSQL is already installed on a non-standard port, pass it, e.g.
    ... .\scripts\install-native.ps1 -DbPort 1088

Then register the auto-starting Windows service:

    powershell -ExecutionPolicy Bypass -File .\scripts\install-odoo-service.ps1

## 5a. GOAL A only — build a clean database

    powershell -ExecutionPolicy Bypass -File .\scripts\reset-database.ps1

This drops the database, recreates it, and installs all TEN addons on the
current code. It takes an encrypted backup first and asks you to type the
database name to confirm. On a brand-new machine with nothing in it you may
pass -Force to skip the prompt.

Note: install-native.ps1 -Reset does NOT do this — that switch only wipes the
cloned Odoo source and the venv, and leaves the database alone.

## 5b. GOAL B only — restore the live data, then bring it to current code

    powershell -ExecutionPolicy Bypass -File .\scripts\restore-native.ps1 `
        -BackupFile <path to wms-<timestamp>.dump.gpg> -Force

    powershell -ExecutionPolicy Bypass -File .\scripts\upgrade-service.ps1

The restore needs BACKUP_PASSPHRASE from step 3. The upgrade then applies any
database migrations the newer code carries, so the restored data ends up on the
current schema. Do NOT run reset-database.ps1 for this goal — it would delete
the data you just restored.

## 6. Verify, and report back to me

Confirm and show me the evidence for each:

1. All TEN addons are installed. The ten are: wms_location, wms_fifo,
   wms_barcode, wms_repair_damage, wms_ai_forecast, wms_reports, wms_training,
   wms_perishable, wms_analytics, wms_pharmacy.
2. The Odoo-WMS service is running and something is listening on port 8069.
3. Signing in at http://localhost:8069 works. On GOAL A the login is
   admin / admin — change it immediately and tell me you have.
4. WMS -> Reports -> Self-Diagnostics shows no FAIL. In particular these two
   must both read 0, they are the warehouse-blindness checks:
     "Storage outside the warehouse tree (audit blind spot)"
     "Stock the weekly audit cannot see"
5. For GOAL B only: the location count and total on-hand quantity match the
   source machine. Tell me both numbers.

## 7. Ground rules

- Never run reset-database.ps1 against the production machine.
- Every script self-elevates and shows a UAC prompt; I will approve it. Watch
  the elevated window that opens — that is where the output appears.
- If a step fails, stop and show me the actual error. Do not improvise a
  dropdb, a manual schema edit, or a pip install outside the venv.
- Do not commit anything to the repository from this machine unless I ask.
```

---

## Notes for you (not part of the prompt)

**Which goal do you want on the other device?**

- **Goal A** is right for a training machine, a spare desk, or a second store —
  a clean system nobody's data is on yet.
- **Goal B** is right for a standby machine that should be able to take over,
  or for testing an upgrade against real data before touching production.

**Getting a backup to the other device.** Backups are in `backups\` on the
production machine, encrypted, and copied to whatever `BACKUP_OFFSITE_DIR`
points at. Copy both files for the timestamp you want — the `.dump.gpg` and the
matching `-filestore.zip.gpg`. Without the filestore you lose attachments and
label logos.

**The passphrase is the whole security model.** `BACKUP_PASSPHRASE` is not
recoverable. If the other device gets a different value, backups made there
cannot be restored on the production machine, and vice versa.

**Two machines, one database, is not supported.** Each install has its own local
PostgreSQL. If you want them to share data, that is a different setup — ask
before wiring it up.
