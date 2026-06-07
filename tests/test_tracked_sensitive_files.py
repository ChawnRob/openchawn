"""Repo hygiene: fail if runtime or sensitive artifacts are tracked in Git."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import PurePosixPath


# Anything under data/ is local runtime (DB, memory JSON, QEI, semantic indexes).
_FORBIDDEN_PREFIXES = ("data/",)

# Legacy memory directory: allow *.py source, block persisted stores and scratch artifacts.
_FORBIDDEN_MEMORY_GLOBS = (
    "memory/*.json",
    "memory/*.jsonl",
    "memory/fractal",
)

# System / FUSE artifacts anywhere in the tree.
_FORBIDDEN_ANYWHERE_GLOBS = (
    "**/.fuse_hidden*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
)


def _git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def _is_forbidden_tracked_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    posix = PurePosixPath(normalized)

    for prefix in _FORBIDDEN_PREFIXES:
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
            return True

    for pattern in _FORBIDDEN_MEMORY_GLOBS:
        if fnmatch.fnmatch(normalized, pattern):
            return True

    for pattern in _FORBIDDEN_ANYWHERE_GLOBS:
        if posix.match(pattern):
            return True

    return False


def test_no_sensitive_runtime_files_tracked_in_git():
    tracked = _git_ls_files()
    violations = sorted(p for p in tracked if _is_forbidden_tracked_path(p))
    assert not violations, (
        "Sensitive or runtime artifacts must not be tracked in Git. "
        "Remove with: git rm --cached <path>\n"
        + "\n".join(f"  - {p}" for p in violations)
    )
