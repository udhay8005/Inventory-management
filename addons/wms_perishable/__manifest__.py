{
    "name": "WMS — Universal Perishable Engine (Wave 1)",
    # v20 line, first version. Stays on the Odoo 19.0 series (this runs on
    # Odoo 19 CE — "v20" is the PROJECT major, not the Odoo major).
    "version": "19.0.1.13.0",
    "summary": (
        "Per-lot expiry + FEFO + quarantine/recall for the gaushala WMS. Wave 1 in progress "
        "(kinds, lot, receipt, FEFO, issue, blocks, undo, recall, quarantine, per-lot expiry report)."
    ),
    # Additive module: it _inherit-extends the FROZEN v19 addons (FEFO override
    # on the single chokepoint stock.quant._wms_sorted_for_removal, receipt
    # lot-capture, expired-issue block via the existing approval gate) and OWNS
    # the new models (lot lifecycle, wms.lot.recall, quarantine, settings,
    # per-lot reports, dashboard). The v19 addons are NOT edited. See the frozen
    # spec in docs/v20-perishable-engine/.
    "depends": [
        "wms_location",  # the single FEFO chokepoint (_wms_sorted_for_removal)
        "wms_fifo",  # _gather override (MRO picks up the v20 sort)
        "wms_barcode",  # scan wizards (lot capture), lot barcode via resolve()
        "wms_repair_damage",  # quarantine reuses the wms_is_* picker-exclusion pattern
        "wms_reports",  # per-lot reports re-key the expiry-alert view
        "product_expiry",  # Odoo standard: tracking='lot' + use_expiration_date
    ],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    # V20-008 — partial index idx_quant_fefo for fast FEFO removal scans.
    "post_init_hook": "post_init_hook",
    "data": [
        # V20-013 — ACL for the recall model (load before its views).
        "security/ir.model.access.csv",
        # V20-002 — SKU sequences for the new perishable kinds.
        "data/wms_perishable_sku_sequences.xml",
        # V20-005 — auto-lot naming sequence.
        "data/wms_perishable_lot_sequence.xml",
        # V20-013 — recall notice-number sequence.
        "data/wms_perishable_recall_sequence.xml",
        # V20-014 — QC hold number sequence.
        "data/wms_perishable_quarantine_sequence.xml",
        # V20-004 — batch/expiry/supplier columns on the receipt line.
        "views/scan_receipt_views.xml",
        # V20-010 — batch + resulting-balance columns on the issue plan.
        "views/scan_issue_views.xml",
        # V20-013 — lot recall form/list/menu.
        "views/wms_lot_recall_views.xml",
        # V20-014 — lot quarantine form/list/menu.
        "views/wms_lot_quarantine_views.xml",
        # V20-015 — per-lot expiry report list/search/menu.
        "views/wms_lot_expiry_alert_views.xml",
        # Further Wave 1 data/security/views land here as tickets land
        # (see docs/v20-perishable-engine/04-implementation-plan-and-backlog.md).
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
