# Common dev tasks. Run `make` for a list, or `make <target>`.
# Works on Linux / macOS / WSL / Git Bash on Windows.

.PHONY: help up down restart logs build pull lint test test-fast \
        format security sample-backup ci shell psql clean nuke

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Docker stack ──────────────────────────────────────────────────────────
up:  ## Start the full stack (db + odoo) in the background.
	docker compose up -d

down:  ## Stop containers (data persists).
	docker compose down

restart:  ## Restart Odoo (keeps DB up).
	docker compose restart odoo

logs:  ## Tail Odoo logs.
	docker compose logs -f odoo

build:  ## Rebuild the Odoo image.
	docker compose build

pull:  ## Pull latest base images.
	docker compose pull

# ── Quality gates ─────────────────────────────────────────────────────────
lint:  ## Run all linters (black, isort, flake8, xml).
	black --check addons/ scripts/ ai_worker/
	isort --check-only addons/ scripts/ ai_worker/
	flake8 addons/

format:  ## Auto-format everything (black + isort).
	black addons/ scripts/ ai_worker/
	isort addons/ scripts/ ai_worker/

security:  ## bandit + pip-audit.
	bandit -r addons/ -ll
	pip-audit -r requirements.txt

# ── Tests ─────────────────────────────────────────────────────────────────
test:  ## Run WMS tests (only @tagged('wms') — fast & deterministic).
	docker compose run --rm --no-deps odoo \
	    odoo --stop-after-init \
	         -d wms_test \
	         --db_host=db --db_user=odoo --db_password=odoo_local_dev_pw \
	         --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
	         -i wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports \
	         --without-demo=all \
	         --test-enable --test-tags wms \
	         --log-level=test \
	         --logfile=/dev/stdout

test-fast:  ## Run tests for a single module: make test-fast MOD=wms_location
	@test -n "$(MOD)" || { echo "Usage: make test-fast MOD=wms_location"; exit 1; }
	docker compose run --rm --no-deps odoo \
	    odoo --stop-after-init -d wms_test \
	         --db_host=db --db_user=odoo --db_password=odoo_local_dev_pw \
	         --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
	         -u $(MOD) --test-tags $(MOD) --log-level=test --logfile=/dev/stdout

# ── Backup / restore ──────────────────────────────────────────────────────
sample-backup:  ## Run the production backup script (writes to ./backups/).
	./scripts/backup.sh

# ── Convenience ───────────────────────────────────────────────────────────
shell:  ## Open an Odoo shell against the wms DB.
	docker compose exec odoo \
	    odoo shell -d wms --db_host=db --db_user=odoo --db_password=odoo_local_dev_pw \
	    --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons --no-http

psql:  ## Open psql against the wms DB.
	docker compose exec db psql -U odoo -d wms

ci:  ## Run the same checks CI runs (lint + tests).
	$(MAKE) lint
	$(MAKE) test

clean:  ## Remove containers but keep volumes (data safe).
	docker compose down

nuke:  ## DESTRUCTIVE — also delete volumes. You will lose all data.
	@echo "About to delete volumes. Press Ctrl+C now to cancel."
	@sleep 5
	docker compose down -v
