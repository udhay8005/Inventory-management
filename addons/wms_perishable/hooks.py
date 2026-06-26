import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """V20-008 — partial index for fast FEFO removal scans.

    Mirrors wms_fifo's idx_quant_fifo: a partial composite index limited to
    live quants, so the FEFO removal sort scans only stock that can be issued.
    The field-level index=True on wms_effective_expiry covers single-column
    ordering (reports); this composite covers the (product_id, expiry) scan.
    """
    env.cr.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quant_fefo
        ON stock_quant (product_id, wms_effective_expiry)
        WHERE quantity > 0;
        """
    )
    _logger.info("wms_perishable: idx_quant_fefo present.")
