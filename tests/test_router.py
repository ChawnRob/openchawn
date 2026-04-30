import pytest
import app.router as router_mod
from app.mempalace import add_memory
from app.router import handle
<<<<<<< HEAD


class _OK:
    def __init__(self, tag):
        self.tag = tag

    def is_available(self):
        return True

    def generate(self, prompt, user_id="", system_prompt=""):
        return f"[{self.tag}] réponse complète et détaillée: {prompt[:40]}"


class _Down:
    def is_available(self):
        return False

=======
from app.providers.base import BaseProvider


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
>>>>>>> 3b574f3bedca39618e1e690171b52968536d0b88
    def generate(self, *a, **kw):
        return "[ERREUR] down"


@pytest.fixture
def fake_reg(monkeypatch):
    reg = {
        "kimi":    _OK("kimi"),
<<<<<<< HEAD
=======
        "minimax": _Down(),
>>>>>>> 3b574f3bedca39618e1e690171b52968536d0b88
        "mistral": _OK("mistral"),
        "ollama":  _OK("ollama"),
        "openai":  _OK("openai"),
    }
    monkeypatch.setattr(router_mod, "_REGISTRY", reg)
    return reg


<<<<<<< HEAD
@pytest.fixture
def empty_reg(monkeypatch):
    monkeypatch.setattr(router_mod, "_REGISTRY", {})
    return {}


def test_handle_memory_compress():
    res = handle("consolide la mémoire")
    assert res["action"] == "MEMORY_COMPRESS"
    assert res["output"]["status"] == "done"
    assert "report" in res["output"]


def test_handle_memory_compress_alt_keyword():
    res = handle("compresse les souvenirs")
    assert res["action"] == "MEMORY_COMPRESS"
    assert res["output"]["status"] == "done"


def test_handle_memory_read_returns_list():
    add_memory("OpenChawn est un système IA local-first",
               type="rule", importance_score=0.9)
    res = handle("retrouve la mémoire OpenChawn")
    assert res["action"] == "MEMORY_READ"
    assert isinstance(res["output"], list)


def test_handle_model_call_first_available(fake_reg):
    res = handle("code-moi un fizzbuzz en Python")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
    assert res["output"].startswith("[kimi]")
    assert res["learned_memory_id"]


def test_handle_model_call_skips_down(fake_reg, monkeypatch):
    fake_reg["kimi"] = _Down()
    res = handle("raconte moi une chose simple")
=======
def test_handle_memory_read():
    add_memory("ASI-Evolve = cerveau décisionnel local-first",
               type="rule", importance_score=0.9)
    res = handle("quel est le cerveau décisionnel")
    assert res["action"] == "MEMORY_READ"
    assert isinstance(res["output"], list) and res["output"]
    assert res["provider"] is None


def test_handle_memory_write_persists():
    res = handle("retiens que le quicksort est en O(n log n) moyenne")
    assert res["action"] == "MEMORY_WRITE"
    assert "stored_id" in res["output"]


def test_handle_model_call_premium_kimi(fake_reg):
    res = handle("code-moi une fonction Rust de tri rapide")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
    assert res["output"].startswith("[kimi]")


def test_handle_model_call_fallback_skips_down(fake_reg):
    res = handle("raconte moi une chose simple")
    # tier=economic → minimax first (down) → mistral OK
>>>>>>> 3b574f3bedca39618e1e690171b52968536d0b88
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "mistral"


<<<<<<< HEAD
def test_handle_system_improvement_when_all_down(monkeypatch):
    reg = {
        "kimi":    _Down(),
        "mistral": _Down(),
        "ollama":  _Down(),
        "openai":  _Down(),
    }
    monkeypatch.setattr(router_mod, "_REGISTRY", reg)
    res = handle("question quelconque sans provider")
    assert res["action"] == "SYSTEM_IMPROVEMENT"
    assert res["output"]["status"] == "stub"


def test_handle_system_improvement_when_empty_registry(empty_reg):
    res = handle("question quelconque")
    assert res["action"] == "SYSTEM_IMPROVEMENT"
    assert res["output"]["status"] == "stub"
=======
def test_handle_model_call_all_down(fake_reg):
    for k in fake_reg:
        fake_reg[k] = _Down()
    res = handle("question quelconque")
    assert res["output"].startswith("[ERREUR]")
    assert res["provider"] is None


def test_handle_memory_compress_executes_real():
    for _ in range(3):
        add_memory("règle identique pour test compress via router",
                   type="rule", importance_score=0.9)
    res = handle("consolide la mémoire")
    assert res["action"] == "MEMORY_COMPRESS"
    assert res["output"]["status"] == "done"
    assert res["output"]["report"]["dedup_archived"] >= 2


def test_handle_system_improvement_stub():
    res = handle("refactor ASI-Evolve en profondeur")
    assert res["action"] == "SYSTEM_IMPROVEMENT"
    assert res["output"]["status"] == "stub"


def test_handle_model_call_triggers_learn(fake_reg):
    res = handle("code-moi un fizzbuzz en Python")
    assert res["action"] == "MODEL_CALL_NEEDED"
    assert res["provider"] == "kimi"
    assert res.get("learned_memory_id")  # auto-learning actif
>>>>>>> 3b574f3bedca39618e1e690171b52968536d0b88
