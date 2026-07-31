# 17 — CI/CD pipeline

End-to-end automation that protects `main` from broken code. Every push and
pull-request triggers five jobs, and a single `ci_status` check gates the
merge button.

The pipeline runs **native** — Ubuntu runner with a postgres:16 service
container, Python 3.12, and a clone of Odoo 19.0 source. Mirrors the local
Windows setup exactly (just on Linux instead of Windows for speed + cost).

> **Note on the PG pin:** CI runs on PostgreSQL 16 only as a single-version
> smoke. Runtime supports PostgreSQL 15/16/17 (auto-detected; winget installs
> 17 by default). A matrix-test across all three versions is tracked as
> future work; current CI remains a single-version gate to keep run time
> short.

## Pipeline overview

```
git push  ─►  GitHub Actions  ─►  ┌─ lint           (≈ 1 min)
                                  ├─ security       (≈ 1 min, needs: lint)
                                  ├─ odoo_tests     (≈ 5 min, needs: lint)
                                  ├─ native_smoke   (≈ 3 min, needs: odoo_tests)
                                  └─ ci_status      (rolls everything up)
                                                    │
                                  branch protection: ci_status must be green
                                                    │
                                                    ▼
                                               ► merge to main
                                                    │
                                                    ▼
                                         release.yml cuts a tag
                                          (if any manifest version bumped)
```

Concurrency: a new push to the same ref **cancels the in-flight run**, so
fast iteration doesn't burn CI minutes.

## Job 1 — `lint`

| Tool | What it catches |
|---|---|
| `black` | Inconsistent Python formatting |
| `isort` | Wrong import order |
| `flake8` | Unused imports, undefined names, obvious bugs |
| `pylint-odoo` | Missing manifest keys, SQL injection, deprecated Odoo APIs |
| Python XML parse | Malformed view / data XML |

Config lives in [`pyproject.toml`](../pyproject.toml), [`.flake8`](../.flake8),
and [`.pylintrc-odoo`](../.pylintrc-odoo).

## Job 2 — `security`

| Tool | What it catches |
|---|---|
| `bandit` | Code-level CVEs in our Python (eval/exec, weak crypto, unsafe yaml) |
| `pip-audit` | Known CVEs in declared dependencies |

Reports uploaded as artifact `security-reports` (retained 30 days).

## Job 3 — `odoo_tests`

The real test:

1. Spin up `postgres:16` as a **service container** (background, port-mapped to localhost:5432) — same role as the Windows `postgresql-x64-16` service does for local dev.
2. Install system packages: `postgresql-client`, `wkhtmltopdf`, `libldap2-dev`, `libsasl2-dev`, fonts.
3. Grant `CREATEDB` to the `odoo` Postgres role.
4. Clone Odoo 19.0 source.
5. Create a Python venv + `pip install -r odoo/requirements.txt -r requirements.txt`.
6. `createdb wms_ci`.
7. Run `odoo-bin -i wms_location,... --test-enable --stop-after-init --without-demo=all --test-tags wms`.
8. Fail the job if the Odoo log shows any test failure marker, OR if zero tests ran (catches missing `@tagged('wms')` decorators).

Artifact: full `odoo_test.log` (kept 14 days).

## Job 4 — `native_smoke`

The end-to-end "does it actually start" check. Same install as job 3, but
instead of running tests:

1. Run `odoo-bin -d wms_smoke -i wms_location --http-port=8069 &` in the background.
2. Curl `http://localhost:8069/web/login` every 3 s for 2 min.
3. Pass if HTTP 200 or 303 (login page or redirect); fail otherwise.
4. Kill the Odoo process at the end.

Catches issues unit tests can't — broken module dependencies, view-file parse
errors at load time, missing data records, port binding problems.

## Job 5 — `ci_status`

A no-op aggregator that depends on every other job. Single check name to
require in branch protection — set it once in **Settings → Branches → main
→ Require status checks → `CI status`** and you don't have to update the
rule each time you add a job.

## Release automation

[`release.yml`](../.github/workflows/release.yml) watches every push to
`main` that touches any `__manifest__.py`. When the highest version across
all addons changes, it:

