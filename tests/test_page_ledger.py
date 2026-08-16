"""
Tests for stocklib.page_ledger: the nightly page-lifecycle state machine.

The properties worth protecting here are the safety ones. A bug in this module
either deletes URLs Google ranks or freezes stale stock on the site, and both
failures are invisible on the night they happen, so the guards are tested from
the outside (given last night's ledger and tonight's slugs, what changes?)
rather than by poking at internals.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

from stocklib.page_ledger import (  # noqa: E402
    ENTRY_GUARD_LIVE_DAYS, EXIT_GUARD_NIGHTS, FAMILY_SPECIES_STATE,
    FAMILY_VARIETY, LIVE, MAX_TOMBSTONES_PER_NIGHT, REDIRECT, RETIRED, SCHEMA,
    TOMBSTONE, PageLedger, decide_night, default_ledger_dir, ledger_path,
    rename_target, write_page,
)


def row(nursery="daleys", url="https://daleys/p1", available=True, price=49.0):
    return {"nursery_key": nursery, "nursery_name": nursery.title(), "url": url,
            "available": available, "price": price, "states": "NSW, QLD",
            "type_label": ""}


def established(ledger, slug, *, first_seen="2026-05-01", last_seen="2026-06-30",
                live_days=60, rows=None, state=LIVE, **extra):
    """An entry that already satisfies the entry guard, as most real pages do."""
    entry = ledger.seed(slug, today=last_seen, first_seen=first_seen,
                        last_seen=last_seen, live_days=live_days,
                        in_stock_days=live_days, last_in_stock=last_seen,
                        state=state, title=f"Pecan - {slug}", species="Pecan",
                        rows=rows if rows is not None else [row()], **extra)
    entry["seeded"] = True
    return entry


class GuardTestCase(unittest.TestCase):
    """Base for the per-page guard tests.

    Every test here pads the ledger with pages that are still generated
    tonight, because the global floor is a *different* guard: on a two-page
    ledger one page disappearing is a 50% collapse and the breaker fires
    first, hiding the behaviour under test. Real families run to thousands of
    pages, where one disappearance is noise. The floor itself is tested in
    CircuitBreakerTest.
    """

    PAD = [f"pad-{i:03d}" for i in range(30)]

    def setUp(self):
        self.led = PageLedger(FAMILY_VARIETY)
        for slug in self.PAD:
            established(self.led, slug)

    def night(self, today, *, also_tonight=(), **kwargs):
        return decide_night(self.led, list(self.PAD) + list(also_tonight),
                            today=today, **kwargs)


class LoadSaveTest(unittest.TestCase):
    def test_missing_file_seeds_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            logged = []
            led = PageLedger.load(Path(tmp) / "variety.json", FAMILY_VARIETY,
                                  log=logged.append)
            self.assertTrue(led.seeding)
            self.assertTrue(led.missing)
            self.assertEqual(led.pages, {})
            self.assertIn("LEDGER MISSING", " ".join(logged))

    def test_corrupt_file_seeds_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variety.json"
            path.write_text("{not json at all")
            logged = []
            led = PageLedger.load(path, FAMILY_VARIETY, log=logged.append)
            self.assertTrue(led.seeding)
            self.assertTrue(led.corrupt)
            self.assertIn("ERROR", " ".join(logged))

    def test_json_without_pages_object_counts_as_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variety.json"
            path.write_text(json.dumps({"schema": 1, "family": "variety"}))
            led = PageLedger.load(path, FAMILY_VARIETY, log=lambda *_: None)
            self.assertTrue(led.corrupt)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variety.json"
            led = PageLedger(FAMILY_VARIETY)
            led.observe("pecan-mahan-b", today="2026-08-16", rows=[row()],
                        title="Pecan - Mahan (B)", species="Pecan")
            led.save(path, "2026-08-16")

            data = json.loads(path.read_text())
            self.assertEqual(data["schema"], SCHEMA)
            self.assertEqual(data["family"], FAMILY_VARIETY)
            self.assertEqual(data["updated"], "2026-08-16")

            back = PageLedger.load(path, FAMILY_VARIETY)
            self.assertFalse(back.seeding)
            self.assertEqual(back.pages["pecan-mahan-b"]["title"], "Pecan - Mahan (B)")
            self.assertEqual(back.pages["pecan-mahan-b"]["state"], LIVE)

    def test_save_rotates_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variety.json"
            first = PageLedger(FAMILY_VARIETY)
            first.observe("a", today="2026-08-15")
            first.save(path, "2026-08-15")

            second = PageLedger.load(path, FAMILY_VARIETY)
            second.observe("b", today="2026-08-16")
            second.save(path, "2026-08-16")

            prev = json.loads(Path(str(path) + ".prev").read_text())
            self.assertEqual(sorted(prev["pages"]), ["a"])
            self.assertEqual(sorted(json.loads(path.read_text())["pages"]), ["a", "b"])

    def test_corrupt_load_does_not_overwrite_the_backup(self):
        """The .prev copy is what an incident gets recovered from."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variety.json"
            good = PageLedger(FAMILY_VARIETY)
            good.observe("keeper", today="2026-08-15")
            good.save(path, "2026-08-15")
            good.observe("second", today="2026-08-16")
            good.save(path, "2026-08-16")  # .prev now holds the one-page version

            path.write_text("truncated{")
            broken = PageLedger.load(path, FAMILY_VARIETY, log=lambda *_: None)
            broken.observe("fresh", today="2026-08-17")
            broken.save(path, "2026-08-17")

            prev = json.loads(Path(str(path) + ".prev").read_text())
            self.assertEqual(sorted(prev["pages"]), ["keeper"])

    def test_default_dir_respects_env(self):
        import os
        old = os.environ.get("DALE_DATA_DIR")
        os.environ["DALE_DATA_DIR"] = "/tmp/dale-test-data"
        try:
            self.assertEqual(default_ledger_dir(),
                             Path("/tmp/dale-test-data/page-ledger"))
            self.assertEqual(ledger_path(FAMILY_VARIETY).name, "variety.json")
        finally:
            if old is None:
                del os.environ["DALE_DATA_DIR"]
            else:
                os.environ["DALE_DATA_DIR"] = old


