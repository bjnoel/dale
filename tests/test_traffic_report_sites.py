"""Guards on which sites the daily digest reports traffic for.

Two failure modes, both silent, both previously live in this file:

1. A GSC property the service account cannot see (treesmith.app is owned by
   Benedict's personal Google account, not the service account) returns no rows
   rather than an error. Listed in GSC_SITES but absent from GSC_OAUTH_SITES, it
   would print "0 clicks" in the digest as though that were the measurement.

2. Sites we no longer work on keep costing four API calls and a table row a day.
   beestock.com.au is discontinued (DEC-230) and walkthrough.au is paused; both
   were removed 2026-08-24 and neither should drift back in.
"""

import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

AUTONOMOUS = Path(__file__).resolve().parent.parent / "tools" / "autonomous"


def load(name, filename):
    loader = SourceFileLoader(name, str(AUTONOMOUS / filename))
    spec = spec_from_loader(name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


class TrafficReportSitesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tr = load("traffic_report", "traffic_report.py")

    def test_oauth_sites_are_actually_queried(self):
        """A site flagged as OAuth-only but never queried is dead config."""
        self.assertTrue(
            set(self.tr.GSC_OAUTH_SITES) <= set(self.tr.GSC_SITES),
            "GSC_OAUTH_SITES lists a property that GSC_SITES never queries: "
            f"{set(self.tr.GSC_OAUTH_SITES) - set(self.tr.GSC_SITES)}",
        )

    def test_treesmith_gsc_goes_through_oauth(self):
        """The service account cannot see treesmith.app (verified 2026-08-24)."""
        if "sc-domain:treesmith.app" in self.tr.GSC_SITES:
            self.assertIn(
                "sc-domain:treesmith.app",
                self.tr.GSC_OAUTH_SITES,
                "treesmith.app is queried but not marked OAuth-only. The service "
                "account has no access, so the digest would report 0 clicks.",
            )

    def test_treesmith_is_tracked(self):
        self.assertIn("treesmith.app", self.tr.PLAUSIBLE_SITES)
        self.assertIn("sc-domain:treesmith.app", self.tr.GSC_SITES)

    def test_discontinued_sites_stay_out(self):
        for domain in ("beestock.com.au", "walkthrough.au"):
            self.assertNotIn(
                domain,
                self.tr.PLAUSIBLE_SITES,
                f"{domain} is discontinued or paused, do not report its traffic",
            )
            self.assertNotIn(f"sc-domain:{domain}", self.tr.GSC_SITES)
            self.assertNotIn(f"sc-domain:{domain}", self.tr.GSC_OAUTH_SITES)


if __name__ == "__main__":
    unittest.main()
