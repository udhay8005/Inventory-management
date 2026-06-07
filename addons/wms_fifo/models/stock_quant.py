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
        # Note: the Damage/Repair-Out exclusion lives in the higher-level
        # planner (find_oldest_quants_for_product), NOT here. _gather is also
        # called by the legitimate internal-move flows in wms_repair_damage
        # (action_start_repair sources FROM the Damage location, action_finish
        # sources FROM Repair-Out), and a blanket exclusion here would break
        # those by leaving the moves unassigned.
        return quants._wms_sorted_for_removal()