class ObserveTest(unittest.TestCase):
    def test_first_sighting_creates_a_live_entry(self):
        led = PageLedger(FAMILY_VARIETY)
        entry = led.observe("hass", today="2026-08-16", rows=[row()],
                            title="Avocado - Hass")
        self.assertEqual(entry["state"], LIVE)
        self.assertEqual(entry["first_seen"], "2026-08-16")
        self.assertEqual(entry["live_days"], 1)
        self.assertEqual(entry["in_stock_days"], 1)
        self.assertEqual(entry["last_in_stock"], "2026-08-16")
        self.assertEqual(entry["rows_as_of"], "2026-08-16")
        self.assertFalse(entry["seeded"])

    def test_second_run_same_day_does_not_double_count(self):
        """rebuild_pages_email_safe.sh re-runs builders on the same date."""
        led = PageLedger(FAMILY_VARIETY)
        led.observe("hass", today="2026-08-16", rows=[row()])
        entry = led.observe("hass", today="2026-08-16", rows=[row()])
        self.assertEqual(entry["live_days"], 1)
        self.assertEqual(entry["in_stock_days"], 1)

    def test_out_of_stock_night_counts_as_live_but_not_in_stock(self):
        led = PageLedger(FAMILY_VARIETY)
        led.observe("hass", today="2026-08-15", rows=[row(available=True)])
        entry = led.observe("hass", today="2026-08-16", rows=[row(available=False)])
        self.assertEqual(entry["live_days"], 2)
        self.assertEqual(entry["in_stock_days"], 1)
        self.assertEqual(entry["last_in_stock"], "2026-08-15")

    def test_rows_are_capped_per_family(self):
        led = PageLedger(FAMILY_VARIETY)
        entry = led.observe("hass", today="2026-08-16",
                            rows=[row(url=f"https://x/{i}") for i in range(40)])
        self.assertEqual(len(entry["rows"]), 12)

        combo = PageLedger(FAMILY_SPECIES_STATE)
        centry = combo.observe("buy-pecan-trees-wa", today="2026-08-16",
                               rows=[row(url=f"https://x/{i}") for i in range(80)])
        self.assertEqual(len(centry["rows"]), 60)

    def test_rows_keep_only_known_keys(self):
        led = PageLedger(FAMILY_VARIETY)
        noisy = dict(row(), scraped_at="2026-08-16T03:00:00", variants=[1, 2, 3])
        entry = led.observe("hass", today="2026-08-16", rows=[noisy])
        self.assertNotIn("scraped_at", entry["rows"][0])
        self.assertNotIn("variants", entry["rows"][0])
        self.assertEqual(entry["rows"][0]["nursery_key"], "daleys")

    def test_empty_rows_do_not_erase_the_last_known_ones(self):
        """A page can render with no rows tonight; the tombstone still needs
        the last listing we actually saw."""
        led = PageLedger(FAMILY_VARIETY)
        led.observe("hass", today="2026-08-15", rows=[row()])
        entry = led.observe("hass", today="2026-08-16", rows=[])
        self.assertEqual(len(entry["rows"]), 1)
        self.assertEqual(entry["rows_as_of"], "2026-08-15")

    def test_resurrection_restores_state_and_keeps_first_seen(self):
        for state in (TOMBSTONE, REDIRECT, RETIRED):
            with self.subTest(state=state):
                led = PageLedger(FAMILY_VARIETY)
                established(led, "hass", state=state)
                led.pages["hass"]["redirect_to"] = "avocado-hass"
                led.pages["hass"]["retired_reason"] = "left taxonomy"
                led.pages["hass"]["see_also"] = ["other"]

                entry = led.observe("hass", today="2026-08-16", rows=[row()])
                self.assertEqual(entry["state"], LIVE)
                self.assertEqual(entry["first_seen"], "2026-05-01")
                self.assertIsNone(entry["redirect_to"])
                self.assertIsNone(entry["retired_reason"])
                self.assertEqual(entry["see_also"], [])
                self.assertEqual(entry["since"], "2026-08-16")
                self.assertEqual(led.resurrected, ["hass"])

    def test_absent_nights_resets_on_sighting(self):
        led = PageLedger(FAMILY_VARIETY)
        established(led, "hass")
        led.pages["hass"]["absent_nights"] = 1
        entry = led.observe("hass", today="2026-08-16", rows=[row()])
        self.assertEqual(entry["absent_nights"], 0)

    def test_metadata_may_not_write_lifecycle_fields(self):
        led = PageLedger(FAMILY_VARIETY)
        with self.assertRaises(ValueError):
            led.observe("hass", today="2026-08-16", state=TOMBSTONE)
        with self.assertRaises(ValueError):
            led.observe("hass", today="2026-08-16", first_seen="2020-01-01")


