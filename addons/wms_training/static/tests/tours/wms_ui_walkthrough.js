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

/**
 * Click a navbar section, then one of its menu entries, and WAIT FOR THAT
 * SCREEN BY NAME.
 *
 * `title` is not optional decoration — it is the correctness of the tour. A
 * generic "any view is rendered" check is satisfied by the screen that is
 * STILL DISPLAYED while the new action loads, so a tour can march on against
 * the wrong screen: seen here, an asset-register run clicked "New" on the
 * leftover Slots list and spent the rest of the tour on a Slots form. Waiting
 * for the new action's own breadcrumb removes that whole class of false pass.
 *
 * Titles are the action names as stored on each menu's ir.actions.act_window.
 */
function openMenu(sectionXmlid, itemXmlid, title) {
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
        {
            content: `the "${title}" screen is the one on display`,
            trigger: `.o_breadcrumb:contains(${title})`,
        },
    ];
}

registry.category("web_tour.tours").add("wms_ui_navigation", {
    url: "/odoo",
    steps: () => [
        ...OPEN_WMS_APP,

        // ---- Operations: the daily screens ----------------------------
        ...openMenu("wms_location.menu_wms_operations", "wms_location.menu_wms_slots", "Slots"),
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_barcode.menu_wms_products",
            "Products",
        ),
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_repair_damage.menu_wms_damage",
            "Damages",
        ),
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_repair_damage.menu_wms_repair",
            "Repair orders",
        ),
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_barcode.menu_wms_fuel_log",
            "Fuel Log",
        ),
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_reports.menu_wms_audit",
            "Inventory audits",
        ),
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_barcode.menu_wms_issue_approval",
            "Issue Approvals",
        ),

        // ---- Configuration: the storage tree ---------------------------
        ...openMenu("wms_location.menu_wms_config", "wms_location.menu_wms_zones", "Zones"),
        ...openMenu("wms_location.menu_wms_config", "wms_location.menu_wms_racks", "Racks"),

        // ---- Intelligence + Forecast ----------------------------------
        ...openMenu(
            "wms_analytics.menu_wms_analytics_root",
            "wms_analytics.menu_wms_stock_health",
            "Stock Health",
        ),
        ...openMenu(
            "wms_ai_forecast.menu_wms_forecast",
            "wms_ai_forecast.menu_wms_forecast_list",
            "Forecasts",
        ),
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
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_barcode.menu_wms_products",
            "Products",
        ),
        {
            content: "New product",
            trigger: ".o_list_button_add, .o-kanban-button-new",
            run: "click",
        },
        { content: "form opened", trigger: ".o_form_view" },
        {
            content: "type the product name",
            trigger:
                ".o_form_view .o_field_widget[name='name'] input, .o_form_view textarea#name_0",
            run: "edit TOUR Bolt M8",
        },
        {
            content: "open the WMS Classification tab",
            trigger: ".o_notebook .nav-link:contains(WMS Classification)",
            run: "click",
        },
        {
            // Odoo 19 renders a Selection field as a SelectMenu autocomplete
            // (an <input>, NOT a native <select>). Just OPEN it — do not type a
            // filter. Typing re-renders the option list on every keystroke, and
            // a matched option can be swapped out between match and click, so
            // the click lands on a detached node and silently selects nothing
            // (observed as an intermittent failure here). Clicking the closed
            // input shows the full list, which is stable.
            content: "open the WMS Kind dropdown",
            trigger: ".o_field_widget[name='wms_product_kind'] input.o_select_menu_input",
            run: "click",
        },
        {
            content: "choose Spare Part (SPARE)",
            trigger:
                ".o_select_menu_item:contains(Spare Part), .o-dropdown-item:contains(Spare Part)",
            run: "click",
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

/**
 * Assets in service — the register for fitted fans / pumps / extinguishers.
 * Creates one through the real form and records a service, so the whole
 * feature is proven reachable and usable by a human, not just by the ORM.
 */
registry.category("web_tour.tours").add("wms_ui_asset_register", {
    url: "/odoo",
    steps: () => [
        ...OPEN_WMS_APP,
        ...openMenu(
            "wms_location.menu_wms_operations",
            "wms_repair_damage.menu_wms_asset",
            "Assets in service",
        ),
        {
            content: "register a new asset",
            trigger: ".o_list_button_add, .o-kanban-button-new",
            run: "click",
        },
        { content: "asset form", trigger: ".o_form_view" },
        {
            // "TOUR Asset Fan" and "TOUR Asset Shed" are created by the test
            // before the browser starts, so this tour is deterministic on a
            // freshly installed database AND on a copy of the trust's live
            // data. Matching the fixture by name also side-steps two traps
            // seen here: the dropdown briefly holds a "Loading…" placeholder
            // (a bare selector clicks THAT and selects nothing), and for a
            // moment it still shows the previous, unfiltered result list.
            content: "name the item being registered",
            trigger: ".o_field_widget[name='product_id'] input",
            run: "edit TOUR Asset Fan",
        },
        {
            content: "pick that item from the dropdown",
            trigger:
                ".o_field_widget[name='product_id'] .o-autocomplete--dropdown-item a:contains(TOUR Asset Fan)",
            run: "click",
        },
        {
            content: "tag number",
            trigger: ".o_field_widget[name='serial_no'] input",
            run: "edit TOUR-EXT-01",
        },
        {
            content: "where it is installed",
            trigger: ".o_field_widget[name='location_id'] input",
            run: "edit TOUR Asset Shed",
        },
        {
            content: "choose that shed",
            trigger:
                ".o_field_widget[name='location_id'] .o-autocomplete--dropdown-item a:contains(TOUR Asset Shed)",
            run: "click",
        },
        {
            content: "yearly refill interval",
            trigger: ".o_field_widget[name='service_interval_days'] input",
            run: "edit 365",
        },
        { content: "save the asset", trigger: ".o_form_button_save", run: "click" },
        {
            // NOT the breadcrumb: wms.asset overrides _compute_display_name, so
            // the breadcrumb reads "[SKU] product [TAG] @ shed". The stored
            // sequence lives in the title field, and its presence proves the
            // record saved (a missing required Item would have blocked it).
            content: "saved — it now carries an ASSET/ reference",
            trigger: ".o_form_view .o_field_widget[name='name']:contains(ASSET/)",
        },
        {
            content: "the breadcrumb identifies it by tag and shed",
            trigger: ".o_breadcrumb:contains(TOUR-EXT-01)",
        },
        {
            content: "record a service",
            trigger: "button[name='action_service_done']",
            run: "click",
        },
        {
            // The effect of the button, not just a filled box: action_service_done
            // stamps the date AND posts to the record's history. next_service_date
            // already showed a date before the click (it computes off the install
            // date), so asserting on it would prove nothing.
            content: "the service is logged in the asset's history",
            trigger: ".o-mail-Message:contains(Serviced on)",
        },
    ],
});

/**
 * Expired-stock sweep — the Manager's one-click shelf-safety check.
 * Either it quarantines expired batches (a form opens) or it reports the
 * shelves are clean (a notification). Both are a pass; a crash is not.
 */
registry.category("web_tour.tours").add("wms_ui_sweep_expired", {
    url: "/odoo",
    steps: () => [
        ...OPEN_WMS_APP,
        {
            content: "open the Operations section",
            trigger: 'button[data-menu-xmlid="wms_location.menu_wms_operations"]',
            run: "click",
        },
        {
            // A server action, not an act_window: it either opens a
            // quarantine record or raises a notification, so there is no
            // fixed breadcrumb to wait for.
            content: "click Sweep expired stock",
            trigger: '.dropdown-item[data-menu-xmlid="wms_perishable.menu_wms_sweep_expired"]',
            run: "click",
        },
        {
            content: "either a quarantine record opened, or 'nothing expired'",
            trigger:
                ".o_form_view .o_field_widget[name='lot_ids'], .o_notification, .o_notification_manager .o_notification",
        },
    ],
});
