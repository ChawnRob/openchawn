import json
from datetime import datetime
from pathlib import Path

MEMORY_FILE = Path("memory/openchawn_memory.jsonl")

def save_memory(role: str, content: str):
    MEMORY_FILE.parent.mkdir(exist_ok=True)

    item = {
        "time": datetime.utcnow().isoformat(),
        "role": role,
        "content": content
    }

    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_recent_memories(limit: int = 5):
    if not MEMORY_FILE.exists():
        return []

    lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    memories = []

    for line in lines[-limit:]:
        try:
            memories.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    return memories
