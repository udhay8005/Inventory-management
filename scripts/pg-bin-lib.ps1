<#
.SYNOPSIS
    Locate the PostgreSQL client tools (psql.exe + pg_restore.exe) on this host
    and put them on PATH — without hard-coding a version or install directory.

.DESCRIPTION
    Restore operations (restore-native.ps1, restore-drill.ps1) shell out to
    `psql` and `pg_restore` by bare name. On the developer box these happen to
    be on PATH, but on a freshly-provisioned recovery host they often are NOT —
    PostgreSQL's installer does not add its `bin\` to the machine PATH. A DR
    restore that fails with "psql is not recognized" at 2 a.m. is exactly the
    failure this library exists to prevent.

    Resolution order (first hit wins), mirroring the auto-detection already used
    by start-native.ps1 and documented in docs/INSTALLATION-GUIDE.md §3:

      1. PATH               — if both tools already resolve, use them as-is.
      2. Windows service    — the running `postgresql-x64-*` service's ImagePath
                              points at <install>\bin\pg_ctl.exe; derive bin\.
      3. Registry           — HKLM\SOFTWARE\PostgreSQL\Installations\* carries a
                              'Base Directory' for every installed copy.
      4. Standard install   — C:\Program Files\PostgreSQL\<ver>\bin, newest
                              version first.

    This supports the PostgreSQL 15 / 16 / 17 the installer pins (winget ships 17
    by default) and any other version present, because nothing here is hard-coded
    to a single number.

.NOTES
    Dot-source this file, then call Use-PgBin (which throws a clear error if the
    tools cannot be found) or Resolve-PgBin (which returns $null instead).
    Pure helper — no side effects beyond, in Use-PgBin, prepending the resolved
    bin directory to this process's $env:Path.
#>

function Resolve-PgBin {
    <#
    .SYNOPSIS
        Return the directory containing psql.exe AND pg_restore.exe, or $null.
    .DESCRIPTION
        Searches PATH, the postgresql-x64 service, the PostgreSQL registry keys,
        and the standard install roots (newest version first). Does NOT modify
        PATH — callers that want the tools on PATH should use Use-PgBin.
    #>
    [CmdletBinding()]
    param()

    # 1. Already on PATH? Trust it and return its directory.
    $psqlCmd = Get-Command psql.exe -ErrorAction SilentlyContinue
    $prCmd   = Get-Command pg_restore.exe -ErrorAction SilentlyContinue
    if ($psqlCmd -and $prCmd) {
        return (Split-Path -Parent $psqlCmd.Source)
    }

    $candidates = New-Object System.Collections.Generic.List[string]

    # 2. The running PostgreSQL Windows service knows where it lives. Its
    #    PathName is like: "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" runservice ...
    try {
        $svc = Get-CimInstance Win32_Service -Filter "Name LIKE 'postgresql-x64-%'" -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($svc -and $svc.PathName) {
            $exe = if ($svc.PathName -match '^\s*"([^"]+)"') { $Matches[1] }
                   else { ($svc.PathName -split '\s+')[0] }
            if ($exe) { $candidates.Add((Split-Path -Parent $exe)) }
        }
    } catch {
        # CIM unavailable / access denied — fall through to the other probes.
    }

    # 3. Registry: every installed copy records its Base Directory.
    try {
        Get-ItemProperty 'HKLM:\SOFTWARE\PostgreSQL\Installations\*' -ErrorAction SilentlyContinue |
            Sort-Object PSChildName -Descending |
            ForEach-Object {
                $base = $_.'Base Directory'
                if ($base) { $candidates.Add((Join-Path $base 'bin')) }
            }
    } catch {
        # No registry keys (e.g. a portable/zip install) — keep going.
    }

    # 4. Standard install roots, newest major version first.
    foreach ($root in @("$env:ProgramFiles\PostgreSQL", "${env:ProgramFiles(x86)}\PostgreSQL")) {
        if (Test-Path $root) {
            Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                Sort-Object { try { [int]$_.Name } catch { 0 } } -Descending |
                ForEach-Object { $candidates.Add((Join-Path $_.FullName 'bin')) }
        }
    }

    # First candidate that actually carries BOTH tools wins.
    foreach ($bin in ($candidates | Select-Object -Unique)) {
        if ((Test-Path (Join-Path $bin 'psql.exe')) -and
            (Test-Path (Join-Path $bin 'pg_restore.exe'))) {
            return $bin
        }
    }
    return $null
}

function Use-PgBin {
    <#
    .SYNOPSIS
        Ensure psql.exe + pg_restore.exe are callable, then return their bin dir.
    .DESCRIPTION
        Resolves the PostgreSQL bin directory via Resolve-PgBin and prepends it
        to this process's PATH (idempotent). Throws a clear, human-readable error
        — naming everywhere it looked — if the tools cannot be found, so the
        caller surfaces an actionable message instead of a cryptic
        "term not recognized" deep inside a restore.
    #>
    [CmdletBinding()]
    param()

    $bin = Resolve-PgBin
    if (-not $bin) {
        throw (
            "PostgreSQL client tools (psql.exe + pg_restore.exe) were not found. " +
            "Searched: the current PATH, the 'postgresql-x64' Windows service, the " +
            "HKLM\SOFTWARE\PostgreSQL\Installations registry keys, and " +
            "'$env:ProgramFiles\PostgreSQL\<version>\bin'. " +
            "Install PostgreSQL (15, 16, or 17) or add its 'bin' folder to PATH, then re-run."
        )
    }
    if ($env:Path -notlike "*$bin*") {
        $env:Path = "$bin;$env:Path"
    }
    return $bin
}
