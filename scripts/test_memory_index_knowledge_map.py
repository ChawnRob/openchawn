#!/usr/bin/env python3
"""
Smoke test index logique (store JSON isolé).
  cd openchawn && .venv/bin/python scripts/test_memory_index_knowledge_map.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.memory import fractal_memory as fm
    from app.memory import memory_index as mx

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_idx_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    uid = "user-knowledge-map-99"

    def wr(msg: str, reply: str, *, proj_hint: str = "openchawn") -> None:
        r = fm.write_exchange(
            source="script",
            user_message=msg,
            assistant_response=reply,
            project="openChawn Project",
            user_key=uid,
            project_name_hint=proj_hint,
            is_guest=False,
        )
        assert r.saved, r

    wr(
        "DeepSeek est le provider LLM principal pour OpenChawn en production Railway.",
        "OK, DeepSeek reste le principal provider.",
    )
    wr(
        "Railway est notre backend hébergé pour OpenChawn.",
        "Confirmé Railway pour le déploiement.",
    )
    wr(
        "OpenChawn orchestre les providers multiples.",
        "OpenChawn route les conversations.",
        proj_hint="openchawn",
    )

    idx = mx.build_memory_index()
    assert idx.get("status") == "ok", idx

    concepts = list(idx.get("concepts") or [])
    assert concepts, concepts
    for c in concepts:
        assert float(c.get("centrality_score") or 0) >= 0.0
        assert float(c.get("influence_score") or 0) >= 0.0
        assert sum(1 for k in concepts if float(k.get("centrality_score") or 0) > 0) >= 1

    proj_rows = idx.get("projects_gravity") or []
    oc = next(
        (
            row
            for row in proj_rows
            if str(row.get("project_name") or "").lower() == "openchawn"
        ),
        None,
    )
    assert oc is not None, proj_rows
    assert float(oc.get("gravity_score") or 0) > 0.0

    wr(
        "Sur OpenChawn Ollama est le moteur principal en local pour notre développement quotidien.",
        "Confirmé : Ollama reste utilisé uniquement hors production.",
        proj_hint="openchawn",
    )
    wr(
        "Ollama est interdit sur OpenChawn en production, point final — pas d'usage autorisé là-bas.",
        "OK, aucun Ollama en production.",
        proj_hint="openchawn",
    )

    idx2 = mx.build_memory_index()
    gx2 = mx.graph_statistics()
    assert gx2.get("status") == "ok"
    assert (
        int(gx2.get("contradiction_pairs_count") or 0) >= 1
        or any(str(c.get("status")) == "contradicted" for c in (idx2.get("concepts") or []))
    ), "expect Ollama polarity contradiction surfaced in graph or index"

    top = mx.top_concepts_response(limit=20)
    assert top.get("status") == "ok"
    blob = json.dumps(top.get("items") or [], ensure_ascii=False).lower()
    assert "deepseek" in blob and "openchawn" in blob

    assert int(gx2.get("concept_node_count") or 0) >= 1

    # Secrets : aucun motif indexé après sanitisation timeline
    full_dump = json.dumps(idx2, ensure_ascii=False).lower()
    assert "sk-" not in full_dump and "api_key=" not in full_dump

    cen = mx.compute_concept_centrality(fm.entries_snapshot_for_tests())
    assert isinstance(cen, dict) and any(v > 0 for v in cen.values())

    print("OK memory index knowledge map tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