class ExitGuardTest(GuardTestCase):
    """85% of disappearances reverse within 24 hours, so night one changes
    nothing at all."""

    def setUp(self):
        super().setUp()
        established(self.led, "hass")

    def test_first_absent_night_changes_nothing(self):
        plan = self.night("2026-07-01", allow_delete=True)
        self.assertEqual(plan.tombstoned, [])
        self.assertEqual(plan.removals, [])
        self.assertEqual(self.led.pages["hass"]["state"], LIVE)
        self.assertIn("hass", plan.held)
        self.assertEqual(self.led.pages["hass"]["absent_nights"], 1)

    def test_second_absent_night_tombstones(self):
        self.night("2026-07-01")
        plan = self.night("2026-07-02")
        self.assertEqual(plan.tombstoned, ["hass"])
        self.assertEqual(self.led.pages["hass"]["state"], TOMBSTONE)
        self.assertEqual(self.led.pages["hass"]["since"], "2026-07-02")

    def test_one_night_blip_never_tombstones(self):
        self.night("2026-07-01")
        self.led.observe("hass", today="2026-07-02", rows=[row()])
        plan = self.night("2026-07-02", also_tonight=["hass"])
        self.assertEqual(plan.tombstoned, [])
        self.assertEqual(self.led.pages["hass"]["state"], LIVE)
        self.assertEqual(self.led.pages["hass"]["absent_nights"], 0)

    def test_settled_pages_are_not_reconsidered(self):
        self.night("2026-07-01")
        self.night("2026-07-02")
        plan = self.night("2026-07-03")
        self.assertEqual(plan.tombstoned, [])
        self.assertEqual(plan.held, {})


class HealthGateTest(GuardTestCase):
    """A truncated scrape must not read as "these products are gone"."""

    def test_page_seen_only_at_untrusted_nurseries_stays_live(self):
        established(self.led, "hass",
                    rows=[row("ladybird"), row("ladybird", url="u2")])
        plan = self.night("2026-07-01", untrusted={"ladybird"}, allow_delete=True)
        self.assertEqual(self.led.pages["hass"]["state"], LIVE)
        self.assertEqual(plan.held["hass"], "untrusted nurseries")

    def test_untrusted_night_does_not_count_toward_the_exit_guard(self):
        established(self.led, "hass", rows=[row("ladybird")])
        self.night("2026-07-01", untrusted={"ladybird"})
        self.night("2026-07-02", untrusted={"ladybird"})
        self.assertEqual(self.led.pages["hass"]["absent_nights"], 0)
        self.assertEqual(self.led.pages["hass"]["state"], LIVE)

    def test_one_trusted_nursery_is_enough_to_believe_the_absence(self):
        established(self.led, "hass",
                    rows=[row("ladybird"), row("daleys", url="u2")])
        self.night("2026-07-01", untrusted={"ladybird"})
        plan = self.night("2026-07-02", untrusted={"ladybird"})
        self.assertEqual(plan.tombstoned, ["hass"])


