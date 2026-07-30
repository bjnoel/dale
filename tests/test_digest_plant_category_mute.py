"""
Regression tests for DAL-260: a subscriber with plant_categories == [] was
silently dropped from every daily digest while the UI told them the opposite.

Two daily subscribers sat in that state (one for 10 days, one from signup and
never received a single digest). send_digest.py skips the bucket, which is
correct behaviour on its own, but nothing surfaced it: the preferences page
confirmed "fruit only, daily digest", the dry run printed "Would send to", and
the live run printed a bare count.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
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
send_digest = _load(SCRAPERS / "send_digest.py")


class _FakeHandler(subscribe_server.SubscribeHandler):
    """Drives do_POST without a socket. Captures the response instead."""

    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()
        self.headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(self._payload)),
        }
        self.path = "/api/subscribe"
        self.response = None

    def rfile_read(self, n):
        return self._payload[:n]

    def send_json(self, status, data):
        self.response = (status, data)

    def send_html(self, status, body):
        self.response = (status, body)


def _post(payload, monkey):
    h = _FakeHandler(payload)

    class _RFile:
        def __init__(self, b):
            self._b = b

        def read(self, n):
            return self._b[:n]

    h.rfile = _RFile(h._payload)
    monkey(subscribe_server)
    h.do_POST()
    return h.response


def _stub(mod):
    mod.verify_unsubscribe_token = lambda email, token: True
    mod.load_subscribers = lambda: [{"email": "a@b.com", "state": "ALL"}]
    mod.save_subscribers = lambda subs: None


BASE = {
    "email": "a@b.com",
    "token": "t",
    "action": "update_preferences",
    "state": "ALL",
}


class EmptyPlantCategoriesRejected(unittest.TestCase):
    def test_empty_plant_categories_is_rejected(self):
        status, data = _post({**BASE, "plant_categories": [], "frequency": "daily"}, _stub)
        self.assertEqual(status, 400)
        self.assertIn("at least one plant type", data["error"])

    def test_error_names_off_as_the_supported_way_to_stop(self):
        _, data = _post({**BASE, "plant_categories": [], "frequency": "daily"}, _stub)
        self.assertIn("off", data["error"].lower())

    def test_empty_plant_categories_allowed_when_turning_digest_off(self):
        status, _ = _post({**BASE, "plant_categories": [], "frequency": "off"}, _stub)
        self.assertEqual(status, 200)

    def test_unknown_values_that_normalise_to_empty_are_rejected(self):
        # ["kelp"] filters down to [], which would mute just as silently.
        status, _ = _post({**BASE, "plant_categories": ["kelp"], "frequency": "daily"}, _stub)
        self.assertEqual(status, 400)

    def test_valid_selection_still_saves(self):
        status, _ = _post({**BASE, "plant_categories": ["fruit"], "frequency": "daily"}, _stub)
        self.assertEqual(status, 200)

    def test_omitting_plant_categories_entirely_is_untouched(self):
        status, _ = _post({**BASE, "frequency": "weekly"}, _stub)
        self.assertEqual(status, 200)


class PreferencesPageTellsTheTruth(unittest.TestCase):
    """The saved-summary line claimed 'fruit only' whenever bush tucker was
    absent, including when the user had ticked nothing at all."""

    def _render(self, plant_categories):
        captured = {}

        class Fake(subscribe_server.SubscribeHandler):
            def __init__(self):
                pass

            def send_html(self, status, body):
                captured["body"] = body

        Fake().send_preferences_page(
            "a@b.com", "tok", "VIC", ["new_products"], plant_categories, "daily"
        )
        return captured["body"]

    def test_summary_has_a_branch_for_nothing_selected(self):
        js = self._render(["fruit"])
        self.assertIn("plant_categories.length === 0", js)
        self.assertIn("no plant types", js)

    def test_summary_does_not_claim_fruit_when_only_bush_tucker(self):
        self.assertIn("bush tucker only", self._render(["bush_tucker"]))

    def test_rendered_page_has_no_unrendered_format_braces(self):
        js = self._render(["fruit"])
        self.assertNotIn("{{", js)
        self.assertNotIn("}}", js)


class DigestSkipsAndSaysSo(unittest.TestCase):
    def test_empty_plant_categories_resolves_to_nothing(self):
        pcats = send_digest.get_subscriber_plant_categories({"plant_categories": []})
        self.assertEqual(set(pcats), set())

    def test_missing_plant_categories_still_defaults_to_fruit(self):
        pcats = send_digest.get_subscriber_plant_categories({})
        self.assertEqual(set(pcats), {"fruit"})

    def test_skip_branch_warns_on_stderr_with_the_addresses(self):
        src = (SCRAPERS / "send_digest.py").read_text()
        self.assertIn("WARNING: permanently skipping", src)
        self.assertIn("file=sys.stderr", src)

    def test_dry_run_does_not_claim_it_would_send_to_a_muted_subscriber(self):
        src = (SCRAPERS / "send_digest.py").read_text()
        self.assertIn("Would SKIP (nothing selected)", src)


if __name__ == "__main__":
    unittest.main()
