from __future__ import annotations
import re
from typing import Literal

Emotion = Literal[
    "frustrated", "urgent", "uncertain", "curious", "confident", "neutral"
]
Intent = Literal["command", "question", "validation", "exploration", "vent"]
NudgeType = Literal[
    "risk_reduction", "social_proof", "action", "clarity", "momentum"
]

_FRUSTRATED_RE = re.compile(
    r"\b(putain|merde|marre|fuck|damn|bordel|nul|cass[eé]|chiant)\b|!{2,}", re.I
)
_URGENT_RE = re.compile(
    r"\b(urgent|vite|asap|tout de suite|maintenant|now|quickly|rapidement)\b", re.I
)
_UNCERTAIN_RE = re.compile(
    r"\b(peut[- ]être|je sais pas|maybe|pas sûr|unsure|hésite|dois[- ]je|should i)\b",
    re.I,
)
_CURIOUS_RE = re.compile(r"\b(pourquoi|comment|what if|why|how|quelle?s?)\b", re.I)
_CONFIDENT_RE = re.compile(
    r"\b(impose|fais[- ]le|go|vas[- ]y|execute|crée?|ajoute|refactor|continue|commence)\b",
    re.I,
)
_VALIDATION_RE = re.compile(
    r"\b(est[- ]ce|vérifie?|check|valide?|right\?|correct\?|ok\?)\b", re.I
)


def detect_emotion(text: str) -> tuple[Emotion, float]:
    t = text.strip()
    caps_ratio = sum(1 for c in t if c.isupper()) / max(len(t), 1)
    if _FRUSTRATED_RE.search(t) or (len(t) > 10 and caps_ratio > 0.5):
        return "frustrated", 0.8
    if _URGENT_RE.search(t):
        return "urgent", 0.75
    if _UNCERTAIN_RE.search(t):
        return "uncertain", 0.7
    if _CONFIDENT_RE.search(t):
        return "confident", 0.75
    if _CURIOUS_RE.search(t) or t.rstrip().endswith("?"):
        return "curious", 0.65
    return "neutral", 0.5


def detect_hidden_intent(text: str, emotion: Emotion) -> Intent:
    t = text.strip()
    if emotion == "frustrated":
        return "vent"
    if _VALIDATION_RE.search(t):
        return "validation"
    if t.rstrip().endswith("?") or emotion == "curious":
        return "question"
    if emotion in ("confident", "urgent") or _CONFIDENT_RE.search(t):
        return "command"
    return "exploration"


_NUDGE_MAP: dict[Emotion, NudgeType] = {
    "frustrated": "risk_reduction",
    "urgent": "action",
    "uncertain": "clarity",
    "curious": "clarity",
    "confident": "momentum",
    "neutral": "action",
}

_NUDGE_TEXT: dict[NudgeType, str] = {
    "risk_reduction": "Découper en micro-étape et dé-risquer avant d'avancer.",
    "social_proof": "Appuyer la décision sur un pattern déjà validé dans le projet.",
    "action": "Exécuter directement, ne pas sur-délibérer.",
    "clarity": "Clarifier l'intention ou reformuler avant d'agir.",
    "momentum": "Enchaîner sur la lancée, ne pas casser le flow.",
}


def pick_nudge(emotion: Emotion) -> tuple[str, NudgeType]:
    nt = _NUDGE_MAP[emotion]
    return _NUDGE_TEXT[nt], nt


def analyze_human(text: str) -> dict:
    emotion, conf = detect_emotion(text)
    intent = detect_hidden_intent(text, emotion)
    nudge_text, nudge_type = pick_nudge(emotion)
    return {
        "detected_emotion": emotion,
        "intent_hidden": intent,
        "confidence_level": round(conf, 3),
        "recommended_nudge": nudge_text,
        "nudge_type": nudge_type,
    }
