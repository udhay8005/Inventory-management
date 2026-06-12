# SOP 13 — Cloud Backup to Google Drive (Back Up Now, Drive Health, Settings)

## Purpose
This procedure covers the **cloud backup tier**: every encrypted backup also gets a second copy in the trust's Google Drive, off the store-room computer, so a fire, theft, or dead disk in the building cannot take the data and its backups together.

- **Back Up Now** — a one-button wizard any permitted keeper can use to send a fresh copy to Google Drive immediately. No technical knowledge needed.
- **Drive health** — where a Manager confirms the uploads are actually happening (Self-Diagnostics and `/wms/health`).
- **Settings & test buttons** — the Manager-only page that controls the schedule, notifications, and retention, with Test Connection / Test Upload buttons.

The local encrypted backup always runs and is always kept regardless of the cloud tier — Google Drive is the off-site copy on top, never a replacement. For the local backup, the weekly restore drill, and the Backup & DR Audit screen, see SOP 11 (`11-backup-restore-health.md`). The full technical reference is `docs/22-gdrive-backup.md`.

## Who Uses It
- **Store Keeper** with the **"WMS / Can Run Backup Now"** capability — can use the **Back Up Now** wizard, and nothing else of the cloud tier. The Admin grants this per keeper from the user form; Managers have it automatically.
- **WMS / Manager (Admin)** — everything: Back Up Now, the Google Drive Backup settings page, Self-Diagnostics, and the read-only Google Drive Backups browser.
- Keepers deliberately see **no restore surface at all** — restoring is a Manager-and-server job (see section E).
- Read-only viewers are not involved.

## Prerequisites
- The one-time Drive connection has been made on the server: `scripts\setup-gdrive-auth.ps1` run once by the Admin (browser consent; prints the connected account and quota). The Google Cloud setup behind it — including publishing the OAuth consent screen to **"In production"** — is documented in `docs/22-gdrive-backup.md` §2.
- The scheduled tasks are installed (`scripts\install-backup-tasks.ps1`): the Back Up Now wizard works by firing the trigger-less **"WMS Manual Backup"** task, which runs as **NT AUTHORITY\SYSTEM** exactly like the daily **"WMS Daily Backup"** (4:30 PM).
- The keeper has been granted **"WMS / Can Run Backup Now"** (otherwise the menu simply does not appear).

## Step-by-Step Instructions

### A. Back Up Now (keeper or manager)
1. Open **WMS → Back Up Now** (it sits in the main WMS menu, not under Configuration).
2. Read the note on the screen: it makes a safe copy of all WMS data and sends it to Google Drive. **Nothing is deleted or changed**, and you can keep working while it runs.
3. Click **Back Up Now**.
4. The screen reports "Backup started". The whole run takes a few minutes — click **Refresh** to check progress, or close the window and come back later. Double-clicking is harmless; the backup never runs twice at once.
5. When it finishes, the success screen shows three things: the **backup filename**, its **size in MB**, and the **time it was uploaded to Google Drive**.
6. If it instead says **"Drive upload pending"** — the safe copy was made on the server but Google Drive was not reachable. Nothing is lost; the upload is retried automatically on the next backup run.

### B. What the cloud copy looks like (plain language)
- In Google Drive the files live in a folder called **Inventory_Backups**, organised Year → Month → Day. Every set holds the encrypted database and filestore plus a checksum file and a small `backup-info.json` description.
- The files are **encrypted (GPG AES256) before they leave the computer** and their SHA-256 checksums are verified after upload — a copy that doesn't match is retried, never trusted.
- Old copies are tidied automatically by retention tiers: **daily copies ~30 days, weekly ~6 months, monthly ~2 years**. Manual (Back Up Now) and emergency copies are exempt — they stay until a Manager decides otherwise.
- **Never move, rename, or delete anything inside Inventory_Backups from the Drive website.** The app uses the minimal `drive.file` permission, meaning it can only see files it created itself — a hand-"tidied" file becomes invisible to the system.

