"""Regression tests for tools/scrapers/run-all-scrapers.sh.

These reproduce the 2026-08-12 publishing outage directly. Heritage Fruit Trees
started returning HTTP 503 on every URL. bigcommerce_scraper.py did exactly the
right thing: it refused to write a 0-product snapshot and exited 1. The six
scraper calls were bare under `set -euo pipefail`, so the run died on the spot
and took availability_tracker, the dashboard, twenty-odd page builders and both
subscriber sends with it. treestock.com.au froze for two nights.

The alarm built for this (detect_scrape_anomalies.py) was the *last* step of the
same script, so it could never report a failure that aborted the run. ok=false
was recorded correctly in data/scraper-health/ on both nights and nobody was
told. That ordering is the more interesting half of the bug and is pinned here.

The script is run for real against a temp tree with stubbed executables, rather
than asserting on a copy of its logic, because the bug was in `set -e` control
flow and only the real shell reproduces it. `INVOKED` records every command the
stubs saw, so each test asserts on what actually ran.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_SRC = REPO_ROOT / "tools" / "scrapers" / "run-all-scrapers.sh"

SCRAPERS = [
    "shopify_scraper.py",
    "csv_feed_scraper.py",
    "ecwid_scraper.py",
    "wix_scraper.py",
    "woocommerce_scraper.py",
    "bigcommerce_scraper.py",
    "squarespace_scraper.py",
]

# A stub `python3` that logs the .py it was asked to run and fails the ones
# named in FAIL_SCRIPTS. Everything else succeeds.
PYTHON_STUB = """#!/bin/bash
target=""
for a in "$@"; do
    case "$a" in
        *.py) target="$(basename "$a")"; break ;;
    esac
done
echo "$target" >> "$INVOKED"
for f in $FAIL_SCRIPTS; do
    if [ "$f" = "$target" ]; then
        echo "stub: $target failing on purpose" >&2
        exit 1
    fi
