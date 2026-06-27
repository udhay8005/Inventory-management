{
    "name": "WMS — Warehouse Intelligence (Wave 2)",
    # Wave 2 analytics layer. Odoo 19.0 series; "v20" is the project major.
    "version": "19.0.2.0.0",
    "summary": (
        "Wave 2 Warehouse Intelligence: expiry-risk engine, supplier/disposal "
        "analytics, stock-health score, advanced ledgers, recall dashboard, lot "
        "audit score, cold chain, bulk ops, KPI dashboards — additive over Wave 1."
    ),
    # Additive analytics module. Reads the Wave 1 data (lots, quants, forecast,
    # damage, recall, quarantine) and OWNS the new reporting models/views. It
    # _inherit-extends Wave 1 models only to add new fields (audit score, cold
    # chain, supplier links) — it never edits Wave 1 files.
    "depends": [
        "wms_perishable",  # lots, FEFO, recall, quarantine, expiry, effective-expiry
        "wms_ai_forecast",  # consumption velocity (wms.forecast) for the risk engine
    ],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "data/wms_occupancy_snapshot_cron.xml",
        "views/menus.xml",
        "views/wms_intelligence_dashboard.xml",
        "views/wms_heatmap.xml",
        "views/wms_lot_expiry_risk_views.xml",
        "views/stock_lot_views.xml",
        "views/wms_supplier_scorecard_views.xml",
        "views/wms_disposal_report_views.xml",
        "views/wms_stock_health_views.xml",
        "views/wms_recall_dashboard_views.xml",
        "views/wms_ledgers_views.xml",
        "views/wms_usage_reports_views.xml",
        "views/wms_lot_traceability_views.xml",
        "views/wms_bulk_ops_views.xml",
        "views/wms_cold_chain_views.xml",
        "views/wms_forecast_risk_views.xml",
        "views/wms_occupancy_snapshot_views.xml",
        "views/wms_fefo_compliance_views.xml",
        "views/wms_cycle_count_priority_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
