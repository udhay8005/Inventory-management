import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsRackGenerator(models.TransientModel):
    """Create a Rack with any number of shelves and columns. Supports two
    modes:

    1. **Quick grid** — set shelf_count + column_count + default_slot_count
       and we generate one compartment per (shelf, column) cell.

    2. **Custom layout** — the visual Rack Builder writes a JSON layout
       spec into ``layout_json`` describing each compartment (including
       multi-shelf and multi-column 2D rectangles). When present,
       ``layout_json`` overrides quick grid mode.

    Either mode produces the same canonical hierarchy:
        Rack (view) → Compartment (view) → Slot (internal)

    Slots get auto-generated barcodes in the form
    ``<rack_code>-SH<top>[-<bottom>]-C<left>[-<right>]-SL<slot>``
    (zero-padded to 2 digits per segment). Examples:
        R01-SH01-C01-SL01          ← single cell
        R01-SH01-03-C01-SL01       ← spans 3 shelves
        R01-SH01-C01-03-SL01       ← spans 3 columns
        R01-SH01-03-C01-03-SL01    ← 3x3 block
    """

    _name = "wms.rack.generator"
    _description = "Generate a Rack with its compartments and slots"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search([], limit=1),
    )
    parent_location_id = fields.Many2one(
        "stock.location",
        string="Parent location",
        required=True,
        help="Usually a Zone (e.g. 'Pharmacy') or the warehouse stock location.",
        default=lambda self: self._default_parent_location(),
    )
    rack_code = fields.Char(
        required=True,
        default="R01",
        help="Identifier for the rack. Zero-padded by convention: R01, R02, …",
    )
    rack_name = fields.Char(
        string="Display name",
        help="Optional human label shown next to the code, e.g. 'Pharmacy bottles'.",
    )

    # ---- Quick grid inputs -----------------------------------------------
    shelf_count = fields.Integer(
        string="Shelves",
        default=6,
        required=True,
        help="Number of horizontal shelves (grid rows).",
    )
    column_count = fields.Integer(
        string="Columns",
        default=3,
        required=True,
        help="Number of vertical compartments per shelf (grid columns).",
    )
    default_slot_count = fields.Integer(
        string="Slots per compartment",
        default=1,
        required=True,
        help="How many slots each compartment is sub-divided into. "
        "1 means the compartment itself is the storable unit.",
    )
    capacity_per_slot = fields.Float(default=0.0, help="Optional soft cap per slot.")

    # ---- Custom layout (driven by the Rack Builder OWL widget) -----------
    layout_json = fields.Text(
        string="Custom layout",
        help="Generated automatically by the Visual builder above — leave this "
        "alone unless you really want to hand-craft a rack layout. When it has "
        "a value, it takes priority over the Quick grid tab.",
    )

    @api.model
    def _default_parent_location(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        return wh and wh.lot_stock_id or False

    # ---- Public entry point -----------------------------------------------
    def action_generate(self):
        self.ensure_one()
        spec = self._build_spec()
        rack = self._create_rack_from_spec(spec)
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.location",
            "res_id": rack.id,
            "view_mode": "form",
            "target": "current",
        }

    # ---- Spec assembly ----------------------------------------------------
    def _build_spec(self):
        """Either parse the custom layout JSON, or synthesise one from the
        quick-grid inputs."""
        if self.layout_json:
            try:
                spec = json.loads(self.layout_json)
            except json.JSONDecodeError as exc:
                raise UserError("Invalid layout JSON: %s" % exc) from exc
            spec.setdefault("rack_code", self.rack_code)
            spec.setdefault("rack_name", self.rack_name or self.rack_code)
            spec.setdefault("parent_location_id", self.parent_location_id.id)
            return self._validate_spec(spec)

        if self.shelf_count < 1 or self.column_count < 1:
            raise UserError("Shelves and columns must both be at least 1.")
        if self.default_slot_count < 1:
            raise UserError("Slots per compartment must be at least 1.")

        compartments = []
        for s in range(1, self.shelf_count + 1):
            for c in range(1, self.column_count + 1):
                compartments.append(
                    {
                        "shelf_top": s,
                        "shelf_bottom": s,
                        "column_left": c,
                        "column_right": c,
                        "slot_count": self.default_slot_count,
                    }
                )
        return {
            "rack_code": self.rack_code,
            "rack_name": self.rack_name or self.rack_code,
            "parent_location_id": self.parent_location_id.id,
            "shelves": self.shelf_count,
            "columns": self.column_count,
            "compartments": compartments,
        }

    def _validate_spec(self, spec):
        """Validate the spec and normalise three legacy variants:

          1. column_index (single int) -> column_left/column_right
          2. column_left/column_right rectangle -> cells list
          3. cells list with no bounding box -> derived shelf_top/bottom
                                                 + column_left/right

        After this method runs every compartment has both:
          * `cells` = list of [shelf, column] pairs (the canonical
            shape; supports arbitrary 4-connected polyominoes)
          * `shelf_top`/`shelf_bottom`/`column_left`/`column_right` =
            bounding box of `cells` (kept for stock.location's
            wms_shelf_* fields and the warehouse-map renderer)
        """
        required = ("rack_code", "shelves", "columns", "compartments")
        for key in required:
            if key not in spec:
                raise UserError(
                    "The custom rack layout is incomplete (missing %s). "
                    "Re-open the Visual builder tab to regenerate it." % key
                )
        shelves = int(spec["shelves"])
        columns = int(spec["columns"])
        if shelves < 1 or columns < 1:
            raise UserError("Shelves and columns must both be at least 1.")

        # 2D coverage matrix indexed by (shelf, column). Every cell
        # can only be owned by one compartment.
        occupied = {}

        for idx, comp in enumerate(spec["compartments"], start=1):
            # ---- Resolve cells ---------------------------------------
            cells = comp.get("cells")
            if cells:
                # Coerce to list-of-tuples for hashing + sanity check
                try:
                    cells = [(int(p[0]), int(p[1])) for p in cells]
                except (TypeError, ValueError, IndexError):
                    raise UserError(
                        "Compartment #%d has a malformed 'cells' "
                        "entry. Expected list of [shelf, column]." % idx
                    )
            else:
                # Legacy formats - convert to cells.
                top = int(comp["shelf_top"])
                bot = int(comp.get("shelf_bottom") or top)
                if "column_left" in comp:
                    left = int(comp["column_left"])
                    right = int(comp.get("column_right") or left)
                else:
                    left = int(comp.get("column_index", 1))
                    right = int(comp.get("column_index", left))
                cells = [(s, c) for s in range(top, bot + 1) for c in range(left, right + 1)]

            if not cells:
                raise UserError(
                    "Compartment #%d has no cells. Every compartment "
                    "must cover at least one (shelf, column)." % idx
                )

            # ---- Range + uniqueness checks ---------------------------
            for s, c in cells:
                if not (1 <= s <= shelves):
                    raise UserError(
                        "Compartment #%d references shelf %d which is "
                        "out of range 1..%d." % (idx, s, shelves)
                    )
                if not (1 <= c <= columns):
                    raise UserError(
                        "Compartment #%d references column %d which is "
                        "out of range 1..%d." % (idx, c, columns)
                    )
                if (s, c) in occupied:
                    raise UserError(
                        "Cell (shelf %d, column %d) is covered by two "
                        "compartments (#%d and #%d). Compartments "
                        "cannot overlap." % (s, c, occupied[(s, c)], idx)
                    )
                occupied[(s, c)] = idx

            # ---- Compute / store the bounding box --------------------
            tops = [s for s, _ in cells]
            cols = [c for _, c in cells]
            comp["cells"] = [[s, c] for s, c in cells]
            comp["shelf_top"] = min(tops)
            comp["shelf_bottom"] = max(tops)
            comp["column_left"] = min(cols)
            comp["column_right"] = max(cols)
            comp.pop("column_index", None)
            comp["slot_count"] = max(1, int(comp.get("slot_count") or 1))
        return spec

    # ---- Canonical builder ------------------------------------------------
    def _create_rack_from_spec(self, spec):
        Location = self.env["stock.location"]
        parent = self.env["stock.location"].browse(spec["parent_location_id"])
        if not parent:
            raise UserError("Parent location is required.")
        company_id = parent.company_id.id

        rack_code = spec["rack_code"].strip()
        if not rack_code:
            raise UserError("Rack code is required.")
        if Location.search_count(
            [
                ("location_id", "=", parent.id),
                ("wms_location_type", "=", "rack"),
                ("wms_rack_code", "=", rack_code),
            ]
        ):
            raise UserError(
                "A rack with code %s already exists under %s." % (rack_code, parent.display_name)
            )

        rack = Location.create(
            {
                "name": spec.get("rack_name") or rack_code,
                "location_id": parent.id,
                "company_id": company_id,
                "usage": "view",
                "wms_location_type": "rack",
                "wms_rack_code": rack_code,
                "wms_shelf_count": int(spec["shelves"]),
                "wms_column_count": int(spec["columns"]),
                "barcode": rack_code,
            }
        )

        for comp_spec in spec["compartments"]:
            top = int(comp_spec["shelf_top"])
            bot = int(comp_spec["shelf_bottom"])
            left = int(comp_spec["column_left"])
            right = int(comp_spec["column_right"])
            slot_count = int(comp_spec.get("slot_count") or 1)
            cells = comp_spec.get("cells") or []

            # Detect non-rectangular shape: cells count < bbox area.
            bbox_area = (bot - top + 1) * (right - left + 1)
            is_polyomino = bool(cells) and len(cells) < bbox_area

            shelf_label = _shelf_label(top, bot)
            column_label = _column_label(left, right)
            if is_polyomino:
                # For an L / T / U shape the bounding-box label is
                # misleading. Compose the name from each cell so it
                # reads "SH02-C01_SH03-C01-C02" or similar - lists
                # exactly which cells the compartment covers.
                comp_name = comp_spec.get("label") or _polyomino_label(cells)
                # Barcode includes a hash of the cells so two
                # compartments with the same bbox but different
                # interior shape can coexist in one rack.
                shape_tag = "P%d" % (len(cells))
                barcode = "%s-%s-%s-%s" % (
                    rack_code,
                    shelf_label,
                    column_label,
                    shape_tag,
                )
            else:
                comp_name = comp_spec.get("label") or ("%s-%s" % (shelf_label, column_label))
                barcode = "%s-%s-%s" % (rack_code, shelf_label, column_label)
            compartment = Location.create(
                {
                    "name": comp_name,
                    "location_id": rack.id,
                    "company_id": company_id,
                    "usage": "view",
                    "wms_location_type": "compartment",
                    "wms_shelf_top": top,
                    "wms_shelf_bottom": bot,
                    "wms_column_left": left,
                    "wms_column_right": right,
                    "wms_slot_count": slot_count,
                    "barcode": barcode,
                }
            )
            for n in range(1, slot_count + 1):
                slot_label = "SL%02d" % n
                Location.create(
                    {
                        "name": slot_label,
                        "location_id": compartment.id,
                        "company_id": company_id,
                        "usage": "internal",  # slots actually hold stock
                        "wms_location_type": "slot",
                        "wms_slot_number": n,
                        "wms_capacity_units": self.capacity_per_slot,
                        "barcode": "%s-%s-%s-%s"
                        % (rack_code, shelf_label, column_label, slot_label),
                    }
                )
        return rack


