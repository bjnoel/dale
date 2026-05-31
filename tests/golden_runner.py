"""
Golden-file harness for treestock builders (the SEO regression safety net).

Runs a builder against the committed fixture (tests/golden/fixture/) into a temp
dir, normalises the run-date-dependent tokens (the ?v=YYYYMMDD CSS cache-buster
and the 'now' UTC stamp -- everything else, including the fixed fixture
scraped_at values, is stable), and returns {relpath: normalised_text}.
test_golden.py compares these against committed expected output.

Any refactor that changes a builder's output trips a golden diff. Builders are
added to coverage as the PR that refactors them lands (see GOLDEN_CASES in
test_golden.py).

Regenerate goldens after an intended change, then review the diff:
    GOLDEN_UPDATE=1 python3 -m unittest tests.test_golden
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
FIXTURE_DATA = GOLDEN_DIR / "fixture" / "nursery-stock"
EXPECTED_DIR = GOLDEN_DIR / "expected"

# Tokens that vary by the run date/time (not by input). Normalised on both sides
# so the goldens stay stable across days. Keep this list tight: over-normalising
# would mask real output changes.
_NORMALISERS = [
    (re.compile(r"\?v=\d{8}"), "?v=DATE"),                            # CSS cache-buster
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC"), "TIMESTAMP"),  # "now" stamp
]


def normalise(text: str) -> str:
    for rx, repl in _NORMALISERS:
        text = rx.sub(repl, text)
    return text


def run_builder(script: str, arg_template: list[str], output_globs: list[str]) -> dict:
    """Run a builder against the fixture into a temp dir; return {relpath: normalised_text}.

    arg_template entries are literal args, with "{DATA}" and "{OUT}" substituted
    for the fixture data dir and the temp output dir. Returns the normalised text
    of every file matching output_globs (paths relative to OUT).

    The builder's exit code is intentionally ignored: some builders (e.g. the
    dashboard) exit non-zero on the small fixture because of production size/row
    guards, but they still write their output before that check. We assert on the
    produced files instead.
    """
    out = Path(tempfile.mkdtemp(prefix="golden-"))
    args = [a.replace("{DATA}", str(FIXTURE_DATA)).replace("{OUT}", str(out)) for a in arg_template]
    proc = subprocess.run(
        [sys.executable, str(SCRAPERS / script), *args],
        capture_output=True, text=True, cwd=str(SCRAPERS),
    )
    result = {}
    for glob in output_globs:
        for f in sorted(out.glob(glob)):
            if f.is_file():
                result[str(f.relative_to(out))] = normalise(f.read_text())
    if not result:
        raise AssertionError(
            f"{script} produced no files matching {output_globs}.\n"
            f"exit={proc.returncode}\nstderr (tail):\n{proc.stderr[-2000:]}"
        )
    return result
