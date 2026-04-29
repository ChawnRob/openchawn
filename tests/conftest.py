import pytest
from pathlib import Path
from app.mempalace import store as mempalace_store


@pytest.fixture(autouse=True)
def isolate_mempalace(tmp_path, monkeypatch):
    """Chaque test tourne sur un fichier MemPalace vierge."""
    p: Path = tmp_path / "memories.json"
    monkeypatch.setattr(mempalace_store, "_PATH", p)
    yield p
