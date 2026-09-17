"""Guards for the App Downloads / App Store Purchases reader (DAL-299).

Written after DEC-332, whose lesson was that a gap in a record does not average
out, it selects. Most of these tests exist to make a specific silent failure
loud: an instance merge that sums instead of replaces, an empty instance list
rendered as zero sales, a no-row day reported as data loss, and a territory
collapsed out of the key.

Per DEC-326, the rules that matter were each proven to FAIL before being
trusted to pass.
"""

import csv
import datetime
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools", "autonomous"))

import appstore_downloads as dl  # noqa: E402
import appstore_sources as src  # noqa: E402


DL_HEADER = ("Date\tApp Name\tApp Apple Identifier\tDownload Type\tApp Version"
             "\tDevice\tPlatform Version\tSource Type\tPage Type\tPre-Order"
             "\tTerritory\tCounts")
PU_HEADER = ("Date\tApp Name\tApp Apple Identifier\tPurchase Type\tContent Name"
             "\tContent Apple Identifier\tPayment Method\tDevice"
             "\tPlatform Version\tSource Type\tPage Type\tApp Download Date"
             "\tPre-Order\tTerritory\tPurchases\tProceeds in USD\tSales in USD"
             "\tPaying Users")


def dl_row(date, dtype="First-time download", source="App Store search",
           page="Product page", territory="AU", counts=1, version="1.0.11",
           device="iPhone"):
    return (f"{date}\tTreeSmith\t6761506742\t{dtype}\t{version}\t{device}"
            f"\tiOS 26.6\t{source}\t{page}\t\t{territory}\t{counts}")


def pu_row(date, territory="AU", purchases=1, proceeds="17.54", sales="27.55"):
    return (f"{date}\tTreeSmith\t6761506742\tIn-app purchase"
            f"\tTreeSmith Pro Lifetime\t6766142778\tMastercard\tiPhone"
            f"\tiOS 26.5\tApp referrer\tStore sheet\t{date}\t\t{territory}"
            f"\t{purchases}\t{proceeds}\t{sales}\t1")


def tsv(header, *rows):
    return "\n".join((header,) + rows) + "\n"


class TheRollingWindowMerge(unittest.TestCase):
    """DEC-332's rule, re-proved on a report with a NARROWER window.

    r3's DAILY instance carries two days, not three, so consecutive instances
    overlap by one. Summing them would inflate every overlapped day.
    """

    def _pull(self, instances, segments):
        config = {"ASC_REQUEST_ID": "req", "ASC_GRANULARITY": "DAILY"}

        def getter(path, token):
            if "/reports" in path:
                return {"data": [{"id": "r3-req", "attributes": {
                    "name": dl.DOWNLOADS_REPORT, "category": "COMMERCE"}}]}
            if "/instances" in path:
                return {"data": [
                    {"id": i, "attributes": {"granularity": "DAILY",
                                             "processingDate": d}}
                    for i, d in instances]}
            instance = path.split("/")[2]
            return {"data": [{"attributes": {"url": f"seg://{instance}"}}]}

        def fetcher(url, **_):
            return segments[url.split("://")[1]]

        return dl.pull_report(config, dl.DOWNLOADS_REPORT, dl.DL_REQUIRED,
                              dl.aggregate_downloads, token="t",
                              getter=getter, fetcher=fetcher)

    def test_an_overlapping_day_is_replaced_not_summed(self):
        # Both instances report 2026-09-10. The truth is 3, not 6.
        totals, _anomalies, meta = self._pull(
            [("i1", "2026-09-11"), ("i2", "2026-09-12")],
            {"i1": tsv(DL_HEADER, dl_row("2026-09-09", counts=2),
                       dl_row("2026-09-10", counts=3)),
             "i2": tsv(DL_HEADER, dl_row("2026-09-10", counts=3),
                       dl_row("2026-09-11", counts=1))})
        key = ("2026-09-10", "First-time download", "AU",
               "App Store search", "Product page")
        self.assertEqual(totals[key], 3)
        self.assertEqual(meta["instances_read"], 2)

    def test_every_instance_is_read_not_only_the_newest(self):
        # Reading only the newest would lose 2026-09-09 forever: it is outside
        # the newest instance's two-day window and Apple will not re-issue it.
        totals, _anomalies, _meta = self._pull(
            [("i1", "2026-09-11"), ("i2", "2026-09-12")],
            {"i1": tsv(DL_HEADER, dl_row("2026-09-09", counts=2)),
             "i2": tsv(DL_HEADER, dl_row("2026-09-11", counts=1))})
        self.assertEqual(sorted({k[0] for k in totals}),
                         ["2026-09-09", "2026-09-11"])

    def test_segments_within_one_instance_are_summed(self):
        # Within an instance, extra segments are Apple's corrections and late
        # events, so those DO add. The distinction is the whole rule.
        config = {"ASC_REQUEST_ID": "req", "ASC_GRANULARITY": "DAILY"}

        def getter(path, token):
            if "/reports" in path:
                return {"data": [{"id": "r3-req", "attributes": {
                    "name": dl.DOWNLOADS_REPORT, "category": "COMMERCE"}}]}
            if "/instances" in path:
                return {"data": [{"id": "i1", "attributes": {
                    "granularity": "DAILY", "processingDate": "2026-09-12"}}]}
            return {"data": [{"attributes": {"url": "seg://a"}},
                             {"attributes": {"url": "seg://b"}}]}

        parts = {"a": tsv(DL_HEADER, dl_row("2026-09-11", counts=2)),
                 "b": tsv(DL_HEADER, dl_row("2026-09-11", counts=1))}
        totals, _a, meta = dl.pull_report(
            config, dl.DOWNLOADS_REPORT, dl.DL_REQUIRED, dl.aggregate_downloads,
            token="t", getter=getter, fetcher=lambda u, **_: parts[u[6:]])
        self.assertEqual(sum(totals.values()), 3)
        self.assertEqual(meta["segments"], 2)


