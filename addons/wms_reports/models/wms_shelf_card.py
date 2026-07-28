"""Printable shelf cards — the digital replacement for the hand-written
whiteboard cards the trust keeps on every shelf (product, quantity, batch
and expiry, "use first" hint).

The operator selects one or more slots / floor zones and prints; each
location gets one card page listing every product it holds with per-batch
quantities sorted earliest-expiry-first. The card carries the slot and
product barcodes so the shelf itself becomes scannable."""

from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def wms_shelf_card_data(self):
        """Card payload for ONE location: a list of product blocks::

            [{"product": product, "qty": 12.0, "uom": "Units",
              "loose": 2.0,           # quantity carrying no batch
              "lots": [{"name": "LOT-A", "qty": 10.0,
                        "expiry": date|False, "use_first": True}, ...]}]

        Lots sort earliest-expiry-first (expiry-less lots last) and the
        first dated lot is flagged ``use_first`` — the FEFO hint the
        hand-written cards can't give. ``expiration_date`` only exists
        when product_expiry is installed, so read it defensively.
        """
        self.ensure_one()
        has_expiry = "expiration_date" in self.env["stock.lot"]._fields
        far_future = fields.Datetime.from_string("9999-12-31 00:00:00")
        quants = self.env["stock.quant"].search(
            [("location_id", "=", self.id), ("quantity", ">", 0)]
        )
        cards = []
        for product in quants.mapped("product_id").sorted("display_name"):
            pquants = quants.filtered(lambda q: q.product_id == product)
            lots = []
            for lot in pquants.mapped("lot_id"):
                expiry = lot.expiration_date if has_expiry else False
                lots.append(
                    {
                        "name": lot.name,
                        "qty": sum(pquants.filtered(lambda q: q.lot_id == lot).mapped("quantity")),
                        "expiry": expiry and expiry.date(),
                        "_sort": expiry or far_future,
                        "use_first": False,
                    }
                )
            lots.sort(key=lambda item: item["_sort"])
            for item in lots:
                del item["_sort"]
            if lots and lots[0]["expiry"]:
                lots[0]["use_first"] = True
            cards.append(
                {
                    "product": product,
                    "qty": sum(pquants.mapped("quantity")),
                    "uom": product.uom_id.name,
                    "loose": sum(pquants.filtered(lambda q: not q.lot_id).mapped("quantity")),
                    "lots": lots,
                }
            )
        return cards
