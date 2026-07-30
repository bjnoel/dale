"""
Tests for tools/autonomous/budget-tracker.py.

Regression coverage for silent under-reporting of session cost (2026-07-30):
  log_session() read `usage` from the `claude -p --output-format json`
  result, which reports only the final segment. Two distinct failures,
  both observed in real sessions on the same day:

  - 04:00 compacted, so `usage` collapsed to 291 output tokens for a
    session that actually produced 42,341, and duration_ms read 9,131ms
    (9 seconds) for a run cron timed at 11.9 minutes.
  - 03:00 did not compact, but `usage` still counted only the main loop's
    model and dropped Haiku's 2,061 output tokens.

  The second is the nastier one: it looks correct. Nothing about
  "38,781 out" invites suspicion, so the budget log was quietly wrong for
  every mixed-model session, which is all of them.

The fixtures below are the shapes those two sessions actually produced.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

spec = importlib.util.spec_from_file_location(
    "budget_tracker", AUTONOMOUS / "budget-tracker.py"
)
budget_tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget_tracker)


# The 04:00 session: compacted, so `usage` is near-empty and duration_ms is junk
COMPACTED_SESSION = {
    "usage": {
        "input_tokens": 4,
        "output_tokens": 291,
        "cache_read_input_tokens": 270759,
        "cache_creation_input_tokens": 1877,
    },
    "modelUsage": {
        "claude-opus-5": {
            "inputTokens": 1268,
            "outputTokens": 42341,
            "cacheReadInputTokens": 6467432,
            "cacheCreationInputTokens": 61233,
            "costUSD": 5.366702249999998,
        }
    },
    "duration_ms": 9131,
    "duration_api_ms": 681304,
    "total_cost_usd": 5.366702249999998,
    "num_turns": 2,
}

# The 03:00 session: no compaction, but two models ran
MULTI_MODEL_SESSION = {
    "usage": {
        "input_tokens": 23,
        "output_tokens": 38781,
        "cache_read_input_tokens": 616649,
        "cache_creation_input_tokens": 38748,
    },
    "modelUsage": {
        "claude-opus-5": {
            "inputTokens": 1097,
            "outputTokens": 38781,
            "cacheReadInputTokens": 3337969,
            "cacheCreationInputTokens": 41003,
            "costUSD": 3.519,
        },
        "claude-haiku-4-5-20251001": {
            "inputTokens": 342552,
            "outputTokens": 2061,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
            "costUSD": 0.3528202500000001,
        },
    },
    "duration_ms": 649709,
    "duration_api_ms": 618347,
    "total_cost_usd": 3.8718202500000007,
    "num_turns": 53,
}


class SessionUsageTests(unittest.TestCase):
    def test_compacted_session_reports_real_totals(self):
        usage = budget_tracker.session_usage(COMPACTED_SESSION)
        self.assertEqual(usage["tokens_output"], 42341)
        self.assertNotEqual(usage["tokens_output"], 291, "read the final segment again")
        self.assertEqual(usage["tokens_input"], 1268 + 6467432)

    def test_multi_model_session_counts_every_model(self):
        usage = budget_tracker.session_usage(MULTI_MODEL_SESSION)
        # 38781 Opus + 2061 Haiku. Reading `usage` gives 38781 and looks fine.
        self.assertEqual(usage["tokens_output"], 40842)
        self.assertEqual(set(usage["by_model"]), {"claude-opus-5", "claude-haiku-4-5-20251001"})
        self.assertEqual(usage["by_model"]["claude-haiku-4-5-20251001"]["tokens_output"], 2061)

    def test_per_model_costs_reconcile_with_the_session_total(self):
        usage = budget_tracker.session_usage(MULTI_MODEL_SESSION)
        attributed = sum(m["cost_usd"] for m in usage["by_model"].values())
        self.assertAlmostEqual(attributed, MULTI_MODEL_SESSION["total_cost_usd"], places=3)

    def test_falls_back_to_usage_when_modelusage_absent(self):
        # Logs written before modelUsage existed must still parse.
        legacy = {"usage": COMPACTED_SESSION["usage"]}
        usage = budget_tracker.session_usage(legacy)
        self.assertEqual(usage["tokens_output"], 291)
        self.assertEqual(usage["by_model"], {})

    def test_empty_input_does_not_crash(self):
        usage = budget_tracker.session_usage({})
        self.assertEqual(usage["tokens_output"], 0)
        self.assertEqual(usage["tokens_input"], 0)


class SessionDurationTests(unittest.TestCase):
    def test_uses_api_duration_when_wall_clock_is_broken(self):
        # 9.1s reported for a run cron timed at 11.9 minutes
        self.assertAlmostEqual(
            budget_tracker.session_duration_seconds(COMPACTED_SESSION), 681.304, places=2
        )

    def test_uses_wall_clock_when_it_is_the_larger(self):
        self.assertAlmostEqual(
            budget_tracker.session_duration_seconds(MULTI_MODEL_SESSION), 649.709, places=2
        )

    def test_missing_and_null_durations(self):
        self.assertEqual(budget_tracker.session_duration_seconds({}), 0)
        self.assertEqual(
            budget_tracker.session_duration_seconds({"duration_ms": None, "duration_api_ms": None}),
            0,
        )


if __name__ == "__main__":
    unittest.main()
