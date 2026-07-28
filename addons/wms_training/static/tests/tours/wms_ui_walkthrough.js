/**
 * Real-browser UI walkthrough tours (UAT R3).
 *
 * These drive a headless Chrome through the ACTUAL Odoo web client — opening
 * the WMS app from the apps grid, clicking menu entries, and reading what
 * renders — which is the automated equivalent of an operator walking the
 * screens one by one. They complement the engine tests: those prove the
 * business rules, these prove a human can reach and use them.
 *
 * Selectors are taken from the rendered DOM (Odoo 19):
 *   apps grid button  .o_navbar_apps_menu button
 *   app entry         .o_app[data-menu-xmlid="…"]
 *   navbar section    button[data-menu-xmlid="…"]   (class o-dropdown)
 *   dropdown entry    .dropdown-item[data-menu-xmlid="…"]
 */
import { registry } from "@web/core/registry";

/** Open the WMS app the way an operator does: apps grid → WMS. */
const OPEN_WMS_APP = [
    {
        content: "open the apps grid",
        trigger: ".o_navbar_apps_menu button",
        run: "click",
    },
    {
        content: "open the WMS app",
        trigger: '.o_app[data-menu-xmlid="wms_location.menu_wms_root"]',
        run: "click",
    },
    { content: "WMS app is loaded", trigger: ".o_main_navbar" },
];

/** Click a navbar section, then one of its menu entries. */
function openMenu(sectionXmlid, itemXmlid) {
    return [
        {
            content: `open section ${sectionXmlid}`,
            trigger: `button[data-menu-xmlid="${sectionXmlid}"]`,
            run: "click",
        },
        {
            content: `click menu ${itemXmlid}`,
            trigger: `.dropdown-item[data-menu-xmlid="${itemXmlid}"]`,
            run: "click",
        },
    ];
}

/** A screen counts as "rendered" when any Odoo view root is on the page. */
const SCREEN_READY =
    ".o_list_view, .o_form_view, .o_kanban_view, .o_graph_view, .o_pivot_view, .o_content";

registry.category("web_tour.tours").add("wms_ui_navigation", {
    url: "/odoo",
    steps: () => [
        ...OPEN_WMS_APP,

        // ---- Operations: the daily screens ----------------------------
        ...openMenu("wms_location.menu_wms_operations", "wms_location.menu_wms_slots"),
        { content: "Slots screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_operations", "wms_barcode.menu_wms_products"),
        { content: "Products screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_operations", "wms_repair_damage.menu_wms_damage"),
        { content: "Damages screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_operations", "wms_repair_damage.menu_wms_repair"),
        { content: "Repair orders screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_operations", "wms_barcode.menu_wms_fuel_log"),
        { content: "Fuel Log screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_operations", "wms_reports.menu_wms_audit"),
        { content: "Inventory audits screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_operations", "wms_barcode.menu_wms_issue_approval"),
        { content: "Approvals screen", trigger: SCREEN_READY },

        // ---- Configuration: the storage tree ---------------------------
        ...openMenu("wms_location.menu_wms_config", "wms_location.menu_wms_zones"),
        { content: "Zones screen", trigger: SCREEN_READY },

        ...openMenu("wms_location.menu_wms_config", "wms_location.menu_wms_racks"),
        { content: "Racks screen", trigger: SCREEN_READY },

        // ---- Intelligence + Forecast ----------------------------------
        ...openMenu("wms_analytics.menu_wms_analytics_root", "wms_analytics.menu_wms_stock_health"),
        { content: "Stock Health screen", trigger: SCREEN_READY },

        ...openMenu("wms_ai_forecast.menu_wms_forecast", "wms_ai_forecast.menu_wms_forecast_list"),
        { content: "Forecasts screen", trigger: SCREEN_READY },
    ],
});

/**
 * The product-creation flow that failed in manual UAT: picking a WMS Kind
 * must tick Track Inventory and mint the SKU + barcode on save.
 */
registry.category("web_tour.tours").add("wms_ui_product_create", {
    url: "/odoo",
    steps: () => [
        ...OPEN_WMS_APP,
        ...openMenu("wms_location.menu_wms_operations", "wms_barcode.menu_wms_products"),
        { content: "Products list", trigger: ".o_list_view" },
        {
            content: "New product",
            trigger: ".o_list_button_add, .o-kanban-button-new",
            run: "click",
        },
        { content: "form opened", trigger: ".o_form_view" },
        {
            content: "type the product name",
            trigger: ".o_form_view .o_field_widget[name='name'] input, .o_form_view textarea#name_0",
            run: "edit TOUR Bolt M8",
        },
        {
            content: "open the WMS Classification tab",
            trigger: ".o_notebook .nav-link:contains(WMS Classification)",
            run: "click",
        },
        {
            // Odoo 19 renders a Selection field as a SelectMenu autocomplete
            // (an <input>, NOT a native <select>) — type to filter, then pick.
            content: "open the WMS Kind dropdown and filter",
            trigger: ".o_field_widget[name='wms_product_kind'] input.o_select_menu_input",
            run: "edit Spare Part",
        },
        {
            content: "choose Spare Part (SPARE)",
            trigger:
                ".o_select_menu_item:contains(Spare Part), .o-dropdown-item:contains(Spare Part)",
            run: "click",
        },
        {
            content: "the kind is now set",
            trigger:
                ".o_field_widget[name='wms_product_kind'] input.o_select_menu_input:value(Spare Part)",
        },
        {
            content: "save the product",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            // The save signal AND the business assertion in one: once the
            // record is stored, the breadcrumb reads "[SPARE-00001] TOUR Bolt
            // M8" — i.e. choosing a WMS Kind minted the SKU, which is exactly
            // the flow that failed in manual UAT. (Odoo 19 has no
            // ".o_form_saved" class, so the breadcrumb is the honest signal.)
            content: "saved, and the SKU was generated from the Kind",
            trigger: ".o_breadcrumb:contains(SPARE-)",
        },
    ],
});
