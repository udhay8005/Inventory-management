# 06 — Reports & dashboards

All dashboards are read-only SQL views (`_auto = False`) on top of `stock.quant`,
`stock.move`, and `wms.forecast`. They never duplicate data.

## Dashboards (Odoo dashboard view + pivot/graph)

| # | Name | Source | Key filters |
|---|---|---|---|
| 1 | Current Stock by Product | `stock.quant` | active products, qty > 0 |
| 2 | Current Stock by Slot | `stock.quant` (location.type=slot) | rack, divider |
| 3 | Oldest Stock First (FIFO) | `stock.quant` ordered by `in_date` | aging buckets |
| 4 | Stock Movement History | `stock.move` | date range, type |
| 5 | Low Stock Alerts | `wms.forecast` JOIN `stock.quant` | `on_hand < reorder_point` |
| 6 | Reorder Suggestions | `wms.forecast` | `suggested_order > 0` |
| 7 | Monthly Consumption | `stock.move` | by product/category, month |
| 8 | Damaged Items | `wms.damage` | open/closed |
| 9 | Repair Pipeline | `wms.repair.order` | state |
| 10 | Return History | `stock.picking` (returns) + `wms.return` | date |
| 11 | Location Occupancy | `stock.quant` GROUP BY location | % capacity |
| 12 | Barcode Labels Printed | `wms.label.print.log` | by user, date |
| 13 | Dead / Slow Stock | `wms.forecast.velocity_class IN (slow, dead)` | days idle |
| 14 | Item Valuation | `stock.valuation.layer` (CE-compatible) | by category |
| 15 | Purchase Recommendation Summary | `wms.forecast` aggregated by vendor | next-30d |

## Printable PDFs (`reports/*.xml`)

- Slot occupancy by rack (one page per rack)
- Reorder suggestion PO draft
- Damaged-stock weekly summary
- Barcode labels (product / slot / rack) — see `04-barcode-flow.md`

## Implementation pattern (example: oldest stock view)

```python
class WmsOldestStockReport(models.Model):
    _name = "wms.oldest.stock.report"
    _description = "Oldest stock first (FIFO view)"
    _auto = False
    _order = "in_date asc"

    product_id   = fields.Many2one("product.product", readonly=True)
    location_id  = fields.Many2one("stock.location", readonly=True)
    rack_id      = fields.Many2one("stock.location", readonly=True)
    quantity     = fields.Float(readonly=True)
    in_date      = fields.Datetime(readonly=True)
    age_days     = fields.Integer(readonly=True)

    def init(self):
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW wms_oldest_stock_report AS
            SELECT q.id AS id,
                   q.product_id, q.location_id,
                   r.id AS rack_id,
                   q.quantity, q.in_date,
                   EXTRACT(DAY FROM (now() - q.in_date))::int AS age_days
              FROM stock_quant q
              JOIN stock_location s ON s.id = q.location_id
                                   AND s.wms_location_type = 'slot'
              JOIN stock_location d ON d.id = s.location_id
              JOIN stock_location r ON r.id = d.location_id
             WHERE q.quantity > 0;
        ''')
```

This is what we ship for each dashboard — fast, no duplication, always live.
