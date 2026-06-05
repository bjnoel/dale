"""
Jujube growing-guide tests (tools/scrapers/growing_guides/jujube.json).

Jujube (Ziziphus jujuba, Chinese jujube / Chinese date) is a hot-dry-climate,
intensely drought and heat hardy deciduous tree, so like banana/cherry/mulberry it
gets its OWN climate category ("jujube") rather than the generic "temperate /
choose low-chill" note, which understates its heat-and-drought love and wrongly
implies it is hard to get in WA (WA is in fact one of Australia's two leading
jujube states). In its own file so parallel guide runs never collide.

Correctness guards below pin the verified research:
  * Chinese jujube (Z. jujuba) is NOT the evergreen tropical Indian jujube
    (Z. mauritiana); the Indian-jujube RFCA article is kept OUT of further reading.
  * WA's fruit fly is Mediterranean fruit fly (jujube IS a registered Medfly host
    in WA per DPIRD); WA has no established Queensland fruit fly.
  * In the eastern states Chinese jujube is NOT on the official Qfly host list and
    is at most a minor host (do not conflate with Z. mauritiana); net anyway.
  * Largely self-fertile but crops better with a second cultivar (NMSU/CRFG).
  * Suckers come from the wild sour-jujube rootstock, not the grafted cultivar.
  * No invented NPK rate (research on jujube fertilisation is limited).
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    bssp, gg, EM_DASH, EN_DASH, STATES, VALID_SLUGS, load_guide, build_state_pages, assert_no_dashes,
)

JUJUBE_SPECIES = {
    "common_name": "Jujube",
    "latin_name": "Ziziphus jujuba",
    "description": "Generic jujube blurb that should be replaced by the rich guide.",
    "slug": "jujube",
}


def _jujube_products(n=10):
    # Real in-stock jujube cultivars so the table renders alongside the guide.
    names = ["Li", "Honey Jar", "Chico", "GA866", "Shanxi Li", "Si Hong",
             "Sugar Cane", "Tiger Tooth Early", "Lang", "Silverhill"]
    return [
        {
            "title": f"Jujube {names[i % len(names)]}",
            "url": f"https://nursery.example/jujube-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 99.0 + i * 5,
            "available": True,
            "species": JUJUBE_SPECIES,
        }
        for i in range(n)
    ]


JUJUBE_PAGES = build_state_pages("jujube", _jujube_products())
JUJUBE_JSON = load_guide("jujube")

# Each state's distinctive region tokens. Must appear on that state's page and on
# NO other state's page. Pure place names that are not substrings of in-stock
# cultivar names, common words, or site chrome ("Perth" alone is footer chrome,
# so WA uses the two-word "Perth Hills").
JUJUBE_REGION_TOKENS = {
    "WA": ["Perth Hills", "Great Southern", "Gascoyne"],
    "QLD": ["Goondiwindi", "Granite Belt", "Stanthorpe"],
    "NSW": ["Central West", "Mudgee", "Riverina"],
    "VIC": ["Mildura", "Sunraysia", "Irymple"],
}


class JujubeGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in JUJUBE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} jujube page too small")

    def test_canonical_and_og(self):
        wa = JUJUBE_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-jujube-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = JUJUBE_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Jujube in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in JUJUBE_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Jujube in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in JUJUBE_PAGES.items():
            self.assertNotIn("Generic jujube blurb", html, f"{st} still shows the blurb")

    # --- climate category: jujube is its own category, NOT temperate/mediterranean ---
    def test_jujube_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["jujube"], "jujube",
                         "jujube must not inherit the generic temperate or mediterranean note")

    def test_every_state_has_a_jujube_climate_note(self):
        for st in STATES:
            self.assertIn("jujube", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no jujube-specific climate note")

    def test_jujube_climate_note_is_not_the_temperate_note(self):
        # The generic temperate note tells growers to "choose low-chill varieties",
        # which understates jujube's heat/drought love; its note must tell that story.
        for st in STATES:
            note = bssp.get_climate_note("Jujube", st)
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["temperate"],
                                f"{st} jujube note is the generic temperate note")
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["default"],
                                f"{st} jujube note is the generic default note")

    def test_jujube_climate_notes_have_no_dashes(self):
        for st in STATES:
            note = bssp.get_climate_note("Jujube", st)
            self.assertNotIn(EM_DASH, note, f"em dash in {st} jujube climate note")
            self.assertNotIn(EN_DASH, note, f"en dash in {st} jujube climate note")

    def test_wa_climate_note_frames_wa_as_a_leading_producer(self):
        # The generic WA note implies jujube is hard to get here; the real story is
        # the opposite (WA is a leading jujube state), so the jujube note must not
        # lead with the "strict quarantine limits options" framing.
        note = bssp.get_climate_note("Jujube", "WA").lower()
        self.assertIn("jujube", note)
        self.assertIn("one of australia's main jujube regions", note)

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(JUJUBE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two jujube state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in JUJUBE_REGION_TOKENS.items():
            self.assertTrue(any(t in JUJUBE_PAGES[st] for t in tokens),
                            f"{st} jujube page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in JUJUBE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, JUJUBE_PAGES[other],
                                     f"{owner} jujube token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("jujube", "WA")
        self.assertIn("Where jujubes grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)         # core
        self.assertLess(wa.index("Where jujubes grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in JUJUBE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} jujube page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} jujube page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, JUJUBE_JSON, "jujube.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', JUJUBE_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', JUJUBE_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in JUJUBE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in JUJUBE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "agriculture.gov.au", "pubs.nmsu.edu",
            )),
            "expected at least one agriculture-authority among the jujube sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria 403 to automated fetchers, so they cannot
        # be cited under the URL-200 gate (citrus/cherry batch finding). Anchor eastern
        # claims on Business Queensland, DAFF, NT DAF and the grower sources instead.
        joined = json.dumps(JUJUBE_JSON)
        for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au"):
            self.assertNotIn(blocked, joined, f"jujube guide cites a bot-blocked source: {blocked}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in JUJUBE_JSON["sources"]}
        cited = set()
        for block in [JUJUBE_JSON["core"]] + list(JUJUBE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "jujube guide cites an unknown source id")

    def test_sources_note_does_not_leak_other_species_copy(self):
        self.assertNotIn("olive", JUJUBE_PAGES["WA"].lower())

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(JUJUBE_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(JUJUBE_JSON["core"]["faqs"]) + len(JUJUBE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', JUJUBE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("jujube"))

    # --- owned Further reading: WANATCA + RFCA; Indian-jujube article kept OUT ---
    def test_further_reading_has_wanatca_and_rfca(self):
        fr = gg.get_further_reading("jujube")
        self.assertTrue(fr, "jujube should have curated Further reading")
        urls = [e["url"] for e in fr]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "expected a WANATCA jujube link")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Jujube" in u for u in urls),
                        "expected an RFCA jujube link")
        for st in STATES:
            self.assertIn('id="further-reading"', JUJUBE_PAGES[st], f"{st} missing Further reading")
            self.assertIn("wanatca.org.au", JUJUBE_PAGES[st], f"{st} missing WANATCA link")

    def test_indian_jujube_article_excluded_from_further_reading(self):
        # The RFCA folder mixes in "The Indian Jujube" (JujubeCulture3-92.htm), which
        # is Ziziphus MAURITIANA, a different (evergreen, tropical) species with
        # different culture. Chinese-jujube further reading must not surface it
        # (the dragon-fruit Pitaya / papaya babaco mixed-folder pattern).
        urls = [e["url"] for e in gg.get_further_reading("jujube")]
        self.assertFalse(any("JujubeCulture3-92" in u for u in urls),
                         "the Indian-jujube (Z. mauritiana) article leaked into Chinese-jujube further reading")

    # --- correctness guards (pin the verified research) ---
    def test_chinese_vs_indian_jujube_distinguished(self):
        for st in STATES:
            html = JUJUBE_PAGES[st]
            self.assertIn("Ziziphus mauritiana", html,
                          f"{st} page should distinguish Chinese jujube from the Indian jujube")
            self.assertIn("Indian jujube", html, f"{st} page should name the Indian jujube")

    def test_largely_self_fertile_but_plant_two(self):
        sp = gg.render_species_guide("jujube")
        self.assertIn("self-fertile", sp, "core should state jujube is largely self-fertile")
        self.assertIn("two or more different cultivars", sp,
                      "core should recommend a second cultivar for better cropping")

    def test_drought_heat_and_difficult_soil_tolerance(self):
        sp = gg.render_species_guide("jujube").lower()
        for word in ("drought", "heat", "alkaline", "saline"):
            self.assertIn(word, sp, f"core should mention jujube's {word} tolerance")

    def test_rootstock_suckers_are_wild_sour_jujube(self):
        sp = gg.render_species_guide("jujube")
        self.assertIn("sour jujube", sp, "core should name the wild sour-jujube rootstock")
        self.assertIn("suckers", sp.lower(), "core should warn about suckering")
        self.assertIn("not your named variety", sp,
                      "core should explain suckers are rootstock, not the grafted cultivar")

    def test_no_invented_npk_rate(self):
        # The research found no published jujube-specific NPK rate (NMSU: limited
        # research). The guide must say so and must not print a fabricated ratio.
        sp = gg.render_species_guide("jujube")
        self.assertIn("No reliable jujube-specific NPK rate has been published", sp)
        self.assertNotRegex(sp, r"\b\d+\s*[:|]\s*\d+\s*[:|]\s*\d+\b",
                            "core appears to quote an unsourced NPK ratio")

    def test_deciduous_and_frost_escaping(self):
        sp = gg.render_species_guide("jujube").lower()
        self.assertIn("deciduous", sp, "core should state jujube is deciduous")

    def test_wa_fly_is_medfly_and_jujube_is_a_host(self):
        wa = JUJUBE_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa, "WA page must name Medfly")
        self.assertIn("does use jujube as a host", wa,
                      "WA page must state jujube is a Medfly host (DPIRD registers sprays)")
        self.assertIn("no established Queensland fruit fly", wa,
                      "WA page must state WA has no established Qfly")

    def test_eastern_states_qfly_nuance(self):
        # Chinese jujube is NOT on the official Qfly host list and is at most a minor
        # host, but Qfly is endemic in the east so growers still net. Each eastern
        # page must name Qfly AND carry the "minor host" nuance (not a flat host claim).
        for st in ("QLD", "NSW", "VIC"):
            html = JUJUBE_PAGES[st]
            self.assertIn("Queensland fruit fly", html, f"{st} should name Qfly")
            self.assertIn("minor host", html, f"{st} should carry the minor-host nuance")

    def test_wa_is_flagship_leading_producer(self):
        self.assertIn("leading jujube", JUJUBE_PAGES["WA"],
                      "WA overlay should frame WA as a leading jujube state")


if __name__ == "__main__":
    unittest.main()
