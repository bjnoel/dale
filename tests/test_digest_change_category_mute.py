"""
Regression tests for the empty-`categories` half of the DAL-260 defect.

DAL-260 found that a subscriber with `plant_categories == []` was dropped from
every digest while the UI told them the opposite, and guarded that field in
subscribe_server.update_preferences. Both senders skip on `not cats or not
pcats`, so the identical trap was still open on `categories`, and it caught a
third subscriber: they confirmed, spent 35 seconds on the confirm-success
picker, moved themselves from daily to weekly, and saved with all three
"What to include?" boxes unticked. The picker pre-ticks all three and carried no
warning. They then received nothing through two Sunday sends.

These cover the guard, the missing warning on the picker, and the two places
send_weekly_digest.py stayed quiet because the DAL-260 fix only touched
send_digest.py.

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

    def send_json(self, status, data):
        self.response = (status, data)

    def send_html(self, status, body):
        self.response = (status, body)


def _post(payload):
    h = _FakeHandler(payload)

    class _RFile:
        def __init__(self, b):
            self._b = b

        def read(self, n):
            return self._b[:n]

    h.rfile = _RFile(h._payload)
    subscribe_server.verify_unsubscribe_token = lambda email, token: True
    subscribe_server.load_subscribers = lambda: [{"email": "a@b.com", "state": "ALL"}]
    subscribe_server.save_subscribers = lambda subs: None
    h.do_POST()
    return h.response


BASE = {
    "email": "a@b.com",
    "token": "t",
    "action": "update_preferences",
    "state": "ALL",
}


class EmptyChangeCategoriesRejected(unittest.TestCase):
    def test_the_exact_payload_that_muted_a_real_subscriber_is_refused(self):
        # What the confirm-success picker sent: weekly, fruit, nothing ticked.
        status, data = _post({
            **BASE,
            "state": "VIC",
            "categories": [],
            "plant_categories": ["fruit"],
            "frequency": "weekly",
        })
        self.assertEqual(status, 400)
        self.assertIn("at least one update type", data["error"])

    def test_error_names_off_as_the_supported_way_to_stop(self):
        _, data = _post({**BASE, "categories": [], "frequency": "daily"})
        self.assertIn("off", data["error"].lower())

    def test_empty_categories_allowed_when_turning_digest_off(self):
        status, _ = _post({**BASE, "categories": [], "frequency": "off"})
        self.assertEqual(status, 200)

    def test_unknown_values_that_normalise_to_empty_are_rejected(self):
        # ["seaweed"] filters down to [], which would mute just as silently.
        status, _ = _post({**BASE, "categories": ["seaweed"], "frequency": "weekly"})
        self.assertEqual(status, 400)

    def test_one_ticked_box_still_saves(self):
        status, _ = _post({**BASE, "categories": ["price_drops"], "frequency": "weekly"})
        self.assertEqual(status, 200)

    def test_omitting_categories_entirely_is_untouched(self):
        # A caller that never mentions categories must not be second-guessed:
        # a missing key means "all three", not "none".
        status, _ = _post({**BASE, "frequency": "weekly"})
        self.assertEqual(status, 200)

    def test_the_plant_guard_still_fires(self):
        status, data = _post({**BASE, "plant_categories": [], "frequency": "weekly"})
        self.assertEqual(status, 400)
        self.assertIn("at least one plant type", data["error"])


class ConfirmSuccessPickerWarns(unittest.TestCase):
    """The picker pre-ticks every box and had no hint that unticking them all
    cancels the digest. The manage page has carried that line since DAL-260."""

    def _render(self):
        captured = {}

        class Fake(subscribe_server.SubscribeHandler):
            def __init__(self):
                pass

            def _lookup_subscriber_state(self, email):
                return "VIC"

            def send_html(self, status, body):
                captured["body"] = body

        Fake().send_confirm_success_page("a@b.com")
        return captured["body"]

    def test_change_type_section_says_keep_one_ticked(self):
        body = self._render()
        self.assertIn("Unticking all three stops the digest entirely", body)

    def test_change_type_section_points_at_off(self):
        self.assertIn('choose\n    "Off" above', self._render())

    def test_plant_section_says_keep_one_ticked(self):
        self.assertIn("Unticking both stops the digest entirely", self._render())

    def test_boxes_are_still_pre_ticked(self):
        # The warning is the fix, not unchecking the defaults.
        body = self._render()
        self.assertEqual(body.count('name="categories"'), 3)
        self.assertEqual(body.count('name="categories" value="new_products" checked'), 1)

    def test_rendered_page_has_no_unrendered_format_braces(self):
        body = self._render()
        self.assertNotIn("{{", body)
        self.assertNotIn("}}", body)


class WeeklySenderSaysWhoItDrops(unittest.TestCase):
    """DAL-260 made send_digest.py loud about this and left the weekly sender
    printing a bare count and a dry run that named people it would not mail."""

    SRC = (SCRAPERS / "send_weekly_digest.py").read_text()

    def test_skip_branch_warns_on_stderr_with_the_addresses(self):
        self.assertIn("WARNING: permanently skipping", self.SRC)
        self.assertIn("file=sys.stderr", self.SRC)

    def test_skip_warning_names_the_muted_addresses(self):
        self.assertIn('names = ", ".join(s["email"] for s in bucket_subscribers)', self.SRC)

    def test_dry_run_does_not_claim_it_would_send_to_a_muted_subscriber(self):
        self.assertIn("Would SKIP (nothing selected)", self.SRC)

    def test_both_senders_skip_on_the_same_condition(self):
        # If these ever diverge, a guard written against one is wrong for the other.
        self.assertIn("if not cats or not pcats:", self.SRC)
        self.assertIn("if not cats or not pcats:", (SCRAPERS / "send_digest.py").read_text())


class EmptyCategoriesStillMeansNothing(unittest.TestCase):
    def test_empty_list_resolves_to_nothing(self):
        self.assertEqual(set(send_digest.get_subscriber_categories({"categories": []})), set())

    def test_missing_key_still_defaults_to_all_three(self):
        self.assertEqual(
            set(send_digest.get_subscriber_categories({})),
            {"new_products", "price_drops", "back_in_stock"},
        )


if __name__ == "__main__":
    unittest.main()
