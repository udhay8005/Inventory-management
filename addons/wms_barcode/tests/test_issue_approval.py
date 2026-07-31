"""F4 + F5 — Manager-approval gate (min-life re-request guard + high value).

Covers the full defensive test matrix:
  * below-threshold + outside-window issue validates inline (no approval row,
    picking created as before),
  * high-value issue with keeper_reason -> pending approval + notify + NO
    picking + keeper sees it read-only,
  * high-value WITHOUT keeper_reason -> UserError,
  * keeper cannot approve (no write ACL; action_approve raises for a keeper),
  * manager approve -> exactly ONE picking, origin starts
    'Barcode FIFO issue (approved APR-', audit triplet present,
    wms_unit_cost_at_done snapshotted, photo carried,
  * double / concurrent approve -> still exactly one picking,
  * same-dept re-request within min_life -> held; different dept same product
    -> inline,
  * product wms_min_life_days=0 + global default>0 -> uses the global,
  * reject -> nothing issued, state rejected,
  * issue_approval_enabled='0' -> gate fully bypassed,
  * non-numeric high_value_threshold -> gate disabled, no crash,
  * stock moved out between request and approve -> action_approve raises
    cleanly, no half-picking,
  * photo-gate: a Litre / kg product issue requires a photo, a Units product
    does not.
"""

