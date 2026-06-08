# Security Policy

This repository hosts the WMS used by the Dakshin Vrindavan cow-care trust for
their internal warehouse. It is published in the open so a successor admin can
re-install it, but it is **operationally a single-tenant install** — there is
no SaaS, no multi-tenant deployment, no public bug-bounty programme.

## Reporting a vulnerability

If you discover a security issue that could affect this codebase, please email
**office.dakshinvrindavan@gmail.com** with:

- a brief description of the issue
- the smallest reproduction you can construct
- whether the fix appears to touch backup, restore, ACLs, or the audit trail

Please **do not** open a public GitHub issue for security defects. The trust
will acknowledge within seven days and ship a fix (or a documented mitigation)
on the same release cadence as functional work — see `CHANGELOG.md` and the
`v19.0.<release>` tags.

## Scope

In scope:

- The seven custom addons (`addons/wms_*`)
- The deployment scripts (`scripts/*.ps1`)
- The `/wms/*` controllers and JSON endpoints
- The backup + restore + off-site copy pipeline

Out of scope:

- Defects in upstream Odoo 19 CE (report those at <https://github.com/odoo/odoo>)
- Defects in PostgreSQL, Windows, or the host OS
- Issues that require physical access to the prod machine
- Speculation about the trust's specific deployment topology

## Supported versions

Only the latest `v19.0.<release>` tag is supported. Older tags are kept for
historical reference but do not receive security backports — upgrade.
