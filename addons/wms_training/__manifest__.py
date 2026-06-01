{
    "name": "WMS — Training & Help Center",
    "version": "19.0.1.1.0",
    "summary": "Beginner-friendly in-app help: searchable Help Center, role training, "
    "terminology, workflow tutorials, training videos, and a Beginner Mode toggle.",
    "depends": ["wms_location", "web"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "views/wms_help_article_views.xml",
        "views/res_users_views.xml",
        "data/help_articles.xml",
    ],
    "installable": True,
    "application": False,
}