1. Tags the commit `v19.0.X.Y.Z`.
2. Auto-generates a changelog from `git log` since the previous tag.
3. Publishes a GitHub Release.

No manual tagging step.

## Dependabot

[`.github/dependabot.yml`](../.github/dependabot.yml) keeps two ecosystems
patched without you remembering:

- `pip` — our `requirements.txt` and the `ai_worker` deps
- `github-actions` — the workflow actions themselves

(Docker was previously listed; removed when the project moved to native
install. The Odoo source clone is pinned to branch `19.0` and tracks upstream
automatically.)

Opens a PR each Monday morning if anything is behind. The CI pipeline you
just read runs against the PR — if green, you merge with one click.

## Pre-commit (local mirror)

Same checks before `git push`, so 99% of failures get caught on your laptop
in seconds rather than waiting 8 minutes on CI:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files   # one-time scrub
```

Config: [`.pre-commit-config.yaml`](../.pre-commit-config.yaml).

## Makefile shortcuts

```bash
make help            # list available targets
make install         # clone Odoo + venv + pip install (one-shot setup)
make start           # run odoo against local Postgres
make logs            # tail .runtime/logs/odoo.log
make lint            # same checks CI runs
make test            # full test suite (slow)
make test-fast MOD=wms_location   # just one module
make format          # auto-fix formatting
make security        # bandit + pip-audit
make backup          # pg_dump + filestore tar
make shell           # odoo shell against wms DB
make psql            # psql against wms DB
make ci              # lint + test (everything CI runs)
```

Windows-native equivalents (PowerShell):

```powershell
scripts\install-native.ps1
scripts\start-native.ps1
scripts\stop-native.ps1
scripts\backup-native.ps1
```

## What CI does NOT do (yet)

- **Coverage report**: not generated. Adding `coverage` to the test runner produces a `.coverage` file we could upload to Codecov — straightforward but optional.
- **Deploy step**: this repo has no auto-deploy. Production push is manual (`git pull && scripts\start-native.ps1 -Upgrade all`). For a real deploy you'd add an `environments:` block + an `ssh`/WinRM runner — kept off for now since the warehouse runs on a single host.
- **Performance benchmarks**: not measured per-PR. Easy to add a `pytest-bench` job once tests cover the slow paths.

## Recommended branch protection rules

In **Settings → Branches → main**:

- [x] Require a pull request before merging
- [x] Require **at least 1 approval**
- [x] Require status checks to pass:
  - `CI status`  ← single dependent job that aggregates the others
- [x] Require branches to be up-to-date before merging
- [x] Require linear history (no merge commits)
- [x] Do not allow bypassing the above (even for admins)

That's it. The pipeline is the safety net; the rules make sure nobody can
duck under it.

## Troubleshooting CI

| Symptom | Likely cause | Fix |
|---|---|---|
| Lint fails on formatting only | You forgot to run `make format` | `make format && git commit --amend --no-edit` |
| Odoo tests pass locally, fail in CI | Demo data difference (CI uses `--without-demo=all`) | Make tests independent of demo data |
| native_smoke times out at 120 s | New module slow to load OR view parse error | Check the step log — Odoo prints the failing view name on load |
| psycopg2 install fails in CI | Wheel mismatch | The CI uses `psycopg2` (Linux wheels work fine); Windows local install rewrites it to `psycopg2-binary` |
| Security job flagged a CVE | Real or false positive | Read the report; update dep or add an ignore with a `# nosec: B###` comment |
| Release didn't fire | Manifest version didn't actually increase | Bump the highest version across all addons |

## Migrated from the old Docker CI (historical)

We migrated from Docker-based CI to native PowerShell/Linux CI in v19.0.5;
this section is kept for historical reference. If you have an older clone
with the Docker-based `ci.yml`:

```bash
git fetch origin
git checkout main
git pull
# .github/workflows/ci.yml is now the native version.
# The old docker-compose.yml, Dockerfile, and scripts/init-db.sh have been removed.
# Re-run scripts/install-native.ps1 (or `make install`) to set up the local environment.
```
