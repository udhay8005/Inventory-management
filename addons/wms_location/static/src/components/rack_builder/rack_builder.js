/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * WmsRackBuilder – a Text-field widget that renders an interactive rack
 * grid. Click cells to select. Merge / split / change slot count via the
 * side panel. Whatever the user does is serialised back into the field
 * as JSON; the server-side wms.rack.generator wizard reads that JSON to
 * create the actual stock.location records.
 *
 * JSON schema (kept stable so the Python side can parse it without changes):
 *   {
 *     "shelves": 6,
 *     "columns": 3,
 *     "compartments": [
 *       {
 *         "shelf_top": 1, "shelf_bottom": 1,
 *         "column_index": 1, "slot_count": 1,
 *         "label": null
 *       },
 *       ...
 *     ]
 *   }
 */
export class WmsRackBuilder extends Component {
    static template = "wms_location.RackBuilder";
    static props = { ...standardFieldProps };

    setup() {
        const initial = this._parseInitial(this.props.record.data[this.props.name]);
        this.state = useState({
            shelves: initial.shelves,
            columns: initial.columns,
            compartments: initial.compartments,
            selectedId: null,
        });
        // Persist the initial JSON in case the wizard was opened fresh —
        // ensures action_generate() always has something to read.
        this._commit();
    }

    // ------------------------------------------------------------- helpers
    _parseInitial(rawJson) {
        if (rawJson) {
            try {
                const parsed = JSON.parse(rawJson);
                if (parsed.shelves && parsed.columns && Array.isArray(parsed.compartments)) {
                    // Ensure each compartment has an id for OWL key tracking
                    parsed.compartments.forEach((c, idx) => {
                        if (!c.id) c.id = idx + 1;
                    });
                    return parsed;
                }
            } catch (e) {
                // fall through to default
            }
        }
        return this._defaultGrid(6, 3);
    }

    _defaultGrid(shelves, columns) {
        const compartments = [];
        let id = 1;
        for (let s = 1; s <= shelves; s++) {
            for (let c = 1; c <= columns; c++) {
                compartments.push({
                    id: id++,
                    shelf_top: s,
                    shelf_bottom: s,
                    column_index: c,
                    slot_count: 1,
                    label: null,
                });
            }
        }
        return { shelves, columns, compartments };
    }

    async _commit() {
        const payload = {
            shelves: this.state.shelves,
            columns: this.state.columns,
            compartments: this.state.compartments.map((c) => ({
                shelf_top: c.shelf_top,
                shelf_bottom: c.shelf_bottom,
                column_index: c.column_index,
                slot_count: c.slot_count,
                label: c.label || null,
            })),
        };
        await this.props.record.update({
            [this.props.name]: JSON.stringify(payload, null, 2),
        });
    }

    // -------------------------------------------------- shelf/column resize
    async onShelvesChange(ev) {
        const n = Math.max(1, Math.min(30, parseInt(ev.target.value || "0", 10) || 1));
        const grid = this._defaultGrid(n, this.state.columns);
        this.state.shelves = grid.shelves;
        this.state.columns = grid.columns;
        this.state.compartments = grid.compartments;
        this.state.selectedId = null;
        await this._commit();
    }

    async onColumnsChange(ev) {
        const n = Math.max(1, Math.min(20, parseInt(ev.target.value || "0", 10) || 1));
        const grid = this._defaultGrid(this.state.shelves, n);
        this.state.shelves = grid.shelves;
        this.state.columns = grid.columns;
        this.state.compartments = grid.compartments;
        this.state.selectedId = null;
        await this._commit();
    }

    async resetGrid() {
        const grid = this._defaultGrid(this.state.shelves, this.state.columns);
        this.state.compartments = grid.compartments;
        this.state.selectedId = null;
        await this._commit();
    }

    // ------------------------------------------------------ selection / ops
    selectCompartment(id) {
        this.state.selectedId = id;
    }

    get selectedCompartment() {
        return this.state.compartments.find((c) => c.id === this.state.selectedId);
    }

    _findAbove(comp) {
        return this.state.compartments.find(
            (x) =>
                x.column_index === comp.column_index &&
                x.shelf_bottom === comp.shelf_top - 1,
        );
    }

    _findBelow(comp) {
        return this.state.compartments.find(
            (x) =>
                x.column_index === comp.column_index &&
                x.shelf_top === comp.shelf_bottom + 1,
        );
    }

    canMergeUp() {
        const c = this.selectedCompartment;
        return !!(c && c.shelf_top > 1 && this._findAbove(c));
    }

    canMergeDown() {
        const c = this.selectedCompartment;
        return !!(c && c.shelf_bottom < this.state.shelves && this._findBelow(c));
    }

    canSplit() {
        const c = this.selectedCompartment;
        return !!(c && c.shelf_bottom > c.shelf_top);
    }

    async mergeUp() {
        const c = this.selectedCompartment;
        if (!this.canMergeUp()) return;
        const above = this._findAbove(c);
        c.shelf_top = above.shelf_top;
        c.slot_count = Math.max(c.slot_count, above.slot_count);
        this.state.compartments = this.state.compartments.filter((x) => x.id !== above.id);
        await this._commit();
    }

    async mergeDown() {
        const c = this.selectedCompartment;
        if (!this.canMergeDown()) return;
        const below = this._findBelow(c);
        c.shelf_bottom = below.shelf_bottom;
        c.slot_count = Math.max(c.slot_count, below.slot_count);
        this.state.compartments = this.state.compartments.filter((x) => x.id !== below.id);
        await this._commit();
    }

    async split() {
        const c = this.selectedCompartment;
        if (!this.canSplit()) return;
        const oldTop = c.shelf_top;
        const oldBottom = c.shelf_bottom;
        const col = c.column_index;
        c.shelf_bottom = oldTop; // shrink the original to its top row
        let nextId = Math.max(...this.state.compartments.map((x) => x.id)) + 1;
        for (let row = oldTop + 1; row <= oldBottom; row++) {
            this.state.compartments.push({
                id: nextId++,
                shelf_top: row,
                shelf_bottom: row,
                column_index: col,
                slot_count: 1,
                label: null,
            });
        }
        await this._commit();
    }

    async incrementSlots() {
        const c = this.selectedCompartment;
        if (!c) return;
        c.slot_count++;
        await this._commit();
    }

    async decrementSlots() {
        const c = this.selectedCompartment;
        if (!c || c.slot_count <= 1) return;
        c.slot_count--;
        await this._commit();
    }

    // ------------------------------------------------------------- display
    cellLabel(c) {
        const pad = (n) => String(n).padStart(2, "0");
        const shelfPart =
            c.shelf_top === c.shelf_bottom
                ? "SH" + pad(c.shelf_top)
                : "SH" + pad(c.shelf_top) + "-" + pad(c.shelf_bottom);
        return shelfPart + " C" + pad(c.column_index);
    }

    cellStyle(c) {
        return (
            "grid-row: " +
            c.shelf_top +
            " / " +
            (c.shelf_bottom + 1) +
            "; grid-column: " +
            c.column_index +
            ";"
        );
    }

    gridStyle() {
        return (
            "grid-template-rows: repeat(" +
            this.state.shelves +
            ", 60px); grid-template-columns: repeat(" +
            this.state.columns +
            ", minmax(80px, 1fr));"
        );
    }
}

registry.category("fields").add("wms_rack_builder", {
    component: WmsRackBuilder,
    supportedTypes: ["text"],
});
