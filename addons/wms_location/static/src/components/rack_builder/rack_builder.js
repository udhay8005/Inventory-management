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
     * Smart-merge helpers. A single Merge click extends the selected
     * compartment by one row/column, consuming **every** compartment in
     * that adjacent strip — but only if those compartments together
     * tile the strip exactly. The strip is
     *
     *   above:  one row at shelf=(shelf_top - 1), columns
     *           column_left..column_right
     *   below:  one row at shelf=(shelf_bottom + 1)
     *   left:   one column at column=(column_left - 1), shelves
     *           shelf_top..shelf_bottom
     *   right:  one column at column=(column_right + 1)
     *
     * Candidates must lie **entirely** within that strip (no overhang
     * into other rows/columns) so the result stays rectangular. Returns
     * an array of compartments to consume, or null when the merge isn't
     * possible.
     */
    _stripAbove(c) {
        const targetShelf = c.shelf_top - 1;
        if (targetShelf < 1) return null;
        const candidates = this.state.compartments.filter(
            (x) =>
                x.shelf_top === targetShelf &&
                x.shelf_bottom === targetShelf &&
                x.column_left >= c.column_left &&
                x.column_right <= c.column_right,
        );
        return this._tilesRange(candidates, "column_left", "column_right", c.column_left, c.column_right);
    }

    _stripBelow(c) {
        const targetShelf = c.shelf_bottom + 1;
        if (targetShelf > this.state.shelves) return null;
        const candidates = this.state.compartments.filter(
            (x) =>
                x.shelf_top === targetShelf &&
                x.shelf_bottom === targetShelf &&
                x.column_left >= c.column_left &&
                x.column_right <= c.column_right,
        );
        return this._tilesRange(candidates, "column_left", "column_right", c.column_left, c.column_right);
    }

    _stripLeft(c) {
        const targetCol = c.column_left - 1;
        if (targetCol < 1) return null;
        const candidates = this.state.compartments.filter(
            (x) =>
                x.column_left === targetCol &&
                x.column_right === targetCol &&
                x.shelf_top >= c.shelf_top &&
                x.shelf_bottom <= c.shelf_bottom,
        );
        return this._tilesRange(candidates, "shelf_top", "shelf_bottom", c.shelf_top, c.shelf_bottom);
    }

    _stripRight(c) {
        const targetCol = c.column_right + 1;
        if (targetCol > this.state.columns) return null;
        const candidates = this.state.compartments.filter(
            (x) =>
                x.column_left === targetCol &&
                x.column_right === targetCol &&
                x.shelf_top >= c.shelf_top &&
                x.shelf_bottom <= c.shelf_bottom,
        );
        return this._tilesRange(candidates, "shelf_top", "shelf_bottom", c.shelf_top, c.shelf_bottom);
    }

    /**
     * Given a list of non-overlapping candidates and a required range
     * [rangeStart, rangeEnd], return them sorted ASC if they tile the
     * range exactly (no gaps), else null. lowKey / highKey are the
     * property names that hold each candidate's range on this axis.
     */
    _tilesRange(candidates, lowKey, highKey, rangeStart, rangeEnd) {
        if (candidates.length === 0) return null;
        const sorted = [...candidates].sort((a, b) => a[lowKey] - b[lowKey]);
        let cursor = rangeStart;
        for (const x of sorted) {
            if (x[lowKey] !== cursor) return null;
            cursor = x[highKey] + 1;
        }
        return cursor - 1 === rangeEnd ? sorted : null;
    }

    canMergeUp() {
        const c = this.selectedCompartment;
        return !!(c && this._stripAbove(c));
    }
    canMergeDown() {
        const c = this.selectedCompartment;
        return !!(c && this._stripBelow(c));
    }
    canMergeLeft() {
        const c = this.selectedCompartment;
        return !!(c && this._stripLeft(c));
    }
    canMergeRight() {
        const c = this.selectedCompartment;
        return !!(c && this._stripRight(c));
    }
    canSplit() {
        const c = this.selectedCompartment;
        return !!(c && (c.shelf_bottom > c.shelf_top || c.column_right > c.column_left));
    }

    _consume(c, strip, extentField, newValue) {
        c[extentField] = newValue;
        c.slot_count = strip.reduce((m, x) => Math.max(m, x.slot_count), c.slot_count);
        const ids = new Set(strip.map((x) => x.id));
        this.state.compartments = this.state.compartments.filter((x) => !ids.has(x.id));
    }

    async mergeUp() {
        const c = this.selectedCompartment;
        const strip = c && this._stripAbove(c);
        if (!strip) return;
        this._consume(c, strip, "shelf_top", strip[0].shelf_top);
        await this._commit();
    }

    async mergeDown() {
        const c = this.selectedCompartment;
        const strip = c && this._stripBelow(c);
        if (!strip) return;
        this._consume(c, strip, "shelf_bottom", strip[0].shelf_bottom);
        await this._commit();
    }

    async mergeLeft() {
        const c = this.selectedCompartment;
        const strip = c && this._stripLeft(c);
        if (!strip) return;
        this._consume(c, strip, "column_left", strip[0].column_left);
        await this._commit();
    }

    async mergeRight() {
        const c = this.selectedCompartment;
        const strip = c && this._stripRight(c);
        if (!strip) return;
        this._consume(c, strip, "column_right", strip[strip.length - 1].column_right);
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
