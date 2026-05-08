"""
Memory Compression + Summarization Layer V11.6 — heuristiques locales uniquement.
Pas d’appel LLM, pas d’embeddings, pas de vector DB.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any

from app.memory.fractal_memory import (
    MEMORY_LIFECYCLE_ARCHIVED,
    MEMORY_LIFECYCLE_ACTIVE,
    MEMORY_TYPES,
    _STORE_LOCK,
    _contains_sensitive_text,
    _ensure_entry_defaults,
    _load_entries,
    _normalize_project_slug,
    _now_iso,
    _save_entries,
    concept_merge_key,
    is_active_memory,
    recompute_decay_score,
)

MIN_CLUSTER_ITEMS = 3
_COMPRESSION_META_VERSION = "11.6"

_DECISION_HINTS_RE = re.compile(
    r"(principal|priorit|priorité|must|critical|critical|rule|rule|règle|should|should|must not|"
    r"interdit|forbidden|doit|ne pas|important|interdit)",
    re.IGNORECASE,
)


def _metadata_secret_flag(entry: dict) -> bool:
    md = entry.get("metadata")
    if not isinstance(md, dict):
        return False
    for k in (
        "secret",
        "contains_secret",
        "contains_secrets",
        "redacted_secret",
        "api_key_hint",
        "has_token",
    ):
        if md.get(k):
            return True
    return False


def _eligible_source_for_compression(entry: dict, *, include_archived: bool = False) -> bool:
    if str(entry.get("memory_type", "")) == "compressed":
        return False
    if entry.get("metadata") and isinstance(entry.get("metadata"), dict):
        if str((entry["metadata"]).get("compressed_into") or "").strip():
            return False
    st_lc = str(entry.get("lifecycle_status", MEMORY_LIFECYCLE_ACTIVE))
    if st_lc == MEMORY_LIFECYCLE_ARCHIVED:
        if not include_archived:
            return False
    elif not is_active_memory(entry):
        return False
    if bool(entry.get("contradiction_detected")):
        return False
    if _metadata_secret_flag(entry):
        return False
    text_parts = (
        str(entry.get("summary", "")),
        str(entry.get("user_message", "")),
        str(entry.get("assistant_response", "")),
    )
    if _contains_sensitive_text(*text_parts):
        return False
    ml = str(entry.get("memory_level", "")).strip().lower()
    if ml not in ("summary_memory", "concept_memory"):
        return False
    mt = str(entry.get("memory_type", "")).strip().lower()
    if mt not in MEMORY_TYPES or mt == "compressed":
        return False
    return True


def _canonical_bucket(summary: str) -> str:
    key = concept_merge_key(summary or "")
    if key:
        return key[:260]
    return re.sub(r"\s+", " ", (summary or "").strip().lower())[:120]


def _linked_concept_id(entry: dict) -> str:
    md = entry.get("metadata")
    if not isinstance(md, dict):
        return ""
    return str(md.get("linked_concept_id") or "").strip()


def _tags_key(entry: dict) -> tuple[str, ...]:
    raw = entry.get("tags") or []
    if not isinstance(raw, list):
        return ()
    out = sorted({str(t).strip().lower() for t in raw if str(t).strip()})
    return tuple(out)


def _cluster_signature(entry: dict) -> tuple[str, str, str, tuple[str, ...], str]:
    pn = _normalize_project_slug(str(entry.get("project_name") or entry.get("project") or ""))
    mt = str(entry.get("memory_type", "")).strip().lower()
    cid = _linked_concept_id(entry)
    tags = _tags_key(entry)
    canon = _canonical_bucket(str(entry.get("summary", "")))
    return (pn, mt, cid, tags, canon)


def find_compression_candidates(
    entries: list[dict],
    *,
    include_archived: bool = False,
    min_cluster: int = MIN_CLUSTER_ITEMS,
) -> dict[str, Any]:
    """
    Regroupe les souvenirs éligibles par (projet, type, concept_id, tags, canon proche via concept_merge_key).
    Ignore contradictions marquées, secrets, archives (sauf option), entrées déjà compressées ou pointées compressed_into.
    """
    buckets: dict[tuple[str, str, str, tuple[str, ...], str], list[str]] = defaultdict(list)

    skipped_contradictions: list[str] = []

    for e in entries:
        eid = str(e.get("id") or "")
        if not eid:
            continue
        if (
            bool(e.get("contradiction_detected"))
            and _eligible_summary_or_concept(e)
            and eid not in skipped_contradictions
        ):
            skipped_contradictions.append(eid)
        if not _eligible_source_for_compression(e, include_archived=include_archived):
            continue
        sig = _cluster_signature(e)
        buckets[sig].append(eid)

    clusters_out: list[dict[str, Any]] = []
    for sig, ids in buckets.items():
        uniq = sorted(set(ids))
        if len(uniq) < min_cluster:
            continue
        pn, mt, cid, tags, canon = sig
        clusters_out.append(
            {
                "project_name": pn,
                "memory_type": mt,
                "concept_id": cid,
                "tags": list(tags),
                "canonical_bucket": canon,
                "candidate_ids": uniq,
                "cluster_size": len(uniq),
            }
        )

    clusters_out.sort(key=lambda x: (-int(x["cluster_size"]), x["project_name"], x["memory_type"]))
    return {
        "status": "ok",
        "clusters": clusters_out,
        "skipped_contradiction_ids": skipped_contradictions[:200],
        "rules": {
            "min_cluster": min_cluster,
            "include_archived": include_archived,
            "engine": "heuristic_v11_6_no_llm",
        },
    }


def _eligible_summary_or_concept(entry: dict) -> bool:
    ml = str(entry.get("memory_level", "")).strip().lower()
    return ml in ("summary_memory", "concept_memory")


def summarize_memory_cluster(cluster: list[dict]) -> dict[str, Any]:
    """
    Synthèse template sans LLM : agrège textes, motifs « décisions », faits courts, questions ouvertes.
    """
    lines: list[str] = []
    for e in sorted(cluster, key=lambda x: str(x.get("timestamp") or "")):
        s = str(e.get("summary", "")).strip()
        if s:
            lines.append(s)
        um = str(e.get("user_message", "")).strip()
        ar = str(e.get("assistant_response", "")).strip()
        if um and len(um) < 520:
            lines.append(um)
        if ar and len(ar) < 520:
            lines.append(ar)

    merged = " ".join(lines)
    merged = re.sub(r"\s+", " ", merged).strip()

    key_decisions: list[str] = []
    stable_facts: list[str] = []
    open_questions: list[str] = []

    for ln in merged.split(". "):
        t = ln.strip()
        if not t or _contains_sensitive_text(t):
            continue
        tl = t.lower()
        if "?" in t:
            open_questions.append(t[:420])
            continue
        if _DECISION_HINTS_RE.search(tl):
            key_decisions.append(t[:420])
            continue
        if any(k in tl for k in (":", "—", "-", "est ", " is ", " uses ", "railway")) and len(t) <= 520:
            stable_facts.append(t[:420])

    if not stable_facts and lines:
        stable_facts.append(lines[0][:400])

    uniq_bits: list[str] = []
    seen_l: set[str] = set()
    for raw in lines[:16]:
        s = str(raw).strip()
        if not s or _contains_sensitive_text(s):
            continue
        sig = s[:220].lower()
        if sig in seen_l:
            continue
        seen_l.add(sig)
        uniq_bits.append(s[:520])
    compressed_summary = "; ".join(uniq_bits)
    if len(compressed_summary) > 1800:
        compressed_summary = compressed_summary[:1770].rstrip() + " …"

    return {
        "compressed_summary": compressed_summary,
        "key_decisions": key_decisions[:14],
        "stable_facts": stable_facts[:22],
        "open_questions": open_questions[:16],
    }


def build_compressed_memory(cluster: list[dict], *, contradiction_refs: list[str] | None = None) -> dict[str, Any]:
    """Construit une entrée mémoire `memory_type=compressed` (persistée via `_ensure_entry_defaults`)."""
    contradiction_refs = list(contradiction_refs or [])
    summaries = summarize_memory_cluster(cluster)

    pn = ""
    mt = ""
    tags_acc: set[str] = {"compressed"}
    for e in cluster:
        pn = pn or _normalize_project_slug(str(e.get("project_name") or e.get("project") or ""))
        mt = mt or str(e.get("memory_type") or "project").strip().lower()
        for t in e.get("tags") or []:
            if str(t).strip():
                tags_acc.add(str(t).strip().lower())

    ids = sorted({str(e.get("id")) for e in cluster if e.get("id")})

    compression_score = round(min(1.0, 0.18 + 0.07 * len(ids)), 4)

    cid = ""
    md0 = cluster[0].get("metadata") if isinstance(cluster[0].get("metadata"), dict) else {}
    if isinstance(md0, dict):
        cid = str(md0.get("linked_concept_id") or "").strip()

    summary_short = summaries["compressed_summary"][:620]
    meta: dict[str, Any] = {
        "compression_engine": _COMPRESSION_META_VERSION,
        "source_memory_ids": ids,
        "compressed_summary": summaries["compressed_summary"],
        "key_decisions": summaries["key_decisions"],
        "stable_facts": summaries["stable_facts"],
        "open_questions": summaries["open_questions"],
        "contradiction_refs": contradiction_refs[:80],
        "compression_score": compression_score,
        "linked_concept_id": cid or None,
    }

    entry = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "timestamp": _now_iso(),
        "memory_type": "compressed",
        "memory_level": "summary_memory",
        "project_name": pn,
        "project": pn,
        "user_id": str(cluster[0].get("user_id") or ""),
        "source": "memory_compression_v11_6",
        "user_message": "",
        "assistant_response": "",
        "summary": summary_short,
        "tags": sorted(tags_acc),
        "importance_score": max(0.82, round(0.78 + compression_score * 0.06, 3)),
        "parent_id": None,
        "children_ids": [*ids],
        "metadata": meta,
        "lifecycle_status": MEMORY_LIFECYCLE_ACTIVE,
        "contradiction_detected": False,
    }

    entry = _ensure_entry_defaults(entry)
    entry["decay_score"] = recompute_decay_score(entry)
    return entry


def mark_source_memories_compressed(entries: list[dict], source_ids: list[str], compressed_id: str) -> int:
    """Marque les sources : metadata.compressed_into + priorité injection réduite (importance_score)."""
    ix = {str(e.get("id")): e for e in entries if e.get("id")}
    touched = 0
    for sid in source_ids:
        e = ix.get(str(sid))
        if not e:
            continue
        md = e.setdefault("metadata", {})
        if not isinstance(md, dict):
            continue
        md["compressed_into"] = str(compressed_id)
        md.setdefault("compression_source_demoted_at", _now_iso())
        prev = float(e.get("importance_score") or 0.0)
        e["importance_score"] = max(0.02, round(prev * 0.32, 4))
        e["decay_score"] = recompute_decay_score(e)
        touched += 1
    return touched


def compress_project_memories(
    entries: list[dict],
    project_slug: str,
    *,
    include_archived: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    pn = _normalize_project_slug(project_slug)
    filt = [
        e
        for e in entries
        if _normalize_project_slug(str(e.get("project_name") or e.get("project") or "")) == pn
    ]
    return _compress_filtered_entries(filt, entries, dry_run=dry_run, include_archived=include_archived)


def compress_concept_memories(
    entries: list[dict],
    concept_id: str,
    *,
    include_archived: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    cid = (concept_id or "").strip()
    filt = [e for e in entries if _linked_concept_id(e) == cid]
    return _compress_filtered_entries(filt, entries, dry_run=dry_run, include_archived=include_archived)


def _compress_filtered_entries(
    subset: list[dict],
    all_entries: list[dict],
    *,
    include_archived: bool,
    dry_run: bool,
) -> dict[str, Any]:
    report = {"status": "ok", "created": [], "dry_run": dry_run, "candidates_processed": 0}
    cand = find_compression_candidates(subset, include_archived=include_archived)
    clusters = cand.get("clusters") or []

    ix_all = {str(e.get("id")): e for e in all_entries if e.get("id")}

    for cl in clusters:
        ids = cl.get("candidate_ids") or []
        cluster_objs = [ix_all[i] for i in ids if i in ix_all]
        if len(cluster_objs) < MIN_CLUSTER_ITEMS:
            continue

        def _coarse_key(obj: dict) -> tuple[str, str, str, tuple[str, ...]]:
            pn, mt, cid, tags, _c = _cluster_signature(obj)
            return (pn, mt, cid, tags)

        contradiction_refs = [
            str(e.get("id"))
            for e in subset
            if bool(e.get("contradiction_detected"))
            and _eligible_summary_or_concept(e)
            and _coarse_key(e) == _coarse_key(cluster_objs[0])
        ]

        compressed = build_compressed_memory(cluster_objs, contradiction_refs=contradiction_refs)
        report["candidates_processed"] += 1
        if dry_run:
            report["created"].append(
                {"id": compressed["id"], "preview_summary": compressed["summary"][:200], "would_mark": ids}
            )
            continue

        all_entries.append(compressed)
        mark_source_memories_compressed(all_entries, ids, str(compressed["id"]))
        report["created"].append({"id": compressed["id"], "source_memory_ids": ids})

    return report


def run_memory_compression_job(
    *,
    include_archived: bool = False,
    dry_run: bool = False,
    project: str | None = None,
) -> dict[str, Any]:
    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
        if project and str(project).strip():
            res = compress_project_memories(
                entries,
                str(project),
                include_archived=include_archived,
                dry_run=dry_run,
            )
        else:
            res = _compress_filtered_entries(
                entries,
                entries,
                include_archived=include_archived,
                dry_run=dry_run,
            )
        if not dry_run and res.get("created"):
            _save_entries(entries)
        res["persisted"] = not dry_run and bool(res.get("created"))
        return res


def compression_health_report(entries: list[dict] | None = None) -> dict[str, Any]:
    owned = entries is None
    if owned:
        try:
            with _STORE_LOCK:
                snapshot = [_ensure_entry_defaults(dict(e)) for e in _load_entries()]
        except Exception as e:
            return {"status": "error", "detail": str(e)}
    else:
        snapshot = [_ensure_entry_defaults(dict(e)) for e in (entries or [])]

    compressed_n = sum(1 for e in snapshot if str(e.get("memory_type")) == "compressed")
    demoted_sources = sum(
        1
        for e in snapshot
        if isinstance(e.get("metadata"), dict) and str((e["metadata"]).get("compressed_into") or "").strip()
    )
    cand = find_compression_candidates(snapshot, include_archived=False)

    dup_pressure_project: dict[str, int] = defaultdict(int)
    for e in snapshot:
        if str(e.get("memory_type")) == "compressed":
            continue
        if str(e.get("memory_level")) not in ("summary_memory", "concept_memory"):
            continue
        if not is_active_memory(e):
            continue
        ps = _normalize_project_slug(str(e.get("project_name") or ""))
        if ps:
            dup_pressure_project[ps] += 1

    return {
        "status": "ok",
        "snapshot_owned_by_store": owned,
        "compressed_memories": compressed_n,
        "sources_marked_compressed_into": demoted_sources,
        "estimated_candidate_clusters": len(cand.get("clusters") or []),
        "top_project_dup_pressure": sorted(
            ({"project": k, "summary_layer_items": v} for k, v in dup_pressure_project.items()),
            key=lambda x: -int(x["summary_layer_items"]),
        )[:12],
        "min_cluster_items": MIN_CLUSTER_ITEMS,
        "compression_engine": _COMPRESSION_META_VERSION,
    }


def get_compressed_memory_by_id(memory_id: str) -> dict[str, Any]:
    mid = (memory_id or "").strip()
    if not mid:
        return {"status": "error", "detail": "missing_id"}
    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
    for e in entries:
        if str(e.get("id")) != mid:
            continue
        if str(e.get("memory_type")) != "compressed":
            return {"status": "error", "detail": "not_compressed_type"}
        out = dict(e)
        md = out.get("metadata")
        if isinstance(md, dict):
            for fld in (
                "source_memory_ids",
                "compressed_summary",
                "key_decisions",
                "stable_facts",
                "open_questions",
                "contradiction_refs",
                "compression_score",
            ):
                if fld in md and fld not in out:
                    out[fld] = md[fld]
        return {"status": "ok", "memory": out}
    return {"status": "error", "detail": "not_found"}
