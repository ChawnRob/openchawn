from app.asi_evolve.learn import learn_from_exchange


def test_learn_creates_entry_premium():
    e = learn_from_exchange(
        "question de test",
        "réponse assez longue pour passer le seuil minimum de trente caractères.",
        provider="kimi", tier="premium",
    )
    assert e is not None
    assert e.type == "fact"
    assert e.importance_score == 0.70
    assert e.source == "auto_learn:kimi"


def test_learn_skips_short_response():
    assert learn_from_exchange("q", "ok", provider="kimi") is None


def test_learn_skips_error_response():
    assert learn_from_exchange("q", "[ERREUR] timeout", provider="kimi") is None


def test_learn_dedup_second_call_skipped():
    prompt = "quelle est la capitale du Japon ?"
    resp = "La capitale du Japon est Tokyo, centre politique et économique du pays."
    first = learn_from_exchange(prompt, resp, provider="kimi", tier="premium")
    assert first is not None
    second = learn_from_exchange(prompt, resp, provider="kimi", tier="premium")
    assert second is None


def test_learn_redacts_secrets():
    leaky = (
        "voici la clé sk-abcd1234efgh5678ijkl9012mnop "
        "et Bearer abcdef1234567890abcdef1234xyz."
    )
    e = learn_from_exchange("dump config", leaky, provider="openai", tier="premium")
    assert e is not None
    assert "sk-abcd" not in e.content
    assert "Bearer abcdef" not in e.content
    assert "[REDACTED]" in e.content


def test_learn_tier_importance_mapping():
    e1 = learn_from_exchange("q premium", "x" * 60, provider="kimi",    tier="premium")
    e2 = learn_from_exchange("q eco",     "y" * 60, provider="minimax", tier="economic")
    e3 = learn_from_exchange("q local",   "z" * 60, provider="ollama",  tier="local")
    assert e1.importance_score == 0.70
    assert e2.importance_score == 0.55
    assert e3.importance_score == 0.45
