from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Default returnability per WMS kind. The Admin can still override
# per-product on the form (`wms_is_returnable` is read/write — the
# compute only seeds it from the kind, the Admin can flip the boolean
# afterwards if a supplier accepts a partially-used batch back, etc.).
#
# Single-use / consumable things (petrol, screws once welded in,
# food, …) are NOT returnable: once they leave the warehouse they're
# either spent, contaminated, or impossible to reseal. Tools and spare
# parts ARE returnable because they survive use.
# Returnability default per kind. The compute method on
# wms_is_returnable seeds the boolean from this dict; the Admin can
# still flip it per-product if the supplier accepts certain batches
# back (an exception we don't want to encode here).
#
# How to read the defaults:
#   * `True` -> tool / fabric / steel-frame style items that survive
#     use and can re-enter the rack (Scan Return accepts them).
#   * `False` -> once it leaves the gate it is gone: feed eaten,
#     pooja ghee burned, medicine injected, cement set in a wall.
KIND_RETURNABLE_DEFAULTS = {
    "raw_material": True,
    "packaging": True,
    "fluid": False,
    "finished_good": True,
    "wip": True,
    "consumable": False,
    "tool": True,
    "spare": True,
    # --- Added for the trust's actual inventory categories -----------
    "medicine": False,  # veterinary injections, ointments
    "feed": False,  # grass, bran, cattle feed - consumed
    "sanitation": False,  # handwash, soap, disinfectant
    "construction": False,  # cement, steel rod, sand, brick
    "plumbing": False,  # pipe, elbow, valve - one-way install
    "electrical": False,  # switch, wire, bulb, electronics
    "textile": True,  # cloth / towel / blanket - washed and reused
    "stationery": False,  # calendar, photo, book, pen - one-way
    "safety": True,  # fire extinguisher refilled, helmet reused
    "pooja": False,  # ghee, flowers, incense, oil - consumed in puja
}

# Kinds whose stock must be issued by **expiry date** (FEFO), not by
# arrival date (FIFO). Trust workflow: veterinary medicine must leave
# the shelf with the soonest-expiring batch first, cattle feed rots,
# food-grade fluid (ghee, edible oil) goes rancid, pooja items spoil.
#
# When a product belongs to one of these kinds (or has an explicit
# wms_expiry_date set), ``find_oldest_quants_for_product`` switches to
# FEFO: it orders quants by (expiry asc, in_date asc) and expands the
# search to sibling batches with the same name + kind — that way a
# brand-new MED-00042 batch with a 2027 expiry never gets picked while
# an older MED-00037 batch expiring next month is still on the shelf.
EXPIRY_SENSITIVE_KINDS = frozenset({"medicine", "feed", "fluid", "pooja"})

# The dropdown shown on the product form. Order matches the dict
# above; the label in parens echoes the SKU prefix so the Admin
# sees what the auto-generated SKU is going to look like before
# they save.
WMS_KIND_SELECTION = [
    ("raw_material", "Raw Material (RM)"),
    ("packaging", "Packaging (PK)"),
    ("fluid", "Fluid / Liquid / Oil (FL)"),
    ("finished_good", "Finished Good (FG)"),
    ("wip", "Work in Progress (WIP)"),
    ("consumable", "Consumable (CONS)"),
    ("tool", "Tool / Equipment (TOOL)"),
    ("spare", "Spare Part (SPARE)"),
    # --- Trust-specific categories -------------------------------------
    ("medicine", "Medicine - veterinary (MED)"),
    ("feed", "Feed / Grass / Bran (FEED)"),
    ("sanitation", "Sanitation / Handwash / Cleaning (SAN)"),
    ("construction", "Construction: cement / steel / sand (CONST)"),
    ("plumbing", "Plumbing: pipe / fitting / valve (PLMB)"),
    ("electrical", "Electrical / Electronics (ELEC)"),
    ("textile", "Textile / Cloth / Blanket (TEXT)"),
    ("stationery", "Stationery: calendar / book / photo (STAT)"),
    ("safety", "Safety: fire extinguisher / helmet (SAFE)"),
    ("pooja", "Pooja items: lamp / pot / ghee / flowers (POOJA)"),
]

