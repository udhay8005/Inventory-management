from odoo import fields, models


class WmsStorekeeper(models.Model):
    """The roster of human Store Keepers who rotate on the store desk.

    Multiple people can share a single Odoo login (e.g. one shared
    `storekeeper` account is logged in at the desk and whoever is on
    duty uses it for the day). So the Odoo user record alone doesn't
    tell us who was actually running the store.

    The Admin maintains this roster (Configuration → Store Keepers).
    Each Scan Issue picks the on-duty Store Keeper from this list, so
    the audit trail records the real human name even when the Odoo
    login is shared.
    """

    _name = "wms.storekeeper"
    _description = "Store Keeper roster entry"
    _order = "name"

    name = fields.Char(string="Name", required=True, index=True)
    phone = fields.Char(string="Phone")
    note = fields.Text(string="Notes")
    active = fields.Boolean(
        string="On the roster",
        default=True,
        help="Untick to retire a Store Keeper without deleting the historical "
        "issues that mention them.",
    )

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Each Store Keeper name must be unique on the roster.",
    )
