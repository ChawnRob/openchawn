#!/usr/bin/env python3
"""
Tests manuels MVP : timeline + replay + decision-trace (store JSON isolé).
Usage : depuis la racine openchawn :
  python scripts/test_memory_replay_timeline.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.memory import fractal_memory as fm
    from app.memory import memory_timeline as mt

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_tl_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"
    mt.TIMELINE_JSON_PATH = tmp / "memory_timeline.json"

    session_user = "user-test-replay-42"

    # 1) Création mémoire DeepSeek (projet openchawn)
    r1 = fm.write_exchange(
        source="script",
        user_message="Pour openchawn on garde DeepSeek comme provider principal en production.",
        assistant_response="OK, DeepSeek reste le provider principal pour OpenChawn.",
        project="openchawn",
        user_key=session_user,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert r1.saved, r1

    r_merge = fm.write_exchange(
        source="script",
        user_message="Confirme : pour openchawn le provider principal est bien DeepSeek.",
        assistant_response="Oui, provider principal DeepSeek pour OpenChawn.",
        project="openchawn",
        user_key=session_user,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert r_merge.saved, r_merge

    # 2) Retrieval + reinforcement + context_injected
    ctx, mems = fm.build_layered_memory_context(
        "Quel provider LLM pour OpenChawn ?",
        user_key=session_user,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert "DeepSeek" in ctx or any("deepseek" in str(m.get("summary", "")).lower() for m in mems)

    # 3) Contradiction : même sujet deepseek, polarité opposée
    r2 = fm.write_exchange(
        source="script",
        user_message=(
            "Il faut interdire DeepSeek totalement sur openchawn, ce n'est plus autorisé en production."
        ),
        assistant_response="Compris : DeepSeek est banni, on ne l'utilise plus.",
        project="openchawn",
        user_key=session_user,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert r2.saved, r2

    # 4) Archive : entrée faible et ancienne
    with fm._STORE_LOCK:
        entries = fm._load_entries()
        entries = [fm._ensure_entry_defaults(e) for e in entries]
        weak = fm._mk_entry(
            source="script",
            user_message="bruit",
            assistant_response="bruit",
            summary="Weak noise entry for archive test",
            tags=[],
            importance_score=0.2,
            project="openchawn",
            memory_type="session",
            project_name="openchawn",
            user_id=session_user,
            memory_level="summary_memory",
        )
        old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        weak["created_at"] = old_ts
        weak["timestamp"] = old_ts
        weak["last_accessed_at"] = old_ts
        weak["access_count"] = 0
        weak["decay_score"] = 55.0
        weak["lifecycle_status"] = fm.MEMORY_LIFECYCLE_ACTIVE
        entries.append(weak)
        fm._save_entries(entries)

    with fm._STORE_LOCK:
        entries = fm._load_entries()
        entries = [fm._ensure_entry_defaults(e) for e in entries]
        n_arch = fm.apply_archive_rules(
            entries,
            timeline_user_key=session_user,
            timeline_session_id=session_user,
        )
        fm._save_entries(entries)
    assert n_arch >= 1, "expected at least one archived weak entry"

    # 5) Timeline ordre chronologique
    events = mt.load_timeline_events()
    assert events, "timeline should have events"
    ts_list = [str(e.get("timestamp") or "") for e in events]
    assert ts_list == sorted(ts_list), "events should be appended in chronological order"

    etypes = [e.get("event_type") for e in events]
    for need in (
        "memory_created",
        "concept_merged",
        "memory_retrieved",
        "memory_reinforced",
        "context_injected",
        "contradiction_detected",
        "memory_archived",
    ):
        assert need in etypes, f"missing event type {need} in {etypes}"

    # 6) Replay — décisions clés
    replay = mt.build_replay_payload(project="openchawn", limit=400)
    assert replay.get("status") == "ok"
    kds = replay.get("key_decisions") or []
    joined = " ".join(str(x).lower() for x in kds)
    assert "deepseek" in joined

    # 7) Decision trace
    trace = mt.decision_trace(concept="DeepSeek", project="openchawn")
    assert trace.get("status") == "ok"
    assert trace.get("contradictions", 0) >= 1
    sup = trace.get("supporting_memories") or []
    assert sup, "supporting_memories should list entries"

    # 8) Pas de secrets dans le fichier timeline
    raw = mt.TIMELINE_JSON_PATH.read_text(encoding="utf-8")
    lower = raw.lower()
    assert "sk-" not in lower
    assert "api_key=" not in lower
    mt.append_timeline_event(
        event_type="memory_created",
        summary="api_key=sk-fake1234567890abcdefghij",
        user_key=session_user,
        session_id=session_user,
    )
    raw2 = mt.TIMELINE_JSON_PATH.read_text(encoding="utf-8")
    assert "REDACTED_SECRET" in raw2 or "sk-fake" not in raw2.lower()

    # 9) Session replay fallback (user_key)
    sess_repl = mt.build_session_replay(session_user, limit=300)
    assert sess_repl.get("status") == "ok"
    assert len(sess_repl.get("ordered_events") or []) >= 1

    print("OK memory replay + timeline — tmp dir:", tmp)
    print("sample timeline tail:", json.dumps(events[-3:], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