# SKU prefix per kind. The trailing "-" matches the ir.sequence prefix
# in data/wms_sku_sequences.xml so generated codes look like
# "TOOL-00001" / "FEED-00042".
#
# Keep this dict aligned with both WMS_KIND_SELECTION above AND the
# sequence codes referenced in product.template.create() below. The
# constraint _check_sku_prefix uses it to validate manually-typed
# codes match the kind.
KIND_SKU_PREFIX = {
    "raw_material": "RM",
    "packaging": "PK",
    "fluid": "FL",
    "finished_good": "FG",
    "wip": "WIP",
    "consumable": "CONS",
    "tool": "TOOL",
    "spare": "SPARE",
    "medicine": "MED",
    "feed": "FEED",
    "sanitation": "SAN",
    "construction": "CONST",
    "plumbing": "PLMB",
    "electrical": "ELEC",
    "textile": "TEXT",
    "stationery": "STAT",
    "safety": "SAFE",
    "pooja": "POOJA",
}

# ir.sequence.code per kind. The XML data file in
# data/wms_sku_sequences.xml defines one ir.sequence per entry here.
KIND_SEQ_CODE = {
    "raw_material": "wms.sku.raw_material",
    "packaging": "wms.sku.packaging",
    "fluid": "wms.sku.fluid",
    "finished_good": "wms.sku.finished_good",
    "wip": "wms.sku.wip",
    "consumable": "wms.sku.consumable",
    "tool": "wms.sku.tool",
    "spare": "wms.sku.spare",
    "medicine": "wms.sku.medicine",
    "feed": "wms.sku.feed",
    "sanitation": "wms.sku.sanitation",
    "construction": "wms.sku.construction",
    "plumbing": "wms.sku.plumbing",
    "electrical": "wms.sku.electrical",
    "textile": "wms.sku.textile",
    "stationery": "wms.sku.stationery",
    "safety": "wms.sku.safety",
    "pooja": "wms.sku.pooja",
}


