"""Primal's product URLs 301 to a new slug and the 301 drops the query string,
so ?ref=treestock on the API's old-form URL never reached GoAffPro
(found 2026-11-14). affiliate() must emit the redirect TARGET with the ref."""
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib import utm  # noqa: E402
import ecwid_scraper  # noqa: E402

OLD = "https://primalfruits.com.au/products/AXP-Jaboticaba-p805729003"
NEW = "https://primalfruits.com.au/products/axp-jaboticaba"
PRIMAL = ecwid_scraper.NURSERIES["primal-fruits"]


class _DataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = os.environ.get("DALE_DATA_DIR")
        os.environ["DALE_DATA_DIR"] = self.tmp.name
        utm._link_redirects.cache_clear()

    def tearDown(self):
        if self._env is None:
            os.environ.pop("DALE_DATA_DIR", None)
        else:
            os.environ["DALE_DATA_DIR"] = self._env
        utm._link_redirects.cache_clear()
        self.tmp.cleanup()

    def write_map(self, mapping):
        path = utm.link_redirects_path("primal-fruits")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapping))


class AffiliateSwapTest(_DataDir):
    def test_old_url_becomes_redirect_target_with_ref(self):
        self.write_map({OLD: NEW})
        self.assertEqual(utm.affiliate(OLD), NEW + "?ref=treestock")

    def test_outbound_keeps_utm_after_swap(self):
        self.write_map({OLD: NEW})
        self.assertEqual(
            utm.outbound(OLD, "dashboard"),
            NEW + "?ref=treestock&utm_source=treestock&utm_medium=dashboard")

    def test_already_tagged_old_url_is_still_swapped(self):
        # build-dashboard tags before serialising; a second pass over an
        # old-form URL that already carries the ref must still land on NEW.
        self.write_map({OLD: NEW})
        self.assertEqual(utm.affiliate(OLD + "?ref=treestock"),
                         NEW + "?ref=treestock")

    def test_no_map_means_old_behaviour(self):
        self.assertEqual(utm.affiliate(OLD), OLD + "?ref=treestock")

    def test_non_affiliate_untouched_even_if_mapped(self):
        daleys = "https://www.daleysfruit.com.au/fruit/sapodilla.htm"
        self.write_map({daleys: "https://example.com/x"})
        self.assertEqual(utm.affiliate(daleys), daleys)


class _Resp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    """Mimics a no-redirect opener: 3xx surfaces as HTTPError."""
    def __init__(self, table):
        self.table = table
        self.calls = []

    def open(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        status, loc = self.table[url]
        if status == 200:
            return _Resp(200)
        hdrs = Message()
        if loc:
            hdrs["Location"] = loc
        raise urllib.error.HTTPError(url, status, "x", hdrs, None)


class RefreshTest(_DataDir):
    def test_records_relative_location_as_absolute(self):
        opener = _FakeOpener({OLD: (301, "/products/axp-jaboticaba")})
        known = ecwid_scraper.refresh_link_redirects(
            "primal-fruits", PRIMAL, [{"url": OLD}],
            _opener=opener, _sleep=lambda s: None)
        self.assertEqual(known, {OLD: NEW})
        utm._link_redirects.cache_clear()
        self.assertEqual(utm.affiliate(OLD), NEW + "?ref=treestock")

    def test_known_urls_are_not_refetched(self):
        self.write_map({OLD: NEW})
        opener = _FakeOpener({})
        ecwid_scraper.refresh_link_redirects(
            "primal-fruits", PRIMAL, [{"url": OLD}],
            _opener=opener, _sleep=lambda s: None)
        self.assertEqual(opener.calls, [])

    def test_404_is_not_recorded(self):
        opener = _FakeOpener({OLD: (404, None)})
        known = ecwid_scraper.refresh_link_redirects(
            "primal-fruits", PRIMAL, [{"url": OLD}],
            _opener=opener, _sleep=lambda s: None)
        self.assertEqual(known, {})

    def test_non_affiliate_store_is_skipped(self):
        opener = _FakeOpener({})
        known = ecwid_scraper.refresh_link_redirects(
            "wild-garden-organics", ecwid_scraper.NURSERIES["wild-garden-organics"],
            [{"url": "https://wildgardenorganics.com.au/products/x-p1"}],
            _opener=opener, _sleep=lambda s: None)
        self.assertEqual((known, opener.calls), ({}, []))


if __name__ == "__main__":
    unittest.main()
