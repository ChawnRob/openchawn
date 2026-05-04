"""
Compat layer only.

This module is intentionally kept as a thin alias so `app.main` remains the
single application entry point.
"""

from app.main import app  # noqa: F401
