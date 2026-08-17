"""
Curated variety identity: the deny/alias file, and the queue that needs a human.

The parser fixes handle the mechanical cases. This is for the ones that need
someone who knows the plants, and the invariants that stop a curation call
quietly costing a subscriber their alert:

  * alias resolves BEFORE deny, so a slug can be folded onto a target that is
    itself denied, and denying a target does not accidentally spare everything
    pointing at it;
  * grandfathered slugs beat deny, because that set exists to keep existing
    watchers' alerts alive and a later judgement call must not override it;
  * a malformed file raises rather than returning empty, because silently
    disabling curation looks exactly like curation having no effect.

And the review surface: prefix matching finds sibling candidates, and prefix
matching is precisely what must NOT be applied automatically
(avocado-hass-lamb is Lamb Hass, a different cultivar). /admin/varieties shows
the pairs and lets a person decide.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import cultivar_parsing as cp  # noqa: E402
import admin_view  # noqa: E402


def with_overrides(deny=(), alias=None):
    """Install an override set for the duration of a `with` block."""
    class _Ctx:
        def __enter__(self):
            self.orig = cp._OVERRIDES_CACHE
            cp._OVERRIDES_CACHE = {"deny": frozenset(deny), "alias": dict(alias or {})}

        def __exit__(self, *exc):
            cp._OVERRIDES_CACHE = self.orig
    return _Ctx()


class DenyTests(unittest.TestCase):
    def test_a_denied_slug_gets_no_page_and_no_alert_button(self):
        with with_overrides(deny=["avocado-hass"]):
            self.assertIsNone(cp.product_variety_slug("Avocado - Hass"))

    def test_everything_else_is_untouched(self):
        with with_overrides(deny=["avocado-hass"]):
            self.assertEqual(cp.product_variety_slug("Mango - R2E2"), "mango-r2e2")

    def test_grandfathering_beats_deny(self):
        """That set exists to keep existing watchers' alerts alive. A curation
        call made later must not be able to switch one off."""
        slug = "mandevilla-peach-sunrise"
        self.assertIn(slug, cp.GRANDFATHERED_VARIETY_SLUGS)
        with with_overrides(deny=[slug]):
            self.assertEqual(cp.product_variety_slug("Mandevilla - Peach Sunrise"),
                             slug)


class AliasTests(unittest.TestCase):
    def test_an_alias_folds_a_sibling_onto_the_cultivar_it_names(self):
        with with_overrides(alias={"avocado-hass": "avocado-hass-something"}):
            self.assertEqual(cp.product_variety_slug("Avocado - Hass"),
                             "avocado-hass-something")

    def test_the_display_variety_follows_the_alias(self):
        """Otherwise the page at avocado-shepard is titled "Shepard Type B"."""
        with with_overrides(alias={"avocado-hass": "avocado-lamb-hass"}):
            result = cp.canonical_cultivar("Avocado", "Hass", "Avocado - Hass")
            self.assertEqual(result[2], "avocado-lamb-hass")
            self.assertEqual(result[1], "Lamb Hass")

    def test_alias_resolves_before_deny(self):
        """Order matters both ways: a slug can be folded onto a denied target,
        and denying a target must not spare what points at it."""
        with with_overrides(deny=["avocado-lamb-hass"],
                            alias={"avocado-hass": "avocado-lamb-hass"}):
            self.assertIsNone(cp.product_variety_slug("Avocado - Hass"))

    def test_denying_the_source_of_an_alias_does_not_block_the_target(self):
        with with_overrides(deny=["avocado-hass"],
                            alias={"avocado-hass": "avocado-lamb-hass"}):
            self.assertEqual(cp.product_variety_slug("Avocado - Hass"),
                             "avocado-lamb-hass")


class FileLoadingTests(unittest.TestCase):
    def test_the_shipped_file_parses(self):
        data = cp.load_variety_overrides(cp.VARIETY_OVERRIDES_FILE)
        self.assertIsInstance(data["deny"], frozenset)
        self.assertIsInstance(data["alias"], dict)

    def test_the_shipped_file_denies_nothing_that_is_grandfathered(self):
        data = cp.load_variety_overrides(cp.VARIETY_OVERRIDES_FILE)
        self.assertEqual(set(data["deny"]) & set(cp.GRANDFATHERED_VARIETY_SLUGS),
                         set())

    def test_a_missing_file_is_simply_no_curation(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = cp.load_variety_overrides(Path(tmp) / "nope.json")
            self.assertEqual(data["deny"], frozenset())
            self.assertEqual(data["alias"], {})

    def test_a_malformed_file_raises_rather_than_disabling_curation_quietly(self):
        """A silent empty read is indistinguishable from curation having no
        effect, and the whole point of the file is that someone decided
        something."""
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "variety_overrides.json"
            for content in ("{not json", '["a", "b"]',
                            '{"deny": "avocado-hass"}',
                            '{"alias": {"a": 12}}'):
                bad.write_text(content)
                with self.subTest(content=content):
                    with self.assertRaises(cp.VarietyOverrideError):
                        cp.load_variety_overrides(bad)


class AdminReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "variety-index.json").write_text(json.dumps({
            "avocado-hass": "Avocado - Hass",
            "avocado-hass-lamb": "Avocado - Hass Lamb",
            "avocado-shepard": "Avocado - Shepard",
            "mango-r2e2": "Mango - R2E2",
        }))
        # (email, slug, title, species, added_at)
        self.watches = [
            ("a@example.com", "avocado-shepard", "Avocado - Shepard", "avocado", "x"),
            ("b@example.com", "gone-forever", "Gone - Forever", "gone", "x"),
            ("c@example.com", "gone-forever", "Gone - Forever", "gone", "x"),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def model(self):
        return admin_view.load_variety_curation(self.data, self.watches)

    def test_siblings_are_surfaced_not_folded(self):
        groups = {g["base"]: g for g in self.model()["siblings"]}
        self.assertIn("avocado-hass", groups)
        self.assertEqual([s["slug"] for s in groups["avocado-hass"]["siblings"]],
                         ["avocado-hass-lamb"])

    def test_a_watched_slug_with_no_page_is_flagged(self):
        """Each one is an alert whose link 404s. The rollout requires this
        number not to grow."""
        orphans = self.model()["orphan_watches"]
        self.assertEqual(orphans, [{"slug": "gone-forever", "watchers": 2}])

    def test_the_page_renders_and_names_the_risk(self):
        html = admin_view.render_variety_review_html({"varieties": self.model()})
        self.assertIn("gone-forever", html)
        self.assertIn("avocado-hass-lamb", html)
        self.assertIn("Lamb Hass", html)     # the warning against auto-folding

    def test_a_denied_slug_that_someone_watches_is_an_alarm(self):
        model = self.model()
        model["overrides"]["deny"] = ["avocado-shepard"]
        model["denied_but_watched"] = ["avocado-shepard"]
        html = admin_view.render_variety_review_html({"varieties": model})
        self.assertIn("Denied but watched", html)

    def test_the_queue_moved_off_the_inventory_page(self):
        """DAL-283 split the two jobs. /admin/varieties answers "what are my
        variety pages" and asks nothing; the queue is a different screen. A
        sibling suggestion reappearing on the inventory is the regression."""
        model = {"varieties": self.model(), "inventory": {"present": False,
                                                          "path": "x", "error": ""}}
        html = admin_view.render_varieties_html(model)
        self.assertNotIn("Sibling review queue", html)
        self.assertNotIn("avocado-hass-lamb", html)
        self.assertIn("/admin/varieties/review", html)

    def test_the_admin_page_does_not_drag_the_parser_into_the_server(self):
        """subscribe_server imports admin_view at module scope. Pulling
        cultivar_parsing in through it would put a heavy import on the server
        and add a module to deploy.sh's restart fingerprint."""
        source = (SCRAPERS / "admin_view.py").read_text()
        self.assertNotIn("import cultivar_parsing", source)
        self.assertNotIn("from cultivar_parsing", source)

    def test_the_tab_is_registered(self):
        for path in ("/admin/varieties", "/admin/varieties/review"):
            with self.subTest(path=path):
                self.assertIn(path, dict(admin_view.ADMIN_PAGES))
                self.assertIn(path, admin_view.ADMIN_RENDERERS)


if __name__ == "__main__":
    unittest.main()
