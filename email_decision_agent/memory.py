from __future__ import annotations

from dataclasses import dataclass
from typing import List
import numpy as np

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


@dataclass
class Experience:
    state: np.ndarray
    action: int
    next_state: np.ndarray
    reward: float


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32).reshape(1, -1)
    denom = np.linalg.norm(vec, axis=1, keepdims=True) + 1e-12
    return vec / denom


class VectorMemory:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.storage: List[Experience] = []
        self.index = faiss.IndexFlatL2(dim) if faiss is not None else None

    def add(self, state: np.ndarray, action: int, next_state: np.ndarray, reward: float) -> None:
        exp = Experience(
            state=state.astype(np.float32).copy(),
            action=int(action),
            next_state=next_state.astype(np.float32).copy(),
            reward=float(reward),
        )
        self.storage.append(exp)
        if self.index is not None:
            self.index.add(_l2_normalize(exp.state))

    def size(self) -> int:
        return len(self.storage)

    def retrieve_with_reward(self, query_state: np.ndarray, k: int = 5) -> List[Experience]:
        if not self.storage:
            return []

        k = max(1, min(k, len(self.storage)))
        query = _l2_normalize(query_state)

        if self.index is not None:
            _, idx = self.index.search(query, k)
            return [self.storage[i] for i in idx[0]]

        distances = []
        for i, exp in enumerate(self.storage):
            d = np.linalg.norm(query - _l2_normalize(exp.state))
            distances.append((float(d), i))
        distances.sort(key=lambda x: x[0])
        return [self.storage[i] for _, i in distances[:k]]
