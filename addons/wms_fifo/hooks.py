import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Ensure FIFO removal is active on every warehouse's stock location and
    create the partial index for fast FIFO scans.
    """
    # Set FIFO removal strategy on each warehouse Stock location
    fifo = env.ref("stock.removal_fifo", raise_if_not_found=False)
    if fifo:
        for wh in env["stock.warehouse"].search([]):
            wh.lot_stock_id.removal_strategy_id = fifo.id
        _logger.info(
            "wms_fifo: FIFO applied to %d warehouses", len(env["stock.warehouse"].search([]))
        )

    # Fast FIFO scan: partial index limited to live quants.
    env.cr.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quant_fifo
        ON stock_quant (product_id, in_date)
        WHERE quantity > 0;
        """
    )
    _logger.info("wms_fifo: idx_quant_fifo present.")
