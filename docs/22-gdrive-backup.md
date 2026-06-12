# 22 — Google Drive backup & restore

The WMS keeps three copies of every backup: the local encrypted pair in
`backups\`, the off-site mirror at `BACKUP_OFFSITE_DIR`, and — covered by this
guide — an encrypted copy on Google Drive under the operator's own Gmail
account. Drive is the *cloud tier*: it holds the long retention tail
(up to 2 years), survives the loss of both the production host and the
off-site medium, and is browsable from the Odoo UI.

The cloud tier is strictly additive. The local encrypted backup works
unchanged when Drive is disabled or unreachable, and **Drive errors never
fail the local backup** — every Drive failure is logged with the suffix
`(LOCAL backup is intact)` and retried automatically on the next run.

This document is the canonical Drive reference: one-time setup, daily
operation, settings, retention, restore, failure handling, and security.
For the local backup/restore pipeline itself see
[docs/18-restore-drill.md](18-restore-drill.md); for a full bare-metal
rebuild see [docs/19-disaster-recovery.md](19-disaster-recovery.md).

---

## 1. Overview and architecture

### 1.1 Backup path

`scripts\backup-native.ps1` runs as the scheduled tasks **"WMS Daily Backup"**
(daily 4:30 PM) and **"WMS Manual Backup"** (on demand), both as
`NT AUTHORITY\SYSTEM`. The Drive upload is Stage 5, after the local backup is
already complete and verified:

```
backup-native.ps1                                   (Task Scheduler, SYSTEM)
│
├─ 1. Database dump (encrypted)      wms-<stamp>.dump.gpg  + .sha256
├─ 2. Filestore zip (encrypted)      wms-<stamp>-filestore.zip.gpg + .sha256
├─ 3. Local retention                keep last 14
├─ 4. Off-site copy (optional)       BACKUP_OFFSITE_DIR, failure-safe
│
│  ──── local backup is COMPLETE here; nothing below can undo it ────
│
└─ 5. Google Drive upload (optional, failure-safe)
      ├─ 5a. pending sweep: re-upload sets that failed earlier
      │       (≤ 7 days old, oldest first, max 3 sets per run)
      ├─ 5b. upload today's set to Inventory_Backups/YYYY/MM-Month/YYYY-MM-DD/
      │       resumable 8 MiB chunks for files > 5 MB; verified against the
      │       Drive-computed sha256Checksum; retries 2 s/4 s/8 s + jitter
      ├─ 5c. catalog row (wms.gdrive.backup, uploaded=true)
      ├─ 5d. Drive retention tiers (daily 30 d / weekly 6 mo / monthly 2 y)
      └─ 5e. storage-quota cache + heartbeat + backup_gdrive audit row
