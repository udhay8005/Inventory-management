from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _gather(
        self,
        product_id,
        location_id,
        lot_id=None,
        package_id=None,
        owner_id=None,
        strict=False,
        qty=0,
    ):
        """Force FIFO ordering across all child slots.

        Odoo's stock.quant._gather already honours the location's
        `removal_strategy_id`. By the time this method is hit, Odoo has filtered
        the candidate quants to those under `location_id`. We simply re-sort the
        recordset by `in_date ASC` to guarantee oldest-first across multiple
        slots/compartments/racks under the same parent.
        """
        quants = super()._gather(
            product_id,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
            qty=qty,
        )
        # Stable secondary sort by id avoids non-determinism when in_dates tie.
        return quants.sorted(key=lambda q: (q.in_date or q.create_date, q.id))
