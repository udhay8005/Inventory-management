"""Wave 2 #12 — Cold Chain Workflow (vaccines).

Cold-chain handling for temperature-sensitive stock. Three pieces:

  (a) product.template gets a cold-chain flag and a min/max storage temperature
      band. Vaccine-kind products default to cold-chain True, 2-8 C (the WHO
      vaccine fridge range).

  (b) wms.cold.chain.reading records a single temperature observation against a
      lot: temperature, when it was taken, who took it, whether it falls inside
      the product's band (computed), and a free-text note. Store Keepers can
      record readings; Managers have full control.

  (c) When a keeper records an OUT-OF-RANGE reading for a cold-chain product, the
      lot is AUTO put on QC hold by creating a wms.lot.quarantine over that lot.
      That quarantine create freezes the lot (wms_lot_state='quarantine') and
      cancels its open reservations (V20-014), so the cold-broken batch is pulled
      from issuing until QC decides. Because the quarantine create is
      manager-gated, the auto-hold runs as the WMS admin (a seeded manager) so a
      keeper recording a reading can still trigger the protective hold.

Additive over Wave 1: a new model + an _inherit of product.template that only
ADDS fields. No Wave 1 file is edited.
"""

from odoo import api, fields, models

# WHO vaccine cold-chain fridge band, used as the default temperature window for
# cold-chain products (and the seed default for the vaccine kind).
_VACCINE_TEMP_MIN = 2.0
_VACCINE_TEMP_MAX = 8.0


class ProductTemplate(models.Model):
    _inherit = "product.template"

    wms_cold_chain = fields.Boolean(
        string="Cold chain",
        compute="_compute_wms_cold_chain",
        store=True,
        readonly=False,  # admin can override the kind-derived default
        help="When ticked, this product must be kept within a temperature band "
        "(below) and cold-chain readings can be logged against its lots. "
        "Defaults to True for the Vaccine kind; the Admin can override per "
        "product.",
    )
    wms_temp_min = fields.Float(
        string="Min temperature (C)",
        default=_VACCINE_TEMP_MIN,
        help="Lowest acceptable storage temperature in degrees Celsius. A "
        "reading below this is out of range and quarantines the lot.",
    )
    wms_temp_max = fields.Float(
        string="Max temperature (C)",
        default=_VACCINE_TEMP_MAX,
        help="Highest acceptable storage temperature in degrees Celsius. A "
        "reading above this is out of range and quarantines the lot.",
    )

    @api.depends("wms_product_kind")
    def _compute_wms_cold_chain(self):
        """Seed the cold-chain flag from kind: vaccines are cold-chain by
        default, everything else is not. store=True / readonly=False means this
        only seeds — an admin tick/untick afterwards persists (mirrors how
        wms_is_returnable seeds from kind in the v19 product_template)."""
        for tmpl in self:
            tmpl.wms_cold_chain = tmpl.wms_product_kind == "vaccine"


class ProductProduct(models.Model):
    """Surface the cold-chain fields on the variant model so the reading model
    and other addons can read product.wms_cold_chain / temp band directly."""

    _inherit = "product.product"

    wms_cold_chain = fields.Boolean(
        related="product_tmpl_id.wms_cold_chain",
        store=True,
        readonly=False,
        string="Cold chain",
    )
    wms_temp_min = fields.Float(
        related="product_tmpl_id.wms_temp_min",
        store=True,
        readonly=False,
        string="Min temperature (C)",
    )
    wms_temp_max = fields.Float(
        related="product_tmpl_id.wms_temp_max",
        store=True,
        readonly=False,
        string="Max temperature (C)",
    )


class WmsColdChainReading(models.Model):
    _name = "wms.cold.chain.reading"
    _description = "Cold chain temperature reading"
    _order = "reading_datetime desc, id desc"
    _rec_name = "lot_id"

    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot / batch",
        required=True,
        ondelete="cascade",
        index=True,
        help="The lot this temperature reading was taken against.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        compute="_compute_product_id",
        store=True,
        index=True,
        help="Product of the lot (derived). Used to look up the temperature band.",
    )
    temperature = fields.Float(
        string="Temperature (C)",
        required=True,
        help="The measured storage temperature in degrees Celsius.",
    )
    reading_datetime = fields.Datetime(
        string="Reading time",
        required=True,
        default=fields.Datetime.now,
        help="When the temperature was observed.",
    )
    recorded_by = fields.Many2one(
        "res.users",
        string="Recorded by",
        required=True,
        default=lambda self: self.env.user,
        help="The keeper / manager who logged this reading.",
    )
    in_range = fields.Boolean(
        string="In range",
        compute="_compute_in_range",
        store=True,
        help="True when the temperature sits within the product's min/max band. "
        "An out-of-range reading on a cold-chain product quarantines the lot.",
    )
    quarantine_id = fields.Many2one(
        "wms.lot.quarantine",
        string="QC hold raised",
        readonly=True,
        help="The QC hold automatically raised by this out-of-range reading "
        "(blank when the reading was in range).",
    )
    note = fields.Text(
        string="Note",
        help="Optional free-text observation (fridge id, excursion duration, "
        "corrective action, etc.).",
    )

    @api.depends("lot_id")
    def _compute_product_id(self):
        for rec in self:
            rec.product_id = rec.lot_id.product_id

    @api.depends("temperature", "lot_id", "product_id.wms_temp_min", "product_id.wms_temp_max")
    def _compute_in_range(self):
        for rec in self:
            product = rec.product_id
            if not product:
                rec.in_range = True
                continue
            rec.in_range = product.wms_temp_min <= rec.temperature <= product.wms_temp_max

    @api.model_create_multi
    def create(self, vals_list):
        readings = super().create(vals_list)
        readings._wms_handle_excursions()
        return readings

    def _wms_handle_excursions(self):
        """For each freshly recorded reading that is OUT of range on a cold-chain
        product, AUTO put the lot on QC hold by creating a wms.lot.quarantine
        over it. The quarantine create (V20-014) freezes the lot
        (wms_lot_state='quarantine') and cancels its open reservations.

        The quarantine create is manager-gated, but a Store Keeper is allowed to
        record readings — so the protective hold is created as a WMS manager (the
        seeded admin user) when the recorder is not themselves a manager. Already
        held / recalled / destroyed lots are skipped (no point double-holding)."""
        Quarantine = self.env["wms.lot.quarantine"]
        manager_group = "wms_location.group_wms_manager"
        for rec in self:
            if rec.in_range:
                continue
            product = rec.product_id
            lot = rec.lot_id
            if not (product and product.wms_cold_chain and lot):
                continue
            if lot.wms_lot_state != "available":
                # Already frozen by an earlier excursion / recall — nothing to do.
                continue
            quarantine_env = Quarantine
            if not self.env.user.has_group(manager_group):
                admin = self.env.ref("base.user_admin", raise_if_not_found=False)
                if admin and admin.has_group(manager_group):
                    quarantine_env = Quarantine.with_user(admin.id)
            quarantine = quarantine_env.create(
                {
                    "reason": (
                        "Cold-chain excursion: %.1f C recorded on %s "
                        "(allowed band %.1f-%.1f C)."
                        % (
                            rec.temperature,
                            lot.name or "",
                            product.wms_temp_min,
                            product.wms_temp_max,
                        )
                    ),
                    "lot_ids": [(6, 0, lot.ids)],
                }
            )
            # Stamp the link back on the reading (sudo: the keeper may not have
            # read access on the quarantine model, and the create already ran
            # under the elevated env above).
            rec.sudo().quarantine_id = quarantine.id