### C. Manager: check Drive health
1. Open **WMS → Reports → Self-Diagnostics** (Manager-only) and run the checks. The system-health row includes the Drive snapshot: whether the cloud tier is enabled and connected, the **age of the last upload in hours**, **Drive storage used / limit**, and **when the next backup is due**.
2. The same fields appear on **`/wms/health`** (`gdrive_enabled`, `drive_connected`, `last_upload_age_hours`, storage used/limit, `next_backup_at`), so an external monitor sees them too.
3. **Drive problems can only ever make health DEGRADED, never CRITICAL** — the local backup is what pages. A DEGRADED status with a Drive warning means: read the warning (stale upload, auth expired, storage above 90%) and fix at leisure; the local safety net is intact.
4. You don't have to look for problems yourself: a daily **freshness check at 08:05** flags an upload older than ~26 hours, and an hourly notifier (at :25) delivers Drive successes/failures to the Managers' Discuss inbox, per the notification settings in section D.

### D. Manager: settings and the test buttons
1. Open **WMS → Configuration → Google Drive Backup** (Manager-only).
2. The page fronts the `wms_gdrive.*` parameters: enable switches for the automatic upload and for Back Up Now, the **backup time** (default `16:30`), success/failure **notification switches**, the **retention tiers**, and the Drive **folder name**.
3. **Test Connection** — confirms the server can reach Google Drive and shows the connected account and storage quota (it runs `scripts\gdrive-test.ps1` behind the scenes). Use it monthly and after any Google account change.
4. **Test Upload** — round-trips a tiny test file to Drive and verifies it, proving the whole upload path end to end without waiting for the next backup.
5. **Apply Schedule** — pushes a changed backup time into the Windows scheduled task, so the screen and the real schedule cannot drift apart.
6. Click **Save** after changing any setting.

### E. Manager: where restore lives (pointer only)
Restoring from Drive is deliberately **not** part of the keeper-facing flow and is never a one-click web action. A Manager can browse the catalog at **WMS → Configuration → Google Drive Backups** (read-only, grouped Year → Month → Day, with size, checksum, and creator) and copy the ready-made `gdrive-restore.ps1` command from a set's form. The full restore runbook — download, triple verification, `-AutoRestore`, and the production guard — is `docs/22-gdrive-backup.md` §7.

## Worked Example
A keeper finishes entering a festival week's receipts at 6 PM — too late for the day's 4:30 PM automatic backup to have caught the afternoon's work.

1. The keeper opens **WMS → Back Up Now** and clicks **Back Up Now**. The screen says the backup has started; they keep working.
2. Two minutes later they click **Refresh**. The success screen shows the backup filename, its size in MB, and "Uploaded to Google Drive at 18:04".
3. On Monday the Manager opens **Self-Diagnostics**: Drive connected, last upload a few hours old, storage well under the limit — nothing to do.

## Common Errors & What They Mean
- **"Backup Now is turned off."** — A Manager disabled manual backups in the settings page (`wms_gdrive.manual_enabled`). The daily automatic backup is unaffected.
- **"Could not start the backup."** — The **"WMS Manual Backup"** scheduled task is not installed on the server. The Admin runs `scripts\install-backup-tasks.ps1` once, then try again.
- **"Drive upload pending — it will be retried automatically."** — The local backup succeeded but the upload didn't (offline, quota, interruption). Nothing is lost; the next run's pending sweep retries it.
- **"Google Drive auth expired" / `GDRIVE_AUTH_EXPIRED`** — The saved Drive token no longer works. Health shows DEGRADED and Managers are notified. Fix: re-run `scripts\setup-gdrive-auth.ps1` (one browser consent). If this keeps happening every ~7 days, the Google Cloud consent screen is still in "Testing" — it must be published to **"In production"** (`docs/22-gdrive-backup.md` §10).
- **"Google Drive storage above 90%"** — The Drive account is nearly full. Free space in the Google account or upgrade its storage; retention will not delete manual/emergency sets on its own.

## Troubleshooting
- **A keeper cannot see the Back Up Now menu.** The capability hasn't been granted. The Admin opens the keeper's user form and adds **"WMS / Can Run Backup Now"**.
- **Health is DEGRADED with a Drive warning but backups look fine locally.** That is exactly the design: Drive issues degrade, the local tier still protects. Read the specific warning on Self-Diagnostics and fix it calmly.
- **A backup set "disappeared" from the catalog after someone reorganised the Drive folder.** Files moved or renamed in the Drive UI are invisible to the app (`drive.file` scope). Move them back exactly, or treat that set as lost and rely on the others — and don't reorganise the tree again.
- **The wizard sits on "Still working…" for a long time.** The backup runs out-of-process on the server; a very large filestore can take a while. Check **WMS → Reports → Backup & DR Audit** (Manager) for the run's rows before assuming failure.

