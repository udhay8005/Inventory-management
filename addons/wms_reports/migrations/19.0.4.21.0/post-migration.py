"""Backfill wms.audit.line.is_counted on existing databases.

New column, default False — which on an already-reviewed audit would read as
"nobody counted any of this", making the history look like a warehouse that was
never walked. Backfill so existing records keep meaning what they meant:

* lines in a finished audit (submitted / reviewed / rejected) are marked
  counted. Their outcome is already applied and is now history; re-labelling
  them as uncounted would rewrite the record of work that was really done.
* lines in an audit still open (draft / in_progress) are marked counted only
  where a figure was actually entered. A zero on an unfinished sheet is the
  ambiguous case this column exists to remove, and the safe reading of it is
  "not yet walked" — that way accepting the audit leaves that stock alone
  instead of zeroing it.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE wms_audit_line l
           SET is_counted = TRUE
          FROM wms_audit a
         WHERE a.id = l.audit_id
           AND (a.state IN ('submitted', 'reviewed', 'rejected')
                OR COALESCE(l.counted_qty, 0) <> 0)
        """
    )