class NoInstancesIsNotZero(unittest.TestCase):
    """The failure this reader is most likely to meet in production.

    App Store Purchases has no instances at all on the ongoing request today
    (checked 2026-09-17). "No instances" and "no sales" would render
    identically, and only one of them is a fact about the business.
    """

    def test_an_empty_instance_list_raises_rather_than_returning_nothing(self):
        config = {"ASC_REQUEST_ID": "req", "ASC_GRANULARITY": "DAILY"}

        def getter(path, token):
            if "/reports" in path:
                return {"data": [{"id": "r12-req", "attributes": {
                    "name": dl.PURCHASES_REPORT, "category": "COMMERCE"}}]}
            return {"data": []}

        with self.assertRaises(src.NotReady):
            dl.pull_report(config, dl.PURCHASES_REPORT, dl.PU_REQUIRED,
                           dl.aggregate_purchases, token="t", getter=getter)

    def test_an_instance_with_no_segments_is_also_not_ready(self):
        config = {"ASC_REQUEST_ID": "req", "ASC_GRANULARITY": "DAILY"}

        def getter(path, token):
            if "/reports" in path:
                return {"data": [{"id": "r12-req", "attributes": {
                    "name": dl.PURCHASES_REPORT, "category": "COMMERCE"}}]}
            if "/instances" in path:
                return {"data": [{"id": "i1", "attributes": {
                    "granularity": "DAILY", "processingDate": "2026-09-16"}}]}
            return {"data": []}

        with self.assertRaises(src.NotReady):
            dl.pull_report(config, dl.PURCHASES_REPORT, dl.PU_REQUIRED,
                           dl.aggregate_purchases, token="t", getter=getter)


