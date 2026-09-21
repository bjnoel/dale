"""
Size guardrail for the autonomous session prompt.

On 2026-08-10 autonomous Dale stopped running for 44 hours. The proximate cause
was that the prompt was passed as a single argv string and Linux caps one of
those at MAX_ARG_STRLEN (32 pages = 131072 bytes), which is a different and much
lower ceiling than ARG_MAX. The prompt had reached 137785B. It now goes on stdin,
so that particular wall is gone (DEC-279).

The wall is gone; the growth was not. state/business-state.json went 5,679B
(2026-07-23) -> 85,790B (2026-08-12) -> 118,580B (2026-09-17). DEC-279 answered
it by compressing bodies: long prose renders as its opening claim. That bought
five weeks and the ceiling came back, because the growth is not a stale tail to
prune. On 2026-09-21, 79KB of the 118KB was under thirty days old, and the whole
file rendered to 62,921B, which was 64% of the session prompt, carrying 1,530B of
actual metrics.

DEC-349 split it. Metrics stay in state/business-state.json; each finding is its
own file under state/findings/ and reaches the prompt as one line carrying its
claim. The block is now O(number of findings) instead of O(bytes of findings),
so a four-thousand-word investigation costs the same as a one-liner.

These tests are the report that a jump happened. They are the second line of
defence, not the first: the renderers now take a byte budget and degrade under it,
so a breach here means the budget logic is wrong rather than that someone wrote
too much. If one fails, do NOT just raise the ceiling. Look at what grew:

    python3 tools/autonomous/session-prompt.py --session-type normal | wc -c

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE = REPO_ROOT / "state" / "business-state.json"
FINDINGS = REPO_ROOT / "state" / "findings"

# Ceilings, in bytes.
# The state file is metrics only since DEC-349 and measured 11,129B at the split.
# 20,000 is room to breathe; past it, findings are being written back into it.
MAX_STATE_FILE = 20_000
MAX_RENDERED_STATE = 12_000
MAX_RENDERED_FINDINGS = 24_000

# One sentence. A claim that needs more than this is an argument, and the
# argument belongs in the body where it costs the prompt nothing.
MAX_CLAIM_CHARS = 240

# The argv limit that caused DEC-279. Nothing should pass a prompt as one
# argument again, but if something does, this is the number it dies at.
MAX_ARG_STRLEN = 131_072


def _load_prompt_module():
    import importlib.util

    path = REPO_ROOT / "tools" / "autonomous" / "session-prompt.py"
    spec = importlib.util.spec_from_file_location("session_prompt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _findings():
    return sorted(FINDINGS.rglob("*.json"))


class TestBusinessStateSize(unittest.TestCase):
    def test_state_file_has_not_ballooned(self):
        size = STATE.stat().st_size
        self.assertLess(
            size, MAX_STATE_FILE,
            f"state/business-state.json is {size:,}B (ceiling {MAX_STATE_FILE:,}B). "
            "Since DEC-349 it is metrics ONLY. A dated finding belongs in its own "
            "file under state/findings/ with an authored claim. Do not just raise "
            "this number.",
        )

    def test_state_file_is_valid_json(self):
        # render_business_state degrades to an error string rather than raising,
        # so a corrupt file would otherwise shrink the prompt and look like a win.
        with open(STATE) as f:
            json.load(f)

    def test_rendered_state_is_far_smaller_than_the_file(self):
        mod = _load_prompt_module()
        rendered = mod.render_business_state(str(STATE))
        raw = STATE.stat().st_size

        self.assertNotIn("is not valid JSON", rendered)
        self.assertLess(
            len(rendered), MAX_RENDERED_STATE,
            f"rendered business state is {len(rendered):,}B "
            f"(ceiling {MAX_RENDERED_STATE:,}B)",
        )
        self.assertLess(
            len(rendered), raw,
            "the renderer is supposed to shrink the file, not grow it",
        )

    def test_metrics_survive_the_render(self):
        """The headline says "metrics only", so the metrics must come through
        verbatim. Only long prose is allowed to lose its body."""
        mod = _load_prompt_module()
        rendered = mod.render_business_state(str(STATE))
        with open(STATE) as f:
            state = json.load(f)

        for key in ("revenue_monthly", "expenses_monthly", "phase", "last_updated"):
            if key in state:
                self.assertIn(
                    f"{key}: {json.dumps(state[key])}", rendered,
                    f"{key} is a metric and must render verbatim",
                )

    def test_a_long_finding_keeps_its_opening_claim(self):
        """Headlining must preserve the claim. A finding truncated to nothing
        would silently drop the thing that stops a wrong conclusion recurring."""
        mod = _load_prompt_module()
        long_value = (
            "DEC-237's claim that the 30-plant free tier means almost nobody sees "
            "the paywall is WRONG. 76 of 290 people have seen it. " + "x" * 400
        )
        out = mod.render_business_state.__globals__["_first_sentence"](long_value)
        self.assertIn("WRONG", out)
        self.assertLess(len(out), 260)
        self.assertNotIn("xxxxx", out)


class TestStateBudgetIsEnforcedNotReported(unittest.TestCase):
    """The budget is the fix; this file is only the report.

    Before DEC-349 nothing stopped the block growing. The test above failed on
    2026-09-21 at 62,850B against a 60,000B ceiling, which is a breach discovered
    after it had been shipping every hour for days. These assert that the renderer
    refuses to exceed its budget in the first place.
    """

    def test_state_render_obeys_a_tiny_budget(self):
        mod = _load_prompt_module()
        out = mod.render_business_state(str(STATE), budget=800)
        self.assertLessEqual(len(out) - len(out.split("\n(")[-1]), 900)
        self.assertIn("dropped to stay under", out)

    def test_state_render_says_when_it_dropped_something(self):
        """A silent truncation is worse than a large prompt: it reads as absence."""
        mod = _load_prompt_module()
        full = mod.render_business_state(str(STATE))
        squeezed = mod.render_business_state(str(STATE), budget=800)
        self.assertNotIn("dropped to stay under", full)
        self.assertIn("something large has been written into it", squeezed)

    def test_findings_render_obeys_a_tiny_budget(self):
        mod = _load_prompt_module()
        out = mod.render_findings_index(str(FINDINGS), budget=1500)
        body = "\n".join(out.split("\n")[1:]).split("\n(")[0]
        self.assertLessEqual(len(body), 1500)

    def test_findings_degrade_to_date_and_path_before_vanishing(self):
        """Losing the claim is a real loss; losing the line is a worse one."""
        mod = _load_prompt_module()
        out = mod.render_findings_index(str(FINDINGS), budget=2000)
        self.assertIn("shown without their claim", out)
        listed = [l for l in out.splitlines() if l.startswith("20")]
        self.assertGreater(len(listed), 8)

    def test_findings_name_what_they_omitted(self):
        mod = _load_prompt_module()
        out = mod.render_findings_index(str(FINDINGS), budget=300)
        self.assertIn("not listed", out)


class TestFindingsIndex(unittest.TestCase):
    def test_there_are_findings(self):
        self.assertGreater(len(_findings()), 20, "state/findings/ is empty or missing")

    def test_every_finding_has_an_authored_claim_and_date(self):
        """Both are authored, and the reason is measured.

        A prototype derived them from the body. It produced a usable claim for
        about a third ("DEAD, measured twice (DEC-241, DEC-325)") and provenance
        for most of the rest ("DEC-343 / DAL-295 (2026-09-17)"). The date
        heuristic read DAL-301's scheduled 2026-10-15 re-read as the date of the
        finding that mentions it.
        """
        import re

        for f in _findings():
            doc = json.loads(f.read_text())
            rel = f.relative_to(REPO_ROOT)
            for key in ("claim", "date", "track", "was", "body"):
                self.assertIn(key, doc, f"{rel} has no {key}")
            self.assertRegex(doc["date"], r"^20\d\d-\d\d-\d\d$", f"{rel} date")
            self.assertGreater(len(doc["claim"]), 40, f"{rel} claim is too thin to act on")
            self.assertLessEqual(
                len(doc["claim"]), MAX_CLAIM_CHARS,
                f"{rel} claim is {len(doc['claim'])} chars. It is one sentence; the "
                "argument goes in the body, where it costs the prompt nothing.",
            )
            self.assertNotRegex(
                doc["claim"], r"^\s*(DEC|DAL)-\d+",
                f"{rel} claim opens with provenance, not a claim. Say what is true.",
            )

    def test_no_finding_is_dated_in_the_future(self):
        """The date is when we learned it, not when we next look.

        Several findings carry a scheduled re-read date in the body; that is not
        this field.
        """
        from datetime import date, timedelta

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        for f in _findings():
            doc = json.loads(f.read_text())
            self.assertLess(
                doc["date"], tomorrow,
                f"{f.relative_to(REPO_ROOT)} is dated in the future",
            )

    def test_rendered_findings_stay_under_budget(self):
        mod = _load_prompt_module()
        out = mod.render_findings_index(str(FINDINGS))
        self.assertLess(
            len(out), MAX_RENDERED_FINDINGS,
            f"findings index is {len(out):,}B (ceiling {MAX_RENDERED_FINDINGS:,}B). "
            "The index is one line per finding, so this means the count grew a lot "
            "or the claims did. Check the claims first.",
        )

    def test_every_claim_reaches_the_prompt(self):
        mod = _load_prompt_module()
        out = mod.render_findings_index(str(FINDINGS))
        for f in _findings():
            claim = json.loads(f.read_text())["claim"]
            self.assertIn(
                " ".join(claim.split())[:60], out,
                f"{f.relative_to(REPO_ROOT)}'s claim did not reach the prompt",
            )

    def test_an_unreadable_finding_is_reported_not_skipped(self):
        """A finding that silently vanishes from the index is a finding nobody
        knows to read, which is the failure the whole split exists to avoid."""
        import tempfile

        mod = _load_prompt_module()
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "a"
            good.mkdir()
            (good / "ok.json").write_text(json.dumps(
                {"claim": "Something true enough to act on and long enough to pass.",
                 "date": "2026-09-01", "track": "a", "was": "x", "body": {}}))
            (good / "broken.json").write_text("{not json")
            out = mod.render_findings_index(d)
            self.assertIn("UNREADABLE", out)
            self.assertIn("broken.json", out)
            self.assertIn("Something true enough", out)

    def test_findings_are_newest_first(self):
        mod = _load_prompt_module()
        dates = [l.split("  ")[0] for l in
                 mod.render_findings_index(str(FINDINGS)).splitlines() if l.startswith("20")]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_a_missing_directory_says_so_rather_than_rendering_empty(self):
        mod = _load_prompt_module()
        out = mod.render_findings_index("/nonexistent/findings")
        self.assertIn("no findings directory", out)


class TestTheSplitLostNothing(unittest.TestCase):
    """Every finding names the business-state path it came from, and the manifest
    that moved it is committed, so the split is re-derivable rather than a thing
    that happened once (DEC-313)."""

    def test_every_finding_names_its_origin(self):
        for f in _findings():
            doc = json.loads(f.read_text())
            self.assertTrue(
                doc["was"].startswith("tracks."),
                f"{f.relative_to(REPO_ROOT)} does not say where it came from",
            )

    def test_origins_are_unique(self):
        origins = [json.loads(f.read_text())["was"] for f in _findings()]
        dupes = {o for o in origins if origins.count(o) > 1}
        self.assertEqual(dupes, set(), "two findings claim the same origin path")

    def test_the_manifest_covers_every_finding_on_disk(self):
        import importlib.util
        import sys

        sys.path.insert(0, str(REPO_ROOT / "tools" / "state"))
        spec = importlib.util.spec_from_file_location(
            "findings_manifest", REPO_ROOT / "tools" / "state" / "findings_manifest.py")
        manifest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manifest)

        declared = {"tracks." + ".".join(p) for p, _, _, _ in manifest.MOVES}
        on_disk = {json.loads(f.read_text())["was"] for f in _findings()}
        self.assertEqual(
            declared, on_disk,
            "the manifest and state/findings/ disagree; re-run "
            "tools/state/split_business_state.py --check",
        )

    def test_no_finding_was_left_in_the_state_file(self):
        """The test that would have caught the original problem.

        A dated investigation sitting in business-state.json is exactly what made
        the prompt 64% state, and it gets there one key at a time.
        """
        with open(STATE) as f:
            state = json.load(f)
        fat = []
        for track, keys in state.get("tracks", {}).items():
            for k, v in keys.items():
                size = len(json.dumps(v))
                if size > 1200:
                    fat.append(f"tracks.{track}.{k} ({size:,}B)")
        self.assertEqual(
            fat, [],
            "these look like findings, not metrics. Give each an authored claim "
            "and move it to state/findings/: " + ", ".join(fat),
        )


class TestPromptStaysOffArgv(unittest.TestCase):
    def test_runner_feeds_the_prompt_on_stdin(self):
        """DEC-279 regression guard. `claude -p "$PROMPT"` is the bug."""
        runner = (REPO_ROOT / "tools" / "autonomous" / "dale-runner.sh").read_text()
        # Comments only, stripped: the fix is documented in a comment that quotes
        # the broken form verbatim, and matching that is how this test failed the
        # first time it ran.
        code = "\n".join(
            ln for ln in runner.splitlines() if not ln.lstrip().startswith("#")
        )
        self.assertNotIn(
            'claude -p "$PROMPT"', code,
            "the prompt is back on argv, which dies at "
            f"{MAX_ARG_STRLEN:,} bytes with 'Argument list too long' (DEC-279)",
        )
        self.assertIn(
            '< "$PROMPT_FILE"', code,
            "the prompt should be redirected from a file on stdin",
        )


if __name__ == "__main__":
    unittest.main()
