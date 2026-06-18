from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

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

# Default expected-return SLA (in days) per WMS kind, used to SEED
# ``expected_return_days`` on product.template the same way
# KIND_RETURNABLE_DEFAULTS seeds ``wms_is_returnable``. Only returnable
# kinds get a non-zero default — a returnable tool / spare is expected
# back within a fortnight, washable textile / reusable safety gear
# within a week, and everything else is 0 (= fall back to the global
# System Parameter ``wms_reports.default_return_days``).
#
# 0 is also the right default for the NON-returnable kinds (feed,
# medicine, fluid, …): they never come back, so an SLA is meaningless.
# The compute below only seeds a non-zero value when the kind is
# returnable, so a kind absent from this map (or a non-returnable one)
# simply stays at 0. Admin-overridable per product, exactly like the
# returnable boolean.
KIND_DEFAULT_RETURN_DAYS = {
    "tool": 14,
    "spare": 14,
    "textile": 7,
    "safety": 7,
}

# Default minimum re-request interval (in days) per WMS kind, used to
# SEED ``wms_min_life_days`` on product.template the same way
# KIND_DEFAULT_RETURN_DAYS seeds ``expected_return_days``. Only the
# kinds that genuinely warrant a "you asked for this too soon" guard
# get a non-zero default; everything else stays 0 (= no per-product
# guard, fall back to the global System Parameter
# ``wms_location.default_min_life_days``).
#
# Sanitation / textile / safety items are durable, slow-burn supplies:
# a fresh tin of disinfectant, a bundle of towels, or a refilled fire
# extinguisher should comfortably last a department a week, so a repeat
# request inside seven days is worth a manager glance (not a hard
# block — Scan Issue asks for a reason and routes it for approval).
# Consumed-daily kinds (feed, fluid) deliberately stay 0 here: a cow
# shed legitimately draws feed every day, so a per-kind min-life guard
# would only generate noise. The admin can still set a per-product
# value on any product, exactly like the cap fields.
KIND_DEFAULT_MIN_LIFE_DAYS = {
    "sanitation": 7,
    "textile": 7,
    "safety": 7,
}

# Kinds whose stock is EXPIRY-SENSITIVE: veterinary medicine, cattle feed,
# food-grade fluid (ghee, edible oil) and pooja items all spoil. Setting an
# expiry date on these drives the Expiry-Alert report, which flags the
# soonest-to-expire stock so it gets rotated out before it spoils.
#
# NOTE: removal at Scan Issue is FIFO (oldest-arrived first) for these kinds
# too. The shared removal engine (stock.quant._wms_sorted_for_removal) keeps an
# expiry-sort branch, but the Scan Issue planner pools within ONE product
# template — and wms_expiry_date is a single template-level field — so that
# branch collapses to plain FIFO. There is NO per-batch FEFO at the picker (the
# trust does not run lot tracking); perishable rotation is the Expiry-Alert
# report's job, not the picker's.
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

# Default Unit-of-Measure per WMS kind, used to SEED ``uom_id`` at
# product-create time only (never retrofitted — changing a UoM
# *category* is blocked once a product has stock, so we must get it
# right the first time and otherwise leave the operator's choice
# alone). Values are uom.uom external ids, all verified present in
# Odoo CE 19's ``uom/data/uom_data.xml``; resolved lazily with
# ``raise_if_not_found=False`` so a half-loaded DB never crashes.
#
# Only two kinds get a non-Units default:
#   * fluid -> Litre  (oil, ghee, disinfectant measured by volume)
#   * feed  -> kg     (grass, bran, cattle feed weighed in)
# EVERYTHING else stays Units (counted by piece).
#
# IMPORTANT — medicine maps to Units on purpose, NOT millilitre:
# Scan Issue's ``_compute_photo_required`` forces a photo whenever the
# product's UoM category is not "Units" (i.e. it is measured, not
# counted). Defaulting medicine to mL would silently switch every vet
# injection into the photo-required gate, an unintended regression.
# Vials / strips are counted; the per-dose strength stays free-text in
# ``wms_dosage``. An operator can still flip a specific bulk medicine
# to mL by hand on the product form.
#
# Length-by-the-metre items (cut pipe, cable/wire spools, cloth) are
# NOT a separate kind: plumbing / electrical / textile default to
# Units (count of pipes / fittings / pieces) and the operator switches
# the individual product to Metre (``uom.product_uom_meter``, Length
# category) when it is stocked / issued by length.
KIND_DEFAULT_UOM = {
    "raw_material": "uom.product_uom_unit",
    "packaging": "uom.product_uom_unit",
    "fluid": "uom.product_uom_litre",
    "finished_good": "uom.product_uom_unit",
    "wip": "uom.product_uom_unit",
    "consumable": "uom.product_uom_unit",
    "tool": "uom.product_uom_unit",
    "spare": "uom.product_uom_unit",
    "medicine": "uom.product_uom_unit",
    "feed": "uom.product_uom_kgm",
    "sanitation": "uom.product_uom_unit",
    "construction": "uom.product_uom_unit",
    "plumbing": "uom.product_uom_unit",
    "electrical": "uom.product_uom_unit",
    "textile": "uom.product_uom_unit",
    "stationery": "uom.product_uom_unit",
    "safety": "uom.product_uom_unit",
    "pooja": "uom.product_uom_unit",
}

