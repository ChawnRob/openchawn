from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Literal, Optional
import uuid

# Types imposés : cœur cognitif OpenChawn
MemoryType = Literal[
    "strategy",    # plan d'action, orientation système
    "rule",        # règle ou contrainte projet
    "failure",     # erreur passée à ne pas répéter
    "insight",     # apprentissage, pattern remarqué
    "fact",        # donnée neutre réutilisable
    "decision",    # choix validé par l'utilisateur
    "summary",     # compression d'un bloc plus large
]
MemoryStatus = Literal["active", "archived", "deprecated"]


@dataclass
class MemoryEntry:
    content: str
    type: MemoryType = "fact"
    project: str = "openchawn"
    summary: str = ""
    importance_score: float = 0.5
    reuse_score: float = 0.0
    confidence: float = 0.8
    source: str = "user"
    status: MemoryStatus = "active"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_used_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(**d)
