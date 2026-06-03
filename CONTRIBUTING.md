# Contributing — the `test → main` workflow

We use **two long-lived branches**:

| Branch | Purpose | CI runs? | Direct push allowed? |
|---|---|---|---|
| **`main`** | Production-ready code. Always green CI. | Yes | No — PRs only |
| **`test`** | Integration / staging. Latest accepted work. | Yes | Yes |

Every change goes through this loop:

```
local work  ──►  git push origin test           ◄── CI runs full pipeline
                                                       │
                                                       ▼
                                  ┌─ green ─►  PR: test → main
                                  │                    │
                                  │                    ▼
                                  │            CI re-runs against
                                  │            the merge commit
                                  │                    │
                                  │                    ▼
                                  │            1 approval, merge button
                                  │                    │
                                  └─ red  ─►  fix locally, push again
                                                       ▼
                                                  main (deployable)
```

No commits land on `main` without passing through `test` first.

## 1 — Day-to-day developer flow

```bash
# Sync with the team's latest test branch
git checkout test
git pull origin test

# Make your change
$EDITOR addons/wms_xxx/models/...

# Run the same checks CI will run, before you push
make lint      # black + isort + flake8 + xml
make test      # WMS Odoo tests
# Or, in one shot:
make ci

# Commit + push
git add .
git commit -m "wms_xxx: add foo because bar"
git push origin test
```

Wait for the CI badge on GitHub to turn green (≈ 6–8 minutes).

## 2 — Promoting `test` to `main`

Once CI is green on `test` and you've manually verified the change in a
local native install (via `scripts\start-native.ps1`), open the PR:

```bash
gh pr create --base main --head test \
    --title "Release: <one-line summary>" \
    --body "What's in this batch. Why. Risk. Rollback."
```

Or via the GitHub UI: **Pull requests → New PR → base: main, compare: test**.

The PR will re-run the entire CI pipeline. Once green + 1 reviewer
approval, merge with **"Create a merge commit"** (preserves the
linearity of `test`).

## 3 — Hotfix (production-down) flow

Reserved for "the warehouse can't scan barcodes" kind of emergency:

```bash
# Branch off main, not test
git checkout main
git pull origin main
git checkout -b hotfix/<short-name>

# Make the fix, commit, push
git push origin hotfix/<short-name>

# PR directly to main, marked URGENT
gh pr create --base main --head hotfix/<short-name> \
    --title "URGENT: <what's broken>" \
    --label "hotfix"

# After merge, immediately back-merge to test
git checkout test
git pull origin test
git merge main
git push origin test
```

CI still runs — never bypass it, even for hotfixes.

## 4 — Local CI parity

The `make ci` target runs exactly what GitHub Actions runs. Pre-commit
hooks catch most issues at `git commit` time:

```bash
pip install pre-commit && pre-commit install
```

After that, `git commit` will refuse a commit that black/isort/flake8
would reject. ~99% of CI failures become impossible to push.

## 5 — Test discipline

Every new model method or wizard action should ship with a test under
`addons/<module>/tests/`. Use `@tagged("wms", ...)` so the test runs
under `--test-tags wms`. Without that tag, CI won't see it.

Example:

```python
from odoo.tests.common import TransactionCase, tagged

@tagged("post_install", "-at_install", "wms")
class TestMyThing(TransactionCase):
    def test_my_thing(self):
        ...
```

## 6 — Commit message style

```
<module>: <imperative summary, ≤ 60 chars>

Why this change matters (1–3 sentences). Reference issue numbers
like #42 or external context, not "fixed bug" / "updated code".
```

Examples:

| Good | Bad |
|---|---|
| `wms_barcode: require photo when scanning litres/kg` | `update scan_issue.py` |
| `wms_reports: include floor zones in cycle-count due` | `bugfix` |
| `ci: scope test-tags to wms only` | `wip` |

## 7 — Branch protection rules (admin one-time setup)

In **Settings → Branches → Add rule for `main`**:

- ☑ Require a PR before merging
- ☑ Require **at least 1 approval**
- ☑ Require status check `CI status` to pass (this is the rolled-up
  check from `ci.yml`)
- ☑ Require branches up-to-date before merging
- ☑ Block force push
- ☑ Block deletion

For `test`: same minus the approval (so the dev who owns the work can
push directly).

## 8 — When CI fails

| Job | What to look at |
|---|---|
| **lint** | Run `make format` locally, commit, push again |
| **security** | Read the bandit / pip-audit report in artifacts |
| **odoo_tests** | Download `odoo-test-log` artifact, grep for `ERROR.*wms_` |
| **native_smoke** | Step summary shows the Odoo startup log — look for missing env vars, port conflicts, or view-parse errors |
| **ci_status** | This is a roll-up — fix the underlying failed job |

Every artifact is kept for 14–30 days. If a flake8 line number is
ambiguous, click "Re-run failed jobs" — it sometimes catches a transient
network blip.

## 9 — Releases

When `main` accepts a PR that bumps any addon manifest's `version` key,
the `release.yml` workflow auto-tags `v19.0.X.Y.Z` and publishes a
GitHub Release with a generated changelog. No manual tagging.

Semver intent for our manifests (`19.0.X.Y.Z` after the Odoo version
prefix):

- **X**: breaking model changes (you need a data migration)
- **Y**: new feature
- **Z**: bug fix / cleanup

Bump only one. Don't squash multiple bumps into a single commit.
