"""
Fig growing-guide tests (tools/scrapers/growing_guides/fig.json). Mediterranean crop.
In its own file so parallel guide runs never collide on a shared test module.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    bssp, EM_DASH, EN_DASH, STATES, VALID_SLUGS, load_guide, build_state_pages, assert_no_dashes,
)

FIG_SPECIES = {
    "common_name": "Fig",
    "latin_name": "Ficus carica",
    "description": "Generic fig blurb that the rich guide should replace.",
    "slug": "fig",
}


def _fig_products(n=6):
    return [
        {"title": f"Fig Variety {i}", "url": f"https://nursery.example/fig-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 25.0 + i * 5,
         "available": True, "species": FIG_SPECIES}
        for i in range(n)
    ]


FIG_PAGES = build_state_pages("fig", _fig_products())
FIG_JSON = load_guide("fig")

FIG_REGION_TOKENS = {
    "WA": ["Swan Valley", "Perth Hills"],
    "QLD": ["Lockyer Valley", "Granite Belt"],
    "NSW": ["Riverina", "Central West"],
    "VIC": ["Mornington Peninsula", "Goulburn Valley"],
}


class FigGuideTests(unittest.TestCase):
    """Fig reuses the olive guards to stay per-state-unique, dash-free, cited, Mediterranean."""

    def test_pages_build_and_mutually_distinct(self):
        bodies = list(FIG_PAGES.values())
        for st, html in FIG_PAGES.items():
            self.assertGreater(len(html), 5000, f"fig {st} page too small")
            self.assertNotIn("Generic fig blurb", html, f"fig {st} still shows the blurb")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two fig state pages are identical")

    def test_each_state_has_region_tokens(self):
        for st, tokens in FIG_REGION_TOKENS.items():
            self.assertTrue(any(t in FIG_PAGES[st] for t in tokens),
                            f"fig {st} page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak(self):
        for owner, tokens in FIG_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, FIG_PAGES[other],
                                     f"fig {owner} token '{t}' leaked onto {other}")

    def test_no_em_or_en_dashes(self):
        for st, html in FIG_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on fig {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on fig {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, FIG_JSON, "fig.json")

    def test_faq_jsonld_parses_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          FIG_PAGES[st], re.S)
            self.assertIsNotNone(m, f"fig {st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(FIG_JSON["core"]["faqs"]) + len(FIG_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"fig {st} FAQ count mismatch")

    def test_sources_and_further_reading_present(self):
        for st in STATES:
            self.assertIn('id="sources"', FIG_PAGES[st], f"fig {st} missing Sources")
            self.assertIn('id="further-reading"', FIG_PAGES[st], f"fig {st} missing Further reading")
        fr = re.search(r'id="further-reading".*?</section>', FIG_PAGES["WA"], re.S).group(0)
        self.assertIn("wanatca.org.au", fr, "fig Further reading missing WANATCA")
        self.assertIn("rfcarchives.org.au", fr, "fig Further reading missing RFCA")

    def test_sources_https_and_cited_ids_resolve(self):
        for s in FIG_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https fig source: {s['url']}")
        src_ids = {s["id"] for s in FIG_JSON["sources"]}
        cited = set()
        for block in [FIG_JSON["core"]] + list(FIG_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "fig guide cites an unknown source id")

    def test_fig_is_mediterranean_not_subtropical(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["fig"], "mediterranean")
        note = bssp.get_climate_note("Fig", "WA")
        self.assertIn("fig", note.lower(), "WA mediterranean climate note should mention figs")
        self.assertNotIn("Chilling hours may be lower", note,
                         "fig should not inherit the stone/pome-fruit chill-hours note")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', FIG_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"fig {st} has /species/ links that would 404")


if __name__ == "__main__":
    unittest.main()
