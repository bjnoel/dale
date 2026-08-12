"""
Size guardrail for the autonomous session prompt.

On 2026-08-10 autonomous Dale stopped running for 44 hours. The proximate cause
was that the prompt was passed as a single argv string and Linux caps one of
those at MAX_ARG_STRLEN (32 pages = 131072 bytes), which is a different and much
lower ceiling than ARG_MAX. The prompt had reached 137785B. It now goes on stdin,
so that particular wall is gone (DEC-279).

The wall is gone; the growth is not. state/business-state.json went from 5,679B
on 2026-07-23 to 85,790B on 2026-08-12, 15x in under three weeks, and nothing
anywhere reported that number until it was fatal. This test is that report. It
does not exist to keep the prompt under any hardware limit, it exists so a jump
in prompt size fails a test rather than being discovered by an outage.

If this fails, do NOT just raise the ceiling. Look at what grew:

    python3 tools/autonomous/session-prompt.py --session-type normal | wc -c

business-state.json is rendered as metrics-verbatim + findings-as-headlines by
render_business_state(), so a jump means real new content, not formatting.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE = REPO_ROOT / "state" / "business-state.json"

# Ceilings, in bytes. Set with headroom over the 2026-08-12 measurements
# (state 85,790B on disk; rendered prompt sections well under these), so this
# catches a step change rather than nagging about ordinary drift.
MAX_STATE_FILE = 120_000
MAX_RENDERED_STATE = 60_000

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


class TestBusinessStateSize(unittest.TestCase):
    def test_state_file_has_not_ballooned(self):
        size = STATE.stat().st_size
        self.assertLess(
            size, MAX_STATE_FILE,
            f"state/business-state.json is {size:,}B (ceiling {MAX_STATE_FILE:,}B). "
            "It is a metrics dashboard, not an archive: point-in-time findings that "
            "are no longer acted on belong in decisions/decision-log.md. Do not just "
            "raise this number.",
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
