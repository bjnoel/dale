"""The store-listing alarm must fire on the defects we actually shipped.

An alarm that passes is worth nothing until it has been shown to fail. DEC-265:
verify limits harder than capabilities, because a failed capability is loud and
a failed limit is silent. So every rule here is checked against the real text
that was live on a store, not against a synthetic string.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "autonomous"))

import store_listing_check as slc  # noqa: E402


LIMITS = {"freePlantLimit": 30, "freeLocationLimit": 1}

# The corrected copy, as served by the AU App Store on 2026-08-27.
GOOD = """TreeSmith is the plant app built for collectors, propagators and orchard keepers.

FREE OR PRO
Free: up to 30 plants, one location, photos, activity log, GPS map, local backup and export.
Pro, a one-time purchase: unlimited plants, multiple locations, reminders and bulk operations.
Cloud Backup is an optional yearly subscription that requires Pro: automatic daily backups and sync across devices.
"""

# DEC-262. Live on the US storefront for roughly four months.
FIFTY_PLANTS = GOOD.replace(
    "Free: up to 30 plants", "Track up to 50 plants, one location, all free"
)

# DEC-247. Live on both stores for roughly three months.
PRO_CLAIMS_CLOUD = """FREE OR PRO
Free: up to 30 plants, one location, photos, activity log, GPS map, local export.
Pro: unlimited plants, multiple locations, cloud backup, bulk operations and CSV import.
"""


def rules(description, limits=LIMITS):
    return {f["rule"]: f for f in slc.check_description(description, limits)}


class CorrectCopyPasses(unittest.TestCase):
    def test_every_rule_passes_on_the_corrected_listing(self):
        for rule, finding in rules(GOOD).items():
            with self.subTest(rule=rule):
                self.assertTrue(finding["ok"], finding["detail"])


class HistoricalDefectsFail(unittest.TestCase):
    def test_fifty_free_plants_against_a_limit_of_thirty_fails(self):
        finding = rules(FIFTY_PLANTS)["free_plant_limit"]
        self.assertFalse(finding["ok"])
        self.assertIn("50", finding["detail"])
        self.assertIn("30", finding["detail"])

    def test_pro_listing_cloud_backup_as_an_included_feature_fails(self):
        finding = rules(PRO_CLAIMS_CLOUD)["pro_excludes_cloud_backup"]
        self.assertFalse(finding["ok"])

    def test_the_same_copy_also_fails_pro_is_one_time(self):
        # It never said one-time either, which is the CLAUDE.md pricing defect.
        self.assertFalse(rules(PRO_CLAIMS_CLOUD)["pro_is_one_time"]["ok"])

    def test_pro_described_as_a_subscription_fails(self):
        bad = GOOD.replace("Pro, a one-time purchase:", "Pro, a yearly subscription:")
        self.assertFalse(rules(bad)["pro_is_one_time"]["ok"])

    def test_dropping_cloud_backup_entirely_fails(self):
        bad = "\n".join(
            line for line in GOOD.splitlines() if "Cloud Backup" not in line
        )
        self.assertFalse(rules(bad)["cloud_backup_described"]["ok"])

    def test_cloud_backup_not_stated_to_require_pro_fails(self):
        bad = GOOD.replace(
            "an optional yearly subscription that requires Pro:",
            "an optional yearly subscription:",
        )
        self.assertFalse(rules(bad)["cloud_backup_described"]["ok"])

    def test_a_missing_free_tier_sentence_fails_rather_than_passes(self):
        # DEC-249: an absence of measurement must not look like a pass.
        bad = "\n".join(
            line for line in GOOD.splitlines() if not line.startswith("Free:")
        )
        self.assertFalse(rules(bad)["free_plant_limit"]["ok"])


class TracksTheAppNotTheText(unittest.TestCase):
    def test_changing_the_app_limit_makes_todays_correct_copy_fail(self):
        # The point of the design: ground truth is the app, so if Benedict
        # changes freePlantLimit and forgets the listing, this fires.
        finding = rules(GOOD, {"freePlantLimit": 15, "freeLocationLimit": 1})
        self.assertFalse(finding["free_plant_limit"]["ok"])

    def test_a_marketing_reword_that_stays_true_does_not_fire(self):
        reworded = GOOD.replace(
            "Free: up to 30 plants, one location, photos, activity log, "
            "GPS map, local backup and export.",
            "Start free with up to 30 plants and one location. "
            "Photos, activity log and GPS map included.",
        ).replace(
            "Pro, a one-time purchase: unlimited plants, multiple locations, "
            "reminders and bulk operations.",
            "Pro, a one-time purchase, lifts every limit: unlimited plants, "
            "multiple locations, reminders and bulk operations.",
        )
        for rule, finding in rules(reworded).items():
            with self.subTest(rule=rule):
                self.assertTrue(finding["ok"], finding["detail"])


class GroundTruthParsing(unittest.TestCase):
    def test_limits_are_read_from_the_flutter_mirror(self):
        if not os.path.exists(os.path.join(slc.APP_MIRROR, slc.ENTITLEMENTS)):
            self.skipTest("treesmith-app mirror not present")
        limits = slc.app_limits()
        self.assertEqual(limits["freePlantLimit"], 30)
        self.assertEqual(limits["freeLocationLimit"], 1)

    def test_a_renamed_constant_raises_rather_than_checking_nothing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, slc.ENTITLEMENTS)
            os.makedirs(os.path.dirname(path))
            with open(path, "w") as fh:
                fh.write("const int somethingElse = 30;\n")
            with self.assertRaises(slc.Unavailable):
                slc.app_limits(tmp)


class StorefrontDivergence(unittest.TestCase):
    def test_two_storefronts_disagreeing_on_the_free_limit_is_a_failure(self):
        # DEC-262: AU was right and US was wrong, so a per-store check that
        # only ever ran on AU would have reported all clear.
        def fake(country):
            return {
                "name": "TreeSmith",
                "version": "1.0.10",
                "description": GOOD if country == "AU" else FIFTY_PLANTS,
            }

        result = slc.check(
            targets=[("ios", "AU"), ("ios", "US")],
            mirror=slc.APP_MIRROR,
            fetchers={"ios": lambda c: fake(c)},
        )
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["divergence"])

    def test_an_unreadable_storefront_is_not_reported_as_passing(self):
        def boom(_country):
            raise slc.Unavailable("Play returned a stripped page")

        result = slc.check(
            targets=[("android", "AU")],
            mirror=slc.APP_MIRROR,
            fetchers={"android": boom},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["unreadable"]), 1)


class PlayExtraction(unittest.TestCase):
    def test_description_block_is_found_by_attribute_not_class(self):
        page = (
            '<div class="XyZ123" data-g-id="description" inert>'
            "Free: up to 30 plants.<br>Pro, a one-time purchase: unlimited plants."
            "</div>"
        )
        text = slc._play_description(page)
        self.assertIn("Free: up to 30 plants.", text)
        self.assertIn("\n", text)

    def test_a_page_without_the_block_raises(self):
        with self.assertRaises(slc.Unavailable):
            slc._play_description("<html><body>nope</body></html>")


if __name__ == "__main__":
    unittest.main()