import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_issue_approval")
class TestIssueApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.param = cls.env["ir.config_parameter"].sudo()
        # Deterministic params for the whole class. Individual tests override
        # then restore where they need a different value.
        cls.param.set_param("wms_barcode.issue_approval_enabled", "1")
        cls.param.set_param("wms_barcode.high_value_threshold", "5000")
        cls.param.set_param("wms_location.default_min_life_days", "0")

        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "APR Keeper"})
        cls.dept_other = cls.env.ref("wms_location.dept_other")
        cls.dept_gaushala = cls.env.ref("wms_location.dept_gaushala")

        # A real WMS Manager runs the Approve/Reject path — the in-method
        # group re-check (and the write ACL) require group_wms_manager. The
        # base test user is not guaranteed to be in that group on every DB.
        cls.manager = cls.env["res.users"].create(
            {
                "name": "APR Manager",
                "login": "apr_manager",
                "group_ids": [(6, 0, [cls.env.ref("wms_location.group_wms_manager").id])],
            }
        )

        # Cheap counted product (Units) — below threshold, no min-life guard.
        cls.cheap = cls.env["product.product"].create(
            {
                "name": "APR Cheap Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "APRCHEAP1",
                "wms_product_kind": "consumable",
                "standard_price": 1.0,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.cheap, cls.stock, 500.0)

        # Expensive product — trips the high-value gate at small qty.
        cls.pricey = cls.env["product.product"].create(
            {
                "name": "APR Pricey Tool",
                "type": "consu",
                "is_storable": True,
                "barcode": "APRPRICEY1",
                "wms_product_kind": "tool",
                "standard_price": 4000.0,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.pricey, cls.stock, 50.0)

        # A COUNTED bundle UoM (a pack of 6 pieces) — self-seeded rather than
        # ref'd from demo data (uom.product_uom_pack_6 is demo-only, absent
        # under CI's --without-demo, which silently skipped this branch). It
        # chains up to the Units root via relative_uom_id, so the photo gate
        # must treat it as counted, NOT measured.
        cls.bundle_uom = cls.env["uom.uom"].create(
            {
                "name": "APR Pack of 6",
                "relative_uom_id": cls.env.ref("uom.product_uom_unit").id,
                "relative_factor": 6.0,
            }
        )

    # ---- helpers ---------------------------------------------------------
    def _make_wizard(self, **extra):
        vals = {
            "warehouse_id": self.wh.id,
            "requested_qty": 1.0,
            "taken_by": "Taker",
            "ordered_by": "Orderer",
            "usage_note": "approval test",
            "storekeeper_id": self.keeper.id,
            "department_id": self.dept_other.id,
        }
        vals.update(extra)
        return self.env["wms.scan.issue"].create(vals)

    def _approvals(self):
        return self.env["wms.issue.approval"].search([])

    # =====================================================================
    # Inline auto-allow path
    # =====================================================================
    def test_below_threshold_outside_window_issues_inline(self):
        before = self._approvals()
        wiz = self._make_wizard(last_scan="APRCHEAP1", requested_qty=2.0)
        wiz.action_plan()
        result = wiz.action_validate()
        self.assertTrue(wiz.picking_id, "a cheap issue must create a picking inline")
        self.assertEqual(result.get("res_model"), "stock.picking", "inline path opens the delivery")
        self.assertEqual(
            self._approvals(), before, "no approval row may be created for an inline issue"
        )
        self.assertEqual(wiz.picking_id.state, "done")

    # =====================================================================
    # High-value gate (F5)
    # =====================================================================
    def test_high_value_with_reason_holds_no_picking(self):
        wiz = self._make_wizard(
            last_scan="APRPRICEY1",
            requested_qty=2.0,  # 2 x 4000 = 8000 > 5000
            keeper_reason="Bulk order pre-approved by Manager",
        )
        wiz.action_plan()
        self.assertTrue(wiz.needs_approval, "the pre-check must flag a high-value plan")
        result = wiz.action_validate()
        self.assertFalse(wiz.picking_id, "NO picking may be created when held")
        self.assertEqual(result.get("res_model"), "wms.issue.approval")
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        self.assertEqual(approval.state, "pending")
        self.assertTrue(approval.reason_high_value)
        self.assertFalse(approval.reason_min_life)
        # Frozen snapshot of value (not a live compute).
        self.assertAlmostEqual(approval.issue_value, 8000.0, places=2)
        self.assertEqual(approval.name[:4], "APR-")
        self.assertEqual(len(approval.line_ids), len(wiz.plan_line_ids))

    def test_high_value_without_reason_raises(self):
        wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0)
        wiz.action_plan()
        with self.assertRaises(UserError):
            wiz.action_validate()
        self.assertFalse(wiz.picking_id, "nothing may be issued without a reason")

    def test_issue_value_is_frozen_not_recomputed(self):
        wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="reason")
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        frozen = approval.issue_value
        # Change the cost AFTER the snapshot; the snapshot must not move.
        self.pricey.standard_price = 9999.0
        approval.invalidate_recordset(["issue_value"])
        self.assertAlmostEqual(
            approval.issue_value, frozen, places=2, msg="issue_value must be frozen"
        )

    # =====================================================================
    # Manager approval replay
    # =====================================================================
    def test_manager_approve_creates_exactly_one_picking(self):
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n")
        wiz = self._make_wizard(
            last_scan="APRPRICEY1",
            requested_qty=2.0,
            keeper_reason="vet authorised",
            photo=png,
        )
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])

        on_hand_before = self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock)
        approval.with_user(self.manager).action_approve()
        approval.invalidate_recordset()
        self.assertEqual(approval.state, "approved")
        picking = approval.picking_id
        self.assertTrue(picking, "approval must create the delivery")
        self.assertEqual(picking.state, "done")
        # Origin must start with the approved-Barcode prefix so the audit
        # triplet CHECK + constrains fire.
        self.assertTrue(
            picking.origin.startswith("Barcode FIFO issue (approved APR-"),
            "origin=%r" % picking.origin,
        )
        # Audit triplet present.
        self.assertTrue(picking.wms_storekeeper_id)
        self.assertTrue(picking.wms_taken_by)
        self.assertTrue(picking.wms_ordered_by)
        self.assertTrue(picking.wms_is_scan_issue)
        # Cost snapshot on the move line.
        for ml in picking.move_ids.move_line_ids:
            self.assertTrue(ml.wms_unit_cost_at_done)
        # Photo carried onto the picking.
        att = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "stock.picking"),
                ("res_id", "=", picking.id),
                ("name", "like", "issue-photo-%"),
            ]
        )
        self.assertTrue(att, "the keeper photo must be carried onto the delivery")
        # Exactly one picking-worth of stock was deducted.
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock),
            on_hand_before - 2.0,
            places=3,
        )

    def test_double_approve_is_idempotent(self):
        wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="reason")
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        approval.with_user(self.manager).action_approve()
        approval.invalidate_recordset()
        first = approval.picking_id
        self.assertTrue(first)
        qty_after_first = self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock)
        # Second approve must short-circuit to opening the same picking, no
        # second deduction.
        approval.with_user(self.manager).action_approve()
        approval.invalidate_recordset()
        self.assertEqual(approval.picking_id, first)
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock),
            qty_after_first,
            places=3,
        )

    def test_reject_issues_nothing(self):
        wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="reason")
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        on_hand = self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock)
        approval.with_user(self.manager).action_reject()
        approval.invalidate_recordset()
        self.assertEqual(approval.state, "rejected")
        self.assertFalse(approval.picking_id, "reject must not issue anything")
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock),
            on_hand,
            places=3,
        )

    def test_stock_moved_before_approve_raises_no_half_picking(self):
        wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="reason")
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        # Empty the warehouse of the pricey product between request and approve.
        self.env["stock.quant"]._update_available_quantity(self.pricey, self.stock, -50.0)
        with self.assertRaises(UserError):
            approval.with_user(self.manager).action_approve()
        self.assertFalse(approval.picking_id, "no half-picking when stock moved")
        self.assertEqual(approval.state, "pending", "state stays pending on a failed approve")
        # Refill for other tests sharing the class quants is unnecessary
        # (each test runs in its own transaction rollback).

    # =====================================================================
    # Keeper cannot approve (defense in depth)
    # =====================================================================
    def test_keeper_cannot_approve(self):
        wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="reason")
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        keeper_user = self.env["res.users"].create(
            {
                "name": "Keeper Only",
                "login": "apr_keeper_only",
                "group_ids": [(6, 0, [self.env.ref("wms_location.group_wms_can_scan_issue").id])],
            }
        )
        # In-method group re-check raises for a non-manager even if forced.
        with self.assertRaises(AccessError):
            approval.with_user(keeper_user).action_approve()
        with self.assertRaises(AccessError):
            approval.with_user(keeper_user).action_reject()

    def test_keeper_has_no_write_acl_on_approval(self):
        keeper_user = self.env["res.users"].create(
            {
                "name": "Keeper ACL",
                "login": "apr_keeper_acl",
                "group_ids": [(6, 0, [self.env.ref("wms_location.group_wms_can_scan_issue").id])],
            }
        )
        Access = self.env["ir.model.access"].with_user(keeper_user)
        self.assertTrue(Access.check("wms.issue.approval", "create", raise_exception=False))
        self.assertTrue(Access.check("wms.issue.approval", "read", raise_exception=False))
        self.assertFalse(
            Access.check("wms.issue.approval", "write", raise_exception=False),
            "a keeper must NOT have write access on the approval model",
        )
        self.assertFalse(Access.check("wms.issue.approval", "unlink", raise_exception=False))

    # =====================================================================
    # Min-life gate (F4)
    # =====================================================================
    def test_same_dept_rerequest_within_window_is_held(self):
        # Per-product min-life window of 30 days on the cheap product.
        self.cheap.wms_min_life_days = 30
        # First issue in Gaushala — inline (no prior history in window).
        w1 = self._make_wizard(
            last_scan="APRCHEAP1", requested_qty=1.0, department_id=self.dept_gaushala.id
        )
        w1.action_plan()
        w1.action_validate()
        self.assertTrue(w1.picking_id, "first issue should go through inline")
        # Second issue, same dept + same product within the window -> held.
        w2 = self._make_wizard(
            last_scan="APRCHEAP1",
            requested_qty=1.0,
            department_id=self.dept_gaushala.id,
            keeper_reason="needed again urgently",
        )
        w2.action_plan()
        self.assertTrue(w2.needs_approval)
        result = w2.action_validate()
        self.assertFalse(w2.picking_id)
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        self.assertTrue(approval.reason_min_life)
        self.assertEqual(approval.min_life_product_id, self.cheap)

    def test_different_dept_same_product_within_window_is_inline(self):
        self.cheap.wms_min_life_days = 30
        w1 = self._make_wizard(
            last_scan="APRCHEAP1", requested_qty=1.0, department_id=self.dept_gaushala.id
        )
        w1.action_plan()
        w1.action_validate()
        self.assertTrue(w1.picking_id)
        # Different department -> the min-life guard does NOT trip.
        w2 = self._make_wizard(
            last_scan="APRCHEAP1", requested_qty=1.0, department_id=self.dept_other.id
        )
        w2.action_plan()
        self.assertFalse(w2.needs_approval)
        w2.action_validate()
        self.assertTrue(w2.picking_id, "a different department within the window issues inline")

    def test_global_default_used_when_product_zero(self):
        self.cheap.wms_min_life_days = 0  # no per-product guard
        self.param.set_param("wms_location.default_min_life_days", "30")
        try:
            w1 = self._make_wizard(
                last_scan="APRCHEAP1", requested_qty=1.0, department_id=self.dept_gaushala.id
            )
            w1.action_plan()
            w1.action_validate()
            self.assertTrue(w1.picking_id)
            w2 = self._make_wizard(
                last_scan="APRCHEAP1",
                requested_qty=1.0,
                department_id=self.dept_gaushala.id,
                keeper_reason="again",
            )
            w2.action_plan()
            self.assertTrue(
                w2.needs_approval, "the global default min-life must apply when product is 0"
            )
        finally:
            self.param.set_param("wms_location.default_min_life_days", "0")

    # =====================================================================
    # Master switch / bad threshold
    # =====================================================================
    def test_gate_bypassed_when_disabled(self):
        self.param.set_param("wms_barcode.issue_approval_enabled", "0")
        try:
            wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0)
            wiz.action_plan()
            self.assertFalse(wiz.needs_approval, "the gate is off, no approval flagged")
            wiz.action_validate()
            self.assertTrue(wiz.picking_id, "a disabled gate issues high value inline")
            self.assertFalse(self.env["wms.issue.approval"].search([("picking_id", "=", False)]))
        finally:
            self.param.set_param("wms_barcode.issue_approval_enabled", "1")

    def test_non_numeric_threshold_disables_high_value_no_crash(self):
        self.param.set_param("wms_barcode.high_value_threshold", "not-a-number")
        try:
            wiz = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0)
            wiz.action_plan()
            self.assertFalse(wiz.needs_approval, "a bad threshold disables the high-value check")
            # Must not crash.
            wiz.action_validate()
            self.assertTrue(wiz.picking_id)
        finally:
            self.param.set_param("wms_barcode.high_value_threshold", "5000")

    # =====================================================================
    # Photo gate (uom_id != Units)
    # =====================================================================
    def test_litre_product_requires_photo(self):
        litre = self.env.ref("uom.product_uom_litre", raise_if_not_found=False)
        if not litre:
            self.skipTest("Litre UoM not present")
        fluid = self.env["product.product"].create(
            {
                "name": "APR Milk",
                "type": "consu",
                "is_storable": True,
                "barcode": "APRMILK1",
                "wms_product_kind": "fluid",
                "uom_id": litre.id,
                "standard_price": 1.0,
            }
        )
        self.env["stock.quant"]._update_available_quantity(fluid, self.stock, 100.0)
        wiz = self._make_wizard(last_scan="APRMILK1", requested_qty=2.0)
        wiz.action_plan()
        self.assertTrue(wiz.photo_required, "a measured (Litre) product must require a photo")
        with self.assertRaises(UserError):
            wiz.action_validate()

    def test_kg_product_requires_photo(self):
        kg = self.env.ref("uom.product_uom_kgm", raise_if_not_found=False)
        if not kg:
            self.skipTest("kg UoM not present")
        feed = self.env["product.product"].create(
            {
                "name": "APR Bran",
                "type": "consu",
                "is_storable": True,
                "barcode": "APRBRAN1",
                "wms_product_kind": "feed",
                "uom_id": kg.id,
                "standard_price": 1.0,
            }
        )
        self.env["stock.quant"]._update_available_quantity(feed, self.stock, 100.0)
        wiz = self._make_wizard(last_scan="APRBRAN1", requested_qty=2.0)
        wiz.action_plan()
        self.assertTrue(wiz.photo_required, "a measured (kg) product must require a photo")
        with self.assertRaises(UserError):
            wiz.action_validate()

    def test_units_product_does_not_require_photo(self):
        wiz = self._make_wizard(last_scan="APRCHEAP1", requested_qty=2.0)
        wiz.action_plan()
        self.assertFalse(wiz.photo_required, "a counted (Units) product must NOT require a photo")
        wiz.action_validate()
        self.assertTrue(wiz.picking_id)

    def test_counted_bundle_does_not_require_photo(self):
        """A product measured in a *bundle* of Units (Pack of 6 / Dozens) is
        still COUNTED, not measured — its UoM chains up to the Units root via
        ``relative_uom_id`` — so the photo gate must stay OFF. Guards against a
        naive ``uom_id != Units`` check that would treat every non-Units UoM,
        including counted bundles, as measured."""
        pack6 = self.bundle_uom
        # Sanity: this UoM really is a child of the Units chain, not a root.
        self.assertEqual(
            pack6.relative_uom_id,
            self.env.ref("uom.product_uom_unit"),
            "Pack of 6 should chain up to the Units UoM",
        )
        bundled = self.env["product.product"].create(
            {
                "name": "APR Egg 6-pack",
                "type": "consu",
                "is_storable": True,
                "barcode": "APRPACK6",
                "wms_product_kind": "consumable",
                "uom_id": pack6.id,
                "standard_price": 1.0,
            }
        )
        self.env["stock.quant"]._update_available_quantity(bundled, self.stock, 100.0)
        wiz = self._make_wizard(last_scan="APRPACK6", requested_qty=2.0)
        wiz.action_plan()
        self.assertFalse(
            wiz.photo_required,
            "a counted bundle (Pack of 6) must NOT require a photo — it counts pieces",
        )
        wiz.action_validate()
        self.assertTrue(wiz.picking_id)

    def test_held_issue_schedules_and_clears_manager_activity(self):
        """A held issue raises a To-Do activity on the manager(s) so the systray
        badge flags it (more reliable than a Discuss ping on a shared screen),
        and the activity clears once the request is decided."""
        wiz = self._make_wizard(
            last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="vet authorised"
        )
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        todo = self.env.ref("mail.mail_activity_data_todo")
        acts = approval.activity_ids.filtered(lambda a: a.activity_type_id == todo)
        self.assertTrue(acts, "holding an issue must raise a manager To-Do activity")
        self.assertIn(
            self.manager, acts.mapped("user_id"), "the WMS manager must receive the activity"
        )
        approval.with_user(self.manager).action_approve()
        approval.invalidate_recordset()
        self.assertFalse(
            approval.activity_ids.filtered(lambda a: a.activity_type_id == todo),
            "deciding the request must clear the held-issue activity badge",
        )

    # =====================================================================
    # Daily-cap is re-checked at approval time (approve is NOT a back door
    # around the rolling-24h cap)
    # =====================================================================
    def test_daily_cap_rechecked_on_approve(self):
        """A held high-value issue passed the daily cap when it was held, but
        other issues can consume the 24h window before a Manager approves. The
        approve path MUST re-run the cap so it can't issue over the limit."""
        # Cap the pricey product at 3 per 24h.
        self.pricey.product_tmpl_id.wms_daily_cap = 3.0
        # Hold a high-value issue of 2 (8000 > 5000) — under the cap at hold time.
        wiz = self._make_wizard(
            last_scan="APRPRICEY1", requested_qty=2.0, keeper_reason="vet authorised"
        )
        wiz.action_plan()
        result = wiz.action_validate()
        approval = self.env["wms.issue.approval"].browse(result["res_id"])
        self.assertEqual(approval.state, "pending")

        # Consume the 24h window with an inline issue of 2 (gate off so it
        # issues immediately rather than being held too).
        self.param.set_param("wms_barcode.issue_approval_enabled", "0")
        try:
            consume = self._make_wizard(last_scan="APRPRICEY1", requested_qty=2.0)
            consume.action_plan()
            consume.action_validate()
            self.assertTrue(consume.picking_id, "the inline consume issue should be created")
        finally:
            self.param.set_param("wms_barcode.issue_approval_enabled", "1")

        # Approving the held 2 now would make 2 + 2 = 4 > 3 — must be blocked.
        on_hand = self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock)
        with self.assertRaises(UserError):
            approval.with_user(self.manager).action_approve()
        approval.invalidate_recordset()
        self.assertFalse(approval.picking_id, "an over-cap approval must issue nothing")
        self.assertEqual(approval.state, "pending", "a blocked approve leaves it pending")
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(self.pricey, self.stock),
            on_hand,
            places=3,
            msg="no stock may move when the daily cap blocks the approve",
        )
