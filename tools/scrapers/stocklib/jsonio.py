"""Crash-safe JSON writes for snapshots and history files.

Every scraper used to write latest.json with open(path, "w") + json.dump. That
truncates the file first, so a crash, a kill or a full disk mid-write left torn
JSON behind, and the next reader (every page builder, the alert senders)
failed on json.load. The disk has filled once already (ClickHouse logs), and
availability.json for Ladybird alone is ~40MB, a long window to die in.

atomic_write_json writes a sibling temp file, fsyncs it, then os.replace()s it
over the target. Readers see the old file or the new one, never half of one.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _mode_for(path: Path) -> int:
    try:
        return path.stat().st_mode & 0o777
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def atomic_write_json(path, obj, *, indent: int | None = 2, **dump_kwargs) -> Path:
    """Serialise `obj` to `path` atomically. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        # mkstemp creates 0600. Keep the target's mode if it exists, else give
        # what open(path, "w") would have (0666 minus umask), so switching to
        # atomic writes does not quietly make every snapshot owner-only.
        os.chmod(tmp, _mode_for(path))
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=indent, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return path
