"""
End-to-end tests for build_variety_pages.py under a page ledger.

The unit tests in test_page_ledger.py pin the state machine. These pin the
things only a real run can show: that the builder without --ledger deletes
nothing, that a tombstone renders with a *working* watch form, and that the
tombstoned slug reaches the canonical title map the subscribe server validates
against. That last one is the whole point of a tombstone and it fails silently:
a form that 404s on submit looks exactly like a form that works.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
FIXTURE_DATA = Path(__file__).resolve().parent / "golden" / "fixture" / "nursery-stock"

sys.path.insert(0, str(SCRAPERS))

from stocklib.page_ledger import (  # noqa: E402
    FAMILY_VARIETY, LIVE, REDIRECT, SCHEMA, TOMBSTONE,
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def gone_entry(**over) -> dict:
    """A page that was live for months, is absent tonight, and has already used
    up its one free night of absence."""
    entry = {
        "state": LIVE,
        "first_seen": days_ago(120), "last_seen": days_ago(1),
        "live_days": 100, "in_stock_days": 80, "last_in_stock": days_ago(3),
        "since": days_ago(120), "seeded": True,
        "title": "Pecan - Mahan (B)", "species": "Pecan",
        "species_slug": "pecan", "variety": "Mahan (B)",
        "rows": [{"nursery_key": "daleys", "nursery_name": "Daleys",
                  "title": "Pecan - Mahan (B)", "price": 49.0, "available": True,
                  "url": "https://daleys/pecan-mahan", "states": "NSW, QLD",
                  "type_label": ""}],
        "rows_as_of": days_ago(1), "redirect_to": None, "retired_reason": None,
        "see_also": [], "absent_nights": 1,
    }
    entry.update(over)
    return entry


def fixture_slugs() -> list[str]:
    """The slugs the golden fixture builds, read from the committed goldens.

    The ledger has to know about these as live pages, or every run here looks
    like the site collapsing: the global floor compares tonight's page count
    against the ledger's live count, and it would fire before any of the guards
    under test got a look in.
    """
    expected = (Path(__file__).resolve().parent / "golden" / "expected"
                / "variety" / "variety")
    return sorted(p.stem for p in expected.glob("*.html") if p.stem != "index")


class BuilderRun:
    """One build into a temp dir, with an optional starting ledger."""

    def __init__(self, pages=None, extra_args=()):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"
        self.out.mkdir(parents=True)
        self.ledger_path = Path(self.tmp.name) / "variety.json"
        self.index_out = Path(self.tmp.name) / "variety-index.json"
        self.health_dir = Path(self.tmp.name) / "health"
        self.health_dir.mkdir()
        self.pages = {
            slug: gone_entry(title=f"Fixture - {slug}", absent_nights=0)
            for slug in fixture_slugs()
        }
        self.pages.update(pages or {})
        self.extra_args = list(extra_args)

    def write_ledger(self):
        self.ledger_path.write_text(json.dumps({
            "schema": SCHEMA, "family": FAMILY_VARIETY, "updated": days_ago(1),
            "skipped_nights": 0, "review": [], "pages": self.pages,
        }))

    def run(self, with_ledger=True):
        if with_ledger:
            self.write_ledger()
        args = [str(FIXTURE_DATA), str(self.out),
                "--index-out", str(self.index_out)]
        if with_ledger:
            args += ["--ledger", str(self.ledger_path),
                     "--health-dir", str(self.health_dir)]
        args += self.extra_args
        self.proc = subprocess.run(
            [sys.executable, str(SCRAPERS / "build_variety_pages.py"), *args],
            capture_output=True, text=True, cwd=str(SCRAPERS))
        return self

    def page(self, slug):
        return (self.out / "variety" / f"{slug}.html")

    def ledger(self):
        return json.loads(self.ledger_path.read_text())

    def index(self):
        return json.loads(self.index_out.read_text())

    def close(self):
        self.tmp.cleanup()


class StatelessRunTest(unittest.TestCase):
    """Without --ledger the builder must behave exactly as it did, minus the
    delete. That is what makes "all 19 goldens unchanged" a meaningful claim."""

    def setUp(self):
        self.run = BuilderRun()
        # A page from a previous run that tonight's build does not generate.
        (self.run.out / "variety").mkdir(parents=True, exist_ok=True)
        self.stale = self.run.out / "variety" / "pecan-mahan-b.html"
        self.stale.write_text("<html>old</html>")
        self.run.run(with_ledger=False)
        self.addCleanup(self.run.close)

    def test_it_builds(self):
        self.assertTrue(self.run.page("avocado-hass").exists(),
                        self.run.proc.stderr[-2000:])

    def test_it_deletes_nothing(self):
        self.assertTrue(self.stale.exists())
        self.assertEqual(self.stale.read_text(), "<html>old</html>")

    def test_it_writes_no_ledger(self):
        self.assertFalse(self.run.ledger_path.exists())

    def test_pages_carry_no_state_meta(self):
        """No ledger means no page states, so declaring one would be declaring
        something this run does not know."""
        self.assertNotIn("treestock-page-state",
                         self.run.page("avocado-hass").read_text())


class TombstoneRunTest(unittest.TestCase):
    def setUp(self):
        self.run = BuilderRun(pages={"pecan-mahan-b": gone_entry()}).run()
        self.addCleanup(self.run.close)
        self.html = self.run.page("pecan-mahan-b").read_text()

    def test_the_page_exists_instead_of_404ing(self):
        self.assertTrue(self.run.page("pecan-mahan-b").exists(),
                        self.run.proc.stderr[-3000:])
        self.assertEqual(
            self.run.ledger()["pages"]["pecan-mahan-b"]["state"], TOMBSTONE)

    def test_it_declares_itself_a_tombstone(self):
        self.assertIn('content="tombstone"', self.html)

    def test_it_leads_with_the_variety_not_the_absence(self):
        """A page whose first content is a variety description is not a soft
        404 to any classifier."""
        h1 = self.html.index("<h1")
        callout = self.html.index("No nursery we track is currently listing")
        self.assertLess(h1, callout)
        self.assertIn("Buy Pecan - Mahan (B) Trees in Australia", self.html)

    def test_it_carries_the_history_sentence(self):
        self.assertIn("It was last in stock on", self.html)
        self.assertIn("We tracked it at 1 nursery", self.html)

    def test_it_keeps_a_working_watch_form(self):
        self.assertIn('id="watchForm"', self.html)
        self.assertIn("/api/watch-variety", self.html)

    def test_the_slug_stays_in_the_canonical_title_map(self):
        """The subscribe server 404s a watch on a slug absent from this map, so
        leaving a tombstone out of it puts a form on the page that cannot
        work."""
        self.assertEqual(self.run.index().get("pecan-mahan-b"),
                         "Pecan - Mahan (B)")

    def test_it_shows_the_last_known_rows_without_linking_dead_urls(self):
        self.assertIn("Daleys", self.html)
        self.assertIn("$49.00", self.html)
        self.assertNotIn("https://daleys/pecan-mahan", self.html)
        self.assertIn("/nursery/daleys.html", self.html)

    def test_it_drops_the_updated_line(self):
        self.assertNotIn("nurseries tracked", self.html)

    def test_it_advertises_no_purchasable_product(self):
        self.assertNotIn('"@type": "Product"', self.html)
        self.assertNotIn('"@type": "Offer"', self.html)

    def test_it_is_out_of_the_browsable_index(self):
        index = (self.run.out / "variety" / "index.html").read_text()
        self.assertNotIn("pecan-mahan-b", index)

    def test_a_tombstone_is_not_deleted_on_later_nights(self):
        self.run.pages = self.run.ledger()["pages"]
        self.run.run()
        self.assertTrue(self.run.page("pecan-mahan-b").exists())

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.html)


class CurationTombstoneRunTest(unittest.TestCase):
    """A page retired by curation must not offer an alert it can never send.

    The slug was denied or left the taxonomy, so it can never be generated
    again and send_variety_alerts can never match it. A watch form there takes
    an email and promises a notification that no code path can produce, which
    is the DEC-294 failure the tombstone exists to prevent, reached from the
    other side.
    """

    def setUp(self):
        entry = gone_entry(retired_reason="not a distinct variety")
        self.run = BuilderRun(pages={"pecan-mahan-b": entry})
        # The species link only renders when the species page really exists,
        # which the builder checks. Without this the block degrades to nothing
        # and the test would pass by not looking.
        (self.run.out / "species").mkdir(parents=True, exist_ok=True)
        (self.run.out / "species" / "pecan.html").write_text("<html></html>")
        self.run.run()
        self.addCleanup(self.run.close)
        self.html = self.run.page("pecan-mahan-b").read_text()

    def test_it_is_still_a_tombstone_and_still_a_page(self):
        self.assertEqual(
            self.run.ledger()["pages"]["pecan-mahan-b"]["state"], TOMBSTONE)
        self.assertIn('content="tombstone"', self.html)

    def test_it_carries_no_watch_form(self):
        self.assertNotIn('id="watchForm"', self.html)
        self.assertNotIn("/api/watch-variety", self.html)

    def test_it_does_not_claim_the_plant_is_unavailable(self):
        self.assertIn("We no longer track", self.html)
        self.assertNotIn("No nursery we track is currently listing", self.html)
        self.assertNotIn("is back in stock", self.html)

    def test_it_sends_the_reader_to_the_species_instead(self):
        self.assertIn("Looking for Pecan?", self.html)
        self.assertIn("/species/pecan.html", self.html)

    def test_the_slug_still_reaches_the_canonical_title_map(self):
        """No form means no submit to 404, but the map is also what the alert
        sender and the admin view read, so dropping it would hide the page."""
        self.assertIn("pecan-mahan-b", self.run.index())

    def test_it_stops_promising_the_listing_will_come_back(self):
        self.assertNotIn("will appear here again as soon as one lists it", self.html)
        self.assertIn("no longer track", self.html)

    def test_no_em_dashes(self):
        self.assertNotIn("\u2014", self.html)


class ResurrectionTest(unittest.TestCase):
    def test_a_tombstoned_slug_that_comes_back_is_overwritten_by_the_real_page(self):
        run = BuilderRun(pages={
            "avocado-hass": gone_entry(state=TOMBSTONE, title="Avocado - Hass",
                                       species="Avocado", variety="Hass"),
        }).run()
        self.addCleanup(run.close)
        html = run.page("avocado-hass").read_text()
        self.assertNotIn("No nursery we track is currently listing", html)
        self.assertIn('content="live"', html)
        self.assertEqual(run.ledger()["pages"]["avocado-hass"]["state"], LIVE)


class RedirectStubTest(unittest.TestCase):
    def setUp(self):
        # Its last known product URL is one the fixture lists under a different
        # slug tonight, which is what a rename looks like from the outside.
        moved = gone_entry(
            title="Avocado - Hass Dwarf", species="Avocado",
            variety="Hass Dwarf",
            rows=[{"nursery_key": "daleys", "nursery_name": "Daleys",
                   "title": "Avocado - Hass", "price": 49.0, "available": True,
                   "url": self._fixture_url("Avocado - Hass"), "states": "NSW"}])
        self.run = BuilderRun(pages={"avocado-hass-dwarf": moved}).run()
        self.addCleanup(self.run.close)

    @staticmethod
    def _fixture_url(title):
        for nursery in sorted(FIXTURE_DATA.iterdir()):
            snap = nursery / "latest.json"
            if not snap.exists():
                continue
            for p in json.loads(snap.read_text()).get("products", []):
                if p.get("title") == title:
                    return p.get("url")
        raise AssertionError(f"fixture has no product titled {title!r}")

    def test_the_old_slug_serves_a_stub_pointing_at_the_new_one(self):
        entry = self.run.ledger()["pages"]["avocado-hass-dwarf"]
        self.assertEqual(entry["state"], REDIRECT, self.run.proc.stdout[-2000:])
        self.assertEqual(entry["redirect_to"], "avocado-hass")
        html = self.run.page("avocado-hass-dwarf").read_text()
        self.assertIn('content="redirect"', html)
        self.assertIn('href="/variety/avocado-hass.html"', html)

    def test_the_stub_refreshes_and_canonicals_to_the_target(self):
        html = self.run.page("avocado-hass-dwarf").read_text()
        self.assertIn('http-equiv="refresh"', html)
        self.assertIn('rel="canonical" href="https://treestock.com.au/variety/'
                      'avocado-hass.html"', html)

    def test_the_stub_carries_no_watch_form(self):
        """A watch on a slug that is never generated again can never fire."""
        html = self.run.page("avocado-hass-dwarf").read_text()
        self.assertNotIn("<form", html)
        self.assertNotIn("/api/", html)


class DeleteGuardTest(unittest.TestCase):
    """The two irreversible outcomes, and the flag that gates both."""

    def _young(self):
        return gone_entry(first_seen=days_ago(3), last_seen=days_ago(1),
                          live_days=3, title="Pecan - Brandnew",
                          variety="Brandnew")

    def test_a_page_below_the_entry_guard_survives_without_allow_delete(self):
        run = BuilderRun(pages={"pecan-brandnew": self._young()}).run()
        self.addCleanup(run.close)
        self.assertIn("pecan-brandnew", run.ledger()["pages"])

    def test_and_is_deleted_with_it(self):
        run = BuilderRun(pages={"pecan-brandnew": self._young()},
                         extra_args=["--allow-delete"]).run()
        self.addCleanup(run.close)
        self.assertNotIn("pecan-brandnew", run.ledger()["pages"])
        self.assertFalse(run.page("pecan-brandnew").exists())

    def test_dry_run_writes_no_ledger_and_no_tombstone(self):
        run = BuilderRun(pages={"pecan-mahan-b": gone_entry()},
                         extra_args=["--dry-run"]).run()
        self.addCleanup(run.close)
        self.assertEqual(run.ledger()["pages"]["pecan-mahan-b"]["state"], LIVE)
        self.assertFalse(run.page("pecan-mahan-b").exists())
        self.assertIn("DRY RUN", run.proc.stdout)


class UnchangedPagesAreNotRewrittenTest(unittest.TestCase):
    def test_a_second_identical_run_leaves_mtimes_alone(self):
        """Once pages are permanent, a nightly rewrite of identical bytes is
        what makes every sitemap <lastmod> a lie."""
        run = BuilderRun(pages={"pecan-mahan-b": gone_entry()}).run()
        self.addCleanup(run.close)
        page = run.page("pecan-mahan-b")
        before = page.stat().st_mtime_ns
        run.pages = run.ledger()["pages"]
        run.run()
        self.assertEqual(page.stat().st_mtime_ns, before)


class TestSeedFromAvailability(unittest.TestCase):
    """--seed is bootstrap-only, ran once, and had no test at all.

    availability.json is keyed by product URL, or `<url>|sku:…` / `|id:…` /
    `|v:…` for a variant, and the scraped title is a *field* of the record.
    Seeding read the key as the title, so slug_for_title was handed a URL,
    parsed no cultivar out of it and returned None for very nearly everything.
    The bootstrap that exists to give each page its real age instead gave every
    page a first_seen of tonight, which is the state --seed was written to
    avoid: the entry guard then holds the whole site for a week and a page live
    since March looks exactly like one built an hour ago.

    Caught by the dry run on 2026-08-17, which seeded 1 entry out of 2,570.
    """

    def _seed(self, products: dict, on_disk: set[str] | None = None) -> tuple[int, dict]:
        import build_variety_pages as bvp
        from stocklib.page_ledger import PageLedger

        if on_disk is None:
            on_disk = {s for s in (bvp.slug_for_title(r.get("title") or "")
                                   for r in products.values()) if s}
        with tempfile.TemporaryDirectory() as tmp:
            nursery = Path(tmp) / "nursery-stock" / "daleys"
            nursery.mkdir(parents=True)
            (nursery / "availability.json").write_text(json.dumps({
                "nursery": "daleys", "nursery_name": "Daleys",
                "products": products,
            }))
            ledger = PageLedger.load(Path(tmp) / "variety.json", FAMILY_VARIETY,
                                     log=lambda *a, **k: None)
            seeded = bvp.seed_from_availability(ledger, nursery.parent, TODAY, on_disk)
        return seeded, ledger.pages

    def test_seeds_from_the_title_field_not_the_key(self):
        import build_variety_pages as bvp

        seeded, pages = self._seed({
            "https://daleys.com.au/pecan-mahan/|sku:pm-1": {
                "title": "Pecan - Mahan (B)",
                "first_seen": "2026-03-05",
                "days": {"2026-03-05": {"a": True},
                         "2026-03-06": {"a": False},
                         "2026-03-07": {"a": True}},
            },
        })

        self.assertEqual(seeded, 1, "one real product must seed one entry")
        slug = bvp.slug_for_title("Pecan - Mahan (B)")
        self.assertIn(slug, pages, "seeded under the key, not the title")
        entry = pages[slug]
        self.assertEqual(entry["first_seen"], "2026-03-05")
        self.assertEqual(entry["live_days"], 3)
        self.assertEqual(entry["in_stock_days"], 2)
        self.assertEqual(entry["last_in_stock"], "2026-03-07")

    def test_variants_of_one_product_collapse_to_one_slug(self):
        """Three variant keys, one cultivar. The aggregate is a union of days,
        not three separate pages and not one row's history."""
        seeded, pages = self._seed({
            "https://daleys.com.au/pecan-mahan/|sku:a": {
                "title": "Pecan - Mahan (B)", "first_seen": "2026-03-05",
                "days": {"2026-03-05": {"a": True}},
            },
            "https://daleys.com.au/pecan-mahan/|sku:b": {
                "title": "Pecan - Mahan (B)", "first_seen": "2026-03-06",
                "days": {"2026-03-06": {"a": False}},
            },
            "https://daleys.com.au/pecan-mahan/|v:Large": {
                "title": "Pecan - Mahan (B)", "first_seen": "2026-03-07",
                "days": {"2026-03-07": {"a": True}},
            },
        })

        self.assertEqual(seeded, 1)
        entry = next(iter(pages.values()))
        self.assertEqual(entry["first_seen"], "2026-03-05")
        self.assertEqual(entry["live_days"], 3)
        self.assertEqual(entry["in_stock_days"], 2)

    def test_history_without_a_page_on_disk_is_not_seeded(self):
        """PageLedger.seed's contract is a page that already exists.

        Availability history is re-parsed under today's parser, so it also
        yields slugs that were never a URL: a title that parsed differently in
        May, or a multi-graft listing today's parser splits. Seeding those as
        live would have the nightly find them absent, run the exit guard, and
        tombstone them into existence at URLs nobody ever linked or indexed,
        which is the reverse of the point. On 2026-08-17 that was 641 entries
        against 2,570 real pages.

        Recovering genuinely dead URLs is task R1, and it works from a verified
        old-slug to new-slug mapping that emits redirects, not from whatever
        archaeology re-parses into.
        """
        products = {
            "https://daleys.com.au/pecan-mahan/|sku:pm-1": {
                "title": "Pecan - Mahan (B)", "first_seen": "2026-03-05",
                "days": {"2026-03-05": {"a": True}},
            },
            "https://daleys.com.au/apple-3-way/|sku:x": {
                "title": "Apple 3-Way Gala Pink Lady Red Fuji",
                "first_seen": "2026-03-05",
                "days": {"2026-03-05": {"a": True}},
            },
        }
        import build_variety_pages as bvp
        kept = bvp.slug_for_title("Pecan - Mahan (B)")

        seeded, pages = self._seed(products, on_disk={kept})

        self.assertEqual(seeded, 1, "only the slug with a page may be seeded")
        self.assertEqual(set(pages), {kept})