```

Any Stage 5 failure warns `Drive upload failed (LOCAL backup is intact)`,
writes a failed `backup_gdrive` audit row plus a *pending* catalog row, pings
the `HEALTHCHECK_GDRIVE_URL` `/fail` endpoint, and leaves every local artifact
in place. The next run's pending sweep (5a) re-uploads it.

### 1.2 Restore path

Restore execution never happens in the web UI — the Odoo restore browser is a
read-only catalog (§ 7.1). The only executor is `scripts\gdrive-restore.ps1`:

```
gdrive-restore.ps1 -SetStamp <stamp> -AutoRestore -TargetDb <db>
│
├─ 0. PROD GUARD: target is live 'wms'? require -Force AND -ConfirmTarget wms
│      (literal typed match) or exit 5 BEFORE any side effect
├─ 1. emergency pre-restore backup
│      backup-native.ps1 -Source emergency -FilePrefix 'emergency-'
├─ 2. download set → TRIPLE SHA-256 verify (backup-info.json vs SHA256.txt
│      vs fresh Get-FileHash) → GPG AES256 envelope check → rename to local names
├─ 3. pg_restore --list TOC gate (≥ 100 entries)
├─ 4. live-aware Stop-Service Odoo-WMS (only when the restore can collide
│      with the live install; scratch-into-scratch leaves it running)
├─ 5. restore-native.ps1 -BackupFile <staged> -DbName <target> -Force
├─ 6. integrity probes (res_users ≥ 1, ir_module_module ≥ 1)
├─ 7. Start-Service Odoo-WMS + /wms/health poll (36 × 5 s)
└─ 8. restore_gdrive audit row + heartbeat + manager notification
```

A backup that has never been restored is not a backup — § 7 covers the
download-only verification path you should exercise periodically, and the
weekly drill in [docs/18-restore-drill.md](18-restore-drill.md) keeps proving
the local tier.

---

## 2. One-time setup

Done once per Google account, by the operator (NOT as SYSTEM). Budget
~15 minutes. Everything below is free-tier; no Google review is required.

### 2.1 Why an OAuth Desktop client (and why NOT a service account)

Service accounts are **impossible on consumer Gmail**: they have no storage
quota and cannot own files, so every upload into a folder shared from a
personal My Drive fails with `storageQuotaExceeded`. Shared drives (the
service-account workaround) require a paid Workspace subscription. The only
supported path for a personal Gmail account is OAuth 2.0 acting as the user —
hence the Desktop-app client and the one-time browser consent below.

### 2.2 Google Cloud Console steps

1. **Create a project** at https://console.cloud.google.com (any name, e.g.
   `wms-backup`).
2. **Enable the Google Drive API**: APIs & Services → Library → "Google Drive
   API" → Enable.
3. **Configure the OAuth consent screen**: APIs & Services → OAuth consent
   screen → User type **External** → fill in the app name + your email → add
   your own Gmail address as a **test user** → save.
4. **Publish the consent screen to "In production"** (same page, Publishing
   status → "Publish app").

   > **Do not skip this step.** While the consent screen sits in "Testing"
   > status, Google expires the refresh token after **7 days** — uploads work
   > for a week and then silently die with `GDRIVE_AUTH_EXPIRED` (§ 10.1).
   > Publishing requires **no verification review** because the app uses only
   > the non-sensitive `drive.file` scope.

5. **Create the OAuth client**: APIs & Services → Credentials → Create
   credentials → OAuth client ID → Application type **Desktop app**. Copy the
   client ID and client secret.

### 2.3 `.env` keys

Add the credentials to `.env` (all keys blank by default = feature disabled;
the block already exists in `.env.example`):

```ini
# --- Google Drive backup (optional; blank = disabled) ---------------------
GDRIVE_CLIENT_ID=<your Desktop-app client id>
GDRIVE_CLIENT_SECRET=<your Desktop-app client secret>
# Optional: ID of an existing My Drive folder to hold "Inventory_Backups".
# Blank = create Inventory_Backups at My Drive root.
GDRIVE_PARENT_FOLDER_ID=
# healthchecks.io-style heartbeat for the Drive upload stage (blank = off)
HEALTHCHECK_GDRIVE_URL=
```

Desktop-app client secrets are public-class credentials (they grant nothing
without a user consent), so plaintext `.env` storage matches the house
posture — see § 9.

### 2.4 Run the consent script once

```powershell
scripts\setup-gdrive-auth.ps1
```

The script opens your default browser for the Google consent prompt
(sign in as the backup account), then prints the connected account and its
storage quota, and creates the `Inventory_Backups` folder tree. The refresh
token is stored **DPAPI machine-scope** at `config\gdrive-token.json.dpapi`:
readable by `NT AUTHORITY\SYSTEM` (so the scheduled tasks can use it),
useless if copied off this machine, and gitignored.

Maintenance switches:

```powershell
scripts\setup-gdrive-auth.ps1 -Status     # decrypt + show account, mint date, refresh test
scripts\setup-gdrive-auth.ps1 -Revoke     # revoke the token at Google + delete the file
```

`✅ CHECKPOINT` — `setup-gdrive-auth.ps1` printed your Gmail address and
quota, `Test-Path config\gdrive-token.json.dpapi` is True, and the
`Inventory_Backups` folder is visible at https://drive.google.com.

The next daily run of **"WMS Daily Backup"** picks the token up
automatically — no service restart, no task re-registration. To confirm
immediately, use the Backup Now wizard (§ 4.2) or the Test buttons on the
settings page (§ 5.2).

---

## 3. What gets uploaded

### 3.1 Drive layout

```
<My Drive or GDRIVE_PARENT_FOLDER_ID>/
└── Inventory_Backups/                      (wms_gdrive.folder_name)
    ├── _connection_test/                   (Test Upload scratch; auto-cleaned)
    └── 2026/
        └── 06-June/
            └── 2026-06-12/
                ├── WMS_DB_2026-06-12_16-30-00.dump.gpg
                ├── WMS_FILESTORE_2026-06-12_16-30-00.zip.gpg
                ├── SHA256.txt
                └── backup-info.json