# Fallback UoM xmlid for any kind not in KIND_DEFAULT_UOM (e.g. a
# future kind added to WMS_KIND_SELECTION before this dict is updated).
_KIND_DEFAULT_UOM_FALLBACK = "uom.product_uom_unit"


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

    expected_return_days = fields.Integer(
        string="Expected return (days)",
        compute="_compute_expected_return_days",
        store=True,
        readonly=False,  # admin can override the kind-derived default
        tracking=True,
        help="Days within which a returnable item is expected back. 0 = use "
        "the global default (System Parameter wms_reports.default_return_days). "
        "Advisory SLA — drives the overdue-returns alert, does not block "
        "issuing. Auto-seeded from WMS Kind for returnable items "
        "(tool/spare = 14, textile/safety = 7); the Admin can override per "
        "product, exactly like the Returnable flag.",
    )

    @api.depends("wms_product_kind")
    def _compute_expected_return_days(self):
        """Seed the expected-return SLA from kind, mirroring
        ``_compute_wms_is_returnable``. A returnable kind gets its per-kind
        default (tool/spare = 14, textile/safety = 7, others 0); a
        non-returnable or unset kind gets 0 (= fall back to the global
        default). No fields.Integer ``default`` is declared on purpose:
        a stored editable compute with an explicit default is treated as
        user-supplied at create time and the compute would not seed. The
        compute assigns in every branch so the stored value is always
        concrete, and being store=True / readonly=False it only seeds —
        an admin override afterwards persists."""
        for p in self:
            if p.wms_product_kind and KIND_RETURNABLE_DEFAULTS.get(p.wms_product_kind):
                p.expected_return_days = KIND_DEFAULT_RETURN_DAYS.get(p.wms_product_kind, 0)
            else:
                p.expected_return_days = 0

    wms_min_life_days = fields.Integer(
        string="Min re-request interval (days)",
        compute="_compute_wms_min_life_days",
        store=True,
        readonly=False,  # admin can override the kind-derived default
        tracking=True,
        help="Minimum number of days the SAME department should wait before "
        "re-requesting this product. 0 = no per-product guard (falls back to "
        "the global System Parameter wms_location.default_min_life_days; 0 "
        "there too means the guard is off). A too-soon request is NOT blocked "
        "outright — Scan Issue asks the keeper for a reason and routes the "
        "issue to a Manager for approval. Auto-seeded from WMS Kind "
        "(sanitation/textile/safety = 7, others = 0); the Admin can override "
        "per product, exactly like the Returnable flag and the usage caps.",
    )

    @api.depends("wms_product_kind")
    def _compute_wms_min_life_days(self):
        """Seed the min re-request interval from kind, mirroring
        ``_compute_expected_return_days`` / ``_compute_wms_is_returnable``.
        Durable slow-burn kinds (sanitation/textile/safety) get 7 days; every
        other (or unset) kind gets 0 (= no per-product guard, fall back to the
        global default). No fields.Integer ``default`` is declared on purpose:
        a stored editable compute with an explicit default is treated as
        user-supplied at create time and the compute would not seed. The
        compute assigns in every branch so the stored value is always
        concrete, and being store=True / readonly=False it only seeds — an
        admin override afterwards persists."""
        for p in self:
            if p.wms_product_kind:
                p.wms_min_life_days = KIND_DEFAULT_MIN_LIFE_DAYS.get(p.wms_product_kind, 0)
            else:
                p.wms_min_life_days = 0

    def _wms_default_uom_id(self):
        """Return the UoM id this product's WMS kind should default to.

        Looks the kind up in ``KIND_DEFAULT_UOM`` (falling back to
        Units for an unmapped / blank kind) and resolves the external
        id with ``raise_if_not_found=False`` so a half-loaded DB never
        crashes the create path — it just returns False and the caller
        leaves Odoo's own default in place.

        Returns the integer uom.uom id, or False when neither the
        kind's UoM nor the Units fallback can be resolved.
        """
        self.ensure_one()
        xmlid = KIND_DEFAULT_UOM.get(self.wms_product_kind, _KIND_DEFAULT_UOM_FALLBACK)
        uom = self.env.ref(xmlid, raise_if_not_found=False)
        if not uom:
            uom = self.env.ref(_KIND_DEFAULT_UOM_FALLBACK, raise_if_not_found=False)
        return uom.id if uom else False

    @api.model
    def _wms_kind_default_uom_id(self, kind):
        """Class-level twin of ``_wms_default_uom_id`` for the create
        path, where there is no record yet to seed ``uom_id`` from.

        Same resolution rules: kind -> KIND_DEFAULT_UOM (Units
        fallback), resolved with ``raise_if_not_found=False``. Returns
        the uom.uom id or False.
        """
        xmlid = KIND_DEFAULT_UOM.get(kind, _KIND_DEFAULT_UOM_FALLBACK)
        uom = self.env.ref(xmlid, raise_if_not_found=False)
        if not uom:
            uom = self.env.ref(_KIND_DEFAULT_UOM_FALLBACK, raise_if_not_found=False)
        return uom.id if uom else False

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

    # ---- Overuse / abuse-prevention limits ---------------------------------
    #
    # The trust runs on shared stock — one rogue request can drain a
    # whole shelf if nobody catches it at the desk. These two caps let
    # the Admin define product-level limits that Scan Issue checks at
    # validate-time:
    #
    #   wms_max_per_issue : single-issue HARD cap.
    #     0 = no cap. If the requested qty for this product in one
    #     Scan Issue wizard exceeds this, the issue is blocked with
    #     a clear UserError naming the cap and the configured value.
    #     Use for tools (1 hammer at a time), medicine (1 dose), etc.
    #
    #   wms_daily_cap : 24h rolling HARD cap (across ALL keepers and
    #     ALL pickings). 0 = no cap. The check sums every "done"
    #     stock.move.line for this product in the last 24 hours and
    #     blocks if the new issue would push the total past the cap.
    #     Use for feed (50 kg / day), oil (5 L / day), etc.
    #
    # Both default to 0 (no cap) so existing products are unaffected.
    # Admin sets them on the WMS Classification tab.
    wms_max_per_issue = fields.Float(
        string="Max per issue",
        default=0.0,
        help="Hard cap on how many units of this product can leave the "
        "warehouse in a single Scan Issue. Set 0 for no cap. "
        "Example: medicine = 1 (one dose at a time), tool = 1, "
        "consumable bolt = 50.",
    )
    wms_daily_cap = fields.Float(
        string="Daily cap (24h rolling)",
        default=0.0,
        help="Hard cap on the total units of this product that can leave "
        "across ALL store keepers and ALL issue tickets in any rolling "
        "24-hour window. Set 0 for no cap. Example: feed = 50 (kg), "
        "veterinary syringe = 5. Counted from stock.move.line on done "
        "out-pickings.",
    )

    # ======================================================================
    # Enterprise product identity (P2) — universal on EVERY product
    # ======================================================================
    #
    # Family / Brand / Form are admin-editable master registers (each
    # carrying a stable uppercase `code`); Variant / Strength / Pack are
    # free text. Together they identify a stockable item and compose the
    # human-readable BUSINESS SKU (= default_code). These fields apply to
    # ALL product kinds — medicine, feed, tool, chemical, spare, … — the
    # CATEGORY (product.category.wms_effective_req_*) decides which are
    # *required* (enforced in P3), not the field set.
    wms_family_id = fields.Many2one(
        "wms.family",
        string="Family",
        index=True,
        help="Generic group / molecule (Paracetamol, Cow Feed, Liv52). Its "
        "code becomes the Family segment of the SKU.",
    )
    wms_brand_id = fields.Many2one(
        "wms.brand",
        string="Brand",
        index=True,
        help="Manufacturer / label (Cipla, Himalaya, Local). Its code becomes "
        "the Brand segment of the SKU.",
    )
    wms_form_id = fields.Many2one(
        "wms.form",
        string="Form / Model",
        index=True,
        help="Physical form (Tablet, Syrup, Pellet) — or the Model for tools / "
        "spare parts. Its code becomes the Form segment of the SKU; its "
        "suggested unit pre-fills the UoM on a new product.",
    )
    wms_variant = fields.Char(
        string="Variant",
        help="Product line within a brand (Premium, Citrus, Cordless, Adult). "
        "Optional. Squeezed into the SKU.",
    )
    wms_pack_size = fields.Char(
        string="Pack size",
        help="The pack you receive / scan as a unit: 10, 50kg, 5L, 1L. Enter "
        "just the quantity + unit; squeezed into the SKU (50kg → 50KG).",
    )
    # Strength reuses the existing wms_dosage field (see above) — no new
    # column; it is the Strength/concentration segment (500mg, 70%, 18V).

    # --- Two-identifier scheme -------------------------------------------
    # default_code = the readable BUSINESS SKU (composed below).
    # wms_product_code = the IMMUTABLE internal handle, stamped once.
    wms_product_code = fields.Char(
        string="Internal product code",
        index=True,
        copy=False,
        readonly=True,
        help="Permanent internal identifier (PRD-NNNNNN), stamped once at "
        "creation and never changed — survives renames, brand / category "
        "changes and migrations. The stable reference for audits, imports and "
        "history. (The readable SKU lives in the Internal Reference field.)",
    )
    wms_sku_frozen = fields.Boolean(
        string="SKU frozen",
        compute="_compute_wms_sku_frozen",
        copy=False,
        help="True once the product has stock or movement: its SKU and barcode "
        "are then in circulation and locked (archive + recreate instead of "
        "renaming a code already on printed labels / in stock history).",
    )

    _wms_product_code_unique = models.Constraint(
        "UNIQUE(wms_product_code)",
        "The internal product code must be unique.",
    )

    def _wms_in_circulation(self):
        """Live, reliable check: the product has a stock.quant or any stock
        movement, so its SKU/barcode are in circulation and must not change.

        Done as a direct query rather than a stored compute because
        stored-compute invalidation does NOT fire on every stock path (e.g.
        stock.quant._update_available_quantity bypasses the variant→template
        dependency), which would let a stale 'not frozen' value slip through.
        The write-guards call this directly so the lock can never be bypassed."""
        self.ensure_one()
        vids = self.product_variant_ids.ids
        if not vids:
            return False
        Quant = self.env["stock.quant"].sudo()
        if Quant.search_count([("product_id", "in", vids)]):
            return True
        MoveLine = self.env["stock.move.line"].sudo()
        return bool(MoveLine.search_count([("product_id", "in", vids)]))

    @api.depends("product_variant_ids.stock_quant_ids")
    def _compute_wms_sku_frozen(self):
        """Non-stored UI mirror of _wms_in_circulation (so the form always
        reflects live stock). The write-guards use _wms_in_circulation directly;
        this just hides the Regenerate button and shows the freeze alert."""
        for tmpl in self:
            tmpl.wms_sku_frozen = tmpl._wms_in_circulation()

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
        seen_skus = set()
        for vals in vals_list:
            kind = vals.get("wms_product_kind")
            code = (vals.get("default_code") or "").strip()
            # Stamp the immutable internal product code once (on EVERY
            # product, structured-SKU or not), if the caller left it blank.
            if not (vals.get("wms_product_code") or "").strip():
                prd = self.env["ir.sequence"].next_by_code("wms.product.code")
                if prd:
                    vals["wms_product_code"] = prd
            # Fill the Business SKU (default_code) only when the operator left
            # it blank: prefer the deterministic structured composition from
            # the identity fields; otherwise fall back to the per-kind
            # KIND-NNNNN sequence (legacy / quick-entry path). A composed SKU
            # that already exists BLOCKS creation (no auto-suffix) so the
            # catalogue stays clean. seen_skus also blocks two rows in the SAME
            # create() batch composing the same code (neither is in the DB yet).
            if not code:
                business = self._wms_compose_business_sku(vals)
                if business:
                    self._wms_block_sku_collision(business, seen=seen_skus)
                    vals["default_code"] = business
                    seen_skus.add(business)
                elif kind:
                    seq_code = KIND_SEQ_CODE.get(kind)
                    if seq_code:
                        new_sku = self.env["ir.sequence"].next_by_code(seq_code)
                        if new_sku:
                            # Route the fallback through the same friendly gate as
                            # the composed / caller-supplied branches: a clash with
                            # a hand-typed KIND-NNNNN (or another row in this batch)
                            # now raises a clear UserError instead of a raw
                            # IntegrityError. next_by_code stays monotonic, so the
                            # normal path is unaffected.
                            self._wms_block_sku_collision(new_sku, seen=seen_skus)
                            vals["default_code"] = new_sku
                            seen_skus.add(new_sku)
            else:
                # Caller supplied the SKU (import / data file): give it the same
                # friendly collision gate instead of a raw DB IntegrityError.
                self._wms_block_sku_collision(code, seen=seen_skus)
                seen_skus.add(code)
            if kind and "sale_ok" not in vals:
                vals["sale_ok"] = False
            # Seed the unit of measure from the kind ONLY when the
            # caller left it blank (mirrors how default_code above is
            # only auto-filled when empty). A non-Units category cannot
            # be changed once a product carries stock, so this
            # create-time seed is the only safe place to set it — we
            # never retrofit an existing catalog. uom_id stays fully
            # editable per-product afterwards. (uom_po_id is NOT set:
            # product.template.uom_po_id was removed in Odoo 19 in
            # favour of per-supplier UoM on product.supplierinfo, and
            # writing it raises — see wms_product_onboard._do_onboard.)
            if kind and not vals.get("uom_id"):
                # Prefer the chosen Form's suggested unit (tablet → Units,
                # syrup → L, powder → kg); fall back to the kind default.
                # Create-time seed only (never retrofits a stocked product).
                uom_id = None
                form_id = self._wms_vals_id(vals.get("wms_form_id"))
                if form_id:
                    form = self.env["wms.form"].browse(form_id)
                    if form.default_uom_id:
                        uom_id = form.default_uom_id.id
                if not uom_id:
                    uom_id = self._wms_kind_default_uom_id(kind)
                if uom_id:
                    vals["uom_id"] = uom_id
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
                        .with_context(active_test=False)
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

    @api.model
    def _wms_validate_barcode(self, code):
        """Validate an operator-entered / imported barcode. Permissive for
        alphanumeric SKU-as-barcode codes (e.g. TOOL-00001); for a full
        13-digit numeric code it verifies the GS1 check digit via
        _ean13_checksum. Empty = allowed (no barcode). Raises a friendly
        ValidationError on control characters or a wrong EAN-13 check digit.
        Fires on both manual create and CSV import (both go through the ORM).
        """
        if not code:
            return
        code = code.strip()
        if not code:
            return
        if any(ord(c) < 32 for c in code):
            raise ValidationError(
                _("Barcode contains blank or control characters - re-scan or re-type it.")
            )
        if code.isdigit() and len(code) == 13:
            want = self._ean13_checksum(code[:12])
            if code[12] != want:
                raise ValidationError(
                    _(
                        "Barcode %(code)s has check digit %(got)s but a valid EAN-13 "
                        "needs %(want)s - re-scan or re-type it."
                    )
                    % {"code": code, "got": code[12], "want": want}
                )

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
        # Bulk barcode back-fill is a CATALOG operation: it writes product
        # barcodes (via sudo in _wms_ensure_barcodes), so without this gate any
        # keeper who can see the product list could trigger it from the Action
        # menu. Require the Manage Catalog capability (managers imply it).
        if not self.env.user.has_group("wms_location.group_wms_can_manage_catalog"):
            raise AccessError(
                _(
                    "Generating barcodes edits the product catalog, so it needs "
                    "the Manage Catalog capability. Ask a Manager (or a keeper "
                    "with Manage Catalog) to run it."
                )
            )
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

    # ---- Business-SKU composition + two-identifier guards (P2) -----------
    #
    # The Business SKU (= default_code) is the readable, deterministic code
    # operators search and print; the immutable wms_product_code (PRD-…)
    # guarantees a stable unique handle regardless. A composed SKU that
    # collides with an existing product BLOCKS creation — the owner's rule:
    # force the catalogue to be corrected, never auto-suffix.

    @staticmethod
    def _wms_squeeze(text, maxlen):
        """Deterministic SKU segment from free text: uppercase, keep only
        A-Z 0-9, cap length. '500 mg' -> '500MG', '50kg' -> '50KG',
        'Premium' -> 'PREM'. Lossy by design — uniqueness is guaranteed by
        the collision block + the immutable PRD code, not the squeeze."""
        if not text:
            return ""
        squeezed = "".join(ch for ch in text.upper() if ch.isalnum())
        return squeezed[: max(0, maxlen)]

    @staticmethod
    def _wms_vals_id(value):
        """Resolve a single id from a Many2one value as it can appear in a
        create() vals dict: a bare int (the form / normal path), or an x2many-
        style command such as (6, 0, [id]) / (4, id) / [(6, 0, [id])] that some
        ORM/import callers emit. Returns the int id or None — never lets a
        command tuple reach browse() (which would crash or browse the wrong
        record and silently drop the SKU segment / the Form-UoM seed)."""
        if not value:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, (list, tuple)):
            # unwrap a singleton list like [(6,0,[id])] or [(4,id)]
            if value and isinstance(value[0], (list, tuple)):
                value = value[0]
            if not value:
                return None
            tag = value[0]
            if tag in (4, 3, 2, 5) and len(value) > 1 and isinstance(value[1], int):
                return value[1]
            if tag in (6, 0) and len(value) > 2 and value[2]:
                ids = value[2]
                return ids[0] if isinstance(ids, (list, tuple)) and ids else None
        return None

    @api.model
    def _wms_master_code(self, model, value):
        rec_id = self._wms_vals_id(value)
        return self.env[model].browse(rec_id).code if rec_id else None

    @api.model
    def _wms_compose_business_sku(self, vals):
        """Compose KINDPREFIX-FAMILY-BRAND-[VARIANT]-FORM-[STRENGTH]-[PACK]
        from a vals dict. Returns '' when the kind + Family + Brand minimum is
        absent, so create() falls back to KIND-NNNNN. Family/Brand/Form come
        from the master `code` (stable lookup); Variant/Strength(=wms_dosage)/
        Pack are squeezed free text. Optional segments collapse (never empty).
        Many2one values are resolved via _wms_vals_id so command-style vals
        from ORM/import callers don't crash or silently drop a segment."""
        kind = vals.get("wms_product_kind")
        prefix = KIND_SKU_PREFIX.get(kind) if kind else None
        family = self._wms_master_code("wms.family", vals.get("wms_family_id"))
        brand = self._wms_master_code("wms.brand", vals.get("wms_brand_id"))
        if not (prefix and family and brand):
            return ""
        segments = [prefix, family, brand]
        variant = self._wms_squeeze(vals.get("wms_variant"), 4)
        if variant:
            segments.append(variant)
        form = self._wms_master_code("wms.form", vals.get("wms_form_id"))
        if form:
            segments.append(form)
        strength = self._wms_squeeze(vals.get("wms_dosage"), 5)
        if strength:
            segments.append(strength)
        pack = self._wms_squeeze(vals.get("wms_pack_size"), 6)
        if pack:
            segments.append(pack)
        return "-".join(segments)

    @api.model
    def _wms_block_sku_collision(self, business_sku, ignore_tmpl_ids=None, seen=None):
        """Raise a friendly UserError if `business_sku` already belongs to a
        product (the hard duplicate gate — no auto-suffix). `seen` blocks a
        repeat within the same create() batch (the DB search can't see rows not
        yet committed). The search is archive-inclusive (active_test=False) so it
        matches the scope of the UNIQUE(default_code) constraint — otherwise an
        archived holder slips past the friendly gate and dies on a raw DB error
        (the exact 'archive + recreate' path the freeze tells operators to use)."""
        if seen and business_sku in seen:
            raise UserError(
                _(
                    "SKU '%s' is repeated within this batch. Adjust the Brand, "
                    "Variant, Pack size or Strength so each product is distinct."
                )
                % business_sku
            )
        existing = (
            self.env["product.product"]
            .with_context(active_test=False)
            .search([("default_code", "=", business_sku)], limit=1)
        )
        if ignore_tmpl_ids and existing.product_tmpl_id.id in ignore_tmpl_ids:
            return
        if existing:
            raise UserError(
                _(
                    "SKU '%(sku)s' already exists.\n\n"
                    "Existing product: %(name)s (%(prd)s)\n\n"
                    "This Brand / Variant / Form / Strength / Pack combination is "
                    "already in the catalogue. Adjust the Brand, Variant, Pack "
                    "size or Strength to make it distinct — the system never "
                    "creates near-duplicate codes."
                )
                % {
                    "sku": business_sku,
                    "name": existing.display_name,
                    "prd": existing.product_tmpl_id.wms_product_code
                    or existing.default_code
                    or _("no code"),
                }
            )

    def write(self, vals):
        # The internal product code is permanent — never editable once set.
        if "wms_product_code" in vals:
            new = (vals.get("wms_product_code") or "").strip()
            for tmpl in self:
                if tmpl.wms_product_code and new != tmpl.wms_product_code:
                    raise UserError(
                        _("The internal product code (%s) is permanent and " "cannot be changed.")
                        % tmpl.wms_product_code
                    )
        # A SKU in circulation (the product has stock / movement) cannot be
        # renamed. Clearing it stays allowed (archived-item cleanup, per
        # _check_sku_prefix). Archive + recreate instead of renaming. The live
        # _wms_in_circulation check (not the cached field) is the lock.
        if "default_code" in vals:
            new_code = (vals.get("default_code") or "").strip()
            if new_code:
                for tmpl in self:
                    old = (tmpl.default_code or "").strip()
                    if old and new_code != old and tmpl._wms_in_circulation():
                        raise UserError(
                            _(
                                "SKU '%s' is locked: this product has stock or "
                                "movement, so its code is already in circulation. "
                                "Archive it and create a new product instead of "
                                "renaming the SKU."
                            )
                            % tmpl.default_code
                        )
        return super().write(vals)

    @api.onchange(
        "wms_family_id",
        "wms_brand_id",
        "wms_form_id",
        "wms_variant",
        "wms_dosage",
        "wms_pack_size",
    )
    def _onchange_wms_identity_dup(self):
        """Soft, non-blocking heads-up that a product with the same identity
        already exists. The hard block happens at save via the composed SKU."""
        if not (self.wms_family_id and self.wms_brand_id):
            return
        domain = [
            ("wms_family_id", "=", self.wms_family_id.id),
            ("wms_brand_id", "=", self.wms_brand_id.id),
        ]
        if self.wms_form_id:
            domain.append(("wms_form_id", "=", self.wms_form_id.id))
        existing = (
            self.env["product.template"]
            .with_context(active_test=False)
            .search(domain + [("id", "!=", self._origin.id)], limit=3)
        )
        if not existing:
            return
        names = ", ".join("%s (%s)" % (p.display_name, p.wms_product_code or "—") for p in existing)
        return {
            "warning": {
                "title": _("Similar product already exists"),
                "message": _(
                    "An item with this Family / Brand%(form)s already exists:\n"
                    "%(names)s\n\n"
                    "If this is the SAME item, open it instead. If it's a different "
                    "variant / strength / pack, carry on — it gets its own SKU."
                )
                % {"form": _(" / Form") if self.wms_form_id else "", "names": names},
            }
        }

    def action_wms_regenerate_sku(self):
        """Manager tool: re-compose the Business SKU from the current identity
        fields BEFORE the product is frozen (e.g. after fixing the brand).
        Blocks on collision and re-syncs the Code128 barcode. Refused once the
        product is frozen (stock / printed label)."""
        for tmpl in self:
            if tmpl._wms_in_circulation():
                raise UserError(
                    _(
                        "'%s' is frozen (it has stock / movement); its SKU can no "
                        "longer be regenerated. Archive + recreate instead."
                    )
                    % tmpl.display_name
                )
            vals = {
                "wms_product_kind": tmpl.wms_product_kind,
                "wms_family_id": tmpl.wms_family_id.id,
                "wms_brand_id": tmpl.wms_brand_id.id,
                "wms_form_id": tmpl.wms_form_id.id,
                "wms_variant": tmpl.wms_variant,
                "wms_dosage": tmpl.wms_dosage,
                "wms_pack_size": tmpl.wms_pack_size,
            }
            business = tmpl._wms_compose_business_sku(vals)
            if not business:
                raise UserError(
                    _("'%s' needs at least a Kind, Family and Brand to build a " "structured SKU.")
                    % tmpl.display_name
                )
            tmpl._wms_block_sku_collision(business, ignore_tmpl_ids=tmpl.ids)
            tmpl.default_code = business
            # Re-sync the Code128 barcode (= SKU). If another product already
            # owns this string as a barcode, raise rather than silently leave a
            # SKU≠barcode mismatch (archive-inclusive, matching barcode_uniq).
            for variant in tmpl.product_variant_ids:
                clash = (
                    self.env["product.product"]
                    .with_context(active_test=False)
                    .search([("barcode", "=", business), ("id", "!=", variant.id)], limit=1)
                )
                if clash:
                    raise UserError(
                        _(
                            "Cannot re-sync the barcode: '%(sku)s' is already used as a "
                            "barcode by %(name)s. Resolve that conflict first."
                        )
                        % {"sku": business, "name": clash.display_name}
                    )
                variant.barcode = business
        return True

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
        # Count only WAREHOUSE STORAGE (lot-stock + its slot/rack/floor children).
        # The 'Trust internal use' sink (Scan Issue destination, never drains) and
        # the Damage/Repair locations are also usage=internal, so a blanket
        # usage='internal' sum overstates on-hand from a Scan Issue alone. Mirror
        # the lot_stock_id child_of scope used by the value/expiry reports.
        lot_stock_ids = self.env["stock.warehouse"].sudo().search([]).mapped("lot_stock_id").ids
        for tmpl in self:
            variant_ids = tmpl.product_variant_ids.ids
            if not variant_ids or not lot_stock_ids:
                tmpl.wms_total_on_hand = 0.0
                tmpl.wms_location_count = 0
                continue
            quants = Quant.search(
                [
                    ("product_id", "in", variant_ids),
                    ("location_id", "child_of", lot_stock_ids),
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

    _sku_unique = models.Constraint(
        "UNIQUE(default_code)",
        "This SKU / internal reference is already used by another product. "
        "Each product must have a unique SKU.",
    )

    @api.constrains("barcode")
    def _check_barcode_format(self):
        """Reject malformed / bad-check-digit barcodes on create + import
        (reuses product.template._wms_validate_barcode)."""
        Template = self.env["product.template"]
        for rec in self.filtered("barcode"):
            Template._wms_validate_barcode(rec.barcode)

    def write(self, vals):
        # The Code128 barcode (= SKU) is locked once the product has stock /
        # movement — it is already on labels in the field. Clearing it stays
        # allowed; FILLING a blank barcode stays allowed (so _wms_ensure_barcodes
        # and the bulk back-fill still work on a stocked product). Only a RENAME
        # of a non-empty barcode on an in-circulation product is blocked. The
        # live _wms_in_circulation check (not the cached field) is the lock.
        if "barcode" in vals:
            new_bc = (vals.get("barcode") or "").strip()
            if new_bc:
                for rec in self:
                    old = (rec.barcode or "").strip()
                    if old and new_bc != old and rec.product_tmpl_id._wms_in_circulation():
                        raise UserError(
                            _(
                                "The barcode for '%s' is locked: this product has "
                                "stock or movement. Archive it and create a new "
                                "product instead of changing the barcode."
                            )
                            % rec.display_name
                        )
        return super().write(vals)

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
    expected_return_days = fields.Integer(
        related="product_tmpl_id.expected_return_days",
        store=True,
        readonly=False,
        string="Expected return (days)",
    )
    wms_min_life_days = fields.Integer(
        related="product_tmpl_id.wms_min_life_days",
        store=True,
        readonly=False,
        string="Min re-request interval (days)",
    )
