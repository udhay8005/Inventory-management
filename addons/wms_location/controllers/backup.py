"""Web UI for the encrypted database backup.

Wraps `pg_dump | gpg --symmetric` as a controller route the Admin
can fire from a menu button. The encrypted bytes stream straight to
the admin's browser as a `.dump.gpg` download. Same wire format as
`scripts/backup-native.ps1` produces, so either path can feed
`scripts/restore-native.ps1`.

Restore is DELIBERATELY NOT exposed via the web. A bad upload could
wipe the live database in one click. The CLI script requires
`-Force` plus the passphrase, gives the Admin a chance to think.
The web menu just shows the recovery instructions instead.

Auth model:
  - Only `group_wms_manager` (Admin) can hit /wms/admin/backup/*.
  - The route reads the postgres password + BACKUP_PASSPHRASE from
    the running odoo.native.conf / .env so secrets stay off the
    HTTP wire.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime

from markupsafe import escape
from odoo import http
from odoo.http import content_disposition, request

_logger = logging.getLogger(__name__)


# Locations we expect on the trust's Windows install. The first one
# that exists wins; missing entries are silently skipped.
_PG_DUMP_CANDIDATES = [
    r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
    "pg_dump",  # fall back to PATH lookup
]
_GPG_CANDIDATES = [
    r"C:\Program Files\GnuPG\bin\gpg.exe",
    r"C:\Program Files (x86)\GnuPG\bin\gpg.exe",
    "gpg",  # PATH fallback
]


def _which(candidates):
    """First candidate that resolves to an executable, else None."""
    for cand in candidates:
        if os.path.isabs(cand):
            if os.path.isfile(cand):
                return cand
        else:
            for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                full = os.path.join(path_dir, cand)
                if os.path.isfile(full):
                    return full
                if os.path.isfile(full + ".exe"):
                    return full + ".exe"
    return None


def _read_env_value(env_path, key):
    """Tiny .env reader. Returns the raw value or None."""
    if not os.path.isfile(env_path):
        return None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line)
            if m:
                return m.group(1).strip()
    return None


class WmsBackupController(http.Controller):

    @http.route(
        "/wms/admin/backup/download",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def backup_download(self, **kw):
        """Stream an encrypted pg_dump of the current database."""
        user = request.env.user
        manager = request.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
        if not manager or manager not in user.group_ids:
            return request.not_found()

        pg_dump = _which(_PG_DUMP_CANDIDATES)
        gpg = _which(_GPG_CANDIDATES)
        if not pg_dump:
            return self._error_page(
                "pg_dump not found",
                "pg_dump.exe is not on PATH and not at the standard "
                "PostgreSQL\\17\\bin location. Install PostgreSQL "
                "client tools or run the CLI backup script "
                "(scripts\\backup-native.ps1) instead.",
            )
        if not gpg:
            return self._error_page(
                "GPG not found",
                "gpg.exe is not on PATH and not at the standard "
                "GnuPG\\bin location. Install GnuPG via "
                "<code>winget install GnuPG.GnuPG</code> and try again.",
            )

        from odoo.tools import config

        db_name = request.env.cr.dbname
        db_host = config.get("db_host") or "localhost"
        db_port = str(config.get("db_port") or 5432)
        db_user = config.get("db_user") or "odoo"
        db_password = config.get("db_password") or ""

        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                os.pardir,
                os.pardir,
                os.pardir,
            )
        )
        passphrase = _read_env_value(os.path.join(project_root, ".env"), "BACKUP_PASSPHRASE")
        if not passphrase or passphrase == "changeme_backup_passphrase":
            return self._error_page(
                "BACKUP_PASSPHRASE not set",
                "Open <code>.env</code> in the project root and set "
                "<code>BACKUP_PASSPHRASE</code> to a strong value "
                "(24+ characters, no whitespace). Without it the "
                "encrypted backup cannot be restored later.",
            )

        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as dump_file:
            dump_path = dump_file.name
        try:
            dump_cmd = [
                pg_dump,
                "-U",
                db_user,
                "-h",
                db_host,
                "-p",
                db_port,
                "-d",
                db_name,
                "-Fc",
                "-f",
                dump_path,
            ]
            _logger.info("WMS backup: invoking pg_dump for db=%s", db_name)
            result = subprocess.run(
                dump_cmd,
                env=env,
                capture_output=True,
                timeout=600,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", "replace")[:500]
                return self._error_page(
                    "pg_dump failed",
                    f"<pre>{escape(stderr)}</pre>",
                )

            with tempfile.NamedTemporaryFile(suffix=".dump.gpg", delete=False) as enc_file:
                enc_path = enc_file.name
            try:
                gpg_cmd = [
                    gpg,
                    "--batch",
                    "--yes",
                    "--passphrase-fd",
                    "0",
                    "--symmetric",
                    "--cipher-algo",
                    "AES256",
                    "-o",
                    enc_path,
                    dump_path,
                ]
                _logger.info("WMS backup: encrypting dump")
                gpg_result = subprocess.run(
                    gpg_cmd,
                    input=passphrase.encode("utf-8"),
                    capture_output=True,
                    timeout=300,
                )
                if gpg_result.returncode != 0:
                    stderr = gpg_result.stderr.decode("utf-8", "replace")[:500]
                    return self._error_page(
                        "GPG encryption failed",
                        f"<pre>{escape(stderr)}</pre>",
                    )

                with open(enc_path, "rb") as f:
                    payload = f.read()
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = f"{db_name}-{stamp}.dump.gpg"
                _logger.info(
                    "WMS backup: serving %s (%d bytes) to user %s",
                    filename,
                    len(payload),
                    user.login,
                )
                return request.make_response(
                    payload,
                    headers=[
                        ("Content-Type", "application/octet-stream"),
                        ("Content-Length", str(len(payload))),
                        ("Content-Disposition", content_disposition(filename)),
                    ],
                )
            finally:
                try:
                    os.unlink(enc_path)
                except OSError:
                    pass
        finally:
            try:
                os.unlink(dump_path)
            except OSError:
                pass

    @http.route(
        "/wms/admin/restore/info",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def restore_info(self, **kw):
        """Restore-instructions page.

        Restoring from an encrypted backup is a destructive operation:
        the target database is dropped and re-created from the dump.
        We refuse to do it from the web - a misclick or a stale
        browser tab could wipe live data. Instead we show the CLI
        command and the backup folder path.
        """
        user = request.env.user
        manager = request.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
        if not manager or manager not in user.group_ids:
            return request.not_found()
        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                os.pardir,
                os.pardir,
                os.pardir,
            )
        )
        backups_dir = os.path.join(project_root, "backups").replace("/", "\\")
        body = f"""