```

Multiple sets on one day (e.g. the 4:30 PM run plus a manual run) share the
day folder; the `.gpg` names differ by time, and the sidecars switch to
per-set names (`SHA256_<HH-MM-SS>.txt` / `backup-info_<HH-MM-SS>.json`) only
when a collision exists — the first set of the day keeps the bare names.

### 3.2 File naming — local names are UNCHANGED

Drive uses human-readable display names; the local filesystem keeps the
naming every existing consumer (restore-native, restore-drill, retention
globs, the health probe) depends on. `backup-info.json` carries the mapping,
and `gdrive-restore.ps1` renames downloads back to the local convention
before handing them to `restore-native.ps1`:

| Local name (unchanged) | Drive display name |
|---|---|
| `wms-20260612-163000.dump.gpg` | `WMS_DB_2026-06-12_16-30-00.dump.gpg` |
| `wms-20260612-163000-filestore.zip.gpg` | `WMS_FILESTORE_2026-06-12_16-30-00.zip.gpg` |

Uploads are verified without a re-download: the SHA-256 that Drive computes
server-side (`sha256Checksum`) must match the local `Get-FileHash` value, or
the remote file is deleted and the upload retried.

### 3.3 `backup-info.json` schema

One per backup set, uploaded into the day folder and mirrored into the Odoo
catalog (`info_json`). Exact keys:

```json
{
  "schema_version": 1,
  "set_stamp": "20260612-163000",
  "timestamp_utc": "2026-06-12T11:00:00Z",
  "timestamp_local": "2026-06-12 16:30:00 +05:30",
  "db_name": "wms",
  "backup_type": "auto",
  "creator": "system (scheduled)",
  "hostname": "DAKSHIN-WMS01",
  "wms_version": "19.0.3.0.0",
  "odoo_version": "19.0",
  "encryption": { "encrypted": true, "algorithm": "GPG symmetric AES256",
                  "note": "passphrase is NEVER stored on Drive" },
  "toc_entries": 1234,
  "files": [
    { "role": "db",
      "local_name": "wms-20260612-163000.dump.gpg",
      "drive_name": "WMS_DB_2026-06-12_16-30-00.dump.gpg",
      "size_bytes": 52428800, "sha256": "<64-hex>" },
    { "role": "filestore",
      "local_name": "wms-20260612-163000-filestore.zip.gpg",
      "drive_name": "WMS_FILESTORE_2026-06-12_16-30-00.zip.gpg",
      "size_bytes": 10485760, "sha256": "<64-hex>" }
  ],
  "retention": { "manual_exempt": false },
  "restore_hint": "scripts\\gdrive-restore.ps1 -SetStamp 20260612-163000"
}
```

- `backup_type` ∈ `auto` | `manual` | `emergency`; `retention.manual_exempt`
  is true for manual and emergency sets (§ 6).
- `creator` is `system (scheduled)` for the daily task, the Odoo login for
  Backup Now runs, or `<COMPUTERNAME>\<user>` for console runs.
- `files[]` omits the filestore entry when the filestore stage was skipped.

> **drive.file means the app only sees files it created.** Do NOT manually
> reorganize, rename, or move the `Inventory_Backups` tree in the Drive web
> UI — see § 9.4 for what breaks.

---

## 4. Daily operation

### 4.1 The scheduled tasks

`scripts\install-backup-tasks.ps1` registers three tasks, all with
`Principal=NT AUTHORITY\SYSTEM`, `LogonType=ServiceAccount`,
`RunLevel=Highest`, `-StartWhenAvailable`, `ExecutionTimeLimit=2h`, and
`MultipleInstances=IgnoreNew`:

| Task | Trigger | Action |
|---|---|---|
| "WMS Daily Backup" | Daily **4:30 PM** (default; `-BackupAt` overrides) | `backup-native.ps1 -Source auto` — full pipeline incl. Stage 5 |
| "WMS Weekly Restore Drill" | Sunday 3:00 AM (unchanged) | `restore-drill.ps1` — see [docs/18-restore-drill.md](18-restore-drill.md) |
| "WMS Manual Backup" | **None** (on demand only) | `backup-native.ps1 -Source manual` — run by the Backup Now wizard via `schtasks /Run` |

The daily default moved from 1:00 PM to 4:30 PM with the Drive sprint;
existing installs pick the new time up by re-running
`scripts\install-backup-tasks.ps1` (idempotent).

### 4.2 Backup Now (storekeeper-friendly)

**WMS → Back Up Now** shows a single "Back Up Now" button. It runs the exact
same SYSTEM pipeline as the daily task (by triggering "WMS Manual Backup"),
so there is no permission or environment drift. The wizard polls the audit
trail and, on success, shows the backup filename, size, and Drive upload
time in plain language. If the Drive upload fails, it says so and reassures:
the local backup is safe and the upload retries automatically.

Access is gated by the capability group **"WMS / Can Run Backup Now"** —
implied into WMS / Manager automatically, and grantable per storekeeper by
the admin (Settings → Users). Keepers with the group see ONLY this menu;
no restore or catalog surface is visible to them (§ 7.1).

### 4.3 Notifications

Scripts never call Odoo over HTTP; outcomes land as audit rows and two crons
turn them into manager notifications (Discuss inbox + systray):

| Cron | Schedule | What it does |
|---|---|---|
| Drive event notifier | hourly at :25 | New `backup_gdrive` / `restore_gdrive` rows → manager Discuss inbox (success notes obey `wms_gdrive.notify_success`; failures obey `wms_gdrive.notify_failure`) |
| Drive freshness check | daily 08:05 | Last successful upload older than **26 h** → staleness warning row + notification, deduplicated to one alert per 20 h |

### 4.4 Health surface

`/wms/health` (token-gated — see
[docs/19-disaster-recovery.md § 6.2](19-disaster-recovery.md)) and the WMS
Self-Diagnostics page gain these fields once Drive is configured:

| Field | Meaning |
|---|---|
| `gdrive_enabled` | Drive stage is configured and not kill-switched |
| `drive_connected` | Recent successful upload or fresh connection probe |
| `last_upload_age_hours` | Age of the newest successful Drive upload |
| `drive_storage_used_mb` / `drive_storage_limit_mb` | Cached Drive quota (warning above 90%) |
| `next_backup_at` | Next "WMS Daily Backup" fire time per `wms_gdrive.backup_time` |

**Drive problems are DEGRADED only, never CRITICAL.** CRITICAL stays reserved
for the local pipeline: a Drive outage must not page like a failed backup,
because the local artifact is unaffected.

`✅ CHECKPOINT` — the day after setup, `/wms/health` shows
`drive_connected: true` with `last_upload_age_hours` under 24, and the set is
visible in the Drive web UI under `Inventory_Backups/<year>/<month>/<today>`.

---

## 5. Settings reference

### 5.1 `ir.config_parameter` keys (namespace `wms_gdrive.*`)

All parameters are read by the PowerShell side via psql with failure-safe
hardcoded defaults — a down database never blocks a local backup.

| Key | Default | Meaning |
|---|---|---|
| `wms_gdrive.enabled` | `1` | Soft kill-switch for the Drive stage (the token file is the hard gate) |
| `wms_gdrive.manual_enabled` | `1` | Backup Now wizard allowed |
| `wms_gdrive.backup_time` | `16:30` | Daily backup time shown in Settings; Apply Schedule pushes it to Task Scheduler |
| `wms_gdrive.notify_success` | `1` | Manager notification on each successful upload |
| `wms_gdrive.notify_failure` | `1` | Manager notification on failed upload / staleness |
| `wms_gdrive.retention_daily_days` | `30` | Tier 1: keep every set this many days |
| `wms_gdrive.retention_weekly_months` | `6` | Tier 2: keep one set per week this many months |
| `wms_gdrive.retention_monthly_years` | `2` | Tier 3: keep one set per month this many years |
| `wms_gdrive.delete_manual` | `0` | If `1`, manual + emergency sets join Drive retention (§ 6) |
| `wms_gdrive.folder_name` | `Inventory_Backups` | Drive root folder name |
| `wms_gdrive.last_about` | *(internal)* | Cached quota JSON `{used_mb, limit_mb, checked_utc, email}` |
| `wms_gdrive.last_manual_requester` | *(internal)* | `login|timestamp` handshake that attributes Backup Now runs |

### 5.2 The Settings wizard

**WMS → Configuration → Google Drive Settings** (manager-only) fronts the
parameters above — enable flags, backup time, notification flags, retention
tiers, folder name — plus a health strip and three buttons:

- **Test Connection** — refreshes the token and reads the connected account
  + storage quota. Renders the Gmail address and a usage bar, or the error
  (auth-expired failures include the re-consent instruction).
- **Test Upload** — uploads a 1 KB probe file to
  `Inventory_Backups/_connection_test/`, verifies its `sha256Checksum`, and
  deletes it. Proves the full write path end to end.
- **Apply Schedule** — best-effort `schtasks /Change` of the "WMS Daily
  Backup" start time to `wms_gdrive.backup_time`; if that fails it tells you
  to re-run `scripts\install-backup-tasks.ps1 -BackupAt <time>` instead.
  Never throws.

Both test buttons shell out to `scripts\gdrive-test.ps1` — the same
PowerShell stack, token, and retry policy the daily task uses, so a green
test is representative.

---

## 6. Retention

### 6.1 Drive tiers

Drive retention runs once per successful upload (Stage 5d), driven by the
three `wms_gdrive.retention_*` parameters:

| Tier | Window (default) | Kept |
|---|---|---|
| Daily | 30 days | every set |
| Weekly | 6 months | newest set per ISO week |
| Monthly | 2 years | newest set per calendar month |
| Older | — | deleted |

### 6.2 Manual and emergency sets are exempt

Sets with `backup_type` `manual` or `emergency` are **never deleted by Drive
retention** unless `wms_gdrive.delete_manual` is set to `1` in Settings. The
exemption is recorded both in `backup-info.json` (`retention.manual_exempt`)
and in each file's Drive metadata, which is what the retention query filters
on.

### 6.3 Local retention is unaffected

The local window stays at **keep last 14** dumps and the off-site mirror
behavior is unchanged. The two retentions are deliberately independent:
local holds the fast-restore window, Drive holds the long tail. Pending
(never-uploaded) sets are invisible to Drive retention by construction, and
retention only runs *after* a successful upload — no failure mode can delete
the only copy of anything.

---

## 7. Restore

### 7.1 The restore browser (read-only, manager-only)

**WMS → Configuration → Drive Restore Browser** shows the Drive catalog
grouped Year → Month → Day, with size, checksum, type
(auto/manual/emergency), creator, and upload state per set. Opening a set
shows the pre-restore facts plus the exact copy-paste
`gdrive-restore.ps1` command for that set. The browser cannot restore
anything — execution happens only on the console (house policy: no
web-triggered restore). Storekeepers see no restore surface at all: no menu,
no model access.

### 7.2 `scripts\gdrive-restore.ps1` reference

Run from an Admin PowerShell on the production host.

**List the catalog:**

```powershell
scripts\gdrive-restore.ps1 -List
scripts\gdrive-restore.ps1 -List -Year 2026 -Month 06     # optional filters (-Day too)
```

**Download + verify only (no restore):**

```powershell
scripts\gdrive-restore.ps1 -SetStamp 20260612-163000
```

Downloads the set into `backups\restore-staging\` (override with
`-DownloadTo`), verifies SHA-256 with **triple agreement**
(`backup-info.json` vs `SHA256.txt` vs a fresh `Get-FileHash`), verifies the
GPG symmetric AES256 envelope, renames the files back to the local naming
convention, then prints the exact `restore-native.ps1` command to run next.
Nothing is restored.

**Full automated restore:**

```powershell
# Scratch / new database — safe form:
scripts\gdrive-restore.ps1 -SetStamp 20260612-163000 -AutoRestore -TargetDb wms_restore_20260612