class TestSeedReviewed(unittest.TestCase):
    """Task R1's apply step, and the reason it re-checks everything.

    The proposal file is a snapshot of one evening. Between proposing and
    applying, the parser can start generating the old slug again and the target
    can stop being a page, and both turn a URL recovery into an outage at a URL
    that was working. So the conditions are re-tested against tonight's build
    rather than read back out of the file that asserted them.
    """

    def _apply(self, proposals, written_slugs, pages=None):
        import build_variety_pages as bvp
        from stocklib.page_ledger import PageLedger

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.json"
            path.write_text(json.dumps({"proposals": proposals}))
            ledger = PageLedger.load(Path(tmp) / "variety.json", FAMILY_VARIETY,
                                     log=lambda *a, **k: None)
            ledger.pages.update(pages or {})
            redirected, tombstoned, skipped = bvp.seed_reviewed(
                ledger, path, TODAY, set(written_slugs))
        return redirected, tombstoned, skipped, ledger.pages

    @staticmethod
    def _rename(slug="avocado-hass-type-a", target="avocado-hass", **over):
        proposal = {"slug": slug, "target": target, "verdict": "rename",
                    "title": "Avocado - Hass Type A", "species": "Avocado",
                    "variety": "Hass Type A", "approved": True}
        proposal.update(over)
        return proposal

    def test_the_species_is_carried_onto_the_entry(self):
        """A stub does not need it; a tombstone does.

        Converting a redirect to a tombstone is a decision a reviewer can make
        later, and a tombstone with no species draws no breadcrumb and can offer
        no siblings. By then the pre-merge parser is the only other place the
        species could come from, so it is seeded now or not at all.
        """
        *_, pages = self._apply([self._rename()], {"avocado-hass"})
        entry = pages["avocado-hass-type-a"]
        self.assertEqual(entry["species"], "Avocado")
        self.assertEqual(entry["variety"], "Hass Type A")

    def test_a_proposal_without_a_species_still_applies(self):
        """Proposal files written before the species was carried must not break."""
        proposal = self._rename()
        del proposal["species"]
        del proposal["variety"]
        redirected, _, _, pages = self._apply([proposal], {"avocado-hass"})
        self.assertEqual(redirected, 1)
        self.assertEqual(pages["avocado-hass-type-a"]["state"], REDIRECT)

    def test_an_approved_rename_becomes_a_redirect_entry(self):
        redirected, _, _, pages = self._apply([self._rename()], {"avocado-hass"})

        self.assertEqual(redirected, 1)
        entry = pages["avocado-hass-type-a"]
        self.assertEqual(entry["state"], REDIRECT)
        self.assertEqual(entry["redirect_to"], "avocado-hass")
        self.assertEqual(entry["title"], "Avocado - Hass Type A",
                         "the stub says what the OLD url was called")

    def test_an_unreviewed_proposal_is_inert(self):
        """A freshly generated file has no `approved` key at all.

        Defaulting it to applied would mean generating proposals was itself the
        act of publishing them, and the whole point is that a person decides.
        """
        proposal = self._rename()
        del proposal["approved"]
        redirected, _, _, pages = self._apply([proposal], {"avocado-hass"})
        self.assertEqual(redirected, 0)
        self.assertEqual(pages, {})

    def test_an_explicitly_rejected_proposal_is_not_applied(self):
        redirected, tombstoned, *_ = self._apply(
            [self._rename(approved=False)], {"avocado-hass"})
        self.assertEqual((redirected, tombstoned), (0, 0))

    def test_only_renames_become_redirects_even_when_approved(self):
        """A split has no single successor and a retired slug has none at all.

        Approving the row cannot conjure one, so neither may become a redirect
        however the file is edited.
        """
        for verdict in ("split", "retired"):
            with self.subTest(verdict=verdict):
                redirected, *_ = self._apply(
                    [self._rename(verdict=verdict)], {"avocado-hass"})
                self.assertEqual(redirected, 0)

    @staticmethod
    def _retired(slug="kiwifruit-male", **over):
        proposal = {"slug": slug, "verdict": "retired", "target": None,
                    "title": "Kiwifruit - Male", "species": "Kiwifruit",
                    "variety": "Male", "approved": True,
                    "history": {"first_seen": "2026-03-05",
                                "last_seen": "2026-08-16",
                                "live_days": 160, "in_stock_days": 40,
                                "last_in_stock": "2026-07-02"}}
        proposal.update(over)
        return proposal

    def test_an_approved_retired_slug_becomes_a_tombstone(self):
        """It was never a cultivar, so there is nothing to redirect to.

        A tombstone keeps the URL and is honest about it. A redirect would
        assert a successor that does not exist.
        """
        redirected, tombstoned, _, pages = self._apply([self._retired()], set())
        self.assertEqual((redirected, tombstoned), (0, 1))
        entry = pages["kiwifruit-male"]
        self.assertEqual(entry["state"], TOMBSTONE)
        self.assertIsNone(entry.get("redirect_to"))

    def test_the_tombstone_gets_the_dates_it_needs_to_say_anything(self):
        """Both of a tombstone's factual sentences need dates.

        last_stock_sentence needs last_in_stock, tracking_sentence needs the
        first/last span, and each degrades to silence without them. Seeded with
        no history the page renders as a generic "no longer listed", which is
        the one outcome a tombstone exists to avoid.
        """
        *_, pages = self._apply([self._retired()], set())
        entry = pages["kiwifruit-male"]
        self.assertEqual(entry["first_seen"], "2026-03-05")
        self.assertEqual(entry["last_seen"], "2026-08-16")
        self.assertEqual(entry["last_in_stock"], "2026-07-02")
        self.assertEqual(entry["live_days"], 160)
        self.assertEqual(entry["species"], "Kiwifruit",
                         "without a species it can offer no siblings")

    def test_a_retired_slug_with_no_history_still_applies(self):
        """Missing dates cost it two sentences, not the page."""
        redirected, tombstoned, _, pages = self._apply(
            [self._retired(history={})], set())
        self.assertEqual((redirected, tombstoned), (0, 1))
        self.assertEqual(pages["kiwifruit-male"]["state"], TOMBSTONE)

    def test_an_unapproved_retired_slug_is_inert(self):
        proposal = self._retired()
        del proposal["approved"]
        redirected, tombstoned, _, pages = self._apply([proposal], set())
        self.assertEqual((redirected, tombstoned), (0, 0))
        self.assertEqual(pages, {})

    def test_a_curation_tombstone_does_not_claim_the_plant_is_unavailable(self):
        """The contradiction this seeding would otherwise put on 68 pages.

        These slugs ended because we stopped calling them a distinct variety,
        not because stock ran out: several nurseries still list Male Kiwifruit.
        "No nursery we track is currently listing Male Kiwifruit", printed above
        "It was last in stock on 17 August 2026", is both false and visibly
        self-contradicting.
        """
        from stocklib.tombstone import headline_sentence, render_tombstone

        *_, pages = self._apply([self._retired()], set())
        entry = pages["kiwifruit-male"]
        self.assertEqual(entry["retired_reason"], "not a distinct variety")

        html = render_tombstone("Male Kiwifruit", entry)
        self.assertIn("We no longer track Male Kiwifruit as a separate variety.", html)
        self.assertNotIn("No nursery we track is currently listing", html)
        self.assertNotIn("It was last in stock", html)
        self.assertIn("We tracked it", html, "the past-tense sentence stays true")

    def test_a_page_that_really_went_out_of_stock_keeps_the_stock_wording(self):
        from stocklib.tombstone import render_tombstone

        html = render_tombstone("Mahan (B) Pecan", gone_entry())
        self.assertIn("No nursery we track is currently listing Mahan (B) Pecan.", html)
        self.assertIn("It was last in stock on", html)

    def test_a_retired_slug_the_parser_generates_again_is_skipped(self):
        """The taxonomy changed its mind before the file was applied."""
        redirected, tombstoned, skipped, pages = self._apply(
            [self._retired()], {"kiwifruit-male"})
        self.assertEqual((redirected, tombstoned), (0, 0))
        self.assertIn("still a live page", skipped[0])
        self.assertEqual(pages, {})

    def test_a_slug_generated_tonight_is_never_redirected(self):
        """The parser started producing it again while the file sat unapplied.

        Redirecting it would take a live page with content and replace it with a
        stub pointing somewhere else.
        """
        redirected, _, skipped, pages = self._apply(
            [self._rename()], {"avocado-hass", "avocado-hass-type-a"})
        self.assertEqual(redirected, 0)
        self.assertEqual(pages, {})
        self.assertIn("still a live page", skipped[0])

    def test_a_target_that_is_not_a_page_tonight_is_skipped(self):
        """Otherwise the stub swaps a 404 for a 404 and spends the authority."""
        redirected, _, skipped, _ = self._apply([self._rename()], {"something-else"})
        self.assertEqual(redirected, 0)
        self.assertIn("is not a page tonight", skipped[0])

    def test_a_slug_live_in_the_ledger_is_skipped(self):
        redirected, _, skipped, _ = self._apply(
            [self._rename()], {"avocado-hass"},
            pages={"avocado-hass-type-a": {"state": LIVE}})
        self.assertEqual(redirected, 0)
        self.assertIn("live in the ledger", skipped[0])

    def test_a_slug_pointing_at_itself_is_skipped(self):
        redirected, _, skipped, _ = self._apply(
            [self._rename(target="avocado-hass-type-a")], {"avocado-hass-type-a"})
        self.assertEqual(redirected, 0)

    def test_an_unreadable_proposal_file_is_a_warning_not_a_crash(self):
        """The nightly must not fail closed on a bad hand-edit of this file."""
        import build_variety_pages as bvp
        from stocklib.page_ledger import PageLedger

        with tempfile.TemporaryDirectory() as tmp:
            ledger = PageLedger.load(Path(tmp) / "variety.json", FAMILY_VARIETY,
                                     log=lambda *a, **k: None)
            result = bvp.seed_reviewed(
                ledger, Path(tmp) / "nope.json", TODAY, set())
        self.assertEqual(result, (0, 0, []))


if __name__ == "__main__":
    unittest.main()
