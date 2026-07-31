# Common dev tasks for the native (no-Docker) WMS.
# Works on Linux / macOS / WSL / Git Bash on Windows.
#
# Windows-native users: prefer the PowerShell scripts in scripts\ —
#     scripts\install-native.ps1
#     scripts\start-native.ps1
#     scripts\stop-native.ps1
#     scripts\backup-native.ps1

PYTHON ?= python
VENV   ?= .venv
ODOO   ?= .odoo
CONF   ?= config/odoo.native.conf
DB     ?= wms

# Pick the right venv binary path depending on OS.
ifeq ($(OS),Windows_NT)
  PYBIN  = $(VENV)/Scripts/python
  PIPBIN = $(VENV)/Scripts/pip
else
  PYBIN  = $(VENV)/bin/python
  PIPBIN = $(VENV)/bin/pip
endif

.PHONY: help install start logs lint format test test-fast security ci shell psql backup clean nuke

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Native install (POSIX equivalent of install-native.ps1) ──────────────
install:  ## Clone Odoo, make venv, install deps. Postgres must already be installed.
	@test -d $(ODOO) || git clone --depth 1 -b 19.0 https://github.com/odoo/odoo.git $(ODOO)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PIPBIN) install --upgrade pip setuptools wheel
	$(PIPBIN) install -r $(ODOO)/requirements.txt
	$(PIPBIN) install -r requirements.txt
	@echo "Done. Start with: make start"

# ── Server control ───────────────────────────────────────────────────────
start:  ## Start Odoo against the local Postgres.
	$(PYBIN) $(ODOO)/odoo-bin -c $(CONF) -d $(DB)

logs:  ## Tail the Odoo log.
	tail -f .runtime/logs/odoo.log

# ── Quality gates ────────────────────────────────────────────────────────
lint:  ## Run all linters (black, isort, flake8, xml).
	$(PYBIN) -m black --check addons/ scripts/ ai_worker/
	$(PYBIN) -m isort --check-only addons/ scripts/ ai_worker/
	$(PYBIN) -m flake8 addons/

format:  ## Auto-format everything (black + isort).
	$(PYBIN) -m black addons/ scripts/ ai_worker/
	$(PYBIN) -m isort addons/ scripts/ ai_worker/

security:  ## bandit + pip-audit.
	$(PYBIN) -m bandit -r addons/ -ll
	$(PYBIN) -m pip_audit -r requirements.txt --strict

# Keep the module list and the tag list IDENTICAL to .github/workflows/ci.yml.
# They drifted before: this target installed 6 of the 10 addons and passed only
# `--test-tags wms`, so `make test` reported success while never running ~92
# tests that CI does run — the worst kind of green.
WMS_MODULES = wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports,wms_training,wms_perishable,wms_analytics,wms_pharmacy
WMS_TEST_TAGS = wms,wms_audit,wms_delete,wms_health,wms_ui_cert

test:  ## Full Odoo test suite (same modules + tags as CI). Slow.
	$(PYBIN) $(ODOO)/odoo-bin --stop-after-init -d wms_test \
	    -c $(CONF) \
	    -i $(WMS_MODULES) \
	    --without-demo=all --test-enable --test-tags $(WMS_TEST_TAGS) --log-level=test

test-fast:  ## Run tests for a single module: make test-fast MOD=wms_location
	@test -n "$(MOD)" || { echo "Usage: make test-fast MOD=wms_location"; exit 1; }
	$(PYBIN) $(ODOO)/odoo-bin --stop-after-init -d wms_test \
	    -c $(CONF) \
	    -u $(MOD) --test-tags $(MOD) --log-level=test

ci:  ## Run the same checks CI runs (lint + tests).
	$(MAKE) lint
	$(MAKE) test

# ── Convenience ──────────────────────────────────────────────────────────
shell:  ## Open an Odoo shell against the wms DB.
	$(PYBIN) $(ODOO)/odoo-bin shell -c $(CONF) -d $(DB) --no-http

psql:  ## Open psql against the wms DB.
	psql -U odoo -h localhost -d $(DB)

backup:  ## Run the backup (POSIX). Windows users: use scripts\backup-native.ps1
	@set -e; mkdir -p backups; \
	stamp=$$(date +%Y%m%d-%H%M%S); \
	pg_dump -U odoo -h localhost -d $(DB) -Fc -f backups/$(DB)-$$stamp.dump; \
	if [ -d .runtime/data/filestore/$(DB) ]; then \
	    tar czf backups/$(DB)-$$stamp-filestore.tar.gz -C .runtime/data/filestore $(DB); \
	fi; \
	echo "Backup written to backups/"

clean:  ## Remove the cloned Odoo source + venv (keeps DB + filestore).
	rm -rf $(VENV) $(ODOO)

nuke:  ## DESTRUCTIVE — also drop the database. You will lose all WMS data.
	@echo "About to DROP database $(DB). Press Ctrl+C now to cancel."
	@sleep 5
	dropdb -U odoo -h localhost --if-exists $(DB)
	rm -rf .runtime $(VENV) $(ODOO)
