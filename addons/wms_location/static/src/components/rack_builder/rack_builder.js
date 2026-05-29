/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * WmsRackBuilder
 * ==============
 *
 * Visual rack designer. Compartments are arbitrary 4-connected
 * polyominoes -- each cell is a single (shelf, column) pair, and
 * compartments are sets of cells.
 *
 * Two ways to grow a compartment:
 *
 *   1. Directional merge (↑ ↓ ← →) - rectangular bias. Consumes the
 *      entire adjacent row/column that tiles the compartment's
 *      current rectangular extent. Useful for tall bottle columns,
 *      wide drawers, corner cabinets. Disabled when the compartment
 *      is non-rectangular (use Add cell instead).
 *
 *   2. Add adjacent cell. Click the "+ Add cell" toggle, then click
 *      ANY cell 4-adjacent to the current compartment. That single
 *      cell joins. Click as many adjacent cells as needed to build an
 *      L, a T, a U, or whatever the physical compartment looks like.
 *
 * Split breaks the compartment back into single-cell compartments
 * covering the same cells.
 *
 * JSON schema:
 *   {
 *     "shelves": 6,
 *     "columns": 3,
 *     "compartments": [
 *       {
 *         "id": 1,
 *         "cells": [[1, 1]],
 *         "slot_count": 1,
 *         "label": null
 *       },
 *       {
 *         "id": 7,
 *         "cells": [[2, 1], [3, 1], [3, 2]],
 *         "slot_count": 1,
 *         "label": "L-shape"
 *       }
 *     ]
 *   }
 *
 * Backward read: old records with shelf_top/shelf_bottom/column_left/
 * column_right are auto-converted to a cells array (expanded to every
 * cell in the rectangle).
 *
 * Server-side: the wms.rack.generator wizard handles both shapes -
 * for non-rectangular compartments it stores the bounding box on
 * stock.location's wms_shelf_top/_bottom/_column_left/_right and the
 * exact cell list in wms_cells_json so the warehouse-map renderer
 * can draw the precise outline.
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
            addCellMode: false,   // when true, clicks add cells to selection
        });
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
                        if (!Array.isArray(c.cells) || c.cells.length === 0) {
                            // Migrate legacy rectangle compartments
                            const top = c.shelf_top || 1;
                            const bot = c.shelf_bottom || top;
                            const left = c.column_left ?? c.column_index ?? 1;
                            const right = c.column_right ?? left;
                            const cells = [];
                            for (let s = top; s <= bot; s++) {
                                for (let col = left; col <= right; col++) {
                                    cells.push([s, col]);
                                }
                            }
                            c.cells = cells;
                        }
                        // Drop legacy keys; the canonical store is cells[].
                        delete c.shelf_top;
                        delete c.shelf_bottom;
                        delete c.column_left;
                        delete c.column_right;
                        delete c.column_index;
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
                    cells: [[s, c]],
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
            compartments: this.state.compartments.map((c) => {
                const bbox = this._bbox(c.cells);
                return {
                    // canonical
                    cells: c.cells.map((p) => [p[0], p[1]]),
                    slot_count: c.slot_count,
                    label: c.label || null,
                    // legacy bounding-box fields - kept so the server-side
                    // generator + the warehouse-map renderer keep working
                    // without immediate refactor.
                    shelf_top: bbox.top,
                    shelf_bottom: bbox.bottom,
                    column_left: bbox.left,
                    column_right: bbox.right,
                };
            }),
        };
        await this.props.record.update({
            [this.props.name]: JSON.stringify(payload, null, 2),
        });
    }

    _bbox(cells) {
        let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
        for (const [s, c] of cells) {
            if (s < top) top = s;
            if (s > bottom) bottom = s;
            if (c < left) left = c;
            if (c > right) right = c;
        }
        return { top, bottom, left, right };
    }

    // -------------------------------------------------- shelf/column resize

    async onShelvesChange(ev) {
        const n = Math.max(1, Math.min(30, parseInt(ev.target.value || "0", 10) || 1));
        const grid = this._defaultGrid(n, this.state.columns);
        Object.assign(this.state, grid, { selectedId: null, addCellMode: false });
        await this._commit();
    }

    async onColumnsChange(ev) {
        const n = Math.max(1, Math.min(20, parseInt(ev.target.value || "0", 10) || 1));
        const grid = this._defaultGrid(this.state.shelves, n);
        Object.assign(this.state, grid, { selectedId: null, addCellMode: false });
        await this._commit();
    }

    async resetGrid() {
        const grid = this._defaultGrid(this.state.shelves, this.state.columns);
        this.state.compartments = grid.compartments;
        this.state.selectedId = null;
        this.state.addCellMode = false;
        await this._commit();
    }

    // ----------------------------------------------------- cell <-> compartment

    /** Find which compartment owns the given (shelf, column) cell. */
    _compartmentAt(shelf, col) {
        return this.state.compartments.find((c) =>
            c.cells.some((p) => p[0] === shelf && p[1] === col),
        );
    }

    get selectedCompartment() {
        return this.state.compartments.find((c) => c.id === this.state.selectedId);
    }

    /**
     * Click on a cell. Behaviour depends on mode:
     *  - addCellMode OFF: select the compartment that owns the cell.
     *  - addCellMode ON : if the cell belongs to another compartment AND
     *    is 4-adjacent to the selected compartment, transfer that cell
     *    into the selected compartment. The donor compartment is left
     *    minus that cell; if it had only this cell, it's removed.
     */
    onCellClick(shelf, col) {
        const target = this._compartmentAt(shelf, col);
        if (!target) return;
        if (!this.state.addCellMode) {
            this.state.selectedId = target.id;
            return;
        }
        const sel = this.selectedCompartment;
        if (!sel) return;
        if (target.id === sel.id) return;  // already mine

        // Connectivity: the cell must be 4-adjacent to some cell of sel.
        const adj = sel.cells.some(([s, c]) =>
            (s === shelf && Math.abs(c - col) === 1) ||
            (c === col && Math.abs(s - shelf) === 1),
        );
        if (!adj) return;

        // Transfer the cell.
        target.cells = target.cells.filter((p) => !(p[0] === shelf && p[1] === col));
        sel.cells.push([shelf, col]);
        // If donor compartment is now empty, remove it.
        if (target.cells.length === 0) {
            this.state.compartments = this.state.compartments.filter((c) => c.id !== target.id);
        }
        this._commit();
    }

    toggleAddCellMode() {
        if (!this.selectedCompartment) return;
        this.state.addCellMode = !this.state.addCellMode;
    }

    // ----------------------------------------------- rectangle ops (legacy)

    /** True iff the compartment's cells exactly tile a rectangle. */
    _isRectangle(comp) {
        const b = this._bbox(comp.cells);
        const expected = (b.bottom - b.top + 1) * (b.right - b.left + 1);
        return comp.cells.length === expected;
    }

    canMergeUp()    { return this._canMergeDir("up");    }
    canMergeDown()  { return this._canMergeDir("down");  }
    canMergeLeft()  { return this._canMergeDir("left");  }
    canMergeRight() { return this._canMergeDir("right"); }
    canSplit()      { return !!(this.selectedCompartment && this.selectedCompartment.cells.length > 1); }

    /**
     * Direction merge: only allowed if THIS compartment is rectangular
     * AND the strip's cells together tile the matching adjacent rectangle.
     */
    _canMergeDir(dir) {
        const c = this.selectedCompartment;
        if (!c || !this._isRectangle(c)) return false;
        const b = this._bbox(c.cells);
        let stripCells = [];
        if (dir === "up") {
            if (b.top === 1) return false;
            for (let col = b.left; col <= b.right; col++) stripCells.push([b.top - 1, col]);
        } else if (dir === "down") {
            if (b.bottom === this.state.shelves) return false;
            for (let col = b.left; col <= b.right; col++) stripCells.push([b.bottom + 1, col]);
        } else if (dir === "left") {
            if (b.left === 1) return false;
            for (let s = b.top; s <= b.bottom; s++) stripCells.push([s, b.left - 1]);
        } else if (dir === "right") {
            if (b.right === this.state.columns) return false;
            for (let s = b.top; s <= b.bottom; s++) stripCells.push([s, b.right + 1]);
        }
        // Every strip cell must belong to a compartment that is wholly
        // inside the strip (no half-cells overhanging into other rows).
        const donorIds = new Set();
        for (const [s, col] of stripCells) {
            const owner = this._compartmentAt(s, col);
            if (!owner) return false;
            donorIds.add(owner.id);
            // Each donor must have all its cells inside the strip range
            // for the rectangle to stay rectangular post-merge.
            for (const [ds, dc] of owner.cells) {
                const inStrip = stripCells.some((p) => p[0] === ds && p[1] === dc);
                if (!inStrip) return false;
            }
        }
        return donorIds.size > 0;
    }

    _mergeDir(dir) {
        const c = this.selectedCompartment;
        if (!c || !this._canMergeDir(dir)) return;
        const b = this._bbox(c.cells);
        const cellsToAdd = [];
        if (dir === "up") {
            for (let col = b.left; col <= b.right; col++) cellsToAdd.push([b.top - 1, col]);
        } else if (dir === "down") {
            for (let col = b.left; col <= b.right; col++) cellsToAdd.push([b.bottom + 1, col]);
        } else if (dir === "left") {
            for (let s = b.top; s <= b.bottom; s++) cellsToAdd.push([s, b.left - 1]);
        } else if (dir === "right") {
            for (let s = b.top; s <= b.bottom; s++) cellsToAdd.push([s, b.right + 1]);
        }
        const donorIds = new Set();
        for (const [s, col] of cellsToAdd) {
            const owner = this._compartmentAt(s, col);
            if (owner) donorIds.add(owner.id);
        }
        c.cells = c.cells.concat(cellsToAdd);
        c.slot_count = Math.max(
            c.slot_count,
            ...this.state.compartments
                .filter((x) => donorIds.has(x.id))
                .map((x) => x.slot_count),
        );
        this.state.compartments = this.state.compartments.filter(
            (x) => !donorIds.has(x.id) || x.id === c.id,
        );
        this._commit();
    }

    mergeUp()    { this._mergeDir("up");    }
    mergeDown()  { this._mergeDir("down");  }
    mergeLeft()  { this._mergeDir("left");  }
    mergeRight() { this._mergeDir("right"); }

    /** Split a multi-cell compartment back into one compartment per cell. */
    async split() {
        const c = this.selectedCompartment;
        if (!c || c.cells.length <= 1) return;
        const anchor = c.cells[0];  // keep the first cell on this compartment
        const others = c.cells.slice(1);
        c.cells = [anchor];
        let nextId = Math.max(0, ...this.state.compartments.map((x) => x.id)) + 1;
        for (const [s, col] of others) {
            this.state.compartments.push({
                id: nextId++,
                cells: [[s, col]],
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

    _pad(n) { return String(n).padStart(2, "0"); }

    /** Render all the (shelf,column) cells as a flat iterable for the
     *  template -- each cell becomes a separate DOM element. */
    get gridCells() {
        const out = [];
        for (let s = 1; s <= this.state.shelves; s++) {
            for (let c = 1; c <= this.state.columns; c++) {
                const owner = this._compartmentAt(s, c);
                if (!owner) continue;  // shouldn't happen with default grid
                const isAnchor =
                    owner.cells[0][0] === s && owner.cells[0][1] === c;
                // hide border between adjacent same-compartment cells
                const sameUp    = owner.cells.some((p) => p[0] === s - 1 && p[1] === c);
                const sameDown  = owner.cells.some((p) => p[0] === s + 1 && p[1] === c);
                const sameLeft  = owner.cells.some((p) => p[0] === s && p[1] === c - 1);
                const sameRight = owner.cells.some((p) => p[0] === s && p[1] === c + 1);
                out.push({
                    shelf: s,
                    column: c,
                    compartmentId: owner.id,
                    isAnchor,
                    label: isAnchor ? this.compartmentLabel(owner) : null,
                    slotBadge: isAnchor && owner.slot_count > 1
                        ? owner.slot_count + " slots"
                        : null,
                    selected: this.state.selectedId === owner.id,
                    multiCell: owner.cells.length > 1,
                    borderTop: !sameUp,
                    borderBottom: !sameDown,
                    borderLeft: !sameLeft,
                    borderRight: !sameRight,
                });
            }
        }
        return out;
    }

    compartmentLabel(c) {
        if (c.label) return c.label;
        if (c.cells.length === 1) {
            const [s, col] = c.cells[0];
            return "SH" + this._pad(s) + " C" + this._pad(col);
        }
        // For rectangular multi-cell compartments use the range form;
        // for polyominoes show the anchor + count.
        if (this._isRectangle(c)) {
            const b = this._bbox(c.cells);
            const shelfPart = b.top === b.bottom
                ? "SH" + this._pad(b.top)
                : "SH" + this._pad(b.top) + "-" + this._pad(b.bottom);
            const colPart = b.left === b.right
                ? "C" + this._pad(b.left)
                : "C" + this._pad(b.left) + "-" + this._pad(b.right);
            return shelfPart + " " + colPart;
        }
        const [s, col] = c.cells[0];
        return "SH" + this._pad(s) + " C" + this._pad(col) +
               " (+" + (c.cells.length - 1) + ")";
    }

    cellStyle(cell) {
        return "grid-row: " + cell.shelf + "; grid-column: " + cell.column + ";";
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
