"""Wave 2 #3 — AI Forecast: weekly demand + overstock/understock risk.

The Wave 1 AI engine (wms_ai_forecast) already produces per-product daily and
monthly demand, a reorder suggestion, on-hand, lead time, safety stock and a
velocity class. Three operationally useful signals were implicit in that data
but never surfaced: a *weekly* demand figure (the cadence the gaushala keepers
actually plan around) and two risk flags answering "am I sitting on too much?"
(overstock) and "will I run out before the next delivery lands?" (understock).

This module _inherit-extends wms.forecast to add those three stored computed
fields. They are stored + @api.depends on the engine's own output fields so they
recompute automatically whenever the AI engine rewrites a forecast row, and so
they can be searched, filtered and grouped in the existing forecast views.
"""

from odoo import api, fields, models


class WmsForecast(models.Model):
    _inherit = "wms.forecast"

    weekly_avg = fields.Float(
        string="Weekly avg",
        compute="_compute_wms_weekly_avg",
        store=True,
        readonly=True,
        help="Average weekly consumption (daily average x 7) — the cadence keepers "
        "plan replenishment around.",
    )
    overstock_risk = fields.Selection(
        [
            ("none", "None"),
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
        ],
        string="Overstock risk",
        compute="_compute_wms_demand_risk",
        store=True,
        readonly=True,
        default="none",
        help="Capital tied up in stock that demand will not consume over the "
        "forecast horizon. HIGH = dead stock still on hand, or many months of "
        "cover. Driven by months-of-cover vs the horizon and velocity class.",
    )
    understock_risk = fields.Selection(
        [
            ("none", "None"),
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
        ],
        string="Understock risk",
        compute="_compute_wms_demand_risk",
        store=True,
        readonly=True,
        default="none",
        help="Risk of running out before the next delivery lands. HIGH = on hand "
        "already below safety stock, or below the demand expected over the lead "
        "time. Driven by on-hand vs safety stock / lead-time demand / reorder_qty.",
    )

    @api.depends("daily_avg")
    def _compute_wms_weekly_avg(self):
        for rec in self:
            rec.weekly_avg = (rec.daily_avg or 0.0) * 7.0

    @api.depends(
        "on_hand",
        "daily_avg",
        "predicted_qty",
        "reorder_qty",
        "safety_stock",
        "lead_time_days",
        "horizon_days",
        "velocity_class",
    )
    def _compute_wms_demand_risk(self):
        for rec in self:
            on_hand = rec.on_hand or 0.0
            daily = rec.daily_avg or 0.0
            safety = rec.safety_stock or 0.0
            lead = rec.lead_time_days or 0
            horizon = rec.horizon_days or 30

            # --- Overstock: do we hold far more than demand will consume? ---
            # Demand expected over the planning horizon, from daily velocity.
            horizon_demand = daily * horizon
            if rec.velocity_class == "dead" and on_hand > 0:
                # Nothing is moving but stock is sitting there → worst case.
                overstock = "high"
            elif daily <= 0:
                # No measured consumption at all, but holding stock.
                overstock = "medium" if on_hand > 0 else "none"
            else:
                # Months of cover = how long on-hand lasts at the daily rate.
                months_cover = on_hand / (daily * 30.0)
                if months_cover >= 6.0 or on_hand >= 4.0 * horizon_demand:
                    overstock = "high"
                elif months_cover >= 3.0 or on_hand >= 2.0 * horizon_demand:
                    overstock = "medium"
                elif months_cover >= 2.0:
                    overstock = "low"
                else:
                    overstock = "none"
            rec.overstock_risk = overstock

            # --- Understock: will we dip below the reorder point too soon? ---
            lead_demand = daily * lead
            if on_hand <= 0 and (daily > 0 or safety > 0 or (rec.reorder_qty or 0.0) > 0):
                understock = "high"
            elif safety > 0 and on_hand < safety:
                understock = "high"
            elif lead_demand > 0 and on_hand < lead_demand:
                # Won't survive the lead time at current velocity.
                understock = "high"
            elif (rec.reorder_qty or 0.0) > 0:
                # Engine is already suggesting a reorder, but we're not below
                # safety/lead-time yet → an early warning.
                understock = "medium"
            elif lead_demand > 0 and on_hand < 1.5 * lead_demand:
                understock = "low"
            else:
                understock = "none"
            rec.understock_risk = understock
