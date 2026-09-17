"""Tests for the treestock origin access-log summary (DAL-294).

The log exists because Plausible is a client-side tag and therefore blind to
every crawler, every curl, and every fetch of /shipping-reachability.json.

Two of these tests are about privacy rather than analysis, and they are the ones
worth keeping. The Caddyfile makes two promises in a comment: no query string
(because /manage.html carries an HMAC token and a subscriber's email) and no
client IP (because it arrives in four different headers and Go canonicalises
header names, so a delete written as Cf-Connecting-IP silently does nothing).
A comment is not a test. These are.
"""

import gzip
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "autonomous"))

import access_log  # noqa: E402


def record(ts, uri="/", ua="Mozilla/5.0 (X11) Chrome/120", status=200, headers=None):
    hdrs = {"User-Agent": [ua]}
    if headers:
        hdrs.update(headers)
    return json.dumps({
        "level": "info", "ts": ts, "msg": "handled request",
        "request": {"proto": "HTTP/2.0", "method": "GET",
                    "host": "treestock.com.au", "uri": uri, "headers": hdrs},
        "status": status, "size": 100,
    })


class ClassifyTests(unittest.TestCase):
    def test_the_six_ai_agents_dec_269_named_are_all_classified_ai(self):
        for ua in ["GPTBot/1.2", "OAI-SearchBot/1.0", "ChatGPT-User/1.0",
                   "ClaudeBot/1.0", "PerplexityBot/1.0", "CCBot/2.0"]:
            self.assertEqual(access_log.classify_agent(ua), "ai", ua)

    def test_googlebot_is_search_not_ai_even_though_it_says_google(self):
        ua = ("Mozilla/5.0 (compatible; Googlebot/2.1; "
              "+http://www.google.com/bot.html)")
        self.assertEqual(access_log.classify_agent(ua), "search")

    def test_google_extended_is_ai_not_search(self):
        # Ordering matters: Google-Extended is the AI-training agent and must not
        # be counted as crawl budget spent on search.
        self.assertEqual(access_log.classify_agent("Google-Extended"), "ai")

    def test_a_real_browser_is_browser_and_an_empty_ua_is_other(self):
        self.assertEqual(access_log.classify_agent(
            "Mozilla/5.0 (Macintosh) AppleWebKit/605 Safari/605.1"), "browser")
        self.assertEqual(access_log.classify_agent(""), "other")

    def test_an_unknown_thing_calling_itself_a_bot_is_not_silently_a_browser(self):
        self.assertEqual(access_log.classify_agent("SomeNewCrawler/1.0 bot"),
                         "other_bot")

    def test_path_types_separate_the_tail_from_the_earners(self):
        self.assertEqual(access_log.path_type("/variety/pink-lady.html"), "variety")
        self.assertEqual(access_log.path_type("/species/olive.html"), "species")
        self.assertEqual(access_log.path_type(
            "/buy-olive-trees-western-australia.html"), "species+state")
        self.assertEqual(access_log.path_type("/"), "homepage")


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "treestock-access.log")
        self.now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        self.ts = self.now.timestamp()

    def write(self, lines, path=None):
        with open(path or self.path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def summarise(self, hours=24):
        return access_log.summarise(self.now - timedelta(hours=hours), self.path)

    def test_a_missing_log_is_unavailable_not_zero(self):
        # DEC-339: an absence and a real zero must not render identically. A
        # summary saying "0 AI agents" when logging is off is a false all-clear.
        s = access_log.summarise(self.now, os.path.join(self.tmp.name, "nope.log"))
        self.assertFalse(s["available"])
        self.assertEqual(access_log.render_lines(s), [])

    def test_counts_by_class_and_status(self):
        self.write([
            record(self.ts, "/species/olive.html"),
            record(self.ts, "/species/fig.html", ua="Googlebot/2.1"),
            record(self.ts, "/nope.html", ua="curl/8.5.0", status=404),
        ])
        s = self.summarise()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["by_class"]["browser"], 1)
        self.assertEqual(s["by_class"]["search"], 1)
        self.assertEqual(s["by_class"]["tool"], 1)
        self.assertEqual(s["by_status"][404], 1)

    def test_dataset_fetches_are_counted_by_who_fetched_them(self):
        # The DAL-254 question: is the CC BY dataset actually being reused?
        self.write([
            record(self.ts, "/shipping-reachability.json", ua="curl/8.5.0"),
            record(self.ts, "/shipping-reachability.json", ua="GPTBot/1.2"),
            record(self.ts, "/species/olive.html"),
        ])
        s = self.summarise()
        watched = s["watched"]["/shipping-reachability.json"]
        self.assertEqual(sum(watched.values()), 2)
        self.assertEqual(watched["tool"], 1)
        self.assertEqual(watched["ai"], 1)
        self.assertIn("/shipping-reachability.json: 2 fetches",
                      "\n".join(access_log.render_lines(s)))

    def test_search_crawl_is_split_by_page_type(self):
        # The DAL-250 question crawl budget was recorded UNKNOWN for.
        self.write([
            record(self.ts, "/variety/a.html", ua="Googlebot/2.1"),
            record(self.ts, "/variety/b.html", ua="Googlebot/2.1"),
            record(self.ts, "/species/olive.html", ua="bingbot/2.0"),
            record(self.ts, "/variety/c.html"),  # a browser, must not be counted
        ])
        s = self.summarise()
        self.assertEqual(s["search_page_types"]["variety"], 2)
        self.assertEqual(s["search_page_types"]["species"], 1)

    def test_records_outside_the_window_are_excluded(self):
        old = (self.now - timedelta(hours=48)).timestamp()
        self.write([record(old, "/"), record(self.ts, "/")])
        self.assertEqual(self.summarise(24)["total"], 1)
        self.assertEqual(self.summarise(72)["total"], 2)

    def test_a_rolled_log_is_still_read(self):
        # Caddy rolls to <stem>-<timestamp>.log.gz beside the original. Reading
        # only the live file silently halves a window that straddles a roll.
        rolled = os.path.join(self.tmp.name,
                              "treestock-access-2026-09-17T11-00-00.000.log.gz")
        with gzip.open(rolled, "wt") as f:
            f.write(record(self.ts, "/rolled.html") + "\n")
        self.write([record(self.ts, "/live.html")])
        self.assertEqual(self.summarise()["total"], 2)

    def test_a_truncated_last_line_does_not_break_the_summary(self):
        with open(self.path, "w") as f:
            f.write(record(self.ts, "/") + "\n")
            f.write('{"level":"info","ts":17896')
        self.assertEqual(self.summarise()["total"], 1)


