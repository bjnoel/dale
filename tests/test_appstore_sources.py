"""Guards for the App Store discovery source reader (search vs browse).

Every test here pins a way this measurement could quietly say something false
rather than fail. In order of how much damage each would do:

1. **An empty instances list must not read as zero traffic.** Apple takes
   24-48h to generate a snapshot and a ONE_TIME_SNAPSHOT then stops producing
   them, so "not ready" is a normal state that lasts. Summed as zero it says
   the rename killed our impressions (DEC-249).
2. **The incomplete tail must not read as a decline.** The most recent days are
   always partial. Plotted as-is, every single pull ends on a cliff.
3. **A window with no complete post-rename days must not render as a result.**
   Ten months of pre against two partial days of post is a lopsided comparison
   that looks like a finding.
4. **A missing column must not default to zero.** The failure this business has
   already shipped once, with a renamed PostHog event that reported 0/0 for
   eleven days.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (Path(__file__).resolve().parents[1]
               / "tools" / "autonomous" / "appstore_sources.py")
spec = importlib.util.spec_from_file_location("appstore_sources", MODULE_PATH)
asrc = importlib.util.module_from_spec(spec)
sys.modules["appstore_sources"] = asrc
spec.loader.exec_module(asrc)


HEADER = "\t".join([
    "Date", "App Name", "App Apple Identifier", "Event", "Page Type",
    "Page Title", "Source Type", "Source Info", "Campaign", "Engagement Type",
    "Device", "Platform Version", "Territory", "Counts", "Unique Counts",
])


def tsv_row(date, event, source, counts, unique=None):
    """One report line in Apple's real column order."""
    return "\t".join([
        date, "TreeSmith: Fruit Tree Tracker", "6761506742", event, "No page",
        "", source, "", "", "", "iPhone", "iOS 18.6", "AUS",
        str(counts), str(counts if unique is None else unique),
    ])


def report(*rows):
    return "\n".join([HEADER, *rows]) + "\n"


def record(date, source, impressions=0, page_views=0, taps=0,
           pulled_at="2026-08-23T22:40:00Z", complete=True):
    return {
        "pulled_at": pulled_at, "date": date, "source_type": source,
        "impressions": impressions, "impressions_unique": impressions,
        "page_views": page_views, "page_views_unique": page_views,
        "taps": taps, "taps_unique": taps, "complete": complete,
    }


# ── 1. Not ready is not zero ─────────────────────────────────────────────────

class TestEmptyInstancesIsNotZero(unittest.TestCase):
    """The whole point of the NotReady type."""

    def _getter(self, payloads):
        def getter(url, token):
            for fragment, payload in payloads.items():
                if fragment in url:
                    return payload
            raise AssertionError(f"unexpected URL {url}")
        return getter

    def test_empty_instances_raises_not_ready(self):
        getter = self._getter({"/instances": {"data": [], "links": {}}})
        with self.assertRaises(asrc.NotReady):
            asrc.list_instances("tok", "r15-abc", getter=getter)

    def test_not_ready_is_not_an_empty_aggregate(self):
        # The decisive assertion: the failure must be raised, never returned as
        # a zero-length result that a caller would sum to 0.
        getter = self._getter({"/instances": {"data": [], "links": {}}})
        try:
            asrc.list_instances("tok", "r15-abc", getter=getter)
        except asrc.NotReady as exc:
            self.assertIn("not zero traffic", str(exc).lower())
        else:
            self.fail("empty instances returned a value instead of raising")

    def test_instance_with_no_segments_is_also_not_ready(self):
        # A generated instance whose segments have not landed yet is the same
        # state wearing a different hat, and would aggregate to zero rows.
        getter = self._getter({
            "/reports": {"data": [{
                "id": "r15-abc",
                "attributes": {"name": asrc.DEFAULT_REPORT_NAME,
                               "category": "APP_STORE_ENGAGEMENT"},
            }], "links": {}},
            "/instances": {"data": [{
                "id": "i1",
                "attributes": {"granularity": "DAILY",
                               "processingDate": "2026-08-22"},
            }], "links": {}},
            "/segments": {"data": [], "links": {}},
        })
        config = {
            "ASC_REQUEST_ID": "req", "ASC_REPORT_NAME": asrc.DEFAULT_REPORT_NAME,
            "ASC_GRANULARITY": "DAILY",
        }
        with self.assertRaises(asrc.NotReady):
            asrc.pull(config, token="tok", getter=getter)

    def test_a_real_instance_list_is_returned_newest_first(self):
        getter = self._getter({"/instances": {"data": [
            {"id": "old", "attributes": {"granularity": "DAILY",
                                         "processingDate": "2026-08-20"}},
            {"id": "new", "attributes": {"granularity": "DAILY",
                                         "processingDate": "2026-08-22"}},
        ], "links": {}}})
        instances = asrc.list_instances("tok", "r15-abc", getter=getter)
        self.assertEqual([i["id"] for i in instances], ["new", "old"])


