from odoo import fields, models


class WmsAnimal(models.Model):
    """Lightweight animal register (cow / bull / ...) for Scan Issue.

    Optional everywhere — an issue can name the animal it was for (a
    treatment, a feed ration) but is never required to. ``tag`` is the
    ear-tag / token number; the UNIQUE constraint tolerates many NULL
    tags (Postgres treats NULLs as distinct) so only entered tags must
    be unique. ``shed`` is a free Char on purpose: sheds are not always
    storage locations, so animals are not coupled to the location tree.
    """

    _name = "wms.animal"
    _description = "Animal register"
    _order = "name"

    name = fields.Char(required=True, index=True)
    tag = fields.Char(index=True, help="Ear-tag / token number.")
    shed = fields.Char()
    age_class = fields.Selection(
        [
            ("calf", "Calf"),
            ("heifer", "Heifer"),
            ("cow", "Cow"),
            ("dry_pregnant", "Dry / Pregnant"),
            ("bull", "Bull"),
            ("ox", "Ox"),
            ("retired", "Retired"),
        ],
    )
    active = fields.Boolean(default=True)

    _tag_unique = models.Constraint(
        "UNIQUE(tag)",
        "Animal tag must be unique.",
    )
