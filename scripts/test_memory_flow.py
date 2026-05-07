#!/usr/bin/env python3
"""
Smoke tests V11.6 — mémoire fractale (write, retrieval, layering, reinforcement, observabilité).

Prérequis : dépendances OpenChawn (voir docs/memory_test_plan.md).
Force `MEMORY_BACKEND=json` et un fichier store temporaire.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

# Backend JSON + répertoire mémoire isolé (compat CI / Railway si MEMORY_BACKEND existe).
os.environ["MEMORY_BACKEND"] = "json"

# Isoler la JSON store avant tout import qui charge FastAPI ou la mémoire.
import app.memory.fractal_memory as fm  # noqa: E402


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="openchawn_mem_flow_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    from fastapi.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402

    client = TestClient(app)
    uid = "user-memory-flow-test"
    proj_hint = "openchawn"

    # 1) Write — quatre couches pour vérifier l’ordonnancement des blocs dans le prompt
    w1 = fm.write_exchange(
        source="test_memory_flow",
        user_message="Mémoire système globale Railway.",
        assistant_response="Railway bien enregistré comme infra.",
        project_name_hint="",
        user_key=uid,
        is_guest=False,
    )
    if not w1.saved:
        _fail(f"write system refused: {w1.reason}")
        return 1

    # Mémoire projet DeepSeek (+ concept canon "DeepSeek est provider principal").
    proj_user_msg = (
        "Par défaut le projet openchawn utilise DeepSeek sur Railway pour les réponses."
    )
    w2 = fm.write_exchange(
        source="test_memory_flow",
        user_message=proj_user_msg,
        assistant_response="Confirmation : DeepSeek est utilisé comme moteur LLM.",
        project_name_hint=proj_hint,
        user_key=uid,
        is_guest=False,
    )
    if not w2.saved:
        _fail(f"write project refused: {w2.reason}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    snap_early = fm.entries_snapshot_for_tests()
    w2_types = {str(e.get("memory_type")) for e in snap_early if e.get("id") in w2.entry_ids}
    if "project" not in w2_types:
        _fail(
            "écriture DeepSeek doit être memory_type=project "
            "(formulation évite les heuristiques system type « provider principal »); "
            f"observé={w2_types}"
        )
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    w3 = fm.write_exchange(
        source="test_memory_flow",
        user_message="Je préfère des réponses courtes dans les résultats de test.",
        assistant_response="Je note la préférence pour réponses courtes.",
        project_name_hint=proj_hint,
        user_key=uid,
        is_guest=False,
    )
    if not w3.saved:
        _fail(f"write user refused: {w3.reason}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    w4 = fm.write_exchange(
        source="test_memory_flow",
        user_message="Note mémoire-flow strictement session utilisateur.",
        assistant_response="Contexte court terme OK.",
        project_name_hint="",
        project="",
        user_key=uid,
        is_guest=False,
    )
    if not w4.saved:
        _fail(f"write session refused: {w4.reason}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    # 2) Retrieval
    retrieval_q = "Quel provider OpenChawn utilise pour les réponses ?"
    ctx, picks = fm.build_layered_memory_context(
        retrieval_q,
        user_key=uid,
        project_name_hint=proj_hint,
        is_guest=False,
    )
    lowered = ctx.lower()
    if "deepseek" not in lowered:
        _fail("retrieval: contexte sans mention DeepSeek")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    # 3) Layering — ordre des en-têtes (sections vides ignorées)
    markers = [
        ("MÉMOIRE SYSTÈME", "SYSTEM"),
        ("PRÉFÉRENCES UTILISATEUR", "USER"),
        ("MÉMOIRE PROJET", "PROJECT"),
        ("CONTEXTE SESSION", "SESSION"),
    ]
    positions: list[tuple[str, str, int]] = []
    for label, layer in markers:
        i = ctx.find(label)
        if i >= 0:
            positions.append((label, layer, i))
    if len(positions) < 4:
        _fail(
            f"layering: attendu les 4 sections visibles, trouvé {len(positions)} —\n{ctx[:1200]}"
        )
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    for a, b in zip(positions, positions[1:]):
        if a[2] >= b[2]:
            _fail(
                f"layering: '{a[1]}' ({a[2]}) devrait précéder '{b[1]}' ({b[2]})\n{ctx[:800]}"
            )
            shutil.rmtree(tmp, ignore_errors=True)
            return 1

    # 4) Concept extraction
    r_graph = client.get("/memory/concepts/graph")
    if r_graph.status_code != 200:
        _fail(f"/memory/concepts/graph status {r_graph.status_code}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    graph = r_graph.json()
    blobs = json.dumps(graph, ensure_ascii=False).lower()
    if "deepseek est provider principal" not in blobs:
        r_top = client.get("/memory/concepts")
        if r_top.status_code != 200:
            _fail("/memory/concepts indisponible")
            shutil.rmtree(tmp, ignore_errors=True)
            return 1
        concepts_payload = json.dumps(r_top.json(), ensure_ascii=False).lower()
        if "deepseek est provider principal" not in concepts_payload:
            _fail("concept canonique DeepSeek introuvable (graph et /memory/concepts)")
            shutil.rmtree(tmp, ignore_errors=True)
            return 1

    # 5) Reinforcement — deux retrievals consécutifs après la mesure initiale
    if not picks:
        _fail("reinforcement: aucune mémoire sélectionnée")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    target_id = str(picks[0].get("id") or "")

    def _acc(mid: str) -> int:
        for e in fm.entries_snapshot_for_tests():
            if str(e.get("id")) == mid:
                return int(e.get("access_count") or 0)
        return -1

    before = _acc(target_id)
    fm.build_layered_memory_context(
        retrieval_q,
        user_key=uid,
        project_name_hint=proj_hint,
        is_guest=False,
    )
    mid_after = _acc(target_id)
    fm.build_layered_memory_context(
        retrieval_q,
        user_key=uid,
        project_name_hint=proj_hint,
        is_guest=False,
    )
    after = _acc(target_id)
    if after <= before or mid_after <= before:
        _fail(
            "reinforcement: access_count doit croître "
            f"(id={target_id} before={before} mid={mid_after} after={after})"
        )
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    # 6) Last context
    fm.build_layered_memory_context(
        retrieval_q,
        user_key=uid,
        project_name_hint=proj_hint,
        is_guest=False,
    )
    r_last = client.get("/memory/last-context")
    if r_last.status_code != 200:
        _fail(f"/memory/last-context status {r_last.status_code}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    last = r_last.json()
    items = last.get("items") or []
    if not isinstance(items, list) or not items:
        _fail("/memory/last-context : items vide")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    needed = {"why_selected", "relevance_score", "importance_score", "decay_score"}
    for k in needed:
        if k not in items[0]:
            _fail(f"/memory/last-context item[0] sans clé '{k}'")
            shutil.rmtree(tmp, ignore_errors=True)
            return 1

    # 7) Secret filter
    bad = fm.write_exchange(
        source="test_memory_flow",
        user_message="OPENAI_API_KEY=sk-test-secret",
        assistant_response="ignored",
        user_key=uid,
        is_guest=False,
    )
    if bad.saved:
        _fail("secret filter : écriture aurait dû être refusée")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    store_text = (tmp / "fractal_memory.json").read_text(encoding="utf-8").lower()
    if "sk-test-secret" in store_text:
        _fail("secret présent dans le fichier store")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    # 8) Health
    hm = client.get("/health/memory")
    if hm.status_code != 200:
        _fail(f"/health/memory {hm.status_code}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    hmj = hm.json()
    if hmj.get("status") != "ok":
        _fail(f"/health/memory status field {hmj.get('status')}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    hlc = client.get("/health/memory/lifecycle")
    if hlc.status_code != 200:
        _fail(f"/health/memory/lifecycle {hlc.status_code}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    hl = hlc.json()
    if hl.get("status") not in ("ok", "error"):
        _fail("/health/memory/lifecycle statut invalide")

    hv = client.get("/memory/observability/overview")
    if hv.status_code != 200:
        _fail(f"/memory/observability/overview {hv.status_code}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    hvo = hv.json()
    if hvo.get("status") != "ok":
        _fail(str(hvo.get("config_error") or "/memory/observability/overview erreur"))

    shutil.rmtree(tmp, ignore_errors=True)
    print(
        "OK — scripts/test_memory_flow : "
        "tous les contrôles V11.6 mémoire fractale ont réussi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