# ── 2. The incomplete tail ───────────────────────────────────────────────────

class TestIncompleteRecentDays(unittest.TestCase):
    def test_cutoff_is_three_days_back(self):
        # Apple publishes two different lags (two days on the API help page,
        # "within three days" on the report page). We take the longer one.
        self.assertEqual(asrc.INCOMPLETE_TAIL_DAYS, 3)
        self.assertEqual(
            asrc.last_complete_date("2026-08-23T22:40:00Z").isoformat(),
            "2026-08-20",
        )

    def test_the_cutoff_day_itself_is_complete(self):
        self.assertTrue(asrc.is_complete("2026-08-20", "2026-08-23T22:40:00Z"))
        self.assertFalse(asrc.is_complete("2026-08-21", "2026-08-23T22:40:00Z"))

    def test_to_records_stamps_completeness_per_day(self):
        totals = {
            ("2026-08-20", asrc.SOURCE_SEARCH): {"impressions": 10},
            ("2026-08-22", asrc.SOURCE_SEARCH): {"impressions": 2},
        }
        records = asrc.to_records(totals, "2026-08-23T22:40:00Z")
        by_date = {r["date"]: r for r in records}
        self.assertTrue(by_date["2026-08-20"]["complete"])
        self.assertFalse(by_date["2026-08-22"]["complete"])

    def test_incomplete_days_are_excluded_and_named_not_silently_trimmed(self):
        records = [
            record("2026-08-18", asrc.SOURCE_SEARCH, impressions=100),
            record("2026-08-22", asrc.SOURCE_SEARCH, impressions=3,
                   complete=False),
        ]
        split = asrc.split_on_rename(records, pulled_at="2026-08-23T22:40:00Z")
        # The partial day is out of the totals...
        self.assertEqual(split["pre"]["impressions"], 100)
        self.assertEqual(split["post"]["impressions"], 0)
        # ...and is named, so the reader can see WHY the series stops early
        # rather than reading the gap as a collapse in traffic.
        self.assertEqual(split["excluded_incomplete"], ["2026-08-22"])

    def test_a_partial_day_never_becomes_a_post_rename_window(self):
        # Three days of partial post-rename data still means no window.
        records = [
            record("2026-08-18", asrc.SOURCE_SEARCH, impressions=100),
            record("2026-08-20", asrc.SOURCE_SEARCH, impressions=4,
                   complete=False),
            record("2026-08-21", asrc.SOURCE_SEARCH, impressions=2,
                   complete=False),
        ]
        split = asrc.split_on_rename(records, pulled_at="2026-08-22T22:40:00Z")
        self.assertFalse(split["has_post_window"])


# ── 3. No post-rename window ─────────────────────────────────────────────────