class TheAggregationKeeps(unittest.TestCase):
    def test_territory_is_part_of_the_key_not_summed_away(self):
        columns, rows = src.parse_tsv(
            tsv(DL_HEADER, dl_row("2026-09-10", territory="AU"),
                dl_row("2026-09-10", territory="US")),
            required=dl.DL_REQUIRED, optional=())
        totals, _ = dl.aggregate_downloads(columns, rows)
        self.assertEqual(len(totals), 2)
        self.assertEqual({k[2] for k in totals}, {"AU", "US"})

    def test_device_and_version_are_summed_away(self):
        # Two iOS versions of the same download are one number, not two rows.
        columns, rows = src.parse_tsv(
            tsv(DL_HEADER, dl_row("2026-09-10", version="1.0.10"),
                dl_row("2026-09-10", version="1.0.11")),
            required=dl.DL_REQUIRED, optional=())
        totals, _ = dl.aggregate_downloads(columns, rows)
        self.assertEqual(list(totals.values()), [2])

    def test_an_unknown_download_type_is_carried_and_named(self):
        columns, rows = src.parse_tsv(
            tsv(DL_HEADER, dl_row("2026-09-10", dtype="Time Travel")),
            required=dl.DL_REQUIRED, optional=())
        totals, anomalies = dl.aggregate_downloads(columns, rows)
        self.assertEqual(anomalies["unknown_download_types"], {"Time Travel": 1})
        self.assertEqual(sum(totals.values()), 1, "carried, not dropped")

    def test_updates_are_never_counted_as_new_users(self):
        columns, rows = src.parse_tsv(
            tsv(DL_HEADER, dl_row("2026-09-10", dtype="Auto-update", counts=93),
                dl_row("2026-09-10", dtype="First-time download", counts=2)),
            required=dl.DL_REQUIRED, optional=())
        totals, _ = dl.aggregate_downloads(columns, rows)
        records = dl.download_records(totals, "2026-09-20T00:00:00Z")
        summary = dl.summarise_downloads(records)
        self.assertEqual(summary["first_time_downloads"], 2)
        self.assertEqual(summary["updates"], 93)

    def test_a_missing_column_raises_rather_than_zeroing_the_metric(self):
        broken = DL_HEADER.replace("\tCounts", "\tTotals")
        with self.assertRaises(src.ReportSchemaError):
            src.parse_tsv(tsv(broken, dl_row("2026-09-10")),
                          required=dl.DL_REQUIRED, optional=())


class MoneySurvivesTheCsv(unittest.TestCase):
    def test_proceeds_round_trip_as_money_not_as_an_integer(self):
        columns, rows = src.parse_tsv(
            tsv(PU_HEADER, pu_row("2026-07-06", proceeds="17.54",
                                  sales="27.55")),
            required=dl.PU_REQUIRED, optional=())
        totals, _ = dl.aggregate_purchases(columns, rows)
        records = dl.purchase_records(totals, "2026-07-20T00:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.csv")
            src.append(path, records, dl.PURCHASE_SERIES)
            back = src.read(path, dl.PURCHASE_SERIES)
        self.assertEqual(back[0]["proceeds_usd"], 17.54)
        self.assertEqual(back[0]["sales_usd"], 27.55)
        self.assertEqual(back[0]["purchases"], 1)


class CompletenessAndTheFrozenSnapshot(unittest.TestCase):
    def test_the_tail_is_incomplete_by_default(self):
        totals = {("2026-08-20", "First-time download", "AU",
                   "App Store search", "Product page"): 1}
        records = dl.download_records(totals, "2026-08-20T00:00:00Z")
        self.assertFalse(records[0]["complete"])
        self.assertEqual(dl.summarise_downloads(records)["first_time_downloads"],
                         0, "an incomplete day is excluded, not counted")

    def test_final_marks_a_frozen_pull_complete(self):
        # The snapshot request stopped producing instances on 2026-08-20, so
        # its last three days will never be restated. Leaving them incomplete
        # would drop downloads Apple did measure, permanently.
        totals = {("2026-08-20", "First-time download", "AU",
                   "App Store search", "Product page"): 1}
        records = dl.download_records(totals, "2026-08-20T00:00:00Z", final=True)
        self.assertTrue(records[0]["complete"])
        self.assertEqual(dl.summarise_downloads(records)["first_time_downloads"],
                         1)


