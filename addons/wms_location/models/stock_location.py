from odoo import api, fields, models
from odoo.exceptions import ValidationError

LOCATION_TYPES = [
    ("warehouse_view", "Warehouse view"),
    ("zone", "Zone (building / floor / area)"),
    ("rack", "Rack"),
    ("compartment", "Compartment"),
    ("slot", "Slot"),
    # Non-rack storage: pallet area, floor stack, single-shelf slab,
    # outside yard bay, etc. usage='internal' so quants can land here
    # directly, no compartment/slot needed.
    ("floor", "Floor / Open area"),
]


class StockLocation(models.Model):
    """Rack hierarchy is intentionally 3 levels deep in stock.location:

        Rack (view)
        └── Compartment (view)         ← 2D rectangle on the visual grid
            └── Slot (internal)        ← holds stock; 1+ slots per compartment

    'Shelf' and 'Column' are *grid coordinates*, not separate stock.location
    rows. Each rack carries shelf_count + column_count; each compartment
    carries the 2D rectangle (shelf_top..shelf_bottom × column_left..
    column_right) it occupies on that grid.

    The rectangle can span multiple shelves (a tall column for bottles),
    multiple columns (a wide drawer), or both (a corner-cabinet
    compartment). The display name and barcode encode the range:

        SH01    C01         → 1×1 cell
        SH01-03 C01         → 3 shelves tall, 1 column wide
        SH01    C01-03      → 1 shelf tall, 3 columns wide
        SH01-03 C01-03      → 3×3 block (full corner)
    """

    _inherit = "stock.location"

    wms_location_type = fields.Selection(
        LOCATION_TYPES,
        string="WMS Type",
        index=True,
        help="Marks this location as part of the rack → compartment → slot hierarchy.",
    )
    wms_rack_code = fields.Char(string="Rack code", help="e.g. R01, PHARM01")

    # ---- Rack-level layout ------------------------------------------------
    wms_shelf_count = fields.Integer(
        string="Shelves",
        default=6,
        help="Total horizontal shelves in this rack (visual grid rows).",
    )
    wms_column_count = fields.Integer(
        string="Columns",
        default=3,
        help="Total vertical columns in this rack (visual grid columns).",
    )

    # ---- Compartment 2D-rectangle coordinates -----------------------------
    wms_shelf_top = fields.Integer(
        string="Shelf top",
        help="1-based topmost shelf this compartment occupies.",
    )
    wms_shelf_bottom = fields.Integer(
        string="Shelf bottom",
        help="1-based bottommost shelf this compartment occupies. "
        "Equal to shelf_top for a normal compartment; higher when it "
        "spans several shelves vertically.",
    )
    wms_column_left = fields.Integer(
        string="Column left",
        help="1-based leftmost column this compartment occupies.",
    )
    wms_column_right = fields.Integer(
        string="Column right",
        help="1-based rightmost column this compartment occupies. "
        "Equal to column_left for a normal compartment; higher when it "
        "spans several columns horizontally (a wide drawer).",
    )
    wms_slot_count = fields.Integer(
        string="Slots",
        default=1,
        help="Sub-divisions within this compartment. 1 means the "
        "compartment is itself the storable unit.",
    )

    # ---- Slot-level identity ---------------------------------------------
    wms_slot_number = fields.Integer(
        string="Slot #",
        help="1-based slot index within its parent compartment.",
    )

    # ---- Occupancy / search helpers --------------------------------------
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

    # ---- Declarative DB constraints (Odoo 19) ----------------------------
    _wms_shelf_count_positive = models.Constraint(
        "CHECK (wms_shelf_count IS NULL OR wms_shelf_count >= 1)",
        "A rack must have at least 1 shelf.",
    )
    _wms_column_count_positive = models.Constraint(
        "CHECK (wms_column_count IS NULL OR wms_column_count >= 1)",
        "A rack must have at least 1 column.",
    )
    _wms_shelf_range_valid = models.Constraint(
        "CHECK (wms_shelf_top IS NULL OR wms_shelf_bottom IS NULL "
        "OR wms_shelf_bottom >= wms_shelf_top)",
        "Compartment shelf_bottom must be >= shelf_top.",
    )
    _wms_column_range_valid = models.Constraint(
        "CHECK (wms_column_left IS NULL OR wms_column_right IS NULL "
        "OR wms_column_right >= wms_column_left)",
        "Compartment column_right must be >= column_left.",
    )
    _wms_slot_count_positive = models.Constraint(
        "CHECK (wms_slot_count IS NULL OR wms_slot_count >= 1)",
        "A compartment must have at least 1 slot.",
    )

    # ---- Display name overrides ------------------------------------------
    @api.depends(
        "name",
        "location_id",
        "wms_location_type",
        "wms_shelf_top",
        "wms_shelf_bottom",
        "wms_column_left",
        "wms_column_right",
        "wms_slot_number",
        "location_id.name",
        "location_id.wms_location_type",
    )
    def _compute_display_name(self):
        """Make compartment / slot display names self-contained.

        A bare `C01` is ambiguous on a list view spanning several racks,
        so we prefix with the rack code. For compartments that span more
        than one shelf the display reads e.g. `R12 / SH01-03 / C01`; for
        wide compartments `R12 / SH01 / C01-03`; for 2D blocks
        `R12 / SH01-03 / C01-03`.
        """
        wms_recs = self.filtered(lambda r: r.wms_location_type in ("compartment", "slot"))
        for loc in wms_recs:
            if loc.wms_location_type == "compartment":
                rack = loc.location_id
                rack_code = rack.wms_rack_code if rack else (loc.location_id.name or "")
                shelf_label = _shelf_label(loc.wms_shelf_top, loc.wms_shelf_bottom)
                column_label = _column_label(loc.wms_column_left, loc.wms_column_right)
                loc.display_name = "%s / %s / %s" % (rack_code, shelf_label, column_label)
            else:  # slot
                comp = loc.location_id
                rack = comp.location_id if comp else False
                rack_code = rack.wms_rack_code if rack else ""
                shelf_label = (
                    _shelf_label(comp.wms_shelf_top, comp.wms_shelf_bottom) if comp else ""
                )
                column_label = (
                    _column_label(comp.wms_column_left, comp.wms_column_right) if comp else ""
                )
                slot_label = "SL%02d" % (loc.wms_slot_number or 0)
                loc.display_name = "%s / %s / %s / %s" % (
                    rack_code,
                    shelf_label,
                    column_label,
                    slot_label,
                )
        super(StockLocation, self - wms_recs)._compute_display_name()

    @api.depends("quant_ids.quantity", "quant_ids.product_id")
    def _compute_wms_current_qty(self):
        for loc in self:
            quants = loc.quant_ids.filtered(lambda q: q.quantity > 0)
            total = sum(quants.mapped("quantity"))
            loc.wms_current_qty = total
            loc.wms_product_ids = quants.mapped("product_id")
            loc.wms_occupancy_pct = (
                (total / loc.wms_capacity_units * 100.0) if loc.wms_capacity_units else 0.0
            )

    # ---- Hierarchy guards -------------------------------------------------
    @api.constrains(
        "wms_location_type",
        "location_id",
        "wms_shelf_top",
        "wms_shelf_bottom",
        "wms_column_left",
        "wms_column_right",
    )
    def _check_hierarchy(self):
        for loc in self:
            t = loc.wms_location_type
            parent = loc.location_id
            if t == "compartment":
                if not parent or parent.wms_location_type != "rack":
                    raise ValidationError(
                        "A compartment's parent must be a Rack (got %s)."
                        % (parent.wms_location_type if parent else "<none>")
                    )
                shelves = parent.wms_shelf_count or 0
                columns = parent.wms_column_count or 0
                if loc.wms_shelf_top and (loc.wms_shelf_top < 1 or loc.wms_shelf_top > shelves):
                    raise ValidationError(
                        "shelf_top=%d is outside the rack's 1..%d shelf range."
                        % (loc.wms_shelf_top, shelves)
                    )
                if loc.wms_shelf_bottom and (
                    loc.wms_shelf_bottom < 1 or loc.wms_shelf_bottom > shelves
                ):
                    raise ValidationError(
                        "shelf_bottom=%d is outside the rack's 1..%d shelf range."
                        % (loc.wms_shelf_bottom, shelves)
                    )
                if loc.wms_column_left and (
                    loc.wms_column_left < 1 or loc.wms_column_left > columns
                ):
                    raise ValidationError(
                        "column_left=%d is outside the rack's 1..%d column range."
                        % (loc.wms_column_left, columns)
                    )
                if loc.wms_column_right and (
                    loc.wms_column_right < 1 or loc.wms_column_right > columns
                ):
                    raise ValidationError(
                        "column_right=%d is outside the rack's 1..%d column range."
                        % (loc.wms_column_right, columns)
                    )
            elif t == "slot":
                if not parent or parent.wms_location_type != "compartment":
                    raise ValidationError(
                        "A slot's parent must be a Compartment (got %s)."
                        % (parent.wms_location_type if parent else "<none>")
                    )

    # ---- FIFO helper (unchanged contract) ---------------------------------
    @api.model
    def find_oldest_quants_for_product(self, product_id, qty_needed, parent_location_id=None):
        """FIFO helper: returns (plan, missing) where `plan` is an ordered
        list of (quant, take_qty) tuples consuming the oldest quants first.
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
        return plan, remaining


def _shelf_label(top, bottom):
    """Format a shelf coordinate range as SH01 or SH01-03."""
    if not top:
        return "SH??"
    if not bottom or bottom == top:
        return "SH%02d" % top
    return "SH%02d-%02d" % (top, bottom)


def _column_label(left, right):
    """Format a column coordinate range as C01 or C01-03."""
    if not left:
        return "C??"
    if not right or right == left:
        return "C%02d" % left
    return "C%02d-%02d" % (left, right)
