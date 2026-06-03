# Training Flow Diagrams

Clean, beginner-friendly SVG flow diagrams for the Warehouse Training Academy
(Odoo 19 WMS for a cow-care trust that buys and uses stock — never sells).

All diagrams share one style: rounded boxes (height 64), a single downward arrow
between steps, and a fixed colour key.

## Colour key

| Class | Meaning | Fill / Stroke |
| --- | --- | --- |
| start | where a flow begins | green |
| process | a normal step | blue |
| decision | the system chooses / a question | yellow |
| guard / warn | a lock, refusal, or warning | red |
| end | the flow is complete | teal |

## Files

| File | Description |
| --- | --- |
| `receiving.svg` | Receiving a delivery: arrive → scan receipt → quality check + audit → putaway → stock on hand. |
| `warehouse-structure.svg` | How a location is built up: Zone → Rack → Compartment → Slot (the full address). |
| `putaway.svg` | Moving received stock into a slot by scanning the slot barcode. |
| `fifo-issue.svg` | Issuing stock for trust use with FIFO/FEFO picking, photo, and audit trail. |
| `returns.svg` | Returning an item to its slot, with fluids and consumables refused at Validate. |
| `damage-repair.svg` | Filing damage, choosing repair vs urgent buy, running the repair order, scrap if beyond repair. |
| `cycle-count-audit.svg` | Cycle-count audit: count a slot, enter quantities, submit (locks), manager accepts or rejects. |
| `backup-restore-health.svg` | Nightly backup, restore drill, and the /wms/health status (HEALTHY / DEGRADED / CRITICAL). |
| `forecast-reorder.svg` | AI demand forecast feeding reorder suggestions and low-stock / dead-stock reports. |
| `fifo-vs-fefo.svg` | Side-by-side comparison of FIFO (oldest in-date) vs FEFO (soonest-expiry). |
| `roles-permissions.svg` | Who can do what: Manager, Store Keeper, and Read-only viewer. |
