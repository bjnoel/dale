"""
Golden-file SEO regression tests.

Each builder in GOLDEN_CASES is run against the committed fixture and its
date-normalised output compared against tests/golden/expected/. This is the gate
for every output-changing refactor PR: when a refactor is meant to be
output-preserving these must stay green; when output is intentionally changed,
regenerate with GOLDEN_UPDATE=1 and review the diff before committing.

    python3 -m unittest discover tests/                      # run
    GOLDEN_UPDATE=1 python3 -m unittest tests.test_golden    # regenerate goldens

Coverage grows per PR: a builder is golden-pinned by the PR that refactors it.
Currently covered: build-dashboard.py. NOT yet covered: the SEO page builders
(species/variety/nursery/location/compare/digest), added in their PRs.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden_runner import run_builder, EXPECTED_DIR

UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"

GOLDEN_CASES = [
    {
        "name": "dashboard",
        "script": "build-dashboard.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["index.html"],
    },
    {
        "name": "variety",
        "script": "build_variety_pages.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["variety/*.html"],
    },
    {
        "name": "compare",
        "script": "build_compare_pages.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["compare/*.html"],
    },
    {
        "name": "nursery_compare",
        "script": "build_nursery_compare.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["compare/nurseries.html"],
    },
    {
        "name": "rare_finds",
        "script": "build_rare_finds.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["rare.html"],
    },
    {
        "name": "species_trends",
        "script": "build_species_trends.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["trends.html"],
    },
    {
        "name": "species_pages",
        "script": "build_species_pages.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["species/*.html"],
    },
    {
        # The fixture has no dated snapshots, so this pins the no-changes page
        # (shell + empty state). The change-item escaping is verified separately
        # against a crafted 2-date dataset (see the PR).
        "name": "daily_digest",
        "script": "daily_digest.py",
        "args": ["{DATA}", "--page", "--save", "{OUT}/digest.html"],
        "outputs": ["digest.html"],
    },
    {
        # No dated snapshots in the fixture -> the empty-timeline page (const H = []).
        "name": "history",
        "script": "build_history.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["history.html"],
    },
    {
        "name": "location",
        "script": "build_location_pages.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["buy-fruit-trees-*.html"],
    },
    {
        # Index + the combo pages (the fixture yields one, avocado-WA). The
        # combo pages carry the scraped product titles the migration escapes.
        "name": "species_state",
        "script": "build_species_state_pages.py",
        "args": ["{DATA}", "{OUT}"],
        "outputs": ["buy-*-trees-*.html"],
    },
    {
        # static page, no data dir; pinned here so the Jinja2 migration's only
        # golden diff is the entity-escaping (the & in the UTM hrefs).
        "name": "treesmith",
        "script": "build_treesmith_page.py",
        "args": ["{OUT}"],
        "outputs": ["treesmith.html"],
    },
]


class GoldenTest(unittest.TestCase):
    pass


def _make_test(case):
    def test(self):
        produced = run_builder(case["script"], case["args"], case["outputs"])
        expected_root = EXPECTED_DIR / case["name"]
        if UPDATE:
            for old in sorted(expected_root.rglob("*"), reverse=True):
                if old.is_file():
                    old.unlink()
            for rel, text in produced.items():
                dest = expected_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text)
            self.skipTest(f"GOLDEN_UPDATE: wrote {len(produced)} file(s) for {case['name']}")
            return
        self.assertTrue(
            expected_root.exists(),
            f"No goldens for {case['name']}. Generate with GOLDEN_UPDATE=1.",
        )
        expected_files = {
            str(p.relative_to(expected_root)) for p in expected_root.rglob("*") if p.is_file()
        }
        self.assertEqual(
            set(produced), expected_files,
            f"{case['name']}: produced file set != golden file set",
        )
        for rel, text in produced.items():
            self.assertEqual(
                text, (expected_root / rel).read_text(),
                f"{case['name']}/{rel} differs from golden (normalised). "
                f"If intended, regenerate with GOLDEN_UPDATE=1 and review.",
            )

    return test


for _case in GOLDEN_CASES:
    setattr(GoldenTest, f"test_{_case['name']}", _make_test(_case))


if __name__ == "__main__":
    unittest.main()