class EntryGuardTest(GuardTestCase):
    """A page that never established itself is parser noise, not a URL."""

    def _young(self):
        self.led.seed("blip", today="2026-06-28", first_seen="2026-06-25",
                      last_seen="2026-06-28", live_days=3, rows=[row()])

    def test_young_page_is_deleted_when_delete_is_allowed(self):
        self._young()
        self.night("2026-07-01", allow_delete=True)
        plan = self.night("2026-07-02", allow_delete=True)
        self.assertEqual(plan.deleted, ["blip"])
        self.assertEqual(plan.removals, ["blip"])
        self.assertNotIn("blip", self.led.pages)

    def test_young_page_is_held_when_delete_is_not_allowed(self):
        self._young()
        self.night("2026-07-01")
        plan = self.night("2026-07-02")
        self.assertEqual(plan.deleted, [])
        self.assertEqual(plan.removals, [])
        self.assertIn("blip", self.led.pages)
        self.assertIn("blip", plan.held)

    def test_enough_nights_but_too_short_a_span_still_fails(self):
        """The span condition is what stops a page built 7 times in 7 days of
        parser churn from being kept forever."""
        self.led.seed("churn", today="2026-06-30", first_seen="2026-06-26",
                      last_seen="2026-06-30", live_days=ENTRY_GUARD_LIVE_DAYS + 3,
                      rows=[row()])
        self.night("2026-07-01", allow_delete=True)
        plan = self.night("2026-07-02", allow_delete=True)
        self.assertEqual(plan.deleted, ["churn"])

    def test_missed_pipeline_nights_do_not_fail_an_old_page(self):
        """Two missed nights in the last month is why live_days is a count and
        not a streak."""
        self.led.seed("old", today="2026-06-30", first_seen="2026-01-01",
                      last_seen="2026-06-30", live_days=ENTRY_GUARD_LIVE_DAYS,
                      rows=[row()])
        self.night("2026-07-01", allow_delete=True)
        plan = self.night("2026-07-02", allow_delete=True)
        self.assertEqual(plan.deleted, [])
        self.assertEqual(plan.tombstoned, ["old"])