def _shelf_label(top, bottom):
    """Mirror of the helper in stock_location.py — kept local to avoid a
    cross-module import cycle when the wizard is imported standalone."""
    if not top:
        return "SH??"
    if not bottom or bottom == top:
        return "SH%02d" % top
    return "SH%02d-%02d" % (top, bottom)


def _column_label(left, right):
    if not left:
        return "C??"
    if not right or right == left:
        return "C%02d" % left
    return "C%02d-%02d" % (left, right)


def _polyomino_label(cells):
    """Render a polyomino's cells as a deterministic, human-readable
    string. Example: cells = [[2,1],[3,1],[3,2]] -> "SH02-C01_SH03-C01-C02".

    Groups cells by shelf so wide rows compress to a range. The
    underscore separates shelves. The label is unique per cell-set
    which is what we want for the compartment name shown in the rack
    grid view.
    """
    by_shelf = {}
    for s, c in cells:
        by_shelf.setdefault(int(s), []).append(int(c))
    parts = []
    for s in sorted(by_shelf):
        cols = sorted(set(by_shelf[s]))
        # Compress contiguous columns into ranges (1,2,3 -> "01-03").
        runs = []
        i = 0
        while i < len(cols):
            j = i
            while j + 1 < len(cols) and cols[j + 1] == cols[j] + 1:
                j += 1
            if i == j:
                runs.append("C%02d" % cols[i])
            else:
                runs.append("C%02d-%02d" % (cols[i], cols[j]))
            i = j + 1
        parts.append("SH%02d-%s" % (s, "-".join(runs)))
    return "_".join(parts)