class AGapAndAQuietDayAreDifferentThings(unittest.TestCase):
    """The DEC-332 lesson, stated as the distinction it actually needs.

    At ~1.8 first-time downloads a day, most days carry no row. Reporting
    those as missing would cry data loss on a working series; reporting a real
    unread stretch as zero would repeat the error that overstated the rename
    by 22%.
    """

    def _records(self, dates, pulled):
        return [{"pulled_at": p, "date": d, "download_type": "First-time download",
                 "territory": "AU", "source_type": "App Store search",
                 "page_type": "Product page", "counts": 1, "complete": True,
                 "report": dl.DOWNLOADS_REPORT}
                for d, p in zip(dates, pulled)]

    def test_a_quiet_day_is_not_reported_as_missing(self):
        records = self._records(["2026-09-10", "2026-09-12"],
                                ["2026-09-11T00:00:00Z", "2026-09-13T00:00:00Z"])
        summary = dl.summarise_downloads(records)
        self.assertEqual(summary["no_row_days"], ["2026-09-11"])
        self.assertEqual(summary["pull_gaps"], [],
                         "we pulled nightly, so the quiet day was observed")

    def test_a_stretch_we_never_pulled_is_flagged_as_a_gap(self):
        records = self._records(["2026-08-20", "2026-09-14"],
                                ["2026-08-20T00:00:00Z", "2026-09-17T00:00:00Z"])
        summary = dl.summarise_downloads(records)
        self.assertEqual(summary["pull_gaps"],
                         [("2026-08-20", "2026-09-17")])
        self.assertIn("UNOBSERVED", dl.render(downloads=summary))

    def test_two_nights_missed_is_still_inside_the_window(self):
        # The window is two days wide, so pulling every second night still
        # reads everything. Three is what loses a day.
        records = self._records(["2026-09-10", "2026-09-12"],
                                ["2026-09-11T00:00:00Z", "2026-09-13T00:00:00Z"])
        self.assertEqual(dl.pull_gaps(records), [])
        wide = self._records(["2026-09-10", "2026-09-16"],
                             ["2026-09-11T00:00:00Z", "2026-09-17T00:00:00Z"])
        self.assertEqual(len(dl.pull_gaps(wide)), 1)


class TheSeriesSchemaIsNotShared(unittest.TestCase):
    def test_downloads_and_engagement_do_not_share_a_key(self):
        # A copy-paste of the engagement key would merge AU and US into one
        # row per day and silently halve the territory split.
        self.assertIn("territory", dl.DOWNLOAD_SERIES.key_columns)
        self.assertNotIn("territory", src.ENGAGEMENT_SERIES.key_columns)

    def test_a_schema_cannot_name_a_column_it_does_not_carry(self):
        with self.assertRaises(ValueError):
            src.SeriesSchema(columns=["date"], key_columns=("date",),
                             metric_columns=("counts",))

    def test_a_restatement_still_supersedes_under_the_new_schema(self):
        old = dl.download_records(
            {("2026-09-14", "First-time download", "AU", "App Store search",
              "Product page"): 1}, "2026-09-15T00:00:00Z")
        new = dl.download_records(
            {("2026-09-14", "First-time download", "AU", "App Store search",
              "Product page"): 4}, "2026-09-18T00:00:00Z")
        fresh = src.new_rows(old, new, dl.DOWNLOAD_SERIES)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(dl.summarise_downloads(old + fresh)
                         ["first_time_downloads"], 4)


class ReproducesTheHandPull(unittest.TestCase):
    """DEC-321 was pulled by hand on 2026-08-20. The reader must agree.

    If a fresh pull disagrees with the hand pull, the reader is wrong, not
    Apple. These are the three numbers that pin it.
    """

    def test_the_three_real_purchases_reproduce_dec_321(self):
        columns, rows = src.parse_tsv(
            tsv(PU_HEADER,
                pu_row("2026-06-26", territory="PK", proceeds="17.33",
                       sales="24.76"),
                pu_row("2026-07-06", territory="AU", proceeds="17.54",
                       sales="27.55"),
                pu_row("2026-07-23", territory="US", proceeds="17.50",
                       sales="24.99")),
            required=dl.PU_REQUIRED, optional=())
        totals, _ = dl.aggregate_purchases(columns, rows)
        records = dl.purchase_records(totals, "2026-08-20T00:00:00Z", final=True)
        summary = dl.summarise_purchases(records)
        self.assertEqual(summary["purchases"], 3)
        self.assertEqual(summary["sales_usd"], 77.30)
        self.assertEqual(summary["proceeds_usd"], 52.37)
        self.assertEqual(summary["by_territory"], {"AU": 1, "PK": 1, "US": 1})


if __name__ == "__main__":
    unittest.main()
