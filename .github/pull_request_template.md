## What changed

<!-- One-paragraph summary. What and why, not how. -->

## Type
- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup (no behaviour change)
- [ ] Performance
- [ ] Documentation
- [ ] CI / tooling

## Modules touched
- [ ] wms_location
- [ ] wms_fifo
- [ ] wms_barcode
- [ ] wms_repair_damage
- [ ] wms_ai_forecast
- [ ] wms_reports
- [ ] docs / scripts / docker

## How was it tested?
<!-- e.g. "make test", "manual scan receipt round-trip on a fresh DB", "added unit
test that fails before the fix and passes after." -->

## Risk / rollback
<!-- What could this break in production? How do we roll back? -->

## Screenshots (UI changes only)
<!-- Drag-drop a before/after if the visible UI changed. -->

## Checklist
- [ ] `make lint` passes locally
- [ ] `make test` passes locally
- [ ] Touched models have a test in `tests/`
- [ ] Manifest `version` bumped (patch/minor/major)
- [ ] Docs updated if behaviour changed
- [ ] No secrets in code or config
