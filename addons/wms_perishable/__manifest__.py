{
    "name": "WMS — Universal Perishable Engine (Wave 1)",
    # v20 line, first version. Stays on the Odoo 19.0 series (this runs on
    # Odoo 19 CE — "v20" is the PROJECT major, not the Odoo major).
    "version": "19.0.1.0.0",
    "summary": (
        "Per-lot expiry + FEFO + quarantine/recall for the gaushala WMS. "
        "SCAFFOLD — structure only; no features implemented yet (Wave 1 lands here)."
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
    "data": [
        # Wave 1 data/security/views land here as the tickets in
        # docs/v20-perishable-engine/04-implementation-plan-and-backlog.md are built:
        #   "security/wms_perishable_security.xml",
        #   "security/ir.model.access.csv",
        #   "views/...","data/...",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
