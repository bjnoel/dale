"""
The deploy restart fingerprint must cover every module subscribe-server holds.

Python imports at process start, so a module changed on disk does nothing until
the service is bounced. `deploy.sh` decides whether to bounce by checksumming a
hand-written list of modules, and a hand-written list drifts:

- DEC-264 (2026-08-06): admin_view.py was not watched, so the /admin work
  deployed "successfully" and served stale code for three days. That is what
  created the checksum in the first place.
- 2026-08-10: nursery_inbound.py was not watched either. The BCC matcher fix
  would have rsynced onto a server that kept running the old module, and the
  symptom would have been identical to the bug being fixed: a BCC that lands at
  Resend and never reaches the register.

Twice is a pattern, so the list is now checked rather than remembered.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
DEPLOY_SH = REPO_ROOT / "tools" / "deploy.sh"
ENTRYPOINT = SCRAPERS / "subscribe_server.py"


def local_module_imports(path):
    """Top-level modules imported from a file that are local .py siblings.

    Only module-scope imports matter: an import inside a function runs on call,
    picks up whatever is on disk, and does not pin a stale module at start-up.
    """
    tree = ast.parse(path.read_text())
    names = set()
    for node in tree.body:                       # module scope only, deliberate
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return {n for n in names if (SCRAPERS / f"{n}.py").exists()}


def fingerprinted_modules():
    """Module basenames listed in deploy.sh's server_modules_sum()."""
    body = DEPLOY_SH.read_text()
    m = re.search(r"server_modules_sum\(\)\s*\{(.*?)\n\}", body, re.S)
    if not m:
        raise AssertionError("server_modules_sum() not found in deploy.sh")
    return set(re.findall(r"/opt/dale/scrapers/([A-Za-z0-9_]+)\.py", m.group(1)))


class TestDeployRestartList(unittest.TestCase):
    def test_every_module_subscribe_server_imports_is_fingerprinted(self):
        imported = local_module_imports(ENTRYPOINT)
        watched = fingerprinted_modules()
        missing = sorted(imported - watched)
        self.assertEqual(
            missing, [],
            "subscribe_server.py imports these at module scope but deploy.sh "
            f"will not restart the service when they change: {missing}. "
            "Add them to server_modules_sum() or the deploy reports success "
            "while the process keeps serving the old code.")

    def test_the_entrypoint_itself_is_fingerprinted(self):
        self.assertIn("subscribe_server", fingerprinted_modules())

    def test_stocklib_is_covered_by_the_glob(self):
        body = re.search(r"server_modules_sum\(\)\s*\{(.*?)\n\}",
                         DEPLOY_SH.read_text(), re.S).group(1)
        self.assertIn("stocklib/*.py", body)

    def test_nursery_inbound_specifically(self):
        """The one that was missing. Named so a future edit cannot quietly drop
        it and still pass the generic check by also dropping the import."""
        self.assertIn("nursery_inbound", fingerprinted_modules())
