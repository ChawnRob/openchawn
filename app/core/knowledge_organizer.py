"""COCO Study/Career Knowledge Organizer — structured Markdown for Obsidian/AFFiNE."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

KNOWLEDGE_ORGANIZER_MARKER = "knowledge_organizer_v1"

NOTE_TYPES = ("course", "revision", "project", "progress", "career", "idea")

DENIAL_PHRASES = (
    "je ne peux pas interagir avec obsidian",
    "i cannot interact with obsidian",
    "i cannot do anything with obsidian",
    "aucune capacité obsidian",
    "obsidian indisponible",
    "pas de connecteur obsidian",
)


def _normalize(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    return re.sub(r"\s+", " ", t).strip()


def detect_knowledge_organizer_intent(text: str) -> bool:
    t = _normalize(text)
    if not t:
        return False
    patterns = [
        r"\b(range|organis\w*|structure)\w*\s+(ce\s+)?cours\b",
        r"\bcours\b.*\b(obsidian|affine)\b",
        r"\b(obsidian|affine)\b.*\bcours\b",
        r"\bfiche\s+de\s+revision\b",
        r"\bfiche\s+de\s+revis\w+\b",
        r"\bfais[- ]?moi\s+une\s+fiche\b",
        r"\bnote\s+ma\s+progression\b",
        r"\b(progress(?:ion)?|suivi)\b.*\b(anglais|matiere|matière|obsidian|affine)\b",
        r"\b(prepare|prépare|preparer)\w*\s+une\s+note\s+(carriere|carrière|orientation)\b",
        r"\bnote\s+(carriere|carrière|orientation)\b",
        r"\b(mets|met)\w*\s+(cette\s+)?idee\s+(dans\s+)?affine\b",
        r"\b(mets|met)\w*\s+(cette\s+)?idée\s+(dans\s+)?affine\b",
        r"\b(capture|captur)\w*\s+(cette\s+)?idee\b",
        r"\bprojet\b.*\b(note|obsidian|affine)\b",
        r"\b(revision|revis\w+|orientation|carriere|carrière)\b.*\b(obsidian|affine)\b",
    ]
    return any(re.search(p, t) for p in patterns)


def classify_note_type(text: str) -> str:
    t = _normalize(text)
    if re.search(r"\bfiche\s+de\s+revis", t) or re.search(r"\bfais[- ]?moi\s+une\s+fiche\b", t):
        return "revision"
    if re.search(r"\bnote\s+ma\s+progression\b", t) or re.search(r"\bprogress(?:ion)?\b", t):
        return "progress"
    if re.search(r"\b(carriere|carrière|orientation)\b", t):
        return "career"
    if re.search(r"\bidee\b", t) or re.search(r"\bidée\b", text.lower()):
        return "idea"
    if re.search(r"\bprojet\b", t):
        return "project"
    if re.search(r"\bcours\b", t):
        return "course"
    return "idea"


def resolve_suggested_destination(text: str) -> str:
    t = _normalize(text)
    has_obsidian = "obsidian" in t
    has_affine = "affine" in t or "second brain" in t
    if has_obsidian and has_affine:
        return "Obsidian ou AFFiNE"
    if has_affine:
        return "AFFiNE"
    if has_obsidian:
        return "Obsidian"
    return "Obsidian ou AFFiNE"


def _extract_subject(text: str) -> str:
    t = _normalize(text)
    for pat in (
        r"\ben\s+([a-z][a-z\s]{2,24})\b",
        r"\bde\s+([a-z][a-z\s]{2,24})\b",
        r"\bsur\s+([a-z][a-z\s]{2,24})\b",
    ):
        m = re.search(pat, t)
        if m:
            subj = m.group(1).strip()
            if subj not in ("obsidian", "affine", "cours", "note", "fiche", "revision", "maths"):
                return subj.title()
    if "maths" in t or "math" in t:
        return "Maths"
    if "anglais" in t:
        return "Anglais"
    return "Général"


def _note_title(note_type: str, subject: str, created_at: str) -> str:
    stamp = created_at[:10]
    labels = {
        "course": "Cours",
        "revision": "Revision",
        "project": "Projet",
        "progress": "Progression",
        "career": "Carriere",
        "idea": "Idee",
    }
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-") or "general"
    return f"COCO-{labels.get(note_type, 'Note')}-{stamp}-{slug}"


def _sections_for_type(note_type: str, user_text: str, subject: str) -> list[tuple[str, str]]:
    if note_type == "course":
        return [
            ("Objectifs du cours", f"Organiser et structurer : {user_text}"),
            ("Points clés", "_À compléter après la session._"),
            ("Définitions", "_Termes importants à retenir._"),
            ("Exemples", "_Exemples vus en cours._"),
            ("Questions ouvertes", "_Points à clarifier._"),
        ]
    if note_type == "revision":
        return [
            ("Sujet", subject),
            ("À retenir", "_Formulations courtes et mémorables._"),
            ("Formules / règles", "_Liste des règles essentielles._"),
            ("Pièges fréquents", "_Erreurs à éviter._"),
            ("Auto-test", "_3 questions pour vérifier la compréhension._"),
        ]
    if note_type == "project":
        return [
            ("Contexte", user_text),
            ("Objectifs", "_Résultat attendu du projet._"),
            ("Étapes", "_Plan d'action par phases._"),
            ("Ressources", "_Liens, docs, contacts._"),
            ("Prochaines actions", "_3 actions concrètes._"),
        ]
    if note_type == "progress":
        return [
            ("Domaine", subject),
            ("Niveau actuel", "_Auto-évaluation ou dernier résultat._"),
            ("Objectif", "_Où vous voulez arriver._"),
            ("Jalons", "_Étapes intermédiaires mesurables._"),
            ("Notes de séance", user_text),
        ]
    if note_type == "career":
        return [
            ("Profil & intérêts", user_text),
            ("Options explorées", "_Pistes professionnelles ou académiques._"),
            ("Compétences", "_Forces actuelles et à développer._"),
            ("Ressources", "_Contacts, sites, formations._"),
            ("Prochaines étapes", "_Actions concrètes cette semaine._"),
        ]
    return [
        ("Idée", user_text),
        ("Contexte", "_D'où vient cette idée._"),
        ("Pourquoi maintenant", "_Ce qui rend l'idée pertinente._"),
        ("Prochaines actions", "_Première étape pour avancer._"),
    ]


def build_knowledge_organizer_note(user_text: str, note_type: str | None = None) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    ntype = note_type or classify_note_type(user_text)
    if ntype not in NOTE_TYPES:
        ntype = "idea"
    subject = _extract_subject(user_text)
    destination = resolve_suggested_destination(user_text)
    title = _note_title(ntype, subject, created_at)
    tags = ["coco", "study", ntype, subject.lower().replace(" ", "-")]
    sections = _sections_for_type(ntype, user_text.strip(), subject)

    lines = [
        f"# {title}",
        "",
        "## Métadonnées",
        "",
        f"- **Type:** {ntype}",
        f"- **Date:** {created_at}",
        f"- **Sujet:** {subject}",
        f"- **Destination suggérée:** {destination}",
        f"- **Tags:** {' '.join('#' + t for t in tags)}",
        f"- **Source:** COCO Study/Career Knowledge Organizer",
        "",
    ]
    for heading, body in sections:
        lines.extend([f"## {heading}", "", body, ""])
    lines.extend(
        [
            "## Destination",
            "",
            f"Cette note est préparée pour **{destination}**. "
            "L'enregistrement final se fait sur votre appareil via le bouton d'envoi.",
            "",
        ]
    )
    return {
        "title": title,
        "markdown": "\n".join(lines),
        "note_type": ntype,
        "tags": tags,
        "subject": subject,
        "suggested_destination": destination,
        "sections": [h for h, _ in sections],
    }


def build_knowledge_organizer_context() -> str:
    return (
        f"KNOWLEDGE_ORGANIZER_MARKER: {KNOWLEDGE_ORGANIZER_MARKER}\n\n"
        "COCO Study/Career Knowledge Organizer:\n"
        "- COCO can draft structured Markdown notes for Obsidian and AFFiNE (Second Brain).\n"
        "- Note types: course, revision card, project, progress tracking, career/orientation, idea capture.\n"
        "- Each note includes: title, metadata, tags, sections, and suggested destination.\n"
        "- In URI handoff mode, COCO prepares a local handoff but CANNOT confirm final vault persistence.\n"
        "- Say you prepared a Markdown note and offer Envoyer vers Obsidian / AFFiNE / Copier la note.\n"
        "- Forbidden when export is enabled: « je ne peux pas interagir avec Obsidian », "
        "« I cannot do anything with Obsidian », « Obsidian indisponible ».\n"
        "- Never claim « note écrite dans le vault » unless local REST API confirmed success.\n"
        "- Examples: « Range ce cours dans Obsidian », « Fais-moi une fiche de révision en maths », "
        "« Mets cette idée dans AFFiNE », « Note ma progression en anglais », « Prépare une note carrière ».\n"
    )


__all__ = [
    "KNOWLEDGE_ORGANIZER_MARKER",
    "DENIAL_PHRASES",
    "NOTE_TYPES",
    "build_knowledge_organizer_context",
    "build_knowledge_organizer_note",
    "classify_note_type",
    "detect_knowledge_organizer_intent",
    "resolve_suggested_destination",
]