class RenameTest(GuardTestCase):
    def test_products_moved_to_one_slug_redirect(self):
        established(self.led, "dwarf-lychee-salathiel",
                    rows=[row(url="https://d/1"), row(url="https://d/2")])
        urls = {"https://d/1": "lychee-salathiel", "https://d/2": "lychee-salathiel"}
        self.night("2026-07-01", also_tonight=["lychee-salathiel"], url_to_slug=urls)
        plan = self.night("2026-07-02", also_tonight=["lychee-salathiel"],
                          url_to_slug=urls)
        self.assertEqual(plan.redirected, {"dwarf-lychee-salathiel": "lychee-salathiel"})
        entry = self.led.pages["dwarf-lychee-salathiel"]
        self.assertEqual(entry["state"], REDIRECT)
        self.assertEqual(entry["redirect_to"], "lychee-salathiel")

    def test_a_split_tombstones_with_see_also_rather_than_picking_one(self):
        established(self.led, "old",
                    rows=[row(url="https://d/1"), row(url="https://d/2"),
                          row(url="https://d/3")])
        urls = {"https://d/1": "new-a", "https://d/2": "new-a", "https://d/3": "new-b"}
        self.night("2026-07-01", also_tonight=["new-a", "new-b"], url_to_slug=urls)
        plan = self.night("2026-07-02", also_tonight=["new-a", "new-b"],
                          url_to_slug=urls)
        self.assertEqual(plan.redirected, {})
        self.assertEqual(plan.tombstoned, ["old"])
        self.assertEqual(self.led.pages["old"]["see_also"], ["new-a", "new-b"])

    def test_weak_overlap_tombstones_with_see_also(self):
        established(self.led, "old",
                    rows=[row(url=f"https://d/{i}") for i in range(4)])
        urls = {"https://d/0": "new-a"}  # 1 of 4 moved
        self.night("2026-07-01", also_tonight=["new-a"], url_to_slug=urls)
        plan = self.night("2026-07-02", also_tonight=["new-a"], url_to_slug=urls)
        self.assertEqual(plan.redirected, {})
        self.assertEqual(plan.tombstoned, ["old"])
        self.assertEqual(self.led.pages["old"]["see_also"], ["new-a"])

    def test_combo_family_never_renames(self):
        """A combo key comes from taxonomy, so its products cannot reappear
        under a different combo key. No url_to_slug, no rename branch."""
        led = PageLedger(FAMILY_SPECIES_STATE)
        pad = [f"buy-pecan-trees-{i:02d}" for i in range(30)]
        for slug in pad:
            established(led, slug)
        established(led, "buy-feijoa-trees-wa", rows=[row(url="https://d/1")])
        decide_night(led, pad, today="2026-07-01")
        plan = decide_night(led, pad, today="2026-07-02")
        self.assertEqual(plan.redirected, {})
        self.assertEqual(plan.tombstoned, ["buy-feijoa-trees-wa"])

    def test_rename_target_denominator_is_all_stored_rows(self):
        rows = [row(url=f"https://d/{i}") for i in range(4)]
        target, found = rename_target(rows, {"https://d/0": "new", "https://d/1": "new"})
        self.assertEqual(target, "new")  # 2 of 4 is the majority threshold
        target, found = rename_target(rows, {"https://d/0": "new"})
        self.assertIsNone(target)
        self.assertEqual(found, ["new"])

    def test_rename_target_with_no_urls(self):
        self.assertEqual(rename_target([], {"u": "x"}), (None, []))
        self.assertEqual(rename_target([row(url="")], {"u": "x"}), (None, []))


class RetiredTest(GuardTestCase):
    def setUp(self):
        super().setUp()
        established(self.led, "gone")

    def test_retired_deletes_the_file_but_keeps_the_record(self):
        def check(slug, entry):
            return "denied in variety_overrides.json"

        self.night("2026-07-01", retired_check=check, allow_delete=True)
        plan = self.night("2026-07-02", retired_check=check, allow_delete=True)
        self.assertEqual(plan.retired, ["gone"])
        self.assertEqual(self.led.pages["gone"]["state"], RETIRED)
        self.assertEqual(self.led.pages["gone"]["retired_reason"],
                         "denied in variety_overrides.json")

    def test_retired_is_held_when_delete_is_not_allowed(self):
        def check(slug, entry):
            return "left taxonomy"

        self.night("2026-07-01", retired_check=check)
        plan = self.night("2026-07-02", retired_check=check)
        self.assertEqual(plan.retired, [])
        self.assertEqual(self.led.pages["gone"]["state"], LIVE)
        self.assertIn("gone", plan.held)

    def test_still_in_taxonomy_tombstones(self):
        def check(slug, entry):
            return None

        self.night("2026-07-01", retired_check=check, allow_delete=True)
        plan = self.night("2026-07-02", retired_check=check, allow_delete=True)
        self.assertEqual(plan.tombstoned, ["gone"])
        self.assertEqual(plan.removals, [])


