from app.memory.store import MemoryStore


class ContextBuilder:
    """Construit le prompt enrichi avec l'historique de conversation."""

    def __init__(self, store: MemoryStore, max_turns: int = 10):
        self.store = store
        self.max_turns = max_turns

    def build_prompt(self, user_id: str, new_message: str) -> str:
        history = self.store.get_recent(user_id, limit=self.max_turns)

        if not history:
            return new_message

        context_parts = []
        for turn in history:
            role = "User" if turn["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {turn['content']}")

        context = "\n".join(context_parts)
        return f"""Conversation précédente :
{context}

User: {new_message}
Assistant:"""
