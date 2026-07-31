# Support

## What this project is

This is the **Dakshin Vrindavan Gaushala WMS** — an internal warehouse
management system for a single-tenant cow-care trust. It is published on
GitHub so that a successor admin can re-install or extend it, not as a
general-purpose product with a public support channel.

## Getting help

### 1. Read the documentation first

The `docs/` directory contains the full operational and technical
documentation:

| Starting point | What it covers |
|---|---|
| [INSTALLATION-GUIDE.md](docs/INSTALLATION-GUIDE.md) | Full from-scratch deploy |
| [ADMIN-QUICK-START.md](docs/ADMIN-QUICK-START.md) | 15-minute admin path |
| [STOREKEEPER-QUICK-START.md](docs/STOREKEEPER-QUICK-START.md) | Operator daily use |
| [07-deployment.md](docs/07-deployment.md) | Production deploy + restore |
| [08-security.md](docs/08-security.md) | Roles, ACLs, record rules |
| [17-ci-cd.md](docs/17-ci-cd.md) | GitHub Actions pipeline |
| [18-restore-drill.md](docs/18-restore-drill.md) | Backup & restore runbook |
| [docs/v20-perishable-engine/](docs/v20-perishable-engine/) | v20 perishable engine design & pilot guide |

### 2. Check the CHANGELOG

[CHANGELOG.md](CHANGELOG.md) documents every release including what changed,
what to upgrade (`-u`), and known limitations.

### 3. Open a GitHub Issue

If the docs don't cover it:

- **Bug** → use the [Bug report](.github/ISSUE_TEMPLATE/bug_report.yml) template
- **Feature / improvement** → use the [Feature request](.github/ISSUE_TEMPLATE/feature_request.yml) template

Please include the Odoo version, PostgreSQL version, OS/browser, and the
relevant addon name.

### 4. Security issues

Do **not** open a public issue for security defects. Email
**office.dakshinvrindavan@gmail.com** instead — see [SECURITY.md](SECURITY.md).

## Out of scope

This project does not offer:

- Paid support plans
- SLAs or guaranteed response times
- Multi-tenant or SaaS hosting
- Integration with third-party ERP systems beyond what the addons already implement

## Contributing a fix yourself

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch workflow, lint/test
requirements, and PR checklist.
