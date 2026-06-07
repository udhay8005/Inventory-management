from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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
        help="The topmost shelf number this compartment occupies (1 = top of the rack).",
    )
    wms_shelf_bottom = fields.Integer(
        string="Shelf bottom",
        help="The bottommost shelf number this compartment occupies. "
        "Same as Shelf top for a normal compartment; higher when the "
        "compartment is tall and spans several shelves.",
    )
    wms_column_left = fields.Integer(
        string="Column left",
        help="The leftmost column number this compartment occupies (1 = leftmost column).",
    )
    wms_column_right = fields.Integer(
        string="Column right",
        help="The rightmost column number this compartment occupies. "
        "Same as Column left for a normal compartment; higher when the "
        "compartment is wide and spans several columns.",
    )
    wms_slot_count = fields.Integer(
        string="Slots",
        default=1,
        help="How many sub-divisions (slots) sit inside this compartment. "
        "1 means the compartment itself is the storable unit.",
    )
    wms_cells_json = fields.Char(
        string="Compartment cells (JSON)",
        copy=False,
        help="For non-rectangular (L / T / U polyomino) compartments: the exact "
        "list of [shelf, column] cells the compartment covers, as JSON. Empty "
        "for plain rectangular compartments (the shelf/column bounding box "
        "describes those fully). The warehouse-map renderer uses this to draw "
        "the true shape instead of the misleading bounding-box rectangle.",
    )

    # ---- Slot-level identity ---------------------------------------------
    wms_slot_number = fields.Integer(
        string="Slot #",
        help="Position of this slot inside its compartment (1 = first slot).",
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
        help="Total quantity of all products currently on hand at this location.",
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

    @api.constrains("barcode")
    def _check_barcode_globally_unique(self):
        """Critical #4: a location barcode must be globally unique.

        Core only guards UNIQUE(barcode, company_id); a NULL company_id (the
        common single-company tree) defeats that, letting the generators mint
        two slots with the same barcode so a scan resolves to an arbitrary
        one. Enforce non-NULL barcode uniqueness across all locations.
        """
        coded = self.filtered("barcode")
        if not coded:
            return
        barcodes = coded.mapped("barcode")
        clash = self.search([("barcode", "in", barcodes), ("id", "not in", coded.ids)], limit=1)
        if clash:
            raise ValidationError(
                _("Location barcode %s is already used by another location.") % clash.barcode
            )
        seen = set()
        for loc in coded:
            if loc.barcode in seen:
                raise ValidationError(
                    _("Location barcode %s is assigned to two locations at once.") % loc.barcode
                )
            seen.add(loc.barcode)

    # ---- FIFO / FEFO planner ----------------------------------------------
    @api.model
    def find_oldest_quants_for_product(self, product_id, qty_needed, parent_location_id=None):
        """Plan a deduction across slots, returning (plan, missing) where
        ``plan`` is an ordered list of (quant, take_qty) tuples.

        Ordering (Critical #1/#5): pooling is strictly within the scanned
        product's own template (all its variants); the planner never crosses
        to a same-named SIBLING product (which previously could issue a
        different SKU and unit of measure). One template means one UoM, so
        cross-product / cross-UoM substitution is impossible. Different
        physical batches are different products; the keeper scans the specific
        batch to issue. Ordering is delegated to
        ``stock.quant._wms_sorted_for_removal`` (oldest in_date first) — the
        single authoritative removal order shared with ``_gather``.

        Location scoping:
          * Strict pass first: ``child_of parent_location_id`` (typically
            the warehouse's ``lot_stock_id``). Keeps multi-warehouse
            issues tidy.
          * Fallback: if the strict pass finds nothing AND a parent was
            requested, retry across every internal location in the
            active company. Rescues the common single-warehouse setup
            where the trust placed racks under a branded top-level
            location (e.g. "Dakshin Vrindavan") instead of the default
            ``WH/Stock`` tree.
        """
        scanned = self.env["product.product"].browse(product_id).exists()
        if not scanned:
            return [], qty_needed

        # Critical #1: pool ONLY the scanned product's own template (all its
        # variants). Never widen to same-named SIBLING products, which could
        # silently issue a different SKU and even a different unit of measure.
        # One template => one UoM, so cross-product / cross-UoM substitution
        # is impossible. Different physical batches are different products;
        # the keeper scans the specific batch they want to issue.
        product_ids = scanned.product_tmpl_id.product_variant_ids.ids

        # FPAT Critical: the planner must NEVER pull from the Damage or
        # Repair-Out locations. They are usage='internal' (they hold real
        # stock) but the stock there is broken or in-flight and must not be
        # re-issued back to cows. The previous domain only filtered on
        # location.usage, so the fallback widened across damage + repair
        # locations and could silently issue contaminated medicine. We
        # exclude wms_is_damage / wms_is_repair on the joined location.
        base_domain = [
            ("product_id", "in", product_ids),
            ("quantity", ">", 0),
            ("location_id.usage", "=", "internal"),
            ("location_id.wms_is_damage", "=", False),
            ("location_id.wms_is_repair", "=", False),
        ]
        strict = list(base_domain)
        if parent_location_id:
            strict.append(("location_id.id", "child_of", parent_location_id))
        quants = self.env["stock.quant"].search(strict)
        if not quants and parent_location_id:
            company_id = self.env.company.id
            fallback = list(base_domain) + [
                "|",
                ("company_id", "=", company_id),
                ("company_id", "=", False),
            ]
            quants = self.env["stock.quant"].search(fallback)

        # Single authoritative removal ordering, shared with _gather (#5).
        quants = quants._wms_sorted_for_removal()

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

    @api.ondelete(at_uninstall=False)
    def _wms_block_delete_when_used(self):
        """Refuse to delete a rack / compartment / slot / floor that still
        holds stock or has move history. Tell the operator to archive
        instead. Guards against an admin accidentally orphaning audit
        history with one click on the standard form Delete button.
        """
        protected_types = {"rack", "compartment", "slot", "floor"}
        Move = self.env["stock.move"].sudo()
        for loc in self:
            if loc.wms_location_type not in protected_types:
                continue  # leave Odoo core paths untouched

            # 1. Children still hanging off?
            child_count = self.search_count([("location_id", "=", loc.id)])
            if child_count:
                raise UserError(
                    _(
                        "You can't delete %(name)s because it still has %(n)d "
                        "sub-location(s) inside it (shelves, compartments, or "
                        "slots). Delete the smallest units first (work from "
                        "slots up to compartments), then delete the rack."
                    )
                    % {"name": loc.complete_name or loc.display_name, "n": child_count}
                )

            # 2. Live stock?
            on_hand = sum(loc.quant_ids.mapped("quantity") or [0.0])
            if on_hand > 0.001:
                raise UserError(
                    _(
                        "%(name)s still has %(qty).3f unit(s) of stock in it "
                        "(across %(n)d quant(s)). Empty it first by issuing, "
                        "scrapping, or moving the stock to another slot. Once "
                        "it's empty, you can archive (deactivate) it."
                    )
                    % {
                        "name": loc.complete_name or loc.display_name,
                        "qty": on_hand,
                        "n": len(loc.quant_ids),
                    }
                )

            # 3. Any move history? Then archive, do not delete.
            history = Move.search_count(
                [
                    "|",
                    ("location_id", "=", loc.id),
                    ("location_dest_id", "=", loc.id),
                ],
                limit=1,
            )
            if history:
                raise UserError(
                    _(
                        "%(name)s has history in the warehouse records (past "
                        "issues, receipts, returns). You can't delete it "
                        "because the trust needs to keep the audit trail "
                        "intact. Instead, mark it as 'Archived' (inactive) "
                        "on the location form."
                    )
                    % {"name": loc.complete_name or loc.display_name}
                )


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
