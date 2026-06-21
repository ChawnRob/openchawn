"""P1.1 — strategic / market analyst web-search intent."""

from __future__ import annotations

import pytest

from app.tools.web_search_intent import detect_web_search_intent, extract_web_search_query


@pytest.mark.parametrize(
    "message",
    [
        "Analyse Fluxorca comme un consultant McKinsey",
        "Analyse le positionnement de Fluxorca",
        "Quels sont les concurrents de Fluxorca ?",
        "Fais une analyse marché de Fluxorca",
        "Analyse cette entreprise : Fluxorca",
        "Donne-moi les risques et opportunités de Fluxorca",
        "Analyse le business model de Tavily",
        "Compare Fluxorca avec Zapier",
        (
            "Analyse Fluxorca comme un consultant McKinsey. "
            "Quel est le positionnement produit, les concurrents probables, "
            "les risques et les opportunités ?"
        ),
        "Analyse le positionnement produit de Tavily",
    ],
)
def test_analyst_intent_positive(message: str):
    assert detect_web_search_intent(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "Analyse mon idée de produit",
        "Analyse cette image",
        "Analyse notre conversation",
        "Analyse mon projet COCO",
        "Range ce cours dans Obsidian",
        "Ouvre AFFiNE",
        "Fais-moi une fiche de révision en maths",
        "Analyse les risques et opportunités",
        "Analyse le positionnement produit",
    ],
)
def test_analyst_intent_negative(message: str):
    assert detect_web_search_intent(message) is False


def test_mckinsey_fluxorca_query_extraction():
    msg = (
        "Analyse Fluxorca comme un consultant McKinsey. "
        "Quel est le positionnement produit, les concurrents probables, "
        "les risques et les opportunités ?"
    )
    assert detect_web_search_intent(msg) is True
    q = extract_web_search_query(msg)
    assert "Fluxorca" in q
    assert "positioning" in q.lower() or "market" in q.lower()
