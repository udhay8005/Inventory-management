#
# PSScriptAnalyzer settings for the WMS operator scripts (scripts\*.ps1).
#
# These are LOCAL, operator-run ops tools for a single-PC internal Odoo
# install -- not a published PowerShell module and not a network-facing
# service. A handful of default rules are systematically inapplicable to
# this class of script; each exclusion is justified below so the decision
# is reviewable (and revisitable if the threat model ever changes, e.g. if
# any of these scripts become an unattended service exposed to untrusted
# callers). Every OTHER default rule stays active -- this is a scalpel,
# not a blanket "disable analysis".
#
# VS Code's PowerShell extension auto-discovers this file by name at the
# workspace root (powershell.scriptAnalysis.settingsPath default).
#
@{
    ExcludeRules = @(
        # ---- PSAvoidUsingWriteHost -------------------------------------
        # These scripts are interactive console tools: they print colored,
        # human-facing status (Write-Host -ForegroundColor Green/Red/...).
        # Write-Host is the CORRECT cmdlet for that since PS 5.0 -- it
        # writes to the host's information stream, not the success stream.
        # Switching to Write-Output would pollute the pipeline / return
        # value; Write-Information renders nothing unless the operator
        # opts in via $InformationPreference, silencing the very output
        # these tools exist to show.
        'PSAvoidUsingWriteHost',

        # ---- PSAvoidUsingConvertToSecureStringWithPlainText ------------
        # backup-native.ps1 / restore-drill.ps1 deliberately hold the
        # backup passphrase as a [SecureString] in variable space and
        # convert to plaintext ONLY at the gpg --passphrase-fd boundary,
        # wiping the plaintext local the instant it's used. Wrapping a
        # config-sourced string into a SecureString REQUIRES
        # `-AsPlainText -Force` -- there is no other constructor. The rule
        # cannot tell this secure-wrapping entry point from a leak; here
        # the code is more careful than the rule assumes.
        'PSAvoidUsingConvertToSecureStringWithPlainText',

        # NOTE: PSAvoidUsingPlainTextForPassword is intentionally NOT excluded
        # here -- it is handled per-occurrence at each password parameter with
        # an inline [SuppressMessageAttribute] + Justification, and
        # restore-native.ps1 was converted to a [SecureString] passphrase.
        # Keeping the rule active means a NEW plaintext-password parameter in
        # a future script is still flagged at the source.

        # ---- PSUseShouldProcessForStateChangingFunctions ---------------
        # The only functions this rule flags here (Start-GpgPipe,
        # Start-GpgDecrypt, New-SecurePassword) are PRIVATE, in-file
        # helpers -- never exported, never invoked by an operator directly.
        # -WhatIf/-Confirm plumbing belongs on user-facing cmdlets, not
        # internal helpers. The user-facing entry points are already
        # guarded by explicit -Force / -DryRun switches.
        'PSUseShouldProcessForStateChangingFunctions'
    )
}
