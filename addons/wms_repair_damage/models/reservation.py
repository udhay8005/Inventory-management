"""Shared single-product internal-transfer reservation helper.

HIGH fix (TOCTOU race + phantom deduction). The damage / repair workflows used
to do:

    picking.action_confirm()
    picking.action_assign()
    for ml in picking.move_ids.move_line_ids:
        if not ml.quantity:
            ml.quantity = ...          # force the requested qty
    picking.button_validate()

That forces the requested quantity onto the move line even when
``action_assign`` could NOT reserve it (the stock is not physically on the
source slot), posting a phantom deduction that drives on-hand negative. It also
read-then-wrote with no row lock, so a concurrent Scan Issue could grab the same
stock between reservation and validation.

This helper centralises the correct sequence (also retiring three copies of the
picking-validate boilerplate): lock the product, reserve, ABORT if the move did
not reach ``assigned``, then validate.
"""

from odoo.exceptions import UserError


def validate_reserved_or_abort(picking, product, action_label):
    """Confirm + reserve + validate a single-product internal ``picking``.

    :param picking: a freshly-created ``stock.picking`` with its move(s).
    :param product: the ``product.product`` being moved (locked FOR UPDATE).
    :param action_label: short human phrase for the error, e.g. ``"send to
        Damage"``.
    :raises UserError: if the source slot cannot fully reserve the request -
        nothing is moved.
    """
    env = picking.env
    if product:
        # Serialise against concurrent Scan Issue / Receipt on this product so
        # two operators cannot each reserve the same physical stock.
        env.cr.execute(
            "SELECT id FROM product_product WHERE id = %s FOR UPDATE",
            (product.id,),
        )
    picking.action_confirm()
    picking.action_assign()

    # If any move did not reach 'assigned', the requested quantity is not
    # physically available on the source slot. Abort rather than force a
    # phantom deduction that would drive on-hand negative.
    unreserved = picking.move_ids.filtered(lambda m: m.state != "assigned")
    if unreserved:
        requested = sum(picking.move_ids.mapped("product_uom_qty"))
        raise UserError(
            "Not enough stock to %s %s.\n"
            "Requested %g %s at %s, but the slot could not reserve that much.\n"
            "Nothing was moved - restock the slot or choose another."
            % (
                action_label,
                product.display_name,
                requested,
                product.uom_id.name,
                picking.location_id.display_name,
            )
        )

    for ml in picking.move_ids.move_line_ids:
        if not ml.quantity:
            ml.quantity = ml.quantity_product_uom or picking.move_ids[:1].product_uom_qty
    picking.button_validate()
