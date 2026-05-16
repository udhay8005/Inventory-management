# 17 — CI/CD pipeline

End-to-end automation that protects `main` from broken code. Every push and
pull-request triggers five jobs, and a single `ci_status` check gates the
merge button.

## Pipeline overview

```
git push  ─►  GitHub Actions  ─►  ┌─ lint          (≈ 1 min)
                                  ├─ security      (≈ 1 min, needs: lint)
                                  ├─ odoo_tests    (≈ 4 min, needs: lint)
                                  ├─ compose_smoke (≈ 2 min, needs: odoo_tests)
                                  └─ ci_status     (rolls everything up)
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

1. Spin up `postgres:16-alpine` as a service container.
2. Build the Odoo image from our `Dockerfile` (with Docker layer caching).
3. Create a fresh DB.
4. Install every WMS module with `-i wms_location,wms_fifo,...`
5. Run `--test-enable --stop-after-init`. Every `tests/test_*.py` in each
   module runs.
6. Fail the job if the Odoo log shows any test failure marker.

Matrix-ready — flip on Odoo 20 by adding `"20.0"` to the matrix list once
upstream ships it. Currently locked to `19.0`.

Artifacts: full `odoo_test.log` per matrix combination (kept 14 days).

## Job 4 — `compose_smoke`

Goes further: builds the full `docker-compose.yml` stack with `db` + `odoo`,
waits up to 90 s for `/web/database/manager` to return 200, then tears it
down. Catches issues that unit tests can't — missing env vars, port binds,
volume mount problems, `__manifest__.py` data ordering bugs.

## Job 5 — `ci_status`

A no-op job that depends on everyone else. Single check name to require in
branch protection — set it once in **Settings → Branches → main → Require
status checks → `CI status`** and you don't have to update the rule each
time you add a job.

## Release automation

[`release.yml`](../.github/workflows/release.yml) watches every push to
`main` that touches any `__manifest__.py`. When the highest version across
all addons changes, it:

1. Tags the commit `v19.0.X.Y.Z`.
2. Auto-generates a changelog from `git log` since the previous tag.
3. Publishes a GitHub Release.

No manual tagging step.

## Dependabot

[`.github/dependabot.yml`](../.github/dependabot.yml) keeps three ecosystems
patched without you remembering:

- `pip` — our `requirements.txt` and the `ai_worker` deps
- `docker` — the `postgres:16-alpine`, `odoo:19.0` base images
- `github-actions` — the workflow actions themselves

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
make up              # docker compose up -d
make logs            # tail odoo logs
make lint            # same checks CI runs
make test            # full test suite (slow)
make test-fast MOD=wms_location   # just one module
make format          # auto-fix formatting
make security        # bandit + pip-audit
make backup          # run scripts/backup.sh
make shell           # odoo shell against wms DB
make psql            # psql against wms DB
make ci              # lint + test (everything CI runs)
```

## What CI does NOT do (yet)

- **Coverage report**: not generated. Adding `coverage` to the test runner
  produces a `.coverage` file we could upload to Codecov — straightforward
  but optional.
- **Deploy step**: this repo has no auto-deploy. Production push is manual
  (`docker compose pull && docker compose up -d`). For a real deploy you'd
  add an `environments:` block + an `ssh` runner — kept off for now since
  the warehouse runs on a single host.
- **Performance benchmarks**: not measured per-PR. Easy to add a `pytest-bench`
  job once tests cover the slow paths.

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
| compose_smoke times out at 90 s | New module slow to load | Bump the `for i in {1..30}` loop or investigate slow startup |
| Security job flagged a CVE | Real or false positive | Read the report; update dep or add an ignore with a `# nosec: B###` comment |
| Release didn't fire | Manifest version didn't actually increase | Bump the highest version across all addons |
