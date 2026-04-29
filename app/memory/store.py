import json
import os
from datetime import datetime

MEMORY_DIR = os.getenv("OPENCHAWN_MEMORY_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "memory"))


class MemoryStore:
    """Stockage local des conversations par user_id. Fichiers JSON, zéro dépendance."""

    def __init__(self, memory_dir: str = MEMORY_DIR):
        self.memory_dir = memory_dir
        os.makedirs(self.memory_dir, exist_ok=True)

    def _user_file(self, user_id: str) -> str:
        safe_id = user_id.replace("/", "_").replace("..", "_")
        return os.path.join(self.memory_dir, f"{safe_id}.json")

    def load(self, user_id: str) -> list[dict]:
        path = self._user_file(user_id)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_turn(self, user_id: str, role: str, content: str):
        history = self.load(user_id)
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        with open(self._user_file(user_id), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_recent(self, user_id: str, limit: int = 10) -> list[dict]:
        history = self.load(user_id)
        return history[-limit:]

    def clear(self, user_id: str):
        path = self._user_file(user_id)
        if os.path.exists(path):
            os.remove(path)