class TestNoPostRenameWindow(unittest.TestCase):
    def test_pull_before_the_rename_completes_has_no_post_window(self):
        records = [
            record("2026-08-10", asrc.SOURCE_SEARCH, impressions=40),
            record("2026-08-10", asrc.SOURCE_BROWSE, impressions=60),
            record("2026-08-17", asrc.SOURCE_SEARCH, impressions=50),
        ]
        split = asrc.split_on_rename(records, pulled_at="2026-08-20T22:40:00Z")
        self.assertFalse(split["has_post_window"])
        self.assertEqual(split["post"]["day_count"], 0)
        self.assertEqual(split["pre"]["impressions"], 150)

    def test_the_render_says_baseline_and_never_shows_a_delta(self):
        records = [
            record("2026-08-10", asrc.SOURCE_SEARCH, impressions=40),
            record("2026-08-10", asrc.SOURCE_BROWSE, impressions=60),
        ]
        split = asrc.split_on_rename(records, pulled_at="2026-08-20T22:40:00Z")
        text = asrc.render(split)
        self.assertIn("NO POST-RENAME WINDOW YET", text)
        self.assertIn("PRE-RENAME BASELINE", text)
        # No arrow, because there is nothing to compare against.
        self.assertNotIn("->", text)

    def test_a_real_post_window_does_render_a_comparison(self):
        records = [
            record("2026-08-10", asrc.SOURCE_SEARCH, impressions=40),
            record("2026-08-10", asrc.SOURCE_BROWSE, impressions=60),
            record("2026-08-21", asrc.SOURCE_SEARCH, impressions=60),
            record("2026-08-21", asrc.SOURCE_BROWSE, impressions=40),
        ]
        split = asrc.split_on_rename(records, pulled_at="2026-08-27T22:40:00Z")
        self.assertTrue(split["has_post_window"])
        self.assertEqual(split["pre"]["search_share"], 40.0)
        self.assertEqual(split["post"]["search_share"], 60.0)
        self.assertIn("40.0% -> 60.0%", asrc.render(split))

    def test_the_rename_day_belongs_to_neither_window(self):
        # 1.0.10 went live at 13:13 UTC, so the day is half one listing and
        # half the other. Assigning it to either side would be a choice that
        # flatters or damns the rename by accident.
        records = [
            record("2026-08-18", asrc.SOURCE_SEARCH, impressions=10),
            record("2026-08-19", asrc.SOURCE_SEARCH, impressions=999),
            record("2026-08-21", asrc.SOURCE_SEARCH, impressions=20),
        ]
        split = asrc.split_on_rename(records, pulled_at="2026-08-27T22:40:00Z")
        self.assertEqual(split["pre"]["impressions"], 10)
        self.assertEqual(split["post"]["impressions"], 20)
        self.assertEqual(split["boundary"]["impressions"], 999)
        self.assertIn("counted in neither window", asrc.render(split))

    def test_search_share_of_no_impressions_is_none_not_zero(self):
        split = asrc.split_on_rename([], pulled_at="2026-08-27T22:40:00Z")
        self.assertIsNone(split["pre"]["search_share"])


# ── 4. Parsing, without a network ────────────────────────────────────────────

class TestParseTsv(unittest.TestCase):
    def test_parses_apples_real_column_order(self):
        columns, rows = asrc.parse_tsv(report(
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, 120, 100),
        ))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][columns[asrc.COL_SOURCE]], asrc.SOURCE_SEARCH)
        self.assertEqual(rows[0][columns[asrc.COL_COUNTS]], "120")

    def test_header_matching_survives_case_and_spacing(self):
        header = "date\tevent\tsource_type\tcounts"
        columns, rows = asrc.parse_tsv(f"{header}\n2026-08-10\tImpression\tApp Store search\t5\n")
        self.assertEqual(rows[0][columns[asrc.COL_DATE]], "2026-08-10")

    def test_a_missing_column_raises_and_names_the_header(self):
        # Never `row.get("Counts", 0)`. A renamed column has to fail loudly, or
        # it produces a clean-looking series of zeroes nobody questions.
        bad = "Date\tEvent\tSource Type\tTotals\n2026-08-10\tImpression\tApp Store search\t5\n"
        with self.assertRaises(asrc.ReportSchemaError) as caught:
            asrc.parse_tsv(bad)
        self.assertIn("Counts", str(caught.exception))
        self.assertIn("Totals", str(caught.exception))

    def test_a_ragged_row_raises_rather_than_being_padded(self):
        text = report(tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, 5)) \
            + "2026-08-11\tshort\n"
        with self.assertRaises(asrc.ReportSchemaError):
            asrc.parse_tsv(text)

    def test_an_empty_segment_raises(self):
        with self.assertRaises(asrc.ReportSchemaError):
            asrc.parse_tsv("")