<!DOCTYPE html><html><head><title>WMS Restore</title>
<style>body{{font-family:Arial;max-width:760px;margin:60px auto;padding:32px;
border:1px solid #ddd;border-radius:8px}}
code{{background:#f5f5f5;padding:2px 6px;border-radius:3px}}
pre{{background:#1e1e1e;color:#dcdcdc;padding:16px;border-radius:6px;
overflow-x:auto;font-size:13px}}</style></head><body>
<h2>Restore from an encrypted backup</h2>
<p>Restore is intentionally a CLI-only operation. A misclick from the
web could overwrite every product, picking, damage, and audit in the
live database. The PowerShell script gives you a confirmation prompt
and a chance to read what is about to happen.</p>

<h3>Steps</h3>
<ol>
<li>Open PowerShell on the WMS server.</li>
<li>Navigate to the project: <code>cd D:\\Udhay\\projects\\Inventory_mngt</code></li>
<li>List backups: <code>dir backups\\*.dump.gpg</code></li>
<li>Run the restore (replaces the live database):
<pre>scripts\\restore-native.ps1 -BackupFile .\\backups\\&lt;file&gt;.dump.gpg -Force</pre>
</li>
</ol>

<h3>Backup folder</h3>
<p><code>{backups_dir}</code></p>

<p>The script reads <code>BACKUP_PASSPHRASE</code> from <code>.env</code>,
decrypts the GPG file in memory, drops the target database, and
restores from <code>pg_restore</code>.</p>

<p><a href="/odoo">Back to WMS</a></p>
</body></html>
"""
        return request.make_response(body, headers=[("Content-Type", "text/html; charset=utf-8")])

    def _error_page(self, title, body_html):
        html = (
            "<!DOCTYPE html><html><head><title>WMS backup error</title>"
            "<style>body{font-family:Arial;max-width:600px;margin:60px auto;"
            "padding:24px;border:1px solid #ddd;border-radius:6px}"
            "h2{color:#c33}</style></head><body>"
            f"<h2>{title}</h2><div>{body_html}</div>"
            "<p><a href='/odoo'>Back to WMS</a></p>"
            "</body></html>"
        )
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])
