"""Repo hygiene: fail if runtime or sensitive artifacts are tracked in Git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "check_no_tracked_runtime_data.py"


def test_no_sensitive_runtime_files_tracked_in_git():
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        result.stderr.strip() or result.stdout.strip() or "guard script failed"
    )