class CircuitBreakerTest(unittest.TestCase):
    def _led(self, n=100):
        led = PageLedger(FAMILY_VARIETY)
        for i in range(n):
            established(led, f"slug-{i:03d}")
        return led

    def test_collapsed_page_count_changes_no_states(self):
        led = self._led()
        tonight = [f"slug-{i:03d}" for i in range(50)]
        plan = decide_night(led, tonight, today="2026-07-01", allow_delete=True)
        self.assertTrue(plan.skipped)
        self.assertEqual(plan.tombstoned, [])
        self.assertEqual(plan.removals, [])
        self.assertEqual(led.skipped_nights, 1)
        self.assertTrue(all(e["state"] == LIVE for e in led.pages.values()))
        self.assertTrue(all(e["absent_nights"] == 0 for e in led.pages.values()))

    def test_normal_churn_passes_the_floor(self):
        led = self._led()
        tonight = [f"slug-{i:03d}" for i in range(95)]
        plan = decide_night(led, tonight, today="2026-07-01")
        self.assertFalse(plan.skipped)
        self.assertEqual(led.skipped_nights, 0)

    def test_seeding_ledger_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            led = PageLedger.load(Path(tmp) / "nope.json", FAMILY_VARIETY,
                                  log=lambda *_: None)
            led.observe("hass", today="2026-08-16", rows=[row()])
            plan = decide_night(led, ["hass"], today="2026-08-16", allow_delete=True)
            self.assertTrue(plan.seeding)
            self.assertEqual(plan.tombstoned, [])
            self.assertIn("seeding", plan.summary())

    def test_nightly_tombstone_cap_bounds_the_damage(self):
        led = PageLedger(FAMILY_VARIETY)
        for i in range(MAX_TOMBSTONES_PER_NIGHT + 20):
            established(led, f"slug-{i:04d}")
        # Absent for two nights, but the floor must not trip: keep enough of
        # tonight's slugs alive by giving the ledger extra live pages.
        for i in range(2000):
            established(led, f"keep-{i:04d}")
        tonight = [f"keep-{i:04d}" for i in range(2000)]
        decide_night(led, tonight, today="2026-07-01")
        plan = decide_night(led, tonight, today="2026-07-02")
        self.assertEqual(len(plan.tombstoned), MAX_TOMBSTONES_PER_NIGHT)
        self.assertEqual(len(plan.held), 20)
        # Held pages are reconsidered tomorrow without the night counting
        # against them twice.
        plan2 = decide_night(led, tonight, today="2026-07-03")
        self.assertEqual(len(plan2.tombstoned), 20)


class RedirectChainTest(unittest.TestCase):
    def _chain(self):
        led = PageLedger(FAMILY_VARIETY)
        established(led, "a", state=REDIRECT)
        established(led, "b", state=REDIRECT)
        established(led, "c")
        led.pages["a"]["redirect_to"] = "b"
        led.pages["b"]["redirect_to"] = "c"
        return led

    def test_chain_resolves_to_the_terminal_target(self):
        led = self._chain()
        targets = led.resolve_redirects("2026-07-01")
        self.assertEqual(targets, {"a": "c", "b": "c"})
        self.assertEqual(led.pages["a"]["redirect_to"], "c")

    def test_cycle_does_not_hang(self):
        led = PageLedger(FAMILY_VARIETY)
        established(led, "a", state=REDIRECT)
        established(led, "b", state=REDIRECT)
        led.pages["a"]["redirect_to"] = "b"
        led.pages["b"]["redirect_to"] = "a"
        targets = led.resolve_redirects("2026-07-01")
        self.assertEqual(set(targets), {"a", "b"})
        self.assertTrue(any(n["reason"] == "redirect cycle" for n in led.review))

    def test_target_outside_the_ledger_is_kept_as_is(self):
        led = PageLedger(FAMILY_VARIETY)
        established(led, "a", state=REDIRECT)
        led.pages["a"]["redirect_to"] = "somewhere-else"
        self.assertEqual(led.resolve_redirects(), {"a": "somewhere-else"})


class WritePageTest(unittest.TestCase):
    def test_writes_and_creates_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variety" / "hass.html"
            self.assertTrue(write_page(path, "<html>hi</html>"))
            self.assertEqual(path.read_text(), "<html>hi</html>")

    def test_unchanged_content_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hass.html"
            write_page(path, "<html>hi</html>")
            before = path.stat().st_mtime_ns
            self.assertFalse(write_page(path, "<html>hi</html>"))
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_changed_content_is_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hass.html"
            write_page(path, "a")
            self.assertTrue(write_page(path, "b"))
            self.assertEqual(path.read_text(), "b")

    def test_leaves_no_temp_files_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(Path(tmp) / "hass.html", "a")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["hass.html"])


class PlanReportingTest(GuardTestCase):
    def test_summary_names_what_happened(self):
        established(self.led, "hass")
        self.night("2026-07-01")
        plan = self.night("2026-07-02")
        self.assertIn("1 tombstoned", plan.summary())

    def test_review_records_non_obvious_classifications(self):
        established(self.led, "old",
                    rows=[row(url="https://d/1"), row(url="https://d/2")])
        urls = {"https://d/1": "new-a", "https://d/2": "new-b"}
        self.night("2026-07-01", also_tonight=["new-a", "new-b"], url_to_slug=urls)
        self.night("2026-07-02", also_tonight=["new-a", "new-b"], url_to_slug=urls)
        reasons = [n["reason"] for n in self.led.review]
        self.assertIn("split or partial rename", reasons)


if __name__ == "__main__":
    unittest.main()
