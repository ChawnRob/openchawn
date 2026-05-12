import pytest
import app.orchestrator as orch_mod
import app.router as router_mod
from app.mempalace import add_memory
from app.orchestrator import handle
from app.providers.base import BaseProvider


class _FakePM:

    def __init__(self, resolution: list[str]) -> None:
        self.resolution = resolution

    def resolution_order(self) -> list[str]:
        return list(self.resolution)


class _OK(BaseProvider):
    def __init__(self, tag):
        self.tag = tag

    def is_available(self):
        return True

    def generate(self, prompt, user_id="", system_prompt=""):
        return f"[{self.tag}] réponse complète et détaillée sur {prompt[:40]} avec plus de 30 chars."


class _Down(BaseProvider):
    def is_available(self):
        return False

    def generate(self, *a, **kw):
        return "[ERREUR] down"


@pytest.fixture
def fake_reg(monkeypatch):
    monkeypatch.setattr(
        "app.provider_manager.get_provider_manager",
        lambda: _FakePM(["kimi", "deepseek", "openrouter", "openai"]),
    )

    reg = {
        "kimi": _OK("kimi"),
        "deepseek": _Down(),
        "openrouter": _OK("openrouter"),
        "openai": _OK("openai"),
    }
    monkeypatch.setattr(router_mod, "_REGISTRY", reg)
    return reg


def test_handle_memory_read():
    add_memory(
        "ASI-Evolve = cerveau décisionnel local-first",
        type="rule",
        importance_score=0.9,
    )
    res = handle("que dit la mémoire sur le cerveau décisionnel")
    assert res["action"] == "MEMORY_READ"
    assert isinstance(res["output"], list) and res["output"]
    assert "provider" not in res or res["provider"] is None


def test_handle_memory_write_falls_back_to_model(fake_reg):
    res = handle("retiens que le quicksort est en O(n log n) moyenne")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
    assert res["output"].startswith("[kimi]")


def test_handle_model_call_premium_kimi(fake_reg, monkeypatch):
    monkeypatch.setattr(
        "app.provider_manager.get_provider_manager",
        lambda: _FakePM(["kimi", "deepseek", "openrouter", "openai"]),
    )
    res = handle("code-moi une fonction Rust de tri rapide")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
    assert res["output"].startswith("[kimi]")


def test_handle_model_call_fallback_skips_down(fake_reg, monkeypatch):
    monkeypatch.setattr(
        "app.provider_manager.get_provider_manager",
        lambda: _FakePM(["deepseek", "openrouter", "kimi", "openai"]),
    )
    reg = router_mod._REGISTRY
    reg["deepseek"] = _Down()
    reg["openrouter"] = _OK("openrouter")
    reg["kimi"] = _OK("kimi")
    res = handle("raconte moi une chose simple")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "openrouter"


def test_handle_model_call_all_down(fake_reg):
    reg = router_mod._REGISTRY
    for k in reg:
        reg[k] = _Down()
    res = handle("question quelconque")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] is None
    assert (
        "Aucun modèle" in res["output"]
        or "No model replied yet" in res["output"]
        or "[ERREUR]" in res["output"]
    )


def test_handle_memory_compress_executes_real():
    for _ in range(3):
        add_memory(
            "règle identique pour test compress via orchestrator",
            type="rule",
            importance_score=0.9,
        )
    res = handle("consolide la mémoire")
    assert res["action"] == "MEMORY_COMPRESS"
    assert res["output"]["status"] == "done"
    assert res["output"]["report"]["dedup_archived"] >= 2


def test_handle_system_improvement_falls_back_to_model(fake_reg):
    res = handle("refactor ASI-Evolve en profondeur")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
    assert res["output"].startswith("[kimi]")


def test_handle_model_call_triggers_learn(fake_reg):
    res = handle("code-moi un fizzbuzz en Python")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
