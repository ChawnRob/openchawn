"""
World Impact Layer — prédiction de conséquences MVP (heuristiques locales uniquement).
Pas de LLM, JEPA ni embeddings. Prêt pour une future couche world-model / ASI-evolve.
"""

from __future__ import annotations

import copy
from threading import Lock
from typing import Any

from app.memory.memory_timeline import sanitize_timeline_text

_LAST_IMPACT_LOCK = Lock()
_LAST_IMPACT_REPORT: dict[str, Any] = {
    "status": "empty",
    "likely_benefits": [],
    "likely_risks": [],
    "technical_impact": "",
    "cost_impact": "",
    "stability_impact": "",
    "security_impact": "",
    "provider_impact": "",
    "memory_impact": "",
    "confidence_hint": None,
}


def _scrub_lines(lines: list[str], *, max_items: int = 14, max_len: int = 240) -> list[str]:
    out: list[str] = []
    for raw in lines[:max_items]:
        s = sanitize_timeline_text(str(raw).strip(), max_len)
        if s and s != "[REDACTED_SECRET]":
            out.append(s)
    return out


def score_risk_benefit(
    action_lower: str,
    *,
    related_memories: list[dict[str, Any]],
    decision_context: dict[str, Any] | None,
) -> dict[str, float]:
    benefit = 24.0
    risk = 18.0

    if any(k in action_lower for k in ("postgres", "postgresql", "sqlite replacement")):
        benefit += 22.0
        risk += 14.0
    if any(k in action_lower for k in ("redis", "cache", "cdn")):
        benefit += 12.0
        risk += 10.0
    if any(k in action_lower for k in ("migrate", "migration", "schema")):
        risk += 16.0
        benefit += 6.0
    if any(k in action_lower for k in ("delete", "remove prod", "drop table", "truncate")):
        risk += 26.0
    if any(k in action_lower for k in ("encrypt", "tls", "secret rotation", "vault")):
        benefit += 14.0
        risk += 4.0
    if any(k in action_lower for k in ("rollback", "feature flag", "canary")):
        benefit += 10.0
        risk -= 4.0

    dc = decision_context or {}
    conf = dc.get("confidence_hint")
    if isinstance(conf, (int, float)):
        benefit += float(conf) * 6.0
    conflicts = dc.get("conflicts_detected") or []
    risk += min(22.0, len(conflicts) * 4.0)

    for m in related_memories[:12]:
        summ = str((m or {}).get("summary") or "").lower()
        if "contradiction" in summ or "interdit" in summ:
            risk += 5.0
        if "stable" in summ or "validé" in summ:
            benefit += 4.0

    return {"benefit_score": round(benefit, 2), "risk_score": round(max(4.0, risk), 2)}


