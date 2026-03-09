#!/usr/bin/env python3
"""Token usage tracking and failure counting for autonomous Dale."""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
TOKEN_LOG = os.path.join(LOG_DIR, "token-log.json")
FAILURE_LOG = os.path.join(LOG_DIR, "failures.json")


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)


def load_json(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def log_session(session_log_path):
    """Parse Claude output and append to token log."""
    ensure_dirs()
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "date": now,
        "tokens_input": 0,
        "tokens_output": 0,
        "duration_seconds": 0,
        "session_file": os.path.basename(session_log_path),
    }

    if os.path.exists(session_log_path):
        try:
            with open(session_log_path) as f:
                data = json.load(f)
            usage = data.get("usage", {})
            entry["tokens_input"] = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            entry["tokens_output"] = usage.get("output_tokens", 0)
            entry["cache_creation_tokens"] = usage.get("cache_creation_input_tokens", 0)
            entry["duration_seconds"] = data.get("duration_ms", 0) / 1000
            entry["num_turns"] = data.get("num_turns", 0)
            entry["cost_usd"] = data.get("total_cost_usd", 0)
            entry["is_error"] = data.get("is_error", False)
            entry["stop_reason"] = data.get("stop_reason", "unknown")
            result = data.get("result", "")
            entry["task_summary"] = result[:200] if result else "No output"
        except (json.JSONDecodeError, KeyError):
            entry["task_summary"] = "Failed to parse session output"

    log = load_json(TOKEN_LOG)
    log.append(entry)
    save_json(TOKEN_LOG, log)
    print(f"Logged: {entry['tokens_input']} in / {entry['tokens_output']} out")


def get_failure_count():
    """Return count of consecutive failures."""
    failures = load_json(FAILURE_LOG, {"consecutive": 0, "history": []})
    if isinstance(failures, dict):
        return failures.get("consecutive", 0)
    return 0


def log_failure(reason):
    """Record a failure."""
    ensure_dirs()
    failures = load_json(FAILURE_LOG, {"consecutive": 0, "history": []})
    if isinstance(failures, list):
        failures = {"consecutive": 0, "history": failures}
    failures["consecutive"] = failures.get("consecutive", 0) + 1
    failures["history"].append({
        "date": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    })
    save_json(FAILURE_LOG, failures)
    print(f"Failure logged ({failures['consecutive']} consecutive): {reason}")


def clear_failures():
    """Reset consecutive failure count (keeps history)."""
    ensure_dirs()
    failures = load_json(FAILURE_LOG, {"consecutive": 0, "history": []})
    if isinstance(failures, list):
        failures = {"consecutive": 0, "history": failures}
    failures["consecutive"] = 0
    save_json(FAILURE_LOG, failures)


def show_stats():
    """Print usage statistics."""
    log = load_json(TOKEN_LOG)
    if not log:
        print("No sessions logged yet.")
        return

    total_in = sum(e.get("tokens_input", 0) for e in log)
    total_out = sum(e.get("tokens_output", 0) for e in log)
    total_dur = sum(e.get("duration_seconds", 0) for e in log)
    count = len(log)

    print(f"Sessions: {count}")
    print(f"Total tokens: {total_in:,} in / {total_out:,} out")
    print(f"Total duration: {total_dur/60:.1f} minutes")
    if count > 0:
        print(f"Avg per session: {total_in//count:,} in / {total_out//count:,} out")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: budget-tracker.py <log-session|failure-count|log-failure|clear-failures|stats> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "log-session":
        log_session(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "failure-count":
        print(get_failure_count())
    elif cmd == "log-failure":
        log_failure(sys.argv[2] if len(sys.argv) > 2 else "unknown")
    elif cmd == "clear-failures":
        clear_failures()
    elif cmd == "stats":
        show_stats()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
