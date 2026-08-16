"""
The manage page must not render a stored watch title as markup.

Watch titles were caller-supplied until the server started owning them, so the
existing rows can contain anything. Two things follow:

  * the canonical title wins wherever we have one, so a row created before the
    change reads the same as one created today;
  * whatever is left (a slug that has dropped out of the dataset keeps its
    stored title) is escaped.

Also pins the Remove button shape. It used to be an inline
`onclick="removeVariety('<slug>')"`, i.e. a value concatenated into a JS
string literal inside an HTML attribute. The slug is now validated on the way
in, but a data attribute plus a delegated listener is the shape that stays safe
without depending on that.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


subscribe_server = _load(SCRAPERS / "subscribe_server.py")

from stocklib.variety_index import INDEX_FILENAME, write_variety_index  # noqa: E402


class _StubHandler:
    """Just enough of SubscribeHandler to call the row renderer.

    _variety_watch_rows only reaches self._get_variety_watches, so the DB does
    not need to exist.
    """

    def __init__(self, watches):
        self._watches = watches

    def _get_variety_watches(self, email):
        return self._watches


def render(watches, index_titles):
    tmp = tempfile.TemporaryDirectory()
    try:
        path = Path(tmp.name) / INDEX_FILENAME
        write_variety_index(path, index_titles)
        subscribe_server.VARIETY_INDEX_FILE = path
        return subscribe_server.SubscribeHandler._variety_watch_rows(
            _StubHandler(watches), "watcher@example.com")
    finally:
        tmp.cleanup()


class WatchRowRenderingTests(unittest.TestCase):
    def test_canonical_title_replaces_a_stored_one(self):
        html = render(
            [{"slug": "avocado-hass", "title": "whatever the client sent",
              "species": "avocado"}],
            {"avocado-hass": "Avocado - Hass"},
        )
        self.assertIn("Avocado - Hass", html)
        self.assertNotIn("whatever the client sent", html)

    def test_a_hostile_stored_title_is_escaped_when_we_have_no_canonical_one(self):
        html = render(
            [{"slug": "gone-forever", "title": '<img src=x onerror="alert(1)">',
              "species": "gone"}],
            {"avocado-hass": "Avocado - Hass"},
        )
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_the_watch_is_still_listed_when_its_slug_left_the_dataset(self):
        """Dropping the row would be worse than showing a stale name: the
        person could no longer find the alert to remove it."""
        html = render(
            [{"slug": "gone-forever", "title": "Gone - Forever", "species": "gone"}],
            {"avocado-hass": "Avocado - Hass"},
        )
        self.assertIn("Gone - Forever", html)
        self.assertIn('data-slug="gone-forever"', html)

    def test_remove_button_uses_a_data_attribute_not_an_inline_onclick(self):
        html = render(
            [{"slug": "avocado-hass", "title": "Avocado - Hass", "species": "avocado"}],
            {"avocado-hass": "Avocado - Hass"},
        )
        self.assertNotIn("onclick", html)
        self.assertIn('class="remove-watch"', html)
        self.assertIn('data-slug="avocado-hass"', html)

    def test_empty_list_renders_a_message_not_a_crash(self):
        html = render([], {"avocado-hass": "Avocado - Hass"})
        self.assertIn("None.", html)


class ServerIndexWiringTests(unittest.TestCase):
    def test_server_reads_the_index_from_the_state_dir(self):
        """Not from the web root and not from the snapshot dir: it sits beside
        subscribers.json and manage_link_sends.json, which is where
        build_variety_pages.py writes it."""
        self.assertEqual(subscribe_server.VARIETY_INDEX_FILE,
                         Path("/opt/dale/data") / INDEX_FILENAME)

    def test_server_does_not_import_the_parser(self):
        """cultivar_parsing is heavy and would join deploy.sh's restart
        fingerprint list. A flat JSON index keeps the server dumb."""
        source = (SCRAPERS / "subscribe_server.py").read_text()
        self.assertNotIn("import cultivar_parsing", source)
        self.assertNotIn("from cultivar_parsing", source)


if __name__ == "__main__":
    unittest.main()
