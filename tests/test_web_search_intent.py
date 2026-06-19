"""Web search intent detection — backend parity tests."""

from __future__ import annotations

import pytest

from app.tools.web_search_intent import detect_web_search_intent, extract_web_search_query


@pytest.mark.parametrize(
    "message",
    [
        "Recherche les dernières actualités IA",
        "Va sur fluxorca.com",
        "Que fait fluxorca.com ?",
        "Trouve des infos sur AFFiNE",
        "Va sur fluxorca.com et résume ce que tu trouves",
        "search latest AI news",
        "visit https://example.org",
        "what does openchawn.io do",
    ],
)
def test_web_search_intent_positive(message: str):
    assert detect_web_search_intent(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "Range ce cours dans Obsidian",
        "Ouvre AFFiNE",
        "open affine second brain",
        "Note ça dans Obsidian",
        "Bonjour comment ça va ?",
        "Fais-moi une fiche de révision en maths",
    ],
)
def test_web_search_intent_negative(message: str):
    assert detect_web_search_intent(message) is False


def test_extract_web_search_query_url():
    assert extract_web_search_query("Va sur fluxorca.com") == "what is fluxorca.com website"
    assert extract_web_search_query("visit https://example.org/page") == "https://example.org/page"


def test_extract_web_search_query_strips_prefix():
    q = extract_web_search_query("Recherche les dernières actualités IA")
    assert "actualit" in q.lower()
    assert not q.lower().startswith("recherche")
