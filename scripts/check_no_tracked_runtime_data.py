#!/usr/bin/env python3
"""Fail if Git tracks runtime or sensitive local artifacts."""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import PurePosixPath

# Anything under data/ is local runtime (DB, memory JSON, QEI, semantic indexes).
_FORBIDDEN_PREFIXES = ("data/",)

# Legacy memory directory: allow *.py source, block persisted stores and scratch artifacts.
_FORBIDDEN_MEMORY_GLOBS = (
    "memory/*.json",
    "memory/*.jsonl",
    "memory/fractal",
)

# System / FUSE artifacts and local DB files anywhere in the tree.
_FORBIDDEN_ANYWHERE_GLOBS = (
    "**/.fuse_hidden*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
)


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def is_forbidden_tracked_path(path: str) -> bool:
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


def find_tracked_violations() -> list[str]:
    tracked = git_ls_files()
    return sorted(p for p in tracked if is_forbidden_tracked_path(p))


def main() -> int:
    violations = find_tracked_violations()
    if not violations:
        print("OK: no forbidden runtime or sensitive files tracked in Git.")
        return 0

    print("ERROR: forbidden runtime or sensitive files are tracked in Git:", file=sys.stderr)
    for path in violations:
        print(f"  - {path}", file=sys.stderr)
    print("\nRemove with: git rm --cached <path>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