class ProductTemplate(models.Model):
    """WMS classification + returnability — defined on product.template
    so it's shared across product variants. The matching fields are
    surfaced on product.product via related fields below.

    The Admin (WMS / Manager) sets the kind once at product creation.
    The Store Keeper sees these fields read-only on the product form
    (enforced by Odoo's product ACL: stock.group_stock_user has read
    only) and the Scan Return wizard refuses any product whose
    `wms_is_returnable` is False.
    """

    _inherit = "product.template"

    wms_product_kind = fields.Selection(
        WMS_KIND_SELECTION,
        string="WMS Kind",
        index=True,
        tracking=True,
        help="Classification used by WMS for returnability and audit "
        "reporting. Mirrors the SKU prefix convention "
        "(RM/PK/FL/FG/WIP/CONS/TOOL/SPARE).",
    )

    wms_is_returnable = fields.Boolean(
        string="Returnable",
        compute="_compute_wms_is_returnable",
        store=True,
        readonly=False,  # admin can override the kind-derived default
        tracking=True,
        help="When ticked, this product can be received back into stock "
        "via Scan Return (e.g. a tool came back from production). "
        "Auto-set from WMS Kind: tools/spares/raw materials default to "
        "returnable; fluids and consumables default to NOT returnable, "
        "because petrol once dispensed can't come back into a barrel "
        "and screws once welded in can't be unscrewed onto a shelf.",
    )

    @api.depends("wms_product_kind")
    def _compute_wms_is_returnable(self):
        """Seed returnability from kind on first set, but leave existing
        overrides alone on re-compute (e.g. when other fields change)."""
        for p in self:
            if p.wms_product_kind:
                p.wms_is_returnable = KIND_RETURNABLE_DEFAULTS.get(p.wms_product_kind, True)

    # ----------------------------------------------------------------------
    # Kind-specific attribute fields
    # ----------------------------------------------------------------------
    #
    # The product form shows these in a "Kind details" group whose
    # individual fields appear/disappear based on wms_product_kind
    # (see views/product_product_views.xml).
    #
    # Field name convention: wms_<attr> so they're easy to grep and so
    # they don't collide with whatever the upstream Odoo product
    # module ships. Where Odoo already has a strict-typed field for
    # the same thing (uom_id for unit of measure, weight for kg) we
    # leave that to Odoo and only add what's WMS-specific.

    # Fluid (FL) ------------------------------------------------------
    wms_volume_litres = fields.Float(
        string="Volume (L)",
        help="Volume of one unit in litres. Used for ordering, "
        "reconciliation, and the buying-recommendation engine.",
    )
    wms_container_size = fields.Char(
        string="Container size",
        help="Free-text description of the container - '1 L bottle', "
        "'5 L can', '200 L barrel', '50 L drum with tap'. Helps the "
        "store keeper grab the right one off the shelf at scan time.",
    )

    # Medicine (MED) + Feed (FEED) + Fluid (FL, when food-grade) -----
    # + Pooja (POOJA, for ghee that goes rancid).
    wms_expiry_date = fields.Date(
        string="Expiry date",
        index=True,
        tracking=True,
        help="When the product becomes unusable. Drives the Expiry "
        "Alert report. For per-batch tracking enable stock.lot on "
        "the product and Odoo's lot.expiration_date will take over.",
    )
    wms_batch_number = fields.Char(
        string="Batch / lot number",
        tracking=True,
        help="Supplier batch reference. Lets the trust trace back "
        "to a specific lot if a vendor issues a recall.",
    )

    # Medicine (MED) only --------------------------------------------
    wms_dosage = fields.Char(
        string="Dosage / strength",
        help="e.g. '10 ml IM single dose', '2 g/day for 5 days', "
        "'1 tablet per 50 kg body weight'. Plain text - vets adjust "
        "per animal, no need to model it strictly.",
    )

    # Feed (FEED) only -----------------------------------------------
    wms_weight_kg = fields.Float(
        string="Weight per unit (kg)",
        help="Net weight of one bag / bundle in kilograms.",
    )

    # Textile (TEXT) -------------------------------------------------
    wms_size = fields.Char(
        string="Size",
        help="e.g. '60 x 40 cm', 'L', 'XL', '6 ft x 4 ft'.",
    )
    wms_colour = fields.Char(string="Colour")
    wms_material = fields.Char(
        string="Material",
        help="Cotton / polyester / jute / wool / etc. Also used by "
        "Construction (steel grade, brick type) and Plumbing (PVC, "
        "GI, copper).",
    )

    # Construction (CONST) -------------------------------------------
    wms_grade = fields.Char(
        string="Grade / specification",
        help="OPC 53 / Fe-500 / M-sand etc. The technical grade "
        "stamped on the supplier's invoice.",
    )
    wms_dimensions = fields.Char(
        string="Dimensions",
        help="Free-text. '12 mm rod, 12 m length', '230 x 110 x 75 mm " "brick', etc.",
    )

    # Plumbing (PLMB) ------------------------------------------------
    wms_diameter_mm = fields.Float(
        string="Diameter (mm)",
        help="Nominal bore in millimetres. 25 mm = 1 inch.",
    )
    wms_length_m = fields.Float(
        string="Length (m)",
        help="Pipe length per unit, metres. Helps planning the cut " "list during a plumbing job.",
    )

    # Electrical / Electronics (ELEC) --------------------------------
    wms_voltage_v = fields.Float(
        string="Voltage (V)",
        help="Operating voltage. 230 V single-phase mains, 12 V DC, " "415 V three-phase, etc.",
    )
    wms_wattage_w = fields.Float(
        string="Wattage (W)",
        help="Power draw at nominal voltage.",
    )

    # Tool (TOOL) + Spare (SPARE) ------------------------------------
    wms_serial_number = fields.Char(
        string="Serial number",
        index=True,
        help="Manufacturer serial. Lets the trust track an individual "
        "drill / coupling across damage, repair, scrap events.",
    )

    # ---- Structured SKU: <PREFIX>-<NNNNN> --------------------------------
    #
    # When a product is created with a wms_product_kind, the
    # default_code (SKU) is auto-filled from the per-kind ir.sequence
    # if the Admin left it empty. If the Admin DID type a code, we
    # enforce that it starts with the right prefix for that kind via
    # _check_sku_prefix below.

    @api.model_create_multi
    def create(self, vals_list):
        # 1. Stamp SKU before super so the variant gets created with
        #    its default_code already in place. Also force sale_ok=False
        #    for WMS products: the Trust buys and uses inventory but
        #    never sells it — the default ``sale_ok = True`` from
        #    upstream Odoo would otherwise wrongly expose every
        #    medicine / feed / tool on the Sales-side Pricelists,
        #    quotations, and invoicing. Admin can still flip the
        #    boolean back on a per-product basis if a one-off resale
        #    ever happens (excess construction material to a neighbour
        #    trust, for example).
        for vals in vals_list:
            kind = vals.get("wms_product_kind")
            code = (vals.get("default_code") or "").strip()
            if kind and not code:
                seq_code = KIND_SEQ_CODE.get(kind)
                if seq_code:
                    new_sku = self.env["ir.sequence"].next_by_code(seq_code)
                    if new_sku:
                        vals["default_code"] = new_sku
            if kind and "sale_ok" not in vals:
                vals["sale_ok"] = False
        templates = super().create(vals_list)

        # 2. After super().create(), each template has at least one
        #    product.product variant. Stamp:
        #      a. variant.barcode = default_code (Code128 = SKU,
        #         so the same identifier the human reads is what
        #         the scanner reads)
        #      b. a wms.barcode.alias row with a fresh EAN-13 so
        #         retail/POS scanners (12-digit numeric only) can
        #         read the same product
        #    Both are skipped if the Admin pre-set them manually.
        for tmpl in templates:
            tmpl._wms_ensure_barcodes()
        return templates

    def _wms_ensure_barcodes(self):
        """Idempotent: stamp Code128 (= SKU) + EAN-13 alias on every
        variant that doesn't already have them.

        Safe to re-run from the bulk back-fill action.
        """
        Alias = self.env["wms.barcode.alias"].sudo()
        for tmpl in self:
            if not tmpl.default_code:
                continue
            for variant in tmpl.product_variant_ids:
                # a. Primary Code128 barcode = the SKU itself
                if not variant.barcode:
                    # Guard against another product already owning
                    # this string as its barcode (uniqueness is
                    # enforced by Odoo's `barcode_uniq` constraint).
                    clash = (
                        self.env["product.product"]
                        .sudo()
                        .search(
                            [("barcode", "=", tmpl.default_code), ("id", "!=", variant.id)],
                            limit=1,
                        )
                    )
                    if not clash:
                        variant.barcode = tmpl.default_code

                # b. Secondary EAN-13 numeric barcode as an alias.
                #    Look for any existing alias with units_per_scan=1
                #    so re-runs don't pile up duplicate EAN-13s.
                has_unit_alias = Alias.search_count(
                    [
                        ("product_id", "=", variant.id),
                        ("units_per_scan", "=", 1.0),
                    ]
                )
                if not has_unit_alias:
                    ean = self._next_ean13()
                    if ean:
                        Alias.create(
                            {
                                "barcode": ean,
                                "product_id": variant.id,
                                "units_per_scan": 1.0,
                                "note": "Auto-generated EAN-13 unit barcode",
                            }
                        )

    @api.model
    def _next_ean13(self):
        """Pull the next EAN-13 from the per-DB sequence and append
        a valid GS1 checksum digit.

        Returns the 13-digit string, or '' if the sequence isn't
        available yet (e.g. module just installed, no commit yet).
        """
        twelve = self.env["ir.sequence"].next_by_code("wms.barcode.ean13")
        if not twelve or not twelve.isdigit() or len(twelve) != 12:
            return ""
        return twelve + self._ean13_checksum(twelve)

    @staticmethod
    def _ean13_checksum(twelve_digits):
        """Compute the GS1 EAN-13 check digit.

        Algorithm:
            * Number the 12 digits left-to-right starting at 1.
            * Sum digits at ODD positions (1,3,5,7,9,11) with weight 1.
            * Sum digits at EVEN positions (2,4,6,8,10,12) with weight 3.
            * Total mod 10. Subtract from 10, mod 10 again.

        Verified with the GS1 reference 5901234123457:
            odd  = 5+0+2+4+2+4 = 17
            even = 9+1+3+1+3+5 = 22
            (17 + 3*22) mod 10 = 83 mod 10 = 3
            (10 - 3) mod 10 = 7    -> check digit '7' ok
        """
        digits = [int(c) for c in twelve_digits]
        odd_sum = sum(digits[0::2])  # positions 1,3,5,7,9,11
        even_sum = sum(digits[1::2])  # positions 2,4,6,8,10,12
        total = odd_sum + 3 * even_sum
        return str((10 - (total % 10)) % 10)

    def action_generate_missing_barcodes(self):
        """Bulk back-fill server action target.

        Invoked from the Product list 'Action' menu via the
        ir.actions.server defined in data/wms_barcode_actions.xml,
        which passes the selected templates as `records` and calls
        `records.action_generate_missing_barcodes()`. So `self` here
        is the user's selection.

        NOTE: do NOT decorate with @api.model - that would force
        self to be empty and Odoo would treat the recordset ids as
        an extra positional argument.
        """
        targets = self
        before = sum(1 for v in targets.mapped("product_variant_ids") if not v.barcode)
        targets._wms_ensure_barcodes()
        # Force a re-read so the post-write barcode values are
        # visible (the recordset's cache reflected the pre-write
        # state).
        targets.invalidate_recordset(["product_variant_ids"])
        after = sum(1 for v in targets.mapped("product_variant_ids") if not v.barcode)
        filled = before - after
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Barcodes generated",
                "message": (
                    "Filled %d Code128 barcode%s on %d product%s. "
                    "Re-print thermal labels via Action -> Print -> "
                    "WMS thermal label."
                )
                % (
                    filled,
                    "" if filled == 1 else "s",
                    len(targets),
                    "" if len(targets) == 1 else "s",
                ),
                "type": "success" if filled else "info",
                "sticky": False,
            },
        }

    @api.constrains("default_code", "wms_product_kind")
    def _check_sku_prefix(self):
        """Reject codes that contradict the WMS Kind.

        Examples:
          kind=tool, code=DRILL-18V       -> rejected (no TOOL- prefix)
          kind=tool, code=TOOL-00001      -> ok
          kind=tool, code=TOOL-DRILL-18V  -> ok (human-readable variant)
          kind=None, code=ANYTHING        -> ok (kind not set, no rule)
          kind=tool, code=''              -> ok (will be auto-filled on
                                             create, write-time empties
                                             are allowed for archived
                                             items the Admin is cleaning up).
        """
        for tmpl in self:
            if not tmpl.wms_product_kind or not tmpl.default_code:
                continue
            expected = KIND_SKU_PREFIX.get(tmpl.wms_product_kind)
            if not expected:
                continue
            code = (tmpl.default_code or "").strip().upper()
            # Accept either "TOOL-..." or just "TOOL" (length 4) as the
            # whole code. Anything else is a kind/code mismatch.
            if not (code == expected or code.startswith(expected + "-")):
                kind_label = dict(WMS_KIND_SELECTION).get(
                    tmpl.wms_product_kind, tmpl.wms_product_kind
                )
                raise ValidationError(
                    _(
                        "SKU '%(code)s' does not match WMS Kind '%(kind)s'.\n\n"
                        "Expected prefix: %(prefix)s-\n"
                        "Either change the SKU to start with '%(prefix)s-', "
                        "or clear the SKU field and the system will generate "
                        "one automatically from the %(kind)s sequence."
                    )
                    % {"code": tmpl.default_code, "kind": kind_label, "prefix": expected}
                )

    # ---- "Where is it?" smart-button summary -----------------------------
    wms_total_on_hand = fields.Float(
        string="Total on hand (WMS)",
        compute="_compute_wms_location_summary",
        help="Sum of every quantity of this product currently sitting in "
        "an internal slot or floor zone. Reflects scans the moment they "
        "validate — no manual refresh needed.",
    )
    wms_location_count = fields.Integer(
        string="In how many slots",
        compute="_compute_wms_location_summary",
        help="How many distinct slots or floor zones hold at least one "
        "unit of this product right now.",
    )

    @api.depends(
        "product_variant_ids",
        "product_variant_ids.stock_quant_ids.quantity",
        "product_variant_ids.stock_quant_ids.location_id.usage",
    )
    def _compute_wms_location_summary(self):
        Quant = self.env["stock.quant"].sudo()
        for tmpl in self:
            variant_ids = tmpl.product_variant_ids.ids
            if not variant_ids:
                tmpl.wms_total_on_hand = 0.0
                tmpl.wms_location_count = 0
                continue
            quants = Quant.search(
                [
                    ("product_id", "in", variant_ids),
                    ("location_id.usage", "=", "internal"),
                    ("quantity", ">", 0),
                ]
            )
            tmpl.wms_total_on_hand = sum(q.quantity for q in quants)
            tmpl.wms_location_count = len({q.location_id.id for q in quants})

    def action_view_wms_locations(self):
        """Open the per-slot breakdown for this product. Used by the
        "Where is it?" smart button on the product form. Falls back to
        the standard stock-quants screen if the wms.product.stock.report
        view isn't installed yet."""
        self.ensure_one()
        variant_ids = self.product_variant_ids.ids
        if not variant_ids:
            variant_ids = [0]
        action = self.env.ref("wms_reports.action_wms_product_stock", raise_if_not_found=False)
        if action:
            return {
                "name": "Where is %s?" % self.display_name,
                "type": "ir.actions.act_window",
                "res_model": "wms.product.stock.report",
                "view_mode": "list,pivot",
                "domain": [("product_id", "in", variant_ids)],
                "context": {"search_default_group_product": 0},
            }
        # Fall-back: standard stock.quant list filtered to this product.
        return {
            "name": "Where is %s?" % self.display_name,
            "type": "ir.actions.act_window",
            "res_model": "stock.quant",
            "view_mode": "list,form",
            "domain": [
                ("product_id", "in", variant_ids),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ],
        }


class ProductProduct(models.Model):
    """Expose template-level WMS classification on the variant model so
    other wms_* addons can write `product.wms_is_returnable` directly
    instead of going through `product.product_tmpl_id.wms_is_returnable`.
    """

    _inherit = "product.product"

    wms_product_kind = fields.Selection(
        related="product_tmpl_id.wms_product_kind",
        store=True,
        readonly=False,
        string="WMS Kind",
    )
    wms_is_returnable = fields.Boolean(
        related="product_tmpl_id.wms_is_returnable",
        store=True,
        readonly=False,
        string="Returnable",
    )