class PrivacyTests(unittest.TestCase):
    """The Caddyfile's two promises, asserted rather than trusted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "treestock-access.log")
        self.now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

    def test_an_ip_shaped_header_value_is_reported_not_ignored(self):
        # If Cloudflare ever adds a fifth IP-bearing header, or a delete is
        # written in the wrong casing, the digest must say so out loud rather
        # than the comment in the Caddyfile quietly becoming false.
        with open(self.path, "w") as f:
            f.write(record(self.now.timestamp(), "/",
                           headers={"Cf-Connecting-Ip": ["203.0.113.9"]}) + "\n")
        s = access_log.summarise(self.now - timedelta(hours=1), self.path)
        self.assertEqual(s["leaked_ip_headers"]["Cf-Connecting-Ip"], 1)
        self.assertIn("PRIVACY", "\n".join(access_log.render_lines(s)))

    def test_a_clean_log_reports_no_privacy_problem(self):
        with open(self.path, "w") as f:
            f.write(record(self.now.timestamp(), "/",
                           headers={"Cf-Ray": ["a3c8fee34ec48a38-FRA"],
                                    "Cf-Ipcountry": ["AU"]}) + "\n")
        s = access_log.summarise(self.now - timedelta(hours=1), self.path)
        self.assertEqual(s["leaked_ip_headers"], {})
        self.assertNotIn("PRIVACY", "\n".join(access_log.render_lines(s)))


class CaddyfileTests(unittest.TestCase):
    """The recording in infrastructure/ is captured from the live box weekly.
    These assert the shape the summariser depends on, so a hand edit that drops
    a filter shows up as a red test rather than as a token on disk.
    """

    def setUp(self):
        self.text = (REPO_ROOT / "infrastructure" / "Caddyfile").read_text()

    def test_the_query_string_is_stripped(self):
        # /manage.html?token=<hmac>&email=<address>. Without this the log is a
        # file of working subscriber-management credentials.
        self.assertIn('request>uri regexp "\\?.*$" ""', self.text)

    def test_every_header_a_client_ip_arrives_in_is_deleted(self):
        for header in ("Cf-Connecting-Ip", "X-Forwarded-For",
                       "True-Client-Ip", "Forwarded"):
            self.assertIn(f"request>headers>{header} delete", self.text)

    def test_ip_header_deletes_use_gos_canonical_casing(self):
        # Go canonicalises to Cf-Connecting-Ip. A filter written as
        # Cf-Connecting-IP parses fine, validates fine, and does nothing.
        self.assertNotIn("Cf-Connecting-IP delete", self.text)
        self.assertNotIn("True-Client-IP delete", self.text)

    def test_the_log_file_is_readable_by_the_process_that_summarises_it(self):
        self.assertIn("mode 0644", self.text)


if __name__ == "__main__":
    unittest.main()
