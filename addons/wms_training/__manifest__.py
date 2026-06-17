{
    "name": "WMS — Training & Help Center",
    "version": "19.0.1.13.0",
    "summary": "Beginner-friendly in-app help: searchable Help Center, role training, "
    "terminology, workflow tutorials, training videos, and a Beginner Mode toggle.",
    "depends": ["wms_location", "web", "wms_barcode", "wms_reports", "wms_repair_damage"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "views/wms_help_article_views.xml",
        "views/res_users_views.xml",
        "views/wms_repair_scrap_views.xml",
        "data/help_articles.xml",
        "data/help_articles_product_master.xml",
        "data/guided_tours.xml",
        "data/training_index.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
