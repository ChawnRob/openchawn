"""
Initial rules loader with forced-French neutralization.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger("openchawn.initial_rules")

_LOCK = Lock()
_LAST_AUDIT: dict[str, Any] = {
    "forced_french_rule_found": False,
    "forced_french_rule_removed": False,
    "rule_sources_checked": [],
}

_FORCED_FRENCH_PATTERNS = (
    "uniquement en français",
    "répondre uniquement en français",
    "toujours répondre en français",
    "assistant français",
)

_NEUTRAL_LANGUAGE_POLICY = (
    "Language policy:\n"
    "- If the user explicitly asks for translation, answer in the requested target language.\n"
    "- If the user explicitly asks for a language, answer in that language.\n"
    "- Otherwise answer in the dominant language of the latest user message.\n"
    "- Use French only as fallback when the language cannot be detected."
)


def _default_sources() -> list[str]:
    env_candidates = [
        os.getenv("INITIAL_RULES_PATH", "").strip(),
        os.getenv("RULES_PATH", "").strip(),
        os.getenv("SYSTEM_RULES_PATH", "").strip(),
        os.getenv("OPENCHAWN_RULES", "").strip(),
        os.getenv("SYSTEM_PROMPT_PATH", "").strip(),
        os.getenv("CONFIG_PATH", "").strip(),
    ]
    out = [x for x in env_candidates if x]
    out.extend(
        [
            "/etc/openchawn/initial_rules.json",
            "/etc/openchawn/initial_rules",
            "/etc/openchawn/rules.json",
        ]
    )
    uniq: list[str] = []
    seen: set[str] = set()
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def _extract_text(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        payload = json.loads(s)
    except Exception:
        return s
    if isinstance(payload, dict):
        parts: list[str] = []
        for k in ("system_prompt", "rules", "instructions", "content"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
            elif isinstance(v, list):
                parts.extend([str(x).strip() for x in v if str(x).strip()])
        if parts:
            return "\n".join(parts).strip()
    if isinstance(payload, list):
        return "\n".join([str(x).strip() for x in payload if str(x).strip()]).strip()
    return str(payload).strip()


def neutralize_forced_french_rule(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"sanitized_text": "", "forced_french_rule_found": False, "forced_french_rule_removed": False}
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    kept: list[str] = []
    found = False
    for ln in lines:
        low = ln.lower()
        if any(p in low for p in _FORCED_FRENCH_PATTERNS):
            found = True
            continue
        kept.append(ln)
    removed = found
    if found:
        kept.append(_NEUTRAL_LANGUAGE_POLICY)
    return {
        "sanitized_text": "\n".join(kept).strip(),
        "forced_french_rule_found": found,
        "forced_french_rule_removed": removed,
    }


def load_initial_rules() -> dict[str, Any]:
    sources = _default_sources()
    checked: list[str] = []
    loaded = ""
    source_used = ""
    for src in sources:
        checked.append(src)
        p = Path(src)
        if not p.is_file():
            continue
        try:
            loaded = _extract_text(p.read_text(encoding="utf-8"))
            source_used = src
            break
        except Exception:
            continue
    san = neutralize_forced_french_rule(loaded)
    out = {
        "source_used": source_used,
        "rule_sources_checked": checked,
        "rules_text": loaded,
        **san,
    }
    with _LOCK:
        global _LAST_AUDIT
        _LAST_AUDIT = {
            "forced_french_rule_found": bool(out.get("forced_french_rule_found")),
            "forced_french_rule_removed": bool(out.get("forced_french_rule_removed")),
            "rule_sources_checked": list(checked),
            "source_used": source_used,
        }
    if out["forced_french_rule_found"]:
        logger.info("forced_french_rule_removed=true")
    return out


def build_runtime_rules_prompt() -> str:
    rep = load_initial_rules()
    return str(rep.get("sanitized_text") or "").strip()


def language_rule_audit() -> dict[str, Any]:
    with _LOCK:
        return dict(_LAST_AUDIT)

