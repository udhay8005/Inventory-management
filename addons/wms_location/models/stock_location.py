from odoo import api, fields, models
from odoo.exceptions import ValidationError


LOCATION_TYPES = [
    ("warehouse_view", "Warehouse view"),
    ("rack", "Rack"),
    ("divider", "Divider"),
    ("slot", "Slot"),
]

MAX_DIVIDERS = 6
MAX_SLOTS = 3


class StockLocation(models.Model):
    _inherit = "stock.location"

    wms_location_type = fields.Selection(
        LOCATION_TYPES,
        string="WMS Type",
        index=True,
        help="Marks this location as part of the rack→divider→slot hierarchy.",
    )
    wms_rack_code = fields.Char(string="Rack code", help="e.g. R-01")
    wms_divider_number = fields.Integer(string="Divider #", help="1..6 within parent rack")
    wms_slot_number = fields.Integer(string="Slot #", help="1..3 within parent divider")
    wms_capacity_units = fields.Float(
        string="Capacity (units)",
        default=0.0,
        help="Soft capacity hint shown in UI; not enforced.",
    )
    wms_current_qty = fields.Float(
        string="On hand",
        compute="_compute_wms_current_qty",
        help="Total of stock.quant.quantity at this location.",
    )
    wms_occupancy_pct = fields.Float(
        string="Occupancy %",
        compute="_compute_wms_current_qty",
    )
    wms_product_ids = fields.Many2many(
        "product.product",
        string="Products here",
        compute="_compute_wms_current_qty",
    )

    _sql_constraints = [
        (
            "wms_divider_range",
            "CHECK (wms_divider_number IS NULL OR (wms_divider_number BETWEEN 1 AND 6))",
            "Divider number must be between 1 and 6.",
        ),
        (
            "wms_slot_range",
            "CHECK (wms_slot_number IS NULL OR (wms_slot_number BETWEEN 1 AND 3))",
            "Slot number must be between 1 and 3.",
        ),
    ]

    @api.depends("quant_ids.quantity", "quant_ids.product_id")
    def _compute_wms_current_qty(self):
        for loc in self:
            quants = loc.quant_ids.filtered(lambda q: q.quantity > 0)
            total = sum(quants.mapped("quantity"))
            loc.wms_current_qty = total
            loc.wms_product_ids = quants.mapped("product_id")
            loc.wms_occupancy_pct = (
                (total / loc.wms_capacity_units * 100.0)
                if loc.wms_capacity_units
                else 0.0
            )

    @api.constrains("wms_location_type", "location_id")
    def _check_hierarchy(self):
        for loc in self:
            t = loc.wms_location_type
            parent = loc.location_id
            if t == "divider":
                if not parent or parent.wms_location_type != "rack":
                    raise ValidationError(
                        "A divider's parent must be a Rack (got %s)."
                        % (parent.wms_location_type if parent else "<none>")
                    )
                siblings = self.search_count([
                    ("location_id", "=", parent.id),
                    ("wms_location_type", "=", "divider"),
                    ("id", "!=", loc.id),
                ])
                if siblings >= MAX_DIVIDERS:
                    raise ValidationError(
                        "Rack %s already has %d dividers (max %d)."
                        % (parent.display_name, siblings, MAX_DIVIDERS)
                    )
            elif t == "slot":
                if not parent or parent.wms_location_type != "divider":
                    raise ValidationError(
                        "A slot's parent must be a Divider (got %s)."
                        % (parent.wms_location_type if parent else "<none>")
                    )
                siblings = self.search_count([
                    ("location_id", "=", parent.id),
                    ("wms_location_type", "=", "slot"),
                    ("id", "!=", loc.id),
                ])
                if siblings >= MAX_SLOTS:
                    raise ValidationError(
                        "Divider %s already has %d slots (max %d)."
                        % (parent.display_name, siblings, MAX_SLOTS)
                    )

    @api.model
    def find_oldest_quants_for_product(self, product_id, qty_needed,
                                       parent_location_id=None):
        """FIFO helper: returns ordered list of (quant, take_qty) tuples
        consuming `qty_needed` from the oldest quants of `product_id`.

        Used by the barcode "scan issue" wizard. Pure read; does not modify
        anything.
        """
        domain = [
            ("product_id", "=", product_id),
            ("quantity", ">", 0),
            ("location_id.usage", "=", "internal"),
        ]
        if parent_location_id:
            domain.append(("location_id.id", "child_of", parent_location_id))
        quants = self.env["stock.quant"].search(domain, order="in_date asc, id asc")
        plan = []
        remaining = qty_needed
        for q in quants:
            if remaining <= 0:
                break
            available = q.quantity - q.reserved_quantity
            if available <= 0:
                continue
            take = min(available, remaining)
            plan.append((q, take))
            remaining -= take
        return plan, remaining  # remaining > 0 → short on stock
