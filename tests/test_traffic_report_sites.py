"""Guards on which sites the daily digest reports traffic for.

Two failure modes, both silent, both previously live in this file:

1. Querying a GSC property the credential cannot read 403s, but gsc_query
   catches that and returns [], which the caller records as 0 clicks. The
   diagnosis sits in the cron log while an ordinary-looking zero gets published.
   treesmith.app was invisible to the service account until Benedict granted it
   Full on 2026-08-24; beestock.com.au is still siteUnverifiedUser. The report
   must name the access problem and stamp it on the row.

2. Sites we no longer work on keep costing four API calls and a table row a day.
   beestock.com.au is discontinued (DEC-230) and walkthrough.au is paused; both
   were removed 2026-08-24 and neither should drift back in.
"""

import io
import unittest
from contextlib import redirect_stderr
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


class _FakeService:
    """Minimal stand-in for the Search Console client's sites().list() chain."""

    def __init__(self, levels):
        self._levels = levels

    def sites(self):
        return self

    def list(self):
        return self

    def execute(self):
        return {
            "siteEntry": [
                {"siteUrl": url, "permissionLevel": level}
                for url, level in self._levels.items()
            ]
        }


class _ExplodingService(_FakeService):
    def __init__(self):
        super().__init__({})

    def execute(self):
        raise RuntimeError("credentials expired")


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

    def test_unreadable_permission_warns_instead_of_reporting_zero(self):
        """siteUnverifiedUser must reach stderr, not the digest as 0 clicks."""
        service = _FakeService({
            "sc-domain:good.example": "siteFullUser",
            "sc-domain:bad.example": "siteUnverifiedUser",
        })
        err = io.StringIO()
        with redirect_stderr(err):
            levels = self.tr.warn_on_unreadable_sites(
                service,
                ["sc-domain:good.example", "sc-domain:bad.example"],
                "service account",
            )
        output = err.getvalue()
        self.assertIn("sc-domain:bad.example", output)
        self.assertIn("siteUnverifiedUser", output)
        self.assertIn("not traffic", output)
        self.assertNotIn("sc-domain:good.example", output)
        self.assertEqual(levels["sc-domain:bad.example"], "siteUnverifiedUser")

    def test_missing_property_warns(self):
        """A property absent from the credential's list is an access problem."""
        service = _FakeService({"sc-domain:good.example": "siteFullUser"})
        err = io.StringIO()
        with redirect_stderr(err):
            self.tr.warn_on_unreadable_sites(
                service, ["sc-domain:absent.example"], "service account"
            )
        self.assertIn("sc-domain:absent.example", err.getvalue())
        self.assertIn("not traffic", err.getvalue())

    def test_site_list_failure_does_not_break_the_report(self):
        """The access check is advisory. It must never abort the traffic run."""
        err = io.StringIO()
        with redirect_stderr(err):
            levels = self.tr.warn_on_unreadable_sites(
                _ExplodingService(), ["sc-domain:good.example"], "service account"
            )
        self.assertEqual(levels, {})
        self.assertIn("cannot check access", err.getvalue())

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
