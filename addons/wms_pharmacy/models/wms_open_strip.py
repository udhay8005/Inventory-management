# File: models/wms_open_strip.py
# Module: wms_pharmacy
# Description: Open / partial-strip tracking model (wms.open.strip).
#              Represents the loose tablets remaining in a physically opened
#              (but not yet fully consumed) strip at a specific storage location.
#              One row per (product, lot, location) — enforced by SQL UNIQUE.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: product.product, stock.lot, stock.location, res.users

from odoo import _, fields, models
from odoo.exceptions import UserError


class WmsOpenStrip(models.Model):
    """Open / partial-strip register.

    When the dispense wizard opens a sealed strip to serve a partial dose it
    creates a row here recording how many tablets remain. The next dispense
    from the same (product, lot, location) combination draws from this row
    first (open-package optimisation) before breaking open a fresh strip.

    A strip is physically at one location, so the unique constraint is on
    (product_id, lot_id, location_id). ``tablets_remaining`` is decremented
    as tablets are dispensed; the row is deleted when it reaches zero.

    Usage example (typical call from the dispense wizard)::

        open = env['wms.open.strip'].find_for(product, lot, location)
        if open:
            take = min(open.tablets_remaining, needed)
            open.tablets_remaining -= take
            if open.tablets_remaining <= 0:
                open.unlink()
    """

    _name = "wms.open.strip"
    _description = "Open / partial strip register"
    _rec_name = "product_id"
    _order = "product_id, lot_id"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        index=True,
        ondelete="cascade",
        help="The packaged medicine this open strip belongs to.",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        required=True,
        index=True,
        ondelete="cascade",
        help="The lot / batch this open strip was drawn from.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        index=True,
        ondelete="cascade",
        help="The storage slot where this open strip physically sits.",
    )
    tablets_remaining = fields.Integer(
        string="Tablets remaining",
        required=True,
        help="How many individual tablets are left in this open strip. "
        "Decremented by each dispense; the row is deleted when it reaches 0.",
    )
    opened_on = fields.Datetime(
        string="Opened on",
        default=fields.Datetime.now,
        readonly=True,
        help="Date/time when this strip was physically opened.",
    )
    opened_by = fields.Many2one(
        "res.users",
        string="Opened by",
        default=lambda self: self.env.user,
        readonly=True,
        help="The Odoo user who ran the dispense that broke this strip open.",
    )

    # ------------------------------------------------------------------
    # SQL constraints
    # ------------------------------------------------------------------

    _open_strip_unique = models.Constraint(
        "UNIQUE(product_id, lot_id, location_id)",
        "Only one open strip record is allowed per product / lot / location.",
    )
    _tablets_positive = models.Constraint(
        "CHECK(tablets_remaining > 0)",
        "Tablets remaining must be positive — delete the row when it reaches zero.",
    )

    # ------------------------------------------------------------------
    # Helper API called by the dispense wizard
    # ------------------------------------------------------------------

    def find_for(self, product, lot, location):
        """Return the open strip for (product, lot, location), or empty record.

        :param product: ``product.product`` record.
        :param lot: ``stock.lot`` record.
        :param location: ``stock.location`` record.
        :returns: ``wms.open.strip`` singleton or empty recordset.
        """
        return self.search(
            [
                ("product_id", "=", product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", location.id),
                ("tablets_remaining", ">", 0),
            ],
            limit=1,
        )

    def open_new(self, product, lot, location, tablets_remaining):
        """Create or replace the open strip record for (product, lot, location).

        Called when the dispense wizard breaks open a new sealed strip and
        the leftover tablets need to be registered. If a record for this
        (product, lot, location) somehow already exists it is replaced.

        :param product: ``product.product`` record.
        :param lot: ``stock.lot`` record.
        :param location: ``stock.location`` record.
        :param tablets_remaining: int — how many tablets are left (must be > 0).
        :returns: the created or updated ``wms.open.strip`` record.
        :raises UserError: if tablets_remaining is not positive.
        """
        if tablets_remaining <= 0:
            raise UserError(
                _(
                    "Cannot register an open strip with zero or negative tablets "
                    "(%d). Use find_for() to check first."
                )
                % tablets_remaining
            )
        existing = self.find_for(product, lot, location)
        vals = {
            "product_id": product.id,
            "lot_id": lot.id,
            "location_id": location.id,
            "tablets_remaining": tablets_remaining,
            "opened_on": fields.Datetime.now(),
            "opened_by": self.env.user.id,
        }
        if existing:
            existing.write({"tablets_remaining": tablets_remaining})
            return existing
        return self.create(vals)