class TestAggregate(unittest.TestCase):
    def test_sums_counts_by_event_and_source(self):
        columns, rows = asrc.parse_tsv(report(
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, 100, 80),
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, 20, 15),
            tsv_row("2026-08-10", "Page view", asrc.SOURCE_SEARCH, 9, 8),
            tsv_row("2026-08-10", "Tap", asrc.SOURCE_SEARCH, 4, 4),
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_BROWSE, 300, 250),
        ))
        totals, anomalies = asrc.aggregate_sources(columns, rows)
        search = totals[("2026-08-10", asrc.SOURCE_SEARCH)]
        self.assertEqual(search["impressions"], 120)
        self.assertEqual(search["impressions_unique"], 95)
        self.assertEqual(search["page_views"], 9)
        self.assertEqual(search["taps"], 4)
        self.assertEqual(totals[("2026-08-10", asrc.SOURCE_BROWSE)]["impressions"], 300)
        self.assertEqual(anomalies["unknown_events"], {})
        self.assertEqual(anomalies["unknown_sources"], {})

    def test_an_unknown_event_is_named_and_excluded_not_folded_in(self):
        columns, rows = asrc.parse_tsv(report(
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, 10),
            tsv_row("2026-08-10", "Teleport", asrc.SOURCE_SEARCH, 999),
        ))
        totals, anomalies = asrc.aggregate_sources(columns, rows)
        self.assertEqual(totals[("2026-08-10", asrc.SOURCE_SEARCH)]["impressions"], 10)
        self.assertEqual(anomalies["unknown_events"], {"Teleport": 1})

    def test_an_unknown_source_is_carried_not_dropped(self):
        # A source type we have never seen is the single most interesting thing
        # this report could contain. Dropping it would hide it.
        columns, rows = asrc.parse_tsv(report(
            tsv_row("2026-08-10", "Impression", "App Store Vision Pro strip", 7),
        ))
        totals, anomalies = asrc.aggregate_sources(columns, rows)
        self.assertEqual(
            totals[("2026-08-10", "App Store Vision Pro strip")]["impressions"], 7)
        self.assertEqual(anomalies["unknown_sources"],
                         {"App Store Vision Pro strip": 1})

    def test_blank_and_dash_counts_read_as_zero(self):
        columns, rows = asrc.parse_tsv(report(
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, "", ""),
            tsv_row("2026-08-10", "Impression", asrc.SOURCE_SEARCH, "-", "-"),
        ))
        totals, _ = asrc.aggregate_sources(columns, rows)
        self.assertEqual(totals[("2026-08-10", asrc.SOURCE_SEARCH)]["impressions"], 0)


# ── The series ───────────────────────────────────────────────────────────────

class TestSeries(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "series.csv")
        self.addCleanup(self.dir.cleanup)

    def test_round_trips_through_csv_unchanged(self):
        records = [record("2026-08-10", asrc.SOURCE_SEARCH, impressions=12,
                          page_views=3, taps=1)]
        asrc.append(self.path, records)
        self.assertEqual(asrc.read(self.path), records)

    def test_appending_twice_does_not_rewrite_the_header(self):
        asrc.append(self.path, [record("2026-08-10", asrc.SOURCE_SEARCH, 1)])
        asrc.append(self.path, [record("2026-08-11", asrc.SOURCE_SEARCH, 2)])
        with open(self.path) as fh:
            self.assertEqual(fh.read().count("pulled_at"), 1)

    def test_a_missing_series_reads_as_empty_not_an_error(self):
        self.assertEqual(asrc.read(os.path.join(self.dir.name, "nope.csv")), [])

    def test_a_changed_header_raises_rather_than_being_parsed(self):
        with open(self.path, "w") as fh:
            fh.write("pulled_at,date\n2026-08-10,x\n")
        with self.assertRaises(ValueError):
            asrc.read(self.path)

    def test_a_restatement_supersedes_the_earlier_observation(self):
        early = record("2026-08-20", asrc.SOURCE_SEARCH, impressions=5,
                       pulled_at="2026-08-21T22:40:00Z", complete=False)
        late = record("2026-08-20", asrc.SOURCE_SEARCH, impressions=41,
                      pulled_at="2026-08-27T22:40:00Z", complete=True)
        view = asrc.latest_view([early, late])
        self.assertEqual(view[("2026-08-20", asrc.SOURCE_SEARCH)]["impressions"], 41)

    def test_a_day_already_final_is_not_appended_again(self):
        existing = [record("2026-08-10", asrc.SOURCE_SEARCH, impressions=5)]
        candidates = [record("2026-08-10", asrc.SOURCE_SEARCH, impressions=5,
                             pulled_at="2026-08-30T22:40:00Z")]
        self.assertEqual(asrc.new_rows(existing, candidates), [])

    def test_an_unchanged_incomplete_day_is_not_appended_again(self):
        existing = [record("2026-08-22", asrc.SOURCE_SEARCH, impressions=5,
                           complete=False)]
        candidates = [record("2026-08-22", asrc.SOURCE_SEARCH, impressions=5,
                             pulled_at="2026-08-24T22:40:00Z", complete=False)]
        self.assertEqual(asrc.new_rows(existing, candidates), [])

    def test_a_changed_incomplete_day_IS_appended(self):
        existing = [record("2026-08-22", asrc.SOURCE_SEARCH, impressions=5,
                           complete=False)]
        candidates = [record("2026-08-22", asrc.SOURCE_SEARCH, impressions=41,
                             pulled_at="2026-08-25T22:40:00Z", complete=True)]
        self.assertEqual(len(asrc.new_rows(existing, candidates)), 1)

    def test_series_age_tells_a_stopped_job_from_a_quiet_week(self):
        import datetime
        records = [record("2026-08-10", asrc.SOURCE_SEARCH,
                          pulled_at="2026-08-10T22:40:00Z")]
        now = datetime.datetime(2026, 8, 24, tzinfo=datetime.timezone.utc)
        self.assertEqual(asrc.series_age_days(records, now=now), 13)
        self.assertIsNone(asrc.series_age_days([]))


