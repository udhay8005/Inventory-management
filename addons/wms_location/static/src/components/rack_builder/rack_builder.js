/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * WmsRackBuilder – a Text-field widget that renders an interactive rack
 * grid. Click cells to select. Merge / split / change slot count via the
 * side panel. Compartments are 2D rectangles on the grid: they can span
 * any number of shelves AND any number of columns (a corner-cabinet
 * compartment, a wide drawer, a tall column for bottles, …).
 *
 * Whatever the user does is serialised back into the field as JSON; the
 * server-side wms.rack.generator wizard reads that JSON to create the
 * actual stock.location records.
 *
 * JSON schema:
 *   {
 *     "shelves": 6,
 *     "columns": 3,
 *     "compartments": [
 *       {
 *         "shelf_top": 1, "shelf_bottom": 1,
 *         "column_left": 1, "column_right": 1,
 *         "slot_count": 1,
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
        // Persist the initial JSON in case the wizard was opened fresh
        // so action_generate() always has something to read.
        this._commit();
    }

    // ------------------------------------------------------------- helpers
    _parseInitial(rawJson) {
        if (rawJson) {
            try {
                const parsed = JSON.parse(rawJson);
                if (parsed.shelves && parsed.columns && Array.isArray(parsed.compartments)) {
                    parsed.compartments.forEach((c, idx) => {
                        if (!c.id) c.id = idx + 1;
                        // Migrate legacy column_index → column_left/column_right
                        if (c.column_left === undefined && c.column_index !== undefined) {
                            c.column_left = c.column_index;
                            c.column_right = c.column_index;
                            delete c.column_index;
                        }
                        if (c.column_right === undefined) c.column_right = c.column_left;
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
                    column_left: c,
                    column_right: c,
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
                column_left: c.column_left,
                column_right: c.column_right,
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

    /**
     * A merge is valid only when the candidate neighbour has the **same
     * extent** along the perpendicular axis. e.g. to merge UP, the cell
     * directly above must occupy exactly the same column range as the
     * selected cell. Otherwise the result wouldn't be a rectangle.
     */
    _findAbove(c) {
        return this.state.compartments.find(
            (x) =>
                x.shelf_bottom === c.shelf_top - 1 &&
                x.column_left === c.column_left &&
                x.column_right === c.column_right,
        );
    }

    _findBelow(c) {
        return this.state.compartments.find(
            (x) =>
                x.shelf_top === c.shelf_bottom + 1 &&
                x.column_left === c.column_left &&
                x.column_right === c.column_right,
        );
    }

    _findLeft(c) {
        return this.state.compartments.find(
            (x) =>
                x.column_right === c.column_left - 1 &&
                x.shelf_top === c.shelf_top &&
                x.shelf_bottom === c.shelf_bottom,
        );
    }

    _findRight(c) {
        return this.state.compartments.find(
            (x) =>
                x.column_left === c.column_right + 1 &&
                x.shelf_top === c.shelf_top &&
                x.shelf_bottom === c.shelf_bottom,
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
    canMergeLeft() {
        const c = this.selectedCompartment;
        return !!(c && c.column_left > 1 && this._findLeft(c));
    }
    canMergeRight() {
        const c = this.selectedCompartment;
        return !!(c && c.column_right < this.state.columns && this._findRight(c));
    }
    canSplit() {
        const c = this.selectedCompartment;
        return !!(c && (c.shelf_bottom > c.shelf_top || c.column_right > c.column_left));
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

    async mergeLeft() {
        const c = this.selectedCompartment;
        if (!this.canMergeLeft()) return;
        const left = this._findLeft(c);
        c.column_left = left.column_left;
        c.slot_count = Math.max(c.slot_count, left.slot_count);
        this.state.compartments = this.state.compartments.filter((x) => x.id !== left.id);
        await this._commit();
    }

    async mergeRight() {
        const c = this.selectedCompartment;
        if (!this.canMergeRight()) return;
        const right = this._findRight(c);
        c.column_right = right.column_right;
        c.slot_count = Math.max(c.slot_count, right.slot_count);
        this.state.compartments = this.state.compartments.filter((x) => x.id !== right.id);
        await this._commit();
    }

    /**
     * Split a 2D-spanned compartment back into single-cell compartments
     * covering the same rectangle. The original compartment shrinks to
     * the top-left cell of its old rectangle.
     */
    async split() {
        const c = this.selectedCompartment;
        if (!this.canSplit()) return;
        const oldTop = c.shelf_top;
        const oldBottom = c.shelf_bottom;
        const oldLeft = c.column_left;
        const oldRight = c.column_right;
        c.shelf_bottom = oldTop;
        c.column_right = oldLeft;
        let nextId = Math.max(...this.state.compartments.map((x) => x.id)) + 1;
        for (let s = oldTop; s <= oldBottom; s++) {
            for (let col = oldLeft; col <= oldRight; col++) {
                if (s === oldTop && col === oldLeft) continue; // keep original
                this.state.compartments.push({
                    id: nextId++,
                    shelf_top: s,
                    shelf_bottom: s,
                    column_left: col,
                    column_right: col,
                    slot_count: 1,
                    label: null,
                });
            }
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
    _pad(n) {
        return String(n).padStart(2, "0");
    }

    cellLabel(c) {
        const shelfPart =
            c.shelf_top === c.shelf_bottom
                ? "SH" + this._pad(c.shelf_top)
                : "SH" + this._pad(c.shelf_top) + "-" + this._pad(c.shelf_bottom);
        const colPart =
            c.column_left === c.column_right
                ? "C" + this._pad(c.column_left)
                : "C" + this._pad(c.column_left) + "-" + this._pad(c.column_right);
        return shelfPart + " " + colPart;
    }

    cellStyle(c) {
        return (
            "grid-row: " +
            c.shelf_top +
            " / " +
            (c.shelf_bottom + 1) +
            "; grid-column: " +
            c.column_left +
            " / " +
            (c.column_right + 1) +
            ";"
        );
    }

    isSpan(c) {
        return c.shelf_bottom > c.shelf_top || c.column_right > c.column_left;
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
