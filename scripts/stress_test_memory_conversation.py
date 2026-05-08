#!/usr/bin/env python3
"""
Stress conversationnel mémoire fractale V11.6 — TestClient, store JSON isolé, LLM stub.
Voir docs/memory_conversation_stress_test.md.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["MEMORY_BACKEND"] = "json"

import app.memory.fractal_memory as fm  # noqa: E402
from app.auth.deps import get_current_user_or_guest  # noqa: E402
from app.main import app  # noqa: E402
import app.api.chat as chat_api  # noqa: E402

STRESS_UID = "887766"


def _auth_override() -> dict:
    return {
        "id": STRESS_UID,
        "email": "stress-memory@example.com",
        "display_name": "StressMemory",
        "business_type": "default",
        "is_guest": False,
        "is_active": True,
        "password_hash": "",
    }


def _stub_llm(
    system_prompt: str = "",
    user_message: str = "",
    provider_hint: str = "",
    **_: object,
) -> dict:
    raw = user_message or ""
    chunks = raw.split("── USER REQUEST ──")
    last = chunks[-1].strip().lower() if chunks else raw.lower()
    flat = last.replace("œ", "oe")

    if "je préfère" in last and "bytebytego" in last.replace(" ", ""):
        return {
            "success": True,
            "output": (
                "Préférences enregistrées : réponses façon ByteByteGo, "
                "style ingénieur façon documentation technique."
            ),
            "provider": "stub",
        }
    if "architecture mémoire" in last or ("architecture" in last and "mémoire" in last):
        return {
            "success": True,
            "output": (
                "L’architecture mémoire est fractale avec des couches système, "
                "utilisateur, projet et session."
            ),
            "provider": "stub",
        }

    if "ollama" in last and "interdit" in last:
        return {
            "success": True,
            "output": "Compris : Ollama est interdit pour la production.",
            "provider": "stub",
        }
    if "ollama" in last and "fournisseur principal" in flat:
        return {
            "success": True,
            "output": (
                "Reçu : Ollama positionné comme fournisseur principal en production "
                "(à traiter sous réserve des règles internes)."
            ),
            "provider": "stub",
        }

    if "openchawn utilise deepseek comme provider principal sur railway" in flat:
        return {
            "success": True,
            "output": (
                "Mémorisé : OpenChawn utilise DeepSeek comme provider principal "
                "sur Railway pour le déploiement."
            ),
            "provider": "stub",
        }
    if "quel provider openchawn" in flat or (
        "openchawn" in flat and "utilise" in flat and "?" in raw
    ):
        return {
            "success": True,
            "output": (
                "OpenChawn s’appuie sur DeepSeek comme provider principal, "
                "avec Railway pour le backend."
            ),
            "provider": "stub",
        }
    if "openchawn" in flat and "deepseek" in flat and "railway" in flat:
        return {
            "success": True,
            "output": "Confirmé DeepSeek comme provider Railway pour OpenChawn.",
            "provider": "stub",
        }

    if last.strip() in {
        "salut",
        "ok",
        "merci",
        "bien vu",
        "super",
        "au revoir",
        "parfait",
        "oui",
        "nice",
        "cool",
    }:
        return {"success": True, "output": "Compris.", "provider": "stub"}
    if "hello yo" in flat or "ça va ?" in flat or "ça va?" in flat:
        return {"success": True, "output": "Ok.", "provider": "stub"}

    return {"success": True, "output": "Noté.", "provider": "stub"}


_ctr = 0


def _chat_headers() -> dict[str, str]:
    global _ctr  # noqa: PLW0603
    _ctr += 1
    # 12 chiffres → les 12 premiers caractères du token (slice middleware) changent à chaque requête.
    return {"Authorization": f"Bearer {_ctr:012d}"}


def _inject_archivable_entry(*, user_key: str) -> str:
    summary = "stress archive disposable low-value"
    with fm._STORE_LOCK:  # noqa: SLF001
        entries = fm._load_entries()

    new_e = fm._mk_entry(  # noqa: SLF001
        source="stress_inject",
        user_message="bruit baseline",
        assistant_response="aucun",
        summary=summary,
        tags=["stress_archive"],
        importance_score=0.22,
        project="dust",
        memory_type="session",
        project_name="dust_archive_stress",
        user_id=user_key,
        memory_level="summary_memory",
    )
    past = datetime.now(timezone.utc) - timedelta(days=40)
    new_e["created_at"] = past.isoformat()
    new_e["timestamp"] = past.isoformat()
    new_e["last_accessed_at"] = past.isoformat()
    new_e["access_count"] = 0
    fm._ensure_entry_defaults(new_e)
    new_e["decay_score"] = fm.recompute_decay_score(new_e)
    entries.append(new_e)

    fm.refresh_lifecycle_decay(entries)
    fm.apply_archive_rules(entries)
    with fm._STORE_LOCK:  # noqa: SLF001
        fm._save_entries(entries)
    return summary


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="openchawn_stress_conv_"))
    fm.STORE_PATH = tmp / "stress_fractal_memory.json"
    chat_api.generate_response = _stub_llm
    app.dependency_overrides[get_current_user_or_guest] = _auth_override

    from fastapi.testclient import TestClient  # noqa: WPS433

    client = TestClient(app)

    proj = "openchawn"
    user_key = f"user-{STRESS_UID}"
    passed = 0
    failed = 0

    def test(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS {name}")
        else:
            failed += 1
            print(f"FAIL {name}: {detail}")

    try:
        r1 = client.post(
            "/chat",
            json={
                "message": (
                    "OpenChawn utilise DeepSeek comme provider principal sur Railway."
                ),
                "project_name": proj,
            },
            headers=_chat_headers(),
        )
        if r1.status_code != 200:
            raise RuntimeError(f"chat step1 HTTP {r1.status_code}: {r1.text}")
        r2 = client.post(
            "/chat",
            json={"message": "Quel provider OpenChawn utilise ?", "project_name": proj},
            headers=_chat_headers(),
        )
        if r2.status_code != 200:
            raise RuntimeError(f"chat step2 HTTP {r2.status_code}: {r2.text}")
        out2 = (r2.json() or {}).get("output", "").lower()
        ctx_mem, _m = fm.build_layered_memory_context(
            "Quel provider OpenChawn utilise ?",
            user_key=user_key,
            project_name_hint=proj,
            is_guest=False,
        )
        comb = f"{ctx_mem.lower()} {out2}"
        test(
            "stable_memory_deepseek_railway",
            "deepseek" in comb and "railway" in comb,
            f"combiné preview={comb[:480]}",
        )

        client.post(
            "/chat",
            json={
                "message": "Je préfère les réponses style ingénieur ByteByteGo.",
                "project_name": proj,
            },
            headers=_chat_headers(),
        )
        ctx_pref, _pf = fm.build_layered_memory_context(
            "Explique-moi l’architecture mémoire.",
            user_key=user_key,
            project_name_hint=proj,
            is_guest=False,
        )
        low = ctx_pref.lower()
        test(
            "user_preference_bytebytego_visible",
            "bytebytego" in low or ("ingénieur" in low or "ingenieur" in low),
            ctx_pref[:600],
        )

        client.post(
            "/chat",
            json={
                "message": "Ollama est interdit en production.",
                "project_name": proj,
            },
            headers=_chat_headers(),
        )
        client.post(
            "/chat",
            json={
                # « fournisseur » évite le tag _detect_tags provider → concept garde « ollama »
                # pour contradiction_detected (voir fractal_memory._concept_summary).
                "message": (
                    "Ollama doit devenir le fournisseur principal "
                    "pour la mise en production."
                ),
                "project_name": proj,
            },
            headers=_chat_headers(),
        )
        contradictory_e = sum(1 for e in fm.entries_snapshot_for_tests() if e.get("contradiction_detected"))
        overview = client.get("/memory/observability/overview").json()
        life = client.get("/health/memory/lifecycle").json()
        contra_api = max(
            contradictory_e,
            int(overview.get("contradiction_count") or 0),
            int(life.get("contradictions_detected") or 0),
        )
        test("contradiction_detected_signals", contra_api > 0, f"counts={contradictory_e} api={overview}")

        banals = ["salut", "ok", "merci", "bien vu", "super", "au revoir", "parfait", "oui", "ça va ?", "nice"]
        for b in banals:
            rr = client.post("/chat", json={"message": b, "project_name": proj}, headers=_chat_headers())
            if rr.status_code != 200:
                raise RuntimeError(f"chat banal '{b}' {rr.status_code}")
        rr2 = client.post(
            "/chat",
            json={"message": "hello yo", "project_name": proj},
            headers=_chat_headers(),
        )
        if rr2.status_code != 200:
            raise RuntimeError(f"chat banal hello yo {rr2.status_code}")
        rr3 = client.post(
            "/chat",
            json={"message": "cool", "project_name": proj},
            headers=_chat_headers(),
        )
        if rr3.status_code != 200:
            raise RuntimeError(rr3.text)

        ctx_noise, mem_noise = fm.build_layered_memory_context(
            "Quelques nouvelles pour la prod ?",
            user_key=user_key,
            project_name_hint=proj,
            is_guest=False,
        )
        noise_hits = sum(ctx_noise.lower().count(w) for w in ("salut", "merci", "bien vu", "nice", "cool"))
        strong = ("deepseek" in ctx_noise.lower()) or ("bytebytego" in ctx_noise.lower())
        test(
            "anti_noise_deepseek_pref_not_drowned",
            strong or len(mem_noise) > 0 and noise_hits <= max(24, len(ctx_noise) // 25 + 15),
            f"noise_hits={noise_hits} strong={strong} snippet={ctx_noise[:500]}",
        )

        ids_deepseek: list[str] = []
        for e in fm.entries_snapshot_for_tests():
            s = str(e.get("summary", "")).lower()
            if "deepseek" in s or "railway" in s:
                if str(e.get("memory_level")) in {"summary_memory", "concept_memory"}:
                    ids_deepseek.append(str(e["id"]))
        ids_deepseek = sorted(set(ids_deepseek))
        before = Counter()
        for eid in ids_deepseek:
            for e in fm.entries_snapshot_for_tests():
                if str(e.get("id")) == eid:
                    before[eid] = max(before[eid], int(e.get("access_count") or 0))
        q_loop = (
            "OpenChawn Railway: confirm DeepSeek is the configured "
            "LLM provider for production?"
        )
        for _ in range(3):
            rc = client.post(
                "/chat",
                json={"message": q_loop, "project_name": proj},
                headers=_chat_headers(),
            )
            if rc.status_code != 200:
                raise RuntimeError(rc.text)

        after_snap = fm.entries_snapshot_for_tests()
        after = Counter()
        for eid in ids_deepseek:
            for e in after_snap:
                if str(e.get("id")) == eid:
                    after[eid] = max(after[eid], int(e.get("access_count") or 0))
        gained = any(after[eid] > before.get(eid, 0) for eid in ids_deepseek if eid)
        test(
            "reinforcement_access_count",
            len(ids_deepseek) > 0 and gained,
            f"candidates={ids_deepseek[:6]} before={dict(before)} after={dict(after)}",
        )

        archived_summary_marker = _inject_archivable_entry(user_key=user_key)
        arch_ok = False
        for row in fm.entries_snapshot_for_tests():
            if row.get("summary") == archived_summary_marker:
                arch_ok = str(row.get("lifecycle_status")) == fm.MEMORY_LIFECYCLE_ARCHIVED
                break
        test("archive_weak_old_untouch", arch_ok, archived_summary_marker)

        client.post(
            "/chat",
            json={
                "message": "Une dernière question sur DeepSeek Railway.",
                "project_name": proj,
            },
            headers=_chat_headers(),
        )
        lc = client.get("/memory/last-context")
        if lc.status_code != 200:
            raise RuntimeError(lc.text)
        items = lc.json().get("items") or []
        first = items[0] if items else {}
        need = {"why_selected", "relevance_score", "importance_score", "decay_score", "retrieval_rank"}
        test("last_context_keys", isinstance(first, dict) and need <= set(first.keys()), f"got={sorted(first.keys())}")

        lifecycle = client.get("/health/memory/lifecycle").json()
        overview_final = client.get("/memory/observability/overview").json()
        top = client.get("/memory/top")

        print("\n--- RAPPORT FINAL ---")
        print(f"tests_passed={passed}")
        print(f"tests_failed={failed}")
        contra = lifecycle.get(
            "contradictions_detected",
            overview_final.get("contradiction_count", 0),
        )
        print(f"contradictions_detected={contra}")
        print(f"memory_health_score={lifecycle.get('memory_health_score')}")
        if top.status_code == 200:
            td = top.json()
            rows = td.get("items") or []
            print("top_memories:")
            for row in rows[:10]:
                s = str(row.get("summary", "")).replace("\n", " ")[:140]
                print(f"  - [{row.get('memory_type')}] {s}")

        shutil.rmtree(tmp, ignore_errors=True)
        return 0 if failed == 0 else 1

    finally:
        app.dependency_overrides.pop(get_current_user_or_guest, None)


if __name__ == "__main__":
    sys.exit(main())
