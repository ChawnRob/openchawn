"""P1.3 — public discovery web-search intent (profiles, repos, tech, news)."""

from __future__ import annotations

import pytest

from app.tools.web_search_intent import (
    detect_web_search_intent,
    extract_web_search_query,
    is_protected_web_request,
)


@pytest.mark.parametrize(
    "message",
    [
        "Voir le profil public de Robert Lumet sur les réseaux sociaux",
        "Recherche Robert Lumet LinkedIn",
        "Trouve les profils publics de Robert Lumet sur LinkedIn, GitHub et X",
        "Quelle IA utilise Mercedes aujourd'hui ?",
        "Check la repo GitHub ChawnRob/openchawn",
        "Trouve le site officiel de Fluxorca",
        "Trouve le GitHub de OpenChawn",
        "Qui est le fondateur de Tavily ?",
        "Actualités Mercedes IA 2026",
        "Quels modèles IA utilise Mercedes ?",
    ],
)
def test_discovery_intent_positive(message: str):
    assert detect_web_search_intent(message) is True
    assert is_protected_web_request(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "Connecte-toi à mon LinkedIn",
        "Lis mes messages Instagram",
        "Accède à mon compte Facebook",
        "Récupère les emails privés de Robert Lumet",
        "Scrape un profil privé",
        "Ouvre mon compte Facebook",
    ],
)
def test_discovery_intent_protected(message: str):
    assert is_protected_web_request(message) is True
    assert detect_web_search_intent(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "Ouvre AFFiNE",
        "Sync Obsidian",
        "Analyse cette image",
        "Range ce cours dans Obsidian",
        "Analyse mon projet COCO",
        "Notre conversation",
    ],
)
def test_discovery_intent_internal_excluded(message: str):
    assert detect_web_search_intent(message) is False


def test_linkedin_query_extraction():
    q = extract_web_search_query("Recherche Robert Lumet LinkedIn")
    assert "Robert" in q
    assert "linkedin" in q.lower()


def test_github_repo_query_extraction():
    q = extract_web_search_query("Check la repo GitHub ChawnRob/openchawn")
    assert "ChawnRob" in q or "openchawn" in q.lower()


def test_official_site_query_extraction():
    q = extract_web_search_query("Trouve le site officiel de Fluxorca")
    assert "Fluxorca" in q
    assert "official" in q.lower() or "site" in q.lower()
