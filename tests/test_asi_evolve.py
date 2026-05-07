import pytest
from app.mempalace import add_memory
from app.asi_evolve import decide, analyze_human


def test_decision_system_improvement():
    out = decide("refactor ASI-Evolve pour ajouter un scheduler async")
    assert out["decision"] == "SYSTEM_IMPROVEMENT"
    assert out["system_note"]
    assert out["model_routing"] is None


def test_decision_memory_write_rule():
    out = decide("retiens cette règle: zéro dépendance cloud")
    assert out["decision"] == "MEMORY_WRITE"
    assert out["memory_update"]["type"] == "rule"


def test_decision_memory_compress_explicit():
    out = decide("consolide la mémoire du projet openchawn")
    assert out["decision"] == "MEMORY_COMPRESS"
    assert out["memory_query"]["strategy"] == "group_by_type_and_summarize"


def test_decision_memory_read_hits():
    add_memory(
        "ASI-Evolve est le cerveau décisionnel au-dessus du router OpenChawn.",
        type="rule", importance_score=0.95, confidence=0.95,
    )
    out = decide("quel est le rôle d'ASI-Evolve dans OpenChawn")
    assert out["decision"] == "MEMORY_READ"
    assert out["model_routing"] is None
    assert out["memory_query"]["hits"]


def test_decision_model_call_code_premium():
    out = decide("code-moi un quicksort en Rust avec memoization")
    assert out["decision"] == "MODEL_CALL_NEEDED"
    r = out["model_routing"]
    assert r["tier"] == "premium"
    assert r["chain"][0] == "kimi"
    assert r["temperature"] == 0.2


def test_decision_model_call_local():
    out = decide("fais ça en offline sans internet")
    assert out["decision"] == "MODEL_CALL_NEEDED"
    assert out["model_routing"]["tier"] == "local"
    assert out["model_routing"]["chain"] == ["deepseek"]


def test_decision_model_call_economic_default():
    out = decide("raconte moi un fait amusant")
    assert out["decision"] == "MODEL_CALL_NEEDED"
    assert out["model_routing"]["tier"] == "economic"
    assert out["model_routing"]["chain"][0] == "deepseek"


def test_human_layer_complete_schema():
    out = decide("bonjour")
    hl = out["human_layer"]
    assert set(hl.keys()) == {
        "detected_emotion", "intent_hidden", "confidence_level",
        "recommended_nudge", "nudge_type",
    }
    assert hl["nudge_type"] in {
        "risk_reduction", "social_proof", "action", "clarity", "momentum"
    }


def test_human_layer_frustrated_triggers_risk_reduction():
    out = decide("putain ça marche pas bordel!!!")
    assert out["human_layer"]["detected_emotion"] == "frustrated"
    assert out["human_layer"]["nudge_type"] == "risk_reduction"


def test_analyze_human_neutral_default():
    hl = analyze_human("ok.")
    assert hl["detected_emotion"] == "neutral"
    assert hl["nudge_type"] == "action"
