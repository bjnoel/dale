"""
Tests for tools/autonomous/image_advisories.py, the weekly Docker image check.

Plausible CE ran v3.2.0 for four and a half months after CVE-2026-8467 was fixed
in v3.2.1, and was mined on from 2026-09-25. The fixtures below are that
advisory as GitHub returned it, and the containers that were running.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "autonomous"))

import image_advisories as ia  # noqa: E402

NOW = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)

STORYBOOK = {
    "ghsa_id": "GHSA-mhcv-h7gf-57cf", "cve_id": "CVE-2026-8467", "severity": "critical",
    "summary": "Unauthenticated remote code execution via /storybook endpoint",
    "html_url": "https://github.com/plausible/analytics/security/advisories/GHSA-mhcv-h7gf-57cf",
    "withdrawn_at": None,
    "vulnerabilities": [{"vulnerable_version_range": ">=3 and < 3.2.1",
                         "patched_versions": "3.2.1"}],
}


# Real, 2026-10-01: one entry per ClickHouse release line. The first live run
# read it flat and flagged 24.12.6.70, whose own line was fixed at 24.12.5.65.
CLICKHOUSE_1385 = {
    "ghsa_id": "GHSA-5phv-x8x4-83x5", "cve_id": "CVE-2025-1385", "severity": "high",
    "summary": "Fail input validation in clickhouse-library-bridge API could lead to RCE",
    "html_url": "https://github.com/ClickHouse/ClickHouse/security/advisories/GHSA-5phv-x8x4-83x5",
    "withdrawn_at": None,
    "vulnerabilities": [{"vulnerable_version_range": f"< {v}", "patched_versions": v}
                        for v in ("24.3.18.6", "24.8.14.27", "24.11.5.34", "24.12.5.65", "25.1.5.5")],
}


def fake_run(plausible_tag="v3.2.0", extra=(), built="2026-05-15T09:19:45Z",
             clickhouse="24.12.6.70"):
    # Shaped like the real commands: `docker ps` has no image-id field (that
    # assumption crashed the first live run), so ids come from `docker inspect`.
    rows = [f"plausible-plausible-1\tghcr.io/plausible/community-edition:{plausible_tag}",
            "plausible-plausible_events_db-1\tclickhouse/clickhouse-server:24.12-alpine",
            *extra]
    ids = {"plausible-plausible-1": "sha256:p", "plausible-plausible_events_db-1": "sha256:c"}

    def run(cmd):
        if cmd[:2] == ["docker", "ps"]:
            assert "ImageID" not in cmd[-1], "docker ps --format has no ImageID field"
            return "\n".join(rows) + "\n"
        if cmd[:2] == ["docker", "inspect"]:
            return ids.get(cmd[-1], "sha256:other") + "\n"
        if cmd[:3] == ["docker", "image", "inspect"]:
            return (built if cmd[3] != "sha256:c" else "2025-03-11T12:17:16Z") + "\n"
        if cmd[:2] == ["docker", "exec"]:
            return clickhouse + "\n"
        raise AssertionError(cmd)
    return run


def fake_fetch(by_repo, latest_plausible="v3.2.1"):
    def fetch(url):
        if url.endswith("/releases/latest"):
            return {"tag_name": latest_plausible, "published_at": "2026-05-15T09:00:00Z"}
        for repo, advisories in by_repo.items():
            if f"/repos/{repo}/" in url:
                if isinstance(advisories, Exception):
                    raise advisories
                return advisories
        return []
    return fetch


def of(status, severity):
    return [f for f in status["findings"] if f["severity"] == severity]


class InRange(unittest.TestCase):
    def test_the_plausible_range(self):
        r = ">=3 and < 3.2.1"
        self.assertTrue(ia.in_range((3, 2, 0), r))
        self.assertFalse(ia.in_range((3, 2, 1), r))
        self.assertFalse(ia.in_range((2, 1, 9), r))
        self.assertTrue(ia.in_range((3,), r))

    def test_comma_form_and_four_part_versions(self):
        r = ">= 24.1, < 24.3.18.7"
        self.assertTrue(ia.in_range((24, 2, 1), r))
        self.assertFalse(ia.in_range((24, 12, 6, 70), r))

    def test_release_channel_suffix(self):
        # GHSA-432f-r822-j66f, which the first live run could not read.
        self.assertFalse(ia.in_range((24, 12, 6, 70), "< v24.4.2.141-stable"))
        self.assertTrue(ia.in_range((23, 8, 1), "< v23.8.15.35-lts"))

    def test_unreadable_range_is_none_not_false(self):
        self.assertIsNone(ia.in_range((1, 0), "all versions"))
        self.assertIsNone(ia.in_range((1, 0), ""))
        self.assertIsNone(ia.in_range((1, 0), None))

    def test_parse_version_reads_tags_and_command_output(self):
        self.assertEqual(ia.parse_version("v3.2.1"), (3, 2, 1))
        self.assertEqual(ia.parse_version("postgres (PostgreSQL) 16.15"), (16, 15))
        self.assertIsNone(ia.parse_version("latest"))


class Check(unittest.TestCase):
    def run_check(self, **kw):
        fetch = kw.pop("fetch", fake_fetch({"plausible/analytics": [STORYBOOK],
                                            "ClickHouse/ClickHouse": []}))
        return ia.check(now=NOW, _run=fake_run(**kw), _fetch=fetch)

    def test_the_version_we_were_running_is_flagged(self):
        affected = of(self.run_check(plausible_tag="v3.2.0"), "affected")
        self.assertEqual(len(affected), 1)
        self.assertIn("GHSA-mhcv-h7gf-57cf", affected[0]["detail"])
        self.assertIn("Fixed in: 3.2.1", affected[0]["detail"])

    def test_the_patched_version_is_not(self):
        self.assertEqual(of(self.run_check(plausible_tag="v3.2.1"), "affected"), [])

    def test_an_unreadable_feed_is_an_error_not_a_clean_bill(self):
        status = self.run_check(fetch=fake_fetch(
            {"plausible/analytics": OSError("HTTP 403 rate limited"), "ClickHouse/ClickHouse": []}))
        self.assertEqual(of(status, "affected"), [])
        self.assertTrue(any("could not read advisories" in f["detail"] for f in of(status, "error")))

    def test_a_new_unwatched_container_is_named(self):
        status = self.run_check(extra=["cache-1\tredis:7"])
        self.assertTrue(any("redis:7" in f["detail"] for f in of(status, "notice")))

    def test_an_old_image_is_a_notice(self):
        notices = of(self.run_check(plausible_tag="v3.2.1"), "notice")
        self.assertTrue(any("clickhouse" in f["detail"] and "re-pulled" in f["detail"]
                            for f in notices), notices)

    def test_clickhouse_patched_within_its_own_line_is_not_flagged(self):
        fetch = fake_fetch({"plausible/analytics": [], "ClickHouse/ClickHouse": [CLICKHOUSE_1385]})
        self.assertEqual(of(self.run_check(fetch=fetch), "affected"), [])

    def test_clickhouse_below_its_lines_fix_is_flagged(self):
        fetch = fake_fetch({"plausible/analytics": [], "ClickHouse/ClickHouse": [CLICKHOUSE_1385]})
        affected = of(self.run_check(fetch=fetch, clickhouse="24.12.5.1"), "affected")
        self.assertEqual(len(affected), 1)
        self.assertIn("Fixed in: 24.12.5.65", affected[0]["detail"])

    def test_a_line_too_old_for_its_own_fix_is_flagged(self):
        fetch = fake_fetch({"plausible/analytics": [], "ClickHouse/ClickHouse": [CLICKHOUSE_1385]})
        self.assertEqual(len(of(self.run_check(fetch=fetch, clickhouse="23.8.1.1"), "affected")), 1)

    def test_exact_tag_gets_no_age_notice_but_a_newer_release_does(self):
        quiet = self.run_check(plausible_tag="v3.2.1")
        self.assertFalse(any(f["container"] == "plausible-plausible-1" for f in quiet["findings"]),
                         quiet["findings"])
        newer = self.run_check(plausible_tag="v3.2.1", fetch=fake_fetch(
            {"plausible/analytics": [STORYBOOK], "ClickHouse/ClickHouse": []}, latest_plausible="v3.3.0"))
        self.assertTrue(any("v3.3.0 was released" in f["detail"] for f in of(newer, "notice")))

    def test_withdrawn_advisory_is_ignored(self):
        withdrawn = dict(STORYBOOK, withdrawn_at="2026-07-01T00:00:00Z")
        status = self.run_check(fetch=fake_fetch({"plausible/analytics": [withdrawn]}))
        self.assertEqual(of(status, "affected"), [])

    def test_subject_leads_with_the_worst_severity(self):
        self.assertTrue(ia.subject_for(self.run_check(plausible_tag="v3.2.0")).startswith("SECURITY"))
        self.assertTrue(ia.subject_for(self.run_check(plausible_tag="v3.2.1")).startswith("Docker images:"))


if __name__ == "__main__":
    unittest.main()
