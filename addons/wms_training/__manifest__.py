{
    "name": "WMS — Training & Help Center",
    "version": "19.0.1.6.0",
    "summary": "Beginner-friendly in-app help: searchable Help Center, role training, "
    "terminology, workflow tutorials, training videos, and a Beginner Mode toggle.",
    "depends": ["wms_location", "web", "wms_barcode", "wms_reports"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "views/wms_help_article_views.xml",
        "views/res_users_views.xml",
        "data/help_articles.xml",
        "data/guided_tours.xml",
        "data/training_index.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
