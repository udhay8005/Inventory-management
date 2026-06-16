import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Repoint the EAN-13 sequence onto the GS1 restricted-circulation
    range (prefix '02', padding 10) on already-installed databases.

    The sequence record (seq_barcode_ean13) carries noupdate="1" so a
    plain `-u wms_location` will NOT overwrite its prefix/padding - that
    flag exists to protect the running counter from a module reload.
    This migration therefore makes the one-time prefix correction by
    hand, only on a row that still has the OLD prefix, so it is fully
    idempotent (re-running, or a fresh install that already loaded '02'
    from XML, is a no-op).

    The running counter (number_next) is left untouched: old aliases
    minted as 89011110-NNNN-C and new ones minted as 02-NNNNNNNNNN-C can
    never collide (different leading digits), and existing aliases are
    never rewritten. Body length stays 12 digits (2 + 10), preserving
    _next_ean13()'s len==12 precondition.
    """
    cr.execute(
        """
        UPDATE ir_sequence
           SET prefix = '02', padding = 10
         WHERE code = 'wms.barcode.ean13'
           AND prefix = '89011110'
        """
    )
    if cr.rowcount:
        _logger.info(
            "wms_location: repointed EAN-13 sequence from GS1-India '890' "
            "range to restricted-circulation '02' range (prefix 02, padding "
            "10); existing aliases untouched, counter preserved."
        )
