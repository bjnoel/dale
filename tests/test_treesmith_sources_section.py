"""Guards for the "App Store discovery (search vs browse)" digest section.

Three failure modes, all of which would put a false claim in Benedict's inbox
rather than an error:

1. A metrics dict without the "sources" key must still render. The revenue and
   rank tests hand-build one; a direct `metrics["sources"]` would KeyError
   every one of them, which is how a new section takes the whole digest down.

2. A stopped weekly pull must read as "no pull", never as flat traffic. This is
   sharper here than for ranks: a ONE_TIME_SNAPSHOT legitimately stops
   producing instances, so the series going quiet is the EXPECTED end state and
   would otherwise look like a stable search share forever.

3. A pull with no complete post-rename days must render as a baseline and must
   not render a delta. Months of pre-rename data against two partial days would
   read as the rename's result.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = (Path(__file__).resolve().parents[1]
               / "tools" / "autonomous" / "treesmith_analytics.py")
spec = importlib.util.spec_from_file_location("treesmith_analytics", MODULE_PATH)
ta = importlib.util.module_from_spec(spec)
sys.modules["treesmith_analytics"] = ta
spec.loader.exec_module(ta)

SRC_PATH = MODULE_PATH.parent / "appstore_sources.py"
src_spec = importlib.util.spec_from_file_location("appstore_sources", SRC_PATH)
asrc = importlib.util.module_from_spec(src_spec)
sys.modules["appstore_sources"] = asrc
src_spec.loader.exec_module(asrc)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_treesmith_rank_section import base_metrics  # noqa: E402


def series(*rows, pulled_at="2026-08-27T22:40:00Z"):
    """Series records from (date, source, impressions) triples."""
    out = []
    for date, source, impressions in rows:
        out.append({
            "pulled_at": pulled_at, "date": date, "source_type": source,
            "impressions": impressions, "impressions_unique": impressions,
            "page_views": 0, "page_views_unique": 0, "taps": 0, "taps_unique": 0,
            "complete": True,
        })
    return out


def sources_metric(split, stale=False, age_days=1, stale_reason=None,
                   data_age_days=4, newest_complete_date=None):
    return {"ok": True, "data": {"path": "/opt/dale/data/x.csv", "split": split,
                                 "age_days": age_days, "stale": stale,
                                 "stale_reason": stale_reason,
                                 "data_age_days": data_age_days,
                                 "newest_complete_date": newest_complete_date}}


class TestSectionIsOptional(unittest.TestCase):
    def test_a_metrics_dict_without_the_key_still_renders(self):
        text, _ = ta.render(base_metrics())
        self.assertIn("TreeSmith Weekly", text)
        self.assertNotIn("App Store discovery", text)

    def test_a_failed_metric_renders_as_an_error_not_as_silence(self):
        text, _ = ta.render(base_metrics(sources={
            "ok": False,
            "error": "no App Store source series at /opt/dale/data/x.csv"}))
        self.assertIn("App Store discovery", text)
        self.assertIn("ERROR", text)
        self.assertIn("no App Store source series", text)


class TestStaleness(unittest.TestCase):
    def test_a_stopped_pull_says_no_pull(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40),
                   ("2026-08-10", asrc.SOURCE_BROWSE, 60)),
            pulled_at="2026-08-27T22:40:00Z")
        text, html = ta.render(base_metrics(
            sources=sources_metric(split, stale=True, age_days=38)))
        self.assertIn("NO PULL", text)
        self.assertIn("38 days ago", text)
        self.assertIn("older news", text)
        self.assertIn(ta.RED, html)

    def test_a_fresh_pull_does_not_shout(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertNotIn("NO PULL", text)

    def test_a_running_pull_with_a_frozen_report_is_not_called_no_pull(self):
        """2026-08-30: the job ran and appended 0 of 161 rows.

        Calling that "NO PULL" would send Benedict to the crontab, which is
        working. The fix is a new App Store Connect report request, so the two
        failures have to read differently.
        """
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40),
                   ("2026-08-20", asrc.SOURCE_SEARCH, 81)),
            pulled_at="2026-08-23T22:40:00Z")
        text, html = ta.render(base_metrics(sources=sources_metric(
            split, stale=True, stale_reason="data", age_days=1,
            data_age_days=11, newest_complete_date="2026-08-20")))
        self.assertIn("SERIES FROZEN", text)
        self.assertNotIn("NO PULL", text)
        self.assertIn("2026-08-20", text)
        self.assertIn("11 days ago", text)
        self.assertIn("Nothing here is this week's news", text)
        self.assertIn(ta.RED, html)

    def test_a_stopped_job_still_reads_as_no_pull_not_as_frozen(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(
            split, stale=True, stale_reason="pull", age_days=38,
            data_age_days=41)))
        self.assertIn("NO PULL", text)
        self.assertNotIn("SERIES FROZEN", text)

    def test_a_series_behind_its_own_cutoff_says_where_it_actually_stops(self):
        """"Data through" is arithmetic: pull date minus Apple's tail.

        When the report stops advancing it keeps reading like a current date
        while the windows below it stand still, which is precisely how one
        frozen day was presented as a week's search share.
        """
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(
            split, newest_complete_date="2026-08-20")))
        self.assertIn("Newest day actually held", text)
        self.assertIn("2026-08-20", text)

    def test_an_up_to_date_series_does_not_print_the_extra_line(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(
            split, newest_complete_date=split["last_complete_date"])))
        self.assertNotIn("Newest day actually held", text)


class TestNoPostRenameWindow(unittest.TestCase):
    def test_renders_as_a_baseline_with_no_delta(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40),
                   ("2026-08-10", asrc.SOURCE_BROWSE, 60),
                   pulled_at="2026-08-20T22:40:00Z"),
            pulled_at="2026-08-20T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("No post-rename window yet", text)
        self.assertIn("PRE-RENAME BASELINE", text)
        self.assertIn("40.0%", text)          # the baseline share is shown...
        self.assertNotIn("points)", text)     # ...but never as a movement

    def test_an_empty_series_says_so_rather_than_showing_zero_percent(self):
        split = asrc.split_on_rename([], pulled_at="2026-08-20T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("no complete days in the series yet", text)
        self.assertNotIn("0%", text.split("App Store discovery")[1]
                         .split("Activation")[0])


class TestPostRenameWindow(unittest.TestCase):
    def test_renders_the_share_movement_in_points(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40),
                   ("2026-08-10", asrc.SOURCE_BROWSE, 60),
                   ("2026-08-21", asrc.SOURCE_SEARCH, 75),
                   ("2026-08-21", asrc.SOURCE_BROWSE, 25)),
            pulled_at="2026-08-27T22:40:00Z")
        text, html = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("40.0% -> 75.0% (+35.0 points)", text)
        self.assertIn(ta.GREEN, html)
        # Rates, never the two totals side by side: the windows are never the
        # same length and the pre-rename one reaches back through months when
        # the app was near-silent. On real data the lifetime rate was 19.1/day
        # against 36.2/day for the 28 days before the rename, so quoting the
        # lifetime figure alone understated the baseline by nearly half.
        self.assertIn("Impressions/day", text)
        self.assertIn("lifetime", text)
        self.assertIn("before", text)
        self.assertNotIn("Impressions (pre / post)", text)

    def test_a_short_post_window_is_labelled_not_a_trend(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40),
                   ("2026-08-21", asrc.SOURCE_SEARCH, 400)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(split)))
        # A 10x jump on ONE day must not read as a result.
        self.assertIn("Not a trend yet", text)
        self.assertIn("1 complete post-rename day", text)

    def test_a_fall_in_search_share_is_coloured_red(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 80),
                   ("2026-08-10", asrc.SOURCE_BROWSE, 20),
                   ("2026-08-21", asrc.SOURCE_SEARCH, 10),
                   ("2026-08-21", asrc.SOURCE_BROWSE, 90)),
            pulled_at="2026-08-27T22:40:00Z")
        text, html = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("(-70.0 points)", text)
        self.assertIn(ta.RED, html)

    def test_the_incomplete_tail_is_named_as_the_reason_data_stops(self):
        split = asrc.split_on_rename(
            series(("2026-08-21", asrc.SOURCE_SEARCH, 10)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("Data through", text)
        self.assertIn("2026-08-24", text)
        self.assertIn("never a drop", text)

    def test_the_boundary_day_is_called_out_as_belonging_to_neither(self):
        split = asrc.split_on_rename(
            series(("2026-08-10", asrc.SOURCE_SEARCH, 40),
                   ("2026-08-19", asrc.SOURCE_SEARCH, 999),
                   ("2026-08-21", asrc.SOURCE_SEARCH, 10)),
            pulled_at="2026-08-27T22:40:00Z")
        text, _ = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("neither window", text)
        self.assertIn("999", text)


class TestSourceNamesAreEscaped(unittest.TestCase):
    def test_a_source_type_from_apple_is_escaped_into_the_html(self):
        # Source Type values are Apple's strings, not ours. An unrecognised one
        # is carried through by design (it is the most interesting thing the
        # report could contain), so it reaches the HTML unvetted.
        split = asrc.split_on_rename(
            series(("2026-08-21", "Search <b>Ads</b> & browse", 10)),
            pulled_at="2026-08-27T22:40:00Z")
        _, html = ta.render(base_metrics(sources=sources_metric(split)))
        self.assertIn("&lt;b&gt;", html)
        self.assertNotIn("<b>Ads</b>", html)


if __name__ == "__main__":
    unittest.main()