class TestReportDiscovery(unittest.TestCase):
    """Report ids are request-scoped, so the name is the stable handle."""

    def _getter(self, names):
        def getter(url, token):
            return {"data": [
                {"id": f"r{i}-req", "attributes": {"name": n,
                                                   "category": "APP_STORE_ENGAGEMENT"}}
                for i, n in enumerate(names)
            ], "links": {}}
        return getter

    def test_resolves_the_report_name_to_a_request_scoped_id(self):
        getter = self._getter(["App Store Discovery and Engagement Standard",
                               asrc.DEFAULT_REPORT_NAME])
        self.assertEqual(
            asrc.find_report("tok", "req", asrc.DEFAULT_REPORT_NAME, getter=getter),
            "r1-req",
        )

    def test_an_absent_report_lists_what_was_available(self):
        getter = self._getter(["Retention Messaging"])
        with self.assertRaises(LookupError) as caught:
            asrc.find_report("tok", "req", asrc.DEFAULT_REPORT_NAME, getter=getter)
        self.assertIn("Retention Messaging", str(caught.exception))

    def test_pagination_is_followed_to_exhaustion(self):
        pages = {
            "/first": {"data": [{"id": "a"}], "links": {"next": "/second"}},
            "/second": {"data": [{"id": "b"}], "links": {}},
        }
        seen = asrc.api_get_all("/first", "tok",
                                getter=lambda url, token: pages[url])
        self.assertEqual([d["id"] for d in seen], ["a", "b"])


class TestConfig(unittest.TestCase):
    def test_no_credential_is_hardcoded_in_the_module(self):
        # The repo is public and snapshot-server-config.sh fails closed on a
        # literal credential. This is the cheap standing check.
        text = MODULE_PATH.read_text()
        self.assertNotIn("BEGIN PRIVATE KEY", text)
        self.assertNotIn("-----BEGIN", text)
        for name in ("ASC_KEY_ID", "ASC_ISSUER_ID"):
            self.assertNotIn(f'{name} = "', text)

    def test_environment_beats_the_secrets_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = os.path.join(tmp, "key.p8")
            with open(key, "w") as fh:
                fh.write("not a real key")
            with open(os.path.join(tmp, asrc.SECRETS_FILE), "w") as fh:
                fh.write("ASC_KEY_ID=from_file\nASC_ISSUER_ID=iss\n"
                         f"ASC_PRIVATE_KEY_PATH={key}\nASC_REQUEST_ID=req\n")
            config = asrc.load_config(secrets_dir=tmp,
                                      environ={"ASC_KEY_ID": "from_env"})
            self.assertEqual(config["ASC_KEY_ID"], "from_env")
            self.assertEqual(config["ASC_REPORT_NAME"], asrc.DEFAULT_REPORT_NAME)

    def test_a_missing_setting_is_an_error_not_an_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                asrc.load_config(secrets_dir=tmp, environ={})
            self.assertIn("ASC_KEY_ID", str(caught.exception))

    def test_a_missing_private_key_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError) as caught:
                asrc.load_config(secrets_dir=tmp, environ={
                    "ASC_KEY_ID": "k", "ASC_ISSUER_ID": "i",
                    "ASC_PRIVATE_KEY_PATH": os.path.join(tmp, "absent.p8"),
                    "ASC_REQUEST_ID": "r",
                })
            self.assertIn("absent.p8", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
