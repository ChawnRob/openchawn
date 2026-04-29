import json
import uuid
from pathlib import Path
from datetime import datetime

STORE_FILE = Path("memory/memory_store.json")


def _load_store() -> list[dict]:
    """Charge le store JSON. Si vide ou cassé, retourne une liste vide."""
    if not STORE_FILE.exists():
        return []
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, ValueError):
        return []


def _save_store(nodes: list[dict]):
    """Écrit le store JSON sur disque."""
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(
        json.dumps(nodes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _default_node(data: dict) -> dict:
    """Applique les valeurs par défaut aux champs manquants."""
    return {
        "id": data.get("id", f"mem_{uuid.uuid4().hex[:8]}"),
        "content": data.get("content", ""),
        "tags": data.get("tags", []),
        "links": data.get("links", []),
        "emotion": data.get("emotion", "neutral"),
        "importance": data.get("importance", 0.5),
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
        "source": data.get("source", "manual"),
    }


def add_node(content: str, tags: list[str] = None, emotion: str = "neutral",
             importance: float = 0.5, source: str = "manual") -> dict:
    """Ajoute un node au store et le retourne."""
    nodes = _load_store()
    node = _default_node({
        "content": content,
        "tags": tags or [],
        "emotion": emotion,
        "importance": importance,
        "source": source,
    })
    nodes.append(node)
    _save_store(nodes)
    return node


def list_nodes() -> list[dict]:
    """Retourne tous les nodes."""
    return _load_store()


def search_nodes(query: str) -> list[dict]:
    """Recherche simple : texte dans content ou tags."""
    q = query.lower()
    results = []
    for node in _load_store():
         content = node.get("content", "")

         if not isinstance(content, str):
             content =str(content)

         if q in content.lower():
             results.append(node)

         elif any(q in str(tag).lower() for tag in node.get("tags", [])):
             results.append(node)

    return results


def link_nodes(id_from: str, id_to: str) -> dict:
    """Relie deux nodes. Retourne le node source modifié ou une erreur."""
    nodes = _load_store()
    node_map = {n["id"]: n for n in nodes}

    if id_from not in node_map:
        return {"error": f"Node {id_from} introuvable"}
    if id_to not in node_map:
        return {"error": f"Node {id_to} introuvable"}

    if id_to not in node_map[id_from]["links"]:
        node_map[id_from]["links"].append(id_to)

    _save_store(nodes)
    return node_map[id_from]

