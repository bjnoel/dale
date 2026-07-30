"""
Tests for tools/autonomous/linear_poller.py.

Regression coverage for the duplicate-ticket bug (2026-07-27):
  graphql() returned None on any API failure and get_issues_by_state()
  turned that into []. A failed backlog fetch was therefore
  indistinguishable from an empty backlog. dale-runner.sh read
  backlog_count 0, started a generation session, and session-prompt.py
  omitted the "do NOT create duplicates" list entirely (it was guarded by
  `if backlog:`). Dale created 13 tickets in three minutes, three of them
  duplicates of tickets from four days earlier: DAL-236 duplicated
  DAL-220, DAL-226 duplicated DAL-173/DAL-221, DAL-182 duplicated DAL-230.

  Second defect, same class: the query was `first: 50` with no paging, so
  once the queue passed 50 issues the least-recently-updated ones dropped
  out of the duplicate list. Those are precisely the old tickets a new
  proposal is most likely to duplicate.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

spec = importlib.util.spec_from_file_location(
    "linear_poller", AUTONOMOUS / "linear_poller.py"
)
linear_poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linear_poller)


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _issue(identifier, title="t"):
    return {
        "id": f"uuid-{identifier}",
        "identifier": identifier,
        "title": title,
        "description": "",
        "priority": 3,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "state": {"name": "Backlog", "type": "backlog"},
        "assignee": None,
        "labels": {"nodes": []},
        "comments": {"nodes": []},
    }


class GraphqlFailureTests(unittest.TestCase):
    """An API failure must raise, never look like an empty result."""

    def setUp(self):
        patcher = mock.patch.object(linear_poller, "get_token", return_value="tok")
        patcher.start()
        self.addCleanup(patcher.stop)
        log_patcher = mock.patch.object(linear_poller, "log")
        log_patcher.start()
        self.addCleanup(log_patcher.stop)

    def test_http_error_raises(self):
        err = urllib.error.HTTPError("url", 500, "Server Error", {}, None)
        with mock.patch.object(linear_poller.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(linear_poller.LinearAPIError):
                linear_poller.graphql("query {}")

    def test_unreachable_raises(self):
        err = urllib.error.URLError("connection refused")
        with mock.patch.object(linear_poller.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(linear_poller.LinearAPIError):
                linear_poller.graphql("query {}")

    def test_timeout_raises(self):
        with mock.patch.object(linear_poller.urllib.request, "urlopen", side_effect=TimeoutError()):
            with self.assertRaises(linear_poller.LinearAPIError):
                linear_poller.graphql("query {}")

    def test_graphql_errors_field_raises(self):
        payload = {"errors": [{"message": "rate limited"}]}
        with mock.patch.object(linear_poller.urllib.request, "urlopen",
                               return_value=FakeResponse(payload)):
            with self.assertRaises(linear_poller.LinearAPIError):
                linear_poller.graphql("query {}")

    def test_missing_data_field_raises(self):
        with mock.patch.object(linear_poller.urllib.request, "urlopen",
                               return_value=FakeResponse({})):
            with self.assertRaises(linear_poller.LinearAPIError):
                linear_poller.graphql("query {}")

    def test_success_returns_data(self):
        payload = {"data": {"issues": {"nodes": []}}}
        with mock.patch.object(linear_poller.urllib.request, "urlopen",
                               return_value=FakeResponse(payload)):
            self.assertEqual(linear_poller.graphql("query {}"), {"issues": {"nodes": []}})


class GetIssuesByStateTests(unittest.TestCase):
    def test_api_failure_propagates_instead_of_empty_list(self):
        """The actual bug: a failed fetch must not read as 'no tickets'."""
        with mock.patch.object(linear_poller, "graphql",
                               side_effect=linear_poller.LinearAPIError("boom")):
            with self.assertRaises(linear_poller.LinearAPIError):
                linear_poller.get_issues_by_state("team-1", "backlog")

    def test_empty_result_is_still_an_empty_list(self):
        page = {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}
        with mock.patch.object(linear_poller, "graphql", return_value=page):
            self.assertEqual(linear_poller.get_issues_by_state("team-1", "backlog"), [])

    def test_pages_past_the_first_fifty(self):
        """Old tickets beyond page 1 must still reach the duplicate list."""
        first = {"issues": {
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
            "nodes": [_issue(f"DAL-{n}") for n in range(50)],
        }}
        second = {"issues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [_issue("DAL-84"), _issue("DAL-148")],
        }}
        calls = []

        def fake_graphql(query, variables=None):
            calls.append((variables or {}).get("after"))
            return first if len(calls) == 1 else second

        with mock.patch.object(linear_poller, "graphql", side_effect=fake_graphql):
            issues = linear_poller.get_issues_by_state("team-1", "backlog")

        self.assertEqual(len(issues), 52)
        self.assertEqual(calls, [None, "cursor-1"])
        identifiers = [i["identifier"] for i in issues]
        self.assertIn("DAL-84", identifiers)
        self.assertIn("DAL-148", identifiers)

    def test_stops_at_max_pages(self):
        """A server that always claims another page must not loop forever."""
        endless = {"issues": {
            "pageInfo": {"hasNextPage": True, "endCursor": "c"},
            "nodes": [_issue("DAL-1")],
        }}
        with mock.patch.object(linear_poller, "graphql", return_value=endless):
            with mock.patch.object(linear_poller, "log"):
                issues = linear_poller.get_issues_by_state("team-1", "backlog")
        self.assertEqual(len(issues), linear_poller.MAX_PAGES)


if __name__ == "__main__":
    unittest.main()