# LIVE production database — both guard arguments are mandatory:
scripts\gdrive-restore.ps1 -SetStamp 20260612-163000 -AutoRestore -TargetDb wms -Force -ConfirmTarget wms
```

The orchestration is § 1.2: emergency pre-restore backup first
(`backup-native.ps1 -Source emergency -FilePrefix 'emergency-'`; the restore
aborts if it fails), download + triple verification, a
`pg_restore --list` TOC gate (≥ 100 entries), a live-aware
`Stop-Service Odoo-WMS` (skipped for scratch-into-scratch restores),
`restore-native.ps1 -Force`, integrity probes, service restart with a
180-second `/wms/health` poll, and a `restore_gdrive` audit row.

**Production guard.** Restoring over the live `wms` database requires BOTH
`-Force` AND the literal typed `-ConfirmTarget wms`. Without them the script
exits 5 **before any side effect** — no emergency backup, no download, no
service stop.

**Emergency backups** are named `emergency-wms-<stamp>.dump.gpg` (+ filestore
half). The prefix keeps them out of every local retention glob and they
upload to Drive as `backup_type=emergency` — exempt on both tiers (§ 6.2),
never auto-deleted.

**Unattended / one-shot runs:**

```powershell
scripts\gdrive-restore.ps1 -SetStamp <stamp> -AutoRestore -TargetDb <db> -AsTask        # fires in ~1 min
scripts\gdrive-restore.ps1 -SetStamp <stamp> -AutoRestore -TargetDb <db> -AtNextBoot    # fires at next boot
```

`-AsTask` registers a one-shot SYSTEM scheduled task **"WMS Restore Once"**
that re-invokes the script with the resolved arguments plus `-Unattended`
and unregisters itself when done. Unattended mode requires
`BACKUP_PASSPHRASE` in `.env` (no interactive prompt fallback).

**Exit codes** (Event Log id = 400 + code):

| Code | Name | Meaning |
|---|---|---|
| 0 | OK | Completed |
| 1 | SET_NOT_FOUND | No Drive set matches `-SetStamp` |
| 2 | DOWNLOAD_FAILED | Drive download error |
| 3 | VERIFY_FAILED | SHA-256 / GPG envelope mismatch — nothing restored |
| 4 | RESTORE_FAILED | restore-native / probes / health poll failed |
| 5 | PROD_GUARD | Live-`wms` target without `-Force` + `-ConfirmTarget wms` |
| 6 | AUTH_EXPIRED | Drive token expired — re-run `setup-gdrive-auth.ps1` |

Logs: `.runtime\logs\gdrive-restore.log` plus best-effort Windows Event Log
entries under source `WMS_Backup_Drill`.

`✅ CHECKPOINT` — after any restore, the newest `wms_backup_audit` row is
`restore_gdrive` with `status='OK'`, `/wms/health` returns 200, and the
emergency pair sits in `backups\` with the `emergency-` prefix.

---

## 8. Failure handling matrix

Design rule (P14): **no failure mode may lose a valid backup.** Local
artifacts are never deleted on upload failure, and Drive retention only runs
after a successful upload.

| Failure | Automatic behavior | Operator action |
|---|---|---|
| Drive unreachable (offline, DNS, 429/5xx) | Retries 2 s/4 s/8 s + jitter; on final failure: `(LOCAL backup is intact)` warning, failed `backup_gdrive` audit row, pending catalog row, `/fail` heartbeat to `HEALTHCHECK_GDRIVE_URL`; next run's pending sweep re-uploads (≤ 7 days old, oldest first, max 3 sets/run) | Usually none — confirm the next run clears the pending row, or run Backup Now to trigger the sweep immediately |
| Auth expired (`GDRIVE_AUTH_EXPIRED`) | Same as above, plus health goes DEGRADED ("Google Drive auth expired") and managers get a notification with the fix command | Re-run `scripts\setup-gdrive-auth.ps1`; if the consent screen is still in "Testing", publish it to "In production" first (§ 10.1) |
| Drive quota full | Upload fails into the same pending/retry path; health warns when storage exceeds 90% of the quota | Free space in the Google account, upgrade storage, or tighten the retention tiers in Settings |
| Upload interrupted mid-transfer (reboot, network drop) | Resumable sessions continue from the last confirmed chunk; visible partial files failing the `sha256Checksum` check are deleted; the set is re-uploaded by the pending sweep if the run died | None |
| "WMS Manual Backup" task missing | Backup Now fails gracefully with a plain-language hint to ask the administrator | Re-run `scripts\install-backup-tasks.ps1` |
| Catalog/parameter access fails (psql error) | Reads fall back to hardcoded defaults; catalog writes warn and continue — the upload itself still completes | None; bookkeeping reconciles on later runs |

In every row, the local `.gpg` pair and the off-site mirror are already
written before Stage 5 starts — the cloud tier can only ever *lag*, never
*lose*.

---

## 9. Security notes

For the full control framework see [SECURITY.md](../SECURITY.md) and
[docs/08-security.md](08-security.md); this section covers what the Drive
integration adds.

### 9.1 Scope: `drive.file` only

The app holds exactly one OAuth scope, `drive.file` — per-file access to
files **the app itself created**. It cannot read the operator's mail, other
Drive files, Photos, or anything else in the account. The scope is
classified non-sensitive by Google, which is why publishing the consent
screen requires no verification review.

### 9.2 The token file

`config\gdrive-token.json.dpapi` holds the refresh token as a DPAPI
**machine-scope** blob: readable by any local process on this box (including
`NT AUTHORITY\SYSTEM`, which the scheduled tasks need), and **useless if
exfiltrated** — DPAPI machine keys do not leave the host. On-box readability
equals the existing trust boundary of the plaintext `BACKUP_PASSPHRASE` in
`.env`. The file is gitignored. Revocation is instant: run
`setup-gdrive-auth.ps1 -Revoke`, or Google Account → Security → Third-party
access.

### 9.3 What a theft actually yields

| Stolen asset | Attacker gets |
|---|---|
| `.env` (client id/secret) | Nothing by itself — Desktop-app client secrets are public-class; using them to phish a consent mints a *different* token, not ours |
| `gdrive-token.json.dpapi` copied off-box | Nothing — undecryptable without this machine's DPAPI keys |
| The Google account itself | Ciphertext only — every artifact on Drive is a GPG AES256 envelope, and `BACKUP_PASSPHRASE` never leaves the box (stated explicitly in `backup-info.json`) |

### 9.4 Do not reorganize the Drive tree

Because of `drive.file`, the app finds its files by ID and by app-private
metadata, so files you move stay restorable — but the folder-tree lookup
creates a **fresh `Inventory_Backups` tree** for new uploads if the old one
was renamed or moved, splitting your history across two trees. Treat
`Inventory_Backups` as machine-managed: browse it, download from it, but do
not move, rename, or "tidy" it in the Drive UI.

---

## 10. Troubleshooting

### 10.1 PINNED — uploads worked for a week, then died: the "Testing" status trap

Symptom: setup succeeded, daily uploads ran for ~7 days, then every run logs
`GDRIVE_AUTH_EXPIRED`, health shows DEGRADED, managers get the failure
notification. Cause: the GCP OAuth consent screen is still in **"Testing"**
publishing status, so Google expires the refresh token every 7 days.

Fix, in this order:

1. Google Cloud Console → APIs & Services → OAuth consent screen →
   Publishing status → **"Publish app"** (to "In production"; no review is
   needed for `drive.file`).
2. Re-run `scripts\setup-gdrive-auth.ps1` to mint a fresh token.
3. The next backup run's pending sweep uploads anything that accumulated
   while auth was dead — no data was lost (§ 8).

**"Google Drive auth expired" at any other time**
The token was revoked (Google Account security action, password-incident
cleanup, `-Revoke`) or unused for 6 months. Same fix: re-run
`scripts\setup-gdrive-auth.ps1`. Use `setup-gdrive-auth.ps1 -Status` to
inspect the stored token first.

**Health warns "Google Drive storage above 90%"**
The free Gmail tier is 15 GB shared with Gmail/Photos. Options: clear space
in the account, buy Google One storage, or tighten
`wms_gdrive.retention_daily_days` / the weekly/monthly tiers in Settings.
Until resolved, uploads that fail on quota sit in the pending queue and
retry — local backups are unaffected.

**Backup Now shows "Ask your administrator to run install-backup-tasks.ps1"**
The "WMS Manual Backup" task is not registered on this host (the installer
predates the Drive sprint, or the task was deleted). Re-run
`scripts\install-backup-tasks.ps1` from an Admin PowerShell — it idempotently
(re)registers all three tasks and applies the 4:30 PM default.

**Backup log says `Google Drive upload: disabled (run scripts\setup-gdrive-auth.ps1 to enable)`**
The feature gate is closed: the token file is missing,
`GDRIVE_CLIENT_ID`/`GDRIVE_CLIENT_SECRET` are blank in `.env`, or
`wms_gdrive.enabled` is `0`. Complete § 2, or re-enable in Settings.

**Sets missing from the restore browser / a second `Inventory_Backups` appeared in Drive**
Someone manually reorganized the tree in the Drive UI (§ 9.4). Existing sets
remain restorable by `-SetStamp`; new uploads went into the fresh tree.
Leave both trees in place and stop manual reorganizing — history reconverges
as retention ages the old tree out.

---

## 11. Status

Full end-to-end verification has been run against a mock Drive endpoint on
scratch databases: a marker record survived backup → upload → download →
restore, a tampered download was rejected (exit 3) before any restore, and
the production guard refused an unconfirmed live-`wms` target (exit 5).
**Live-Drive E2E is pending the operator's GCP credentials**, and a
supervised production restore drill (`-ConfirmTarget wms` against the live
database) is pending a scheduled maintenance window.

---

## 12. References

- `scripts\setup-gdrive-auth.ps1` — one-time consent + `-Status` / `-Revoke` (§ 2.4).
- `scripts\backup-native.ps1` — backup pipeline; Stage 5 is the Drive upload (§ 1.1).
- `scripts\gdrive-restore.ps1` — list / download / verify / auto-restore (§ 7.2).
- `scripts\gdrive-test.ps1` — connection/upload probe behind the Settings test buttons (§ 5.2).
- `scripts\install-backup-tasks.ps1` — registers all three scheduled tasks (§ 4.1).
- `scripts\gdrive-lib.ps1` — shared Drive REST library (dot-sourced by the above).
- [docs/18-restore-drill.md](18-restore-drill.md) — weekly drill proving the local `.dump.gpg` is recoverable.
- [docs/19-disaster-recovery.md](19-disaster-recovery.md) — bare-metal rebuild runbook; Drive is an additional recovery source.
- [docs/13-operations-playbook.md](13-operations-playbook.md) — day-2 operations incl. backup defaults.
- [docs/INSTALLATION-GUIDE.md](INSTALLATION-GUIDE.md) — first-time install; Drive setup slots in after backup-task registration.
- [SECURITY.md](../SECURITY.md) / [docs/08-security.md](08-security.md) — control framework the § 9 notes extend.
