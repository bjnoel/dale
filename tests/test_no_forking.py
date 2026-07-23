"""
Anti-drift guardrail: shared logic must live in stocklib/ and be imported, never
re-defined in a builder/scraper. This is what stops the "updated in one place,
not the others" problem from coming back (NON_PLANT_KEYWORDS was once 10 drifted
copies; SHIPPING_MAP/NURSERY_NAMES were three parallel dicts; the email footer
was two copies).

If this test fails, you copied a shared definition into a module instead of
importing it from stocklib. Move it back to the package.

Scope: top-level tools/scrapers/*.py plus stocklib/*.py for the constant guards.
The de-forked items (the stock-change engine, and the page <head>/<header>
chrome) additionally scan bee/, since that is where they had forked.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def _scanned_files():
    files = sorted(SCRAPERS.glob("*.py"))            # top-level builders/scrapers/senders
    files += sorted((SCRAPERS / "stocklib").glob("*.py"))
    return files


# (definition regex, the single file allowed to define it). `[:=]` allows an
# optional type annotation (e.g. `SHIPPING_MAP: dict[...] = ...`). Imports start
# with `from`/`import`, so they never match these anchors.
GUARDS = [
    (re.compile(r"^NON_PLANT_KEYWORDS\s*[:=]"), "stocklib/classify.py"),
    (re.compile(r"^TRUE_JUNK\s*[:=]"), "stocklib/classify.py"),
    (re.compile(r"^CATEGORY_KEYWORDS\s*[:=]"), "stocklib/classify.py"),
    (re.compile(r"^def inject_footer\b"), "stocklib/email_footer.py"),
    (re.compile(r"^SHIPPING_MAP\s*[:=]"), "stocklib/registry.py"),
    (re.compile(r"^NURSERY_NAMES\s*[:=]"), "stocklib/registry.py"),
    (re.compile(r"^EVIDENCE_GRADES\s*[:=]"), "stocklib/evidence.py"),
    (re.compile(r"^GRADE_BADGE\s*[:=]"), "stocklib/evidence.py"),
    (re.compile(r"^def nursery_coverage\b"), "stocklib/coverage.py"),
    (re.compile(r"^def usable_dates\b"), "stocklib/coverage.py"),
    (re.compile(r"^RETRYABLE_HTTP\s*[:=]"), "stocklib/retry.py"),
    (re.compile(r"^def request_with_retry\b"), "stocklib/retry.py"),
    (re.compile(r"^def backoff_delay\b"), "stocklib/retry.py"),
    # Title -> species matching (2026-07-23 de-fork: five drifted match_title
    # copies meant "Dwarf Apple ..." counted on one page and not another)
    (re.compile(r"^def match_species\b"), "stocklib/species_match.py"),
    (re.compile(r"^def match_title\b"), "stocklib/species_match.py"),
    (re.compile(r"^def load_species_lookup\b"), "stocklib/species_match.py"),
    (re.compile(r"^def build_species_lookup\b"), "stocklib/species_match.py"),
    # Per-nursery fruit filters (digest's copy had 2 of the dashboard's 12
    # nurseries and no "categories" mode)
    (re.compile(r"^FRUIT_FILTERS\s*[:=]"), "stocklib/fruit_filters.py"),
    (re.compile(r"^def is_fruit_product\b"), "stocklib/fruit_filters.py"),
    # The seed-packet rule ("seeds?" but not seedling/seedless) was retyped
    # inline in 7+ files; only classify.py may spell that regex.
    (re.compile(r"seeds\?"), "stocklib/classify.py"),
    # Email plumbing (DEC-232 follow-up): unsubscribe tokens are
    # security-critical (a drifted copy = broken unsubscribe links from that
    # sender), and the rest were 4-7 identical copies each.
    (re.compile(r"^def get_resend_api_key\b"), "stocklib/mailer.py"),
    (re.compile(r"^def get_unsubscribe_secret\b"), "stocklib/mailer.py"),
    (re.compile(r"^def make_unsubscribe_token\b"), "stocklib/mailer.py"),
    (re.compile(r"^def load_subscribers\b"), "stocklib/mailer.py"),
    (re.compile(r"^def load_sends_log\b"), "stocklib/mailer.py"),
    (re.compile(r"^def save_sends_log\b"), "stocklib/mailer.py"),
    # Senders bind their User-Agent via functools.partial, never a def.
    (re.compile(r"^def send_email\b"), "stocklib/mailer.py"),
]

# Function names that must not be DEFINED anywhere in the scanned set: dead
# fork names whose reappearance means someone re-forked shared logic under the
# old name instead of importing it.
BANNED_DEFS = [
    r"^def is_non_plant\b",           # use classify.is_real_product
    r"^def match_title_to_species\b", # use species_match.match_title
]


class NoForkingTest(unittest.TestCase):
    def test_shared_symbols_are_defined_in_exactly_one_place(self):
        files = _scanned_files()
        self.assertTrue(files, "no files scanned")
        for rx, owner in GUARDS:
            definers = sorted(
                str(f.relative_to(SCRAPERS))
                for f in files
                if any(rx.search(line) for line in f.read_text().splitlines())
            )
            self.assertEqual(
                definers, [owner],
                f"{rx.pattern!r} must be defined only in {owner}, but was found in "
                f"{definers}. Shared logic lives in stocklib/ -- import it, don't copy it.",
            )

    def test_species_file_read_only_by_taxonomy(self):
        """Every consumer goes through stocklib.taxonomy (enabled_species /
        load_species). A direct fruit_species.json read bypasses the category
        gate (DEC-200 P1.4): when a category is enabled or disabled, a direct
        reader silently keeps serving the wrong species set. Scans bee/ too."""
        rx = re.compile(r'''["']fruit_species\.json["']''')
        files = _scanned_files() + sorted((SCRAPERS / "bee").glob("*.py"))
        readers = sorted(
            str(f.relative_to(SCRAPERS))
            for f in files
            if any(rx.search(line) for line in f.read_text().splitlines())
        )
        self.assertEqual(
            readers, ["stocklib/taxonomy.py"],
            "fruit_species.json may only be opened by stocklib/taxonomy.py -- "
            f"import taxonomy.enabled_species() instead. Found in: {readers}",
        )

    def test_dead_fork_names_do_not_reappear(self):
        files = _scanned_files()
        for pattern in BANNED_DEFS:
            rx = re.compile(pattern)
            definers = sorted(
                str(f.relative_to(SCRAPERS))
                for f in files
                if any(rx.search(line) for line in f.read_text().splitlines())
            )
            self.assertEqual(
                definers, [],
                f"{pattern!r} is a retired fork name; import the stocklib "
                f"replacement instead of redefining it (found in {definers}).",
            )

    def test_comparison_engine_not_re_forked(self):
        """The stock-change engine (variant_key / compare_snapshots) lives only in
        stocklib.changes; treestock AND beestock import it. Scans bee/ too, since
        that is where it had forked."""
        files = _scanned_files() + sorted((SCRAPERS / "bee").glob("*.py"))

        def definers(pattern):
            rx = re.compile(pattern)
            return sorted(
                str(f.relative_to(SCRAPERS))
                for f in files
                if any(rx.search(line) for line in f.read_text().splitlines())
            )

        self.assertEqual(definers(r"^def variant_key\b"), ["stocklib/changes.py"])
        self.assertEqual(definers(r"^def compare_snapshots\b"), ["stocklib/changes.py"])
        # the underscore-aliased forks are gone (all import `variant_key as _variant_key`)
        self.assertEqual(definers(r"^def _variant_key\b"), [])

    def test_layout_chrome_not_re_forked(self):
        """The page <head> and the site <header> live only in stocklib/layout.py.
        treestock_layout and bee/beestock_layout bind them to a SiteConfig (via
        functools.partial) rather than redefining them. Scans bee/ too, since
        that is where the layout had forked (logo colour, nav, Plausible)."""
        files = _scanned_files() + sorted((SCRAPERS / "bee").glob("*.py"))

        def definers(pattern):
            rx = re.compile(pattern)
            return sorted(
                str(f.relative_to(SCRAPERS))
                for f in files
                if any(rx.search(line) for line in f.read_text().splitlines())
            )

        self.assertEqual(definers(r"^def render_head\b"), ["stocklib/layout.py"])
        self.assertEqual(definers(r"^def render_header\b"), ["stocklib/layout.py"])


if __name__ == "__main__":
    unittest.main()
