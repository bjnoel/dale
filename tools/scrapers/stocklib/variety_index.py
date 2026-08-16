"""Canonical variety titles, written by the builder and read by the server.

`POST /api/watch-variety` used to store whatever `variety_title` the caller
sent, and `send_variety_alerts.py` then interpolated that stored string into
the subject line and the HTML body of mail sent to *every other* watcher of
the same slug. Combined with an endpoint that takes any valid-looking email,
that let a stranger choose the copy in mail we send to real people.

The fix is to stop taking the title from the caller at all. Every variety page
the builder writes already has a canonical title ("Avocado - Hass"), so
`build_variety_pages.py` emits that map and both the server and the alert
sender read it. The client's `variety_title` is ignored.

Why this lives in stocklib rather than being read via `cultivar_parsing`:
`subscribe_server.py` must not grow a heavy new local import.
`tests/test_deploy_restart_list.py` requires every module the server imports at
module scope to sit inside deploy.sh's restart fingerprint, and
`stocklib/*.py` is already covered by that glob while a new top-level scraper
module would not be. A flat JSON map also keeps the server dumb: no parser, no
species tables, no startup cost.

The file goes in the DATA dir (`/opt/dale/data/variety-index.json`), next to
the other server-read state, not the web root. It is data the server needs,
not a page anyone browses.
"""
import json
import os
import re
import tempfile
from pathlib import Path

INDEX_FILENAME = "variety-index.json"

# What `cultivar_parsing.slugify` can emit: lowercase alphanumerics and single
# dashes, never leading or trailing. Validating the shape is what makes a slug
# safe to render when the index has no entry for it, so keep it strict.
# 120 chars is roughly double the longest slug in production
# ("avocado-shepard-persea-americana-type-b-fruit-tree", 50).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")


def is_valid_slug(slug: str) -> bool:
    """True if `slug` has the shape slugify() produces.

    A slug that passes this contains no character with meaning in HTML, a URL
    query string, or a JS string literal, which is why `title_from_slug` below
    can be used as a display fallback without escaping worries.
    """
    return bool(slug) and bool(SLUG_RE.match(slug))


def title_from_slug(slug: str) -> str:
    """Readable display string derived from the slug alone.

    The fallback for a slug the index does not know. Deliberately derived from
    the slug and not from anything the client sent: it is dull, but it can
    never carry an injection, and /stop-watching.html already shows unknown
    varieties this way.
    """
    return " ".join(w.capitalize() for w in slug.split("-") if w)


# The index is server state, so it lives with the other server state
# (subscribers.json, manage_link_sends.json), NOT in the nursery snapshot dir
# the builders are invoked with and not in the web root. One constant, so the
# writer and the two readers cannot drift.
DEFAULT_INDEX_PATH = Path("/opt/dale/data") / INDEX_FILENAME


def write_variety_index(path: Path, titles: dict[str, str]) -> None:
    """Write {slug: title} atomically.

    The server reads this file while the builder rewrites it, so it is written
    to a temp file in the same directory and renamed: a reader either sees the
    whole old file or the whole new one, never a half-written one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".variety-index-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(dict(sorted(titles.items())), f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class VarietyIndex:
    """Lazily loaded, mtime-cached view of variety-index.json.

    The server is single-threaded stdlib HTTPServer, so a re-read on every
    request would sit in the request path. It is also long-lived and the file
    is rewritten by the nightly build, so a load-once cache would go stale
    until the next restart. mtime+size is the cheap middle: one stat() per
    lookup, a real read only when the builder has been through.

    Note the JSON file is NOT part of deploy.sh's `server_modules_sum()`
    restart fingerprint (that only covers .py), which is exactly why the
    freshness check has to live here.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._titles: dict[str, str] = {}
        self._stamp = None
        self._loaded = False

    def _fresh(self) -> dict[str, str]:
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            # Missing or unreadable. Keep re-stat'ing rather than latching to
            # empty: during a deploy the server restarts before the builder
            # runs, so the file legitimately appears a few minutes later.
            stamp = None
        if self._loaded and stamp == self._stamp:
            return self._titles
        self._stamp = stamp
        self._loaded = True
        if stamp is None:
            self._titles = {}
            return self._titles
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._titles = {}
            return self._titles
        if not isinstance(data, dict):
            self._titles = {}
            return self._titles
        self._titles = {
            str(k): str(v) for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str)
        }
        return self._titles

    @property
    def titles(self) -> dict[str, str]:
        return dict(self._fresh())

    @property
    def available(self) -> bool:
        """True when the index has been read and has entries.

        Callers use this to decide whether "not in the index" means "not a real
        variety" or "the index simply is not there yet". Rejecting every slug
        because a file is missing would take the whole alert signup down.
        """
        return bool(self._fresh())

    def __len__(self) -> int:
        return len(self._fresh())

    def __contains__(self, slug: str) -> bool:
        return slug in self._fresh()

    def title(self, slug: str) -> str | None:
        """Canonical title for `slug`, or None if the index does not know it."""
        return self._fresh().get(slug)

    def display_title(self, slug: str, fallback: str | None = None) -> str:
        """Best available display string for `slug`.

        Canonical title if we have one; otherwise `fallback` (a stored title
        for a slug that has dropped out of the dataset, which callers must
        still escape); otherwise the slug read back as words.
        """
        known = self._fresh().get(slug)
        if known:
            return known
        if fallback:
            return fallback
        return title_from_slug(slug)


_INSTANCES: dict[str, VarietyIndex] = {}


def get_variety_index(path: Path) -> VarietyIndex:
    """Process-wide VarietyIndex for `path`, so the mtime cache is shared."""
    key = str(Path(path))
    if key not in _INSTANCES:
        _INSTANCES[key] = VarietyIndex(Path(path))
    return _INSTANCES[key]
