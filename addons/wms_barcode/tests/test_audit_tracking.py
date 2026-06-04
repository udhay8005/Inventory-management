"""High - the Scan Issue audit triplet (handled-by / ordered-by / storekeeper)
must be change-tracked, so any post-validation edit is recorded in the picking's
chatter rather than silently rewritten. The damage/repair triplets were already
tracked; this closes the gap on the picking."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_audit_tracking")
class TestPickingAuditTracking(TransactionCase):
    def test_audit_triplet_is_tracked(self):
        picking_fields = self.env["stock.picking"]._fields
        for fname in ("wms_taken_by", "wms_ordered_by", "wms_storekeeper_id"):
            self.assertTrue(
                picking_fields[fname].tracking,
                "%s must be tracked so post-done edits are auditable" % fname,
            )
