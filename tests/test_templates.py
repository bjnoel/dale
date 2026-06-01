"""
Tests for stocklib/templates.py -- the shared autoescaping Jinja2 environment
the page builders render through.

The reason this module exists is escaping, so that is what is pinned here: an
`&`/`<`/`>`/quote interpolated into a template comes out as HTML entities, while
literal entity text already in the template is left alone (no double-escaping).
The whitespace flags are pinned too, because byte-stability of the migrated
builders depends on them (keep_trailing_newline in particular).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib import templates  # noqa: E402


class TemplateEnvTest(unittest.TestCase):
    def test_environment_flags(self):
        env = templates.get_env()
        self.assertTrue(env.autoescape, "autoescape must be on -- it is the point")
        self.assertTrue(env.trim_blocks)
        self.assertTrue(env.lstrip_blocks)
        self.assertTrue(
            env.keep_trailing_newline,
            "keep_trailing_newline must be on so migrated builders stay byte-stable "
            "except for escaping",
        )

    def test_interpolated_values_are_escaped(self):
        out = templates.get_env().from_string("{{ v }}").render(v='Fig & Olive <b> "q\'')
        self.assertEqual(out, "Fig &amp; Olive &lt;b&gt; &#34;q&#39;")

    def test_ampersand_in_url_is_escaped(self):
        # the build_treesmith_page case: UTM query strings carry a raw &
        url = "https://treesmith.app/?utm_source=treestock&utm_medium=x"
        out = templates.get_env().from_string('<a href="{{ u }}">x</a>').render(u=url)
        self.assertIn("utm_source=treestock&amp;utm_medium=x", out)

    def test_literal_template_text_is_not_double_escaped(self):
        # a literal &amp; / &rarr; in the template is static text, left as-is;
        # only the interpolated value is escaped.
        out = templates.get_env().from_string("see more &rarr; {{ v }}").render(v="A & B")
        self.assertEqual(out, "see more &rarr; A &amp; B")

    def test_keep_trailing_newline(self):
        self.assertEqual(templates.get_env().from_string("x\n").render(), "x\n")


if __name__ == "__main__":
    unittest.main()