## Best Practices
- **Let the schedule do the work.** The daily 4:30 PM backup uploads automatically; Back Up Now is for "right now" moments — before a planned power cut, a machine move, or after an unusually busy day.
- **Managers: glance at the Drive line in Self-Diagnostics weekly**, and run **Test Connection** monthly so token or quota problems surface before they matter.
- **Treat "Drive upload pending" as information, not alarm** — but if it appears day after day, investigate the connection.
- **Never weaken the separation**: keepers back up, only Managers restore. That asymmetry is intentional (a backup can be made freely; a restore can destroy).
- **Hands off the Inventory_Backups folder in Drive.** All tidying is automatic.

## Related Help-Center Articles
- `what-is-cloud-backup`
- `workflow-cloud-backup-now`
- `what-is-a-backup`
- `what-is-a-health-check`
- `admin-path-backups-and-restore-drill`
- `admin-path-observability-health`

## Narration Script
*(Target length ~3 minutes.)*

- **[0:00]** "In this video we'll look at the cloud backup — how the warehouse system keeps a second, encrypted copy of every backup in the trust's Google Drive, and how anyone with permission can send a fresh copy with one button."
- **[0:15]** "First, why. The daily backup protects against a software fault. But if the only copies live next to the computer, a fire or a theft takes both. The cloud copy lives out of the building."
- **[0:30]** "Here's the button. Open WMS, then Back Up Now. The note tells you it's completely safe — nothing is deleted or changed, and you can keep working. Click Back Up Now."
- **[0:50]** "It runs in the background for a few minutes. Click Refresh — and there's the result: the backup filename, the size in megabytes, and the time it reached Google Drive. That's the whole job."
- **[1:10]** "If it ever says 'Drive upload pending', don't worry — the safe copy was made on the server, the internet just wasn't reachable. It retries automatically on the next run."
- **[1:25]** "One rule for everyone: never tidy the Inventory_Backups folder on the Google Drive website. The system can only see files it created itself — move or rename them and they become invisible to it."
- **[1:40]** "Now the Manager side. Open WMS, Reports, Self-Diagnostics. The health row shows whether Drive is connected, how old the last upload is, how much storage is used, and when the next backup is due. A Drive problem only ever shows as DEGRADED, never CRITICAL — the local backup is the one that pages."
- **[2:10]** "And the settings: WMS, Configuration, Google Drive Backup. Here you set the backup time — half past four in the afternoon by default — the notifications, and the retention tiers: daily copies kept a month, weekly six months, monthly two years. Manual copies are never auto-deleted."
- **[2:35]** "Two buttons are worth a habit: Test Connection shows the connected account and quota, and Test Upload round-trips a tiny file to prove the whole path works. Run them monthly."
- **[2:50]** "Restoring from Drive is a separate, Manager-only, command-line job — see the restore guide. Keepers back up; Managers restore. Thank you."

## Recording Checklist
1. Log in as a keeper who has the **"WMS / Can Run Backup Now"** capability.
2. Open **WMS → Back Up Now**; show the plain-language note.
3. Click **Back Up Now**; show the "Backup started" message.
4. Click **Refresh** until the success screen appears; point out the filename, size in MB, and the Google Drive upload time.
5. Log in as a Manager; open **WMS → Reports → Self-Diagnostics**; point out the Drive line (connected, last upload age, storage, next backup).
6. Open **WMS → Configuration → Google Drive Backup**; show the backup time (16:30), notification switches, and retention tiers.
7. Click **Test Connection**; show the account and quota result. Click **Test Upload**; show the round-trip result.
8. Briefly show **WMS → Configuration → Google Drive Backups** (the read-only catalog grouped Year → Month → Day) and the warning that restore is command-line only — do not run anything.
9. End on the Back Up Now success screen.