def predict_action_consequences(
    proposed_action: str,
    project: str,
    related_memories: list[dict[str, Any]],
    decision_context: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = (proposed_action or "").strip()
    action_safe = sanitize_timeline_text(raw, 800)
    act_l = raw.lower()
    proj_safe = sanitize_timeline_text(str(project or "").strip(), 120)

    benefits: list[str] = []
    risks: list[str] = []

    technical = "impact_technique_modéré"
    cost = "coût_modéré"
    stability = "stabilité_neutre_à_positive"
    security = "surface_de_sécurité_stable"
    provider = "impact_fournisseur_cloud_limité"
    memory = "impact_sur_la_couche_mémoire_modéré"

    if any(k in act_l for k in ("postgres", "postgresql")):
        benefits.extend(
            [
                "Persistance structurée et requêtes relationnelles pour la mémoire et les métadonnées.",
                "Meilleure observabilité et sauvegardes qu'un fichier JSON seul.",
            ]
        )
        risks.extend(
            [
                "Migration des données et stratégie de schéma (versions, migrations).",
                "Gestion des connexions (pool, timeouts) sur Railway / environnement cloud.",
            ]
        )
        technical = "fort_changements_backend_et_drivers_db"
        cost = "coût_récurrent_base_gérée_ou_volume_stockage"
        stability = "stabilité_long_terme_meilleure_si_ops_solides"
        security = "secrets_connexion_tls_et_principle_of_least_privilege"
        memory = "remplacement_ou_duplication_du_store_JSON_actuel"
    elif any(k in act_l for k in ("redis", "cache")):
        benefits.append("Réduction de latence et protection contre les pics de charge mémoire.")
        risks.append("Invalidation de cache et cohérence éventuelle entre instances.")
        technical = "modéré_services_supplémentaires"
        cost = "faible_à_modéré_selon_offre"
        stability = "positive_si_ttl_et_monitoring"
        memory = "complément_possible_au_store_principal"

    if any(k in act_l for k in ("ollama", "local llm")):
        provider = "favorise_execution_locale_dev_coût_api_réduit"
        risks.append("Charge CPU locale et écart prod/cloud si mal documenté.")
    if any(k in act_l for k in ("openrouter", "deepseek", "anthropic", "openai")):
        provider = "dépendance_au_provider_et_aux_quotas_cloud"
        risks.append("Variabilité coût/latence selon le provider et le modèle.")

    if any(k in act_l for k in ("railway", "deploy", "déploi")):
        stability += "_avec_validation_ci_cd"
        risks.append("Régression possible si variables d'environnement ou build mal synchronisés.")

    if any(k in act_l for k in ("encrypt", "tls", "auth", "sso")):
        security = "renforcement_authentification_chiffrement"
        benefits.append("Réduction de surface d'attaque sur les canaux sensibles.")

    if not benefits:
        benefits.append("Action à préciser : gains potentiels liés à l'amélioration opérationnelle du projet.")
    if not risks:
        risks.append("Risques résiduels : régression fonctionnelle sans stratégie de test.")

    scores = score_risk_benefit(act_l, related_memories=related_memories, decision_context=decision_context)
    denom = scores["benefit_score"] + scores["risk_score"]
    confidence = round(max(0.12, min(0.72, scores["benefit_score"] / denom)) if denom else 0.35, 3)

    dc_note = ""
    if decision_context:
        cc = len(decision_context.get("conflicts_detected") or [])
        if cc:
            dc_note = sanitize_timeline_text(
                f"Contexte décision récent : {cc} conflit(s) mémoire signalé(s).",
                280,
            )

    return {
        "proposed_action_preview": action_safe,
        "project": proj_safe,
        "likely_benefits": _scrub_lines(benefits),
        "likely_risks": _scrub_lines(risks + ([sanitize_timeline_text(dc_note.strip(), 280)] if dc_note else [])),
        "technical_impact": sanitize_timeline_text(technical, 160),
        "cost_impact": sanitize_timeline_text(cost, 160),
        "stability_impact": sanitize_timeline_text(stability, 200),
        "security_impact": sanitize_timeline_text(security, 200),
        "provider_impact": sanitize_timeline_text(provider, 200),
        "memory_impact": sanitize_timeline_text(memory, 220),
        "confidence_hint": confidence,
        "_risk_benefit_scores": scores,
    }


def build_impact_report(
    *,
    proposed_action: str,
    project: str = "",
    related_memories: list[dict[str, Any]] | None = None,
    decision_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pred = predict_action_consequences(
        proposed_action,
        project or "",
        list(related_memories or []),
        decision_context,
    )
    pred.pop("_risk_benefit_scores", None)
    report = {
        "status": "ok",
        "likely_benefits": pred["likely_benefits"],
        "likely_risks": pred["likely_risks"],
        "technical_impact": pred["technical_impact"],
        "cost_impact": pred["cost_impact"],
        "stability_impact": pred["stability_impact"],
        "security_impact": pred["security_impact"],
        "provider_impact": pred["provider_impact"],
        "memory_impact": pred["memory_impact"],
        "confidence_hint": pred["confidence_hint"],
        "proposed_action_preview": pred["proposed_action_preview"],
        "project": pred["project"],
    }
    global _LAST_IMPACT_REPORT
    with _LAST_IMPACT_LOCK:
        _LAST_IMPACT_REPORT = copy.deepcopy(report)
    return report


def get_last_impact_report() -> dict[str, Any]:
    with _LAST_IMPACT_LOCK:
        return copy.deepcopy(_LAST_IMPACT_REPORT)


def clear_last_impact_for_tests() -> None:
    with _LAST_IMPACT_LOCK:
        _LAST_IMPACT_REPORT.clear()
        _LAST_IMPACT_REPORT.update(
            {
                "status": "empty",
                "likely_benefits": [],
                "likely_risks": [],
                "technical_impact": "",
                "cost_impact": "",
                "stability_impact": "",
                "security_impact": "",
                "provider_impact": "",
                "memory_impact": "",
                "confidence_hint": None,
            }
        )
