"""Product Master training set — the Help Center articles added to close the
documentation gap the operational acceptance test found (the new Families /
Brands / Forms registers, structured SKU, PRD code, guided wizard, policy).

Asserts the articles loaded, are categorised + audienced sensibly, have unique
slugs, and that the create/policy guides are admin-targeted.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_help_product_master")
class TestHelpProductMaster(TransactionCase):
    SLUGS = [
        "product-master-overview",
        "create-product-guided",
        "product-master-policy",
        "what-is-a-family",
        "what-is-a-brand",
        "what-is-a-form",
        "structured-sku",
        "what-is-prd-code",
        "sku-barcode-freeze",
        "sku-already-exists",
    ]

    def setUp(self):
        super().setUp()
        self.Article = self.env["wms.help.article"]

    def test_all_articles_loaded(self):
        found = self.Article.search([("slug", "in", self.SLUGS)])
        self.assertEqual(
            len(found),
            len(self.SLUGS),
            "every Product Master help article should load: missing %s"
            % (set(self.SLUGS) - set(found.mapped("slug"))),
        )

    def test_categories_and_audience_valid(self):
        valid_cat = dict(self.Article._fields["category"].selection)
        valid_aud = dict(self.Article._fields["audience"].selection)
        for art in self.Article.search([("slug", "in", self.SLUGS)]):
            self.assertIn(art.category, valid_cat, art.slug)
            self.assertIn(art.audience, valid_aud, art.slug)
            self.assertTrue(art.body, "%s must have body content" % art.slug)

    def test_create_and_policy_are_admin(self):
        for slug in ("create-product-guided", "product-master-policy"):
            art = self.Article.search([("slug", "=", slug)], limit=1)
            self.assertEqual(art.audience, "admin", "%s should target admins" % slug)

    def test_terminology_is_searchable_by_everyone(self):
        # A storekeeper reads SKUs on labels, so the terminology articles are 'all'.
        fam = self.Article.search([("slug", "=", "what-is-a-family")], limit=1)
        self.assertEqual(fam.category, "terminology")
        self.assertEqual(fam.audience, "all")