done
exit 0
"""

# The script pipes one builder into `tail -3`; with pipefail a stub exiting
# non-zero there would abort for the wrong reason, so stubs stay silent+0.
TRIVIAL_STUB = "#!/bin/bash\necho \"$(basename $0)\" >> \"$INVOKED\"\nexit 0\n"

# mktemp is called with GNU's --suffix, which macOS mktemp does not support.
MKTEMP_STUB = """#!/bin/bash
f="$(/usr/bin/mktemp "${TMPDIR:-/tmp}/stub.XXXXXX")"
echo "$f"
"""


class RunAllScrapersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        self.script_dir = root / "scrapers"
        self.project_dir = root / "project"
        self.bin_dir = root / "bin"
        for d in (self.script_dir, self.bin_dir,
                  self.project_dir / "dashboard", self.project_dir / "data"):
            d.mkdir(parents=True, exist_ok=True)

        self.script = self.script_dir / "run-all-scrapers.sh"
        self.script.write_bytes(SCRIPT_SRC.read_bytes())
        self.script.chmod(0o755)

        # Files the script copies or checks directly.
        (self.script_dir / "static").mkdir()
        (self.script_dir / "static" / "dashboard.js").write_text("// stub\n")
        purge = self.script_dir / "purge_cloudflare.sh"
        purge.write_text("#!/bin/bash\nexit 0\n")
        purge.chmod(0o755)

        for name in ("python3", "node", "tailwindcss"):
            p = self.bin_dir / name
            p.write_text(PYTHON_STUB if name == "python3" else TRIVIAL_STUB)
            p.chmod(0o755)
        mk = self.bin_dir / "mktemp"
        mk.write_text(MKTEMP_STUB)
        mk.chmod(0o755)

        self.invoked_path = root / "invoked.log"
        self.invoked_path.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, fail_scripts=()):
        env = {
            **os.environ,
            "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
            "DALE_PROJECT_DIR": str(self.project_dir),
            "INVOKED": str(self.invoked_path),
            "FAIL_SCRIPTS": " ".join(fail_scripts),
        }
        proc = subprocess.run(
            ["bash", str(self.script)],
            capture_output=True, text=True, env=env,
        )
        invoked = [l for l in self.invoked_path.read_text().splitlines() if l]
        return proc, invoked

    # --- the outage itself -------------------------------------------------

    def test_one_failed_scraper_still_publishes_and_sends(self):
        """The 2026-08-12 bug. Heritage (BigCommerce) fails; everything
        downstream must still run. Fails against the pre-fix script, which
        aborted at the BigCommerce call."""
        proc, invoked = self.run_script(fail_scripts=["bigcommerce_scraper.py"])

        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        for step in ("availability_tracker.py", "build-dashboard.py",
                     "daily_digest.py", "send_digest.py",
                     "send_variety_alerts.py"):
            self.assertIn(step, invoked,
                          f"{step} did not run after one scraper failed")

    def test_every_other_scraper_still_runs_after_one_fails(self):
        """A failure in the first scraper must not skip the other six."""
        _, invoked = self.run_script(fail_scripts=["shopify_scraper.py"])
        for s in SCRAPERS:
            self.assertIn(s, invoked, f"{s} was skipped")

    # --- the silent alarm --------------------------------------------------

    def test_scrape_health_runs_before_the_build_steps(self):
        """The alarm must sit upstream of everything that can abort the run.
        It used to be the final step, below the smoke test."""
        _, invoked = self.run_script()
        self.assertIn("detect_scrape_anomalies.py", invoked)
        self.assertLess(
            invoked.index("detect_scrape_anomalies.py"),
            invoked.index("build-dashboard.py"),
            "scrape health must be reported before the build steps run",
        )

    def test_scrape_health_reported_even_when_run_aborts(self):
        """The EXIT trap: if the run stops above the floor, the failure that
        stopped it must still be reported."""
        proc, invoked = self.run_script(fail_scripts=SCRAPERS[:5])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("detect_scrape_anomalies.py", invoked,
                      "aborted run reported nothing")

    def test_scrape_health_reported_once(self):
        """Trap plus explicit call must not double-send."""
        _, invoked = self.run_script()
        self.assertEqual(invoked.count("detect_scrape_anomalies.py"), 1)

    # --- the floor ---------------------------------------------------------

    def test_most_scrapers_failing_stops_before_publishing(self):
        """Continuing on 1 of 6 down is a nursery outage. 5 of 6 is us, and
        publishing then would misreport the market from stale data."""
        proc, invoked = self.run_script(fail_scripts=SCRAPERS[:5])
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("build-dashboard.py", invoked)
        self.assertNotIn("send_digest.py", invoked,
                         "subscribers emailed from a mostly-failed scrape")

    def test_at_the_floor_still_publishes(self):
        """Three of six is the documented boundary and must still publish."""
        proc, invoked = self.run_script(fail_scripts=SCRAPERS[:3])
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        self.assertIn("build-dashboard.py", invoked)

    def test_availability_tracker_failure_is_not_fatal(self):
        """It feeds the history page, not the homepage."""
        proc, invoked = self.run_script(fail_scripts=["availability_tracker.py"])
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        self.assertIn("build-dashboard.py", invoked)

    def test_digest_build_failure_is_not_fatal(self):
        """daily_digest.py was bare too: a failure there took the page
        builders and both sends with it."""
        proc, invoked = self.run_script(fail_scripts=["daily_digest.py"])
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        self.assertIn("send_digest.py", invoked)
        self.assertIn("build_variety_pages.py", invoked)

    # --- the sitemap ordering hazard ---------------------------------------

    def test_the_sitemap_is_built_after_every_page_builder(self):
        """The sitemap globs the output dir and now reads each page's declared
        lifecycle state, so it has to run last. It used to run before the
        location and combo builders, which meant tonight's sitemap described
        last night's combo files: harmless while page states did not exist, and
        wrong the moment they did."""
        _, invoked = self.run_script()
        self.assertIn("build_sitemap.py", invoked)
        sitemap_at = invoked.index("build_sitemap.py")
        for builder in ("build_variety_pages.py", "build_location_pages.py",
                        "build_species_state_pages.py"):
            self.assertIn(builder, invoked)
            self.assertLess(
                invoked.index(builder), sitemap_at,
                f"{builder} must run before the sitemap that describes its pages")


if __name__ == "__main__":
    unittest.main()
