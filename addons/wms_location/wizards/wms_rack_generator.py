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
       multi-shelf spans). When present, ``layout_json`` overrides quick
       grid mode.

    Either mode produces the same canonical hierarchy:
        Rack (view) → Compartment (view) → Slot (internal)

    Slots get auto-generated barcodes in the form
    ``<rack_code>-SH<top>[-<bottom>]-C<col>-SL<slot>`` matching the user's
    requested format (zero-padded to 2 digits).
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
        string="Custom layout (JSON)",
        help="When set, overrides shelf_count/column_count and creates "
        "compartments exactly as described. Schema: "
        '{"shelves": N, "columns": M, "compartments": [{"shelf_top": int, '
        '"shelf_bottom": int, "column_index": int, "slot_count": int, '
        '"label": str (optional)}, ...]}',
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
            raise UserError("Shelves and columns must both be >= 1.")
        if self.default_slot_count < 1:
            raise UserError("Default slot count must be >= 1.")

        compartments = []
        for s in range(1, self.shelf_count + 1):
            for c in range(1, self.column_count + 1):
                compartments.append(
                    {
                        "shelf_top": s,
                        "shelf_bottom": s,
                        "column_index": c,
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
        required = ("rack_code", "shelves", "columns", "compartments")
        for key in required:
            if key not in spec:
                raise UserError("Layout spec missing required key '%s'." % key)
        shelves = int(spec["shelves"])
        columns = int(spec["columns"])
        if shelves < 1 or columns < 1:
            raise UserError("shelves and columns must both be >= 1.")
        # Build a coverage matrix so we can flag overlaps.
        occupied = {}
        for idx, comp in enumerate(spec["compartments"], start=1):
            top = int(comp["shelf_top"])
            bot = int(comp.get("shelf_bottom") or top)
            col = int(comp["column_index"])
            if not (1 <= top <= shelves and 1 <= bot <= shelves and bot >= top):
                raise UserError(
                    "Compartment #%d shelf range %d..%d is invalid (rack has %d shelves)."
                    % (idx, top, bot, shelves)
                )
            if not 1 <= col <= columns:
                raise UserError(
                    "Compartment #%d column %d is outside the rack's 1..%d range."
                    % (idx, col, columns)
                )
            for row in range(top, bot + 1):
                key = (row, col)
                if key in occupied:
                    raise UserError(
                        "Cell (shelf %d, column %d) is covered by two compartments "
                        "(#%d and #%d). Compartments cannot overlap."
                        % (row, col, occupied[key], idx)
                    )
                occupied[key] = idx
            comp["shelf_bottom"] = bot
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
                "A rack with code %s already exists under %s."
                % (rack_code, parent.display_name)
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
            col = int(comp_spec["column_index"])
            slot_count = int(comp_spec.get("slot_count") or 1)
            shelf_label = _shelf_label(top, bot)
            column_label = "C%02d" % col
            comp_name = comp_spec.get("label") or ("%s-%s" % (shelf_label, column_label))
            compartment = Location.create(
                {
                    "name": comp_name,
                    "location_id": rack.id,
                    "company_id": company_id,
                    "usage": "view",
                    "wms_location_type": "compartment",
                    "wms_shelf_top": top,
                    "wms_shelf_bottom": bot,
                    "wms_column_index": col,
                    "wms_slot_count": slot_count,
                    "barcode": "%s-%s-%s" % (rack_code, shelf_label, column_label),
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
