import pytest
from app.mempalace import (
    add_memory, load_memories, update_reuse_score, set_status,
    search_memory, has_answer, compress,
)


def test_add_and_load():
    e = add_memory("openchawn est local-first", type="rule", importance_score=0.9)
    mems = load_memories()
    assert len(mems) == 1
    assert mems[0].id == e.id
    assert mems[0].type == "rule"


@pytest.mark.parametrize("mtype", ["strategy", "rule", "failure", "insight"])
def test_required_memory_types(mtype):
    e = add_memory("contenu de test suffisamment long", type=mtype)
    assert e.type == mtype


def test_update_reuse_score():
    e = add_memory("contenu initial")
    updated = update_reuse_score(e.id, increment=2.5)
    assert updated.reuse_score == 2.5
    assert updated.last_used_at is not None


def test_set_status_archived():
    e = add_memory("à archiver")
    set_status(e.id, "archived")
    assert load_memories()[0].status == "archived"


def test_search_finds_relevant():
    add_memory("kimi est un provider premium openchawn",
               type="fact", importance_score=0.9)
    add_memory("weetao est un projet distinct", type="fact", project="weetao")
    hits = search_memory("kimi provider", project="openchawn", touch=False)
    assert hits and "kimi" in hits[0].entry.content


def test_search_project_filter():
    add_memory("entry openchawn", project="openchawn")
    add_memory("entry weetao", project="weetao")
    hits = search_memory("entry", project="openchawn",
                         touch=False, min_relevance=0.0)
    assert all(h.entry.project == "openchawn" for h in hits)


def test_search_touch_increments_reuse():
    e = add_memory("touch me please", project="openchawn")
    search_memory("touch please", project="openchawn", touch=True)
    reloaded = next(m for m in load_memories() if m.id == e.id)
    assert reloaded.reuse_score >= 1.0


def test_has_answer_true_false():
    add_memory("la capitale de la France est Paris",
               type="fact", importance_score=0.8)
    assert has_answer("capitale France")
    assert not has_answer("boson de Higgs cosmologie quantique")


def test_compress_dedup_collapses():
    for _ in range(4):
        add_memory(
            "règle identique pour le test de déduplication mempalace",
            type="rule", importance_score=0.9,
        )
    report = compress(project="openchawn", dedup_threshold=0.8)
    assert report.dedup_archived >= 3
    active = [m for m in load_memories() if m.status == "active"]
    assert len(active) == 1


def test_compress_preserves_distinct():
    add_memory("règle A: providers premium", type="rule", importance_score=0.9)
    add_memory("règle B: compression mémoire", type="rule", importance_score=0.9)
    report = compress(project="openchawn", dedup_threshold=0.85)
    assert report.dedup_archived == 0
    assert sum(1 for m in load_memories() if m.status == "active") == 2
