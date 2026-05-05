from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class EmailSpec:
    urgency: float
    sentiment: float
    client_importance: float
    risk: float
    delay: float
    confidence: float


class EmailEnv:
    """Email decision environment with discrete actions."""

    ACTIONS = {
        0: "repondre maintenant",
        1: "ignorer",
        2: "demander validation",
        3: "relancer plus tard",
    }

    def __init__(self, seed: int = 42) -> None:
        self.state_dim = 6
        self.action_dim = 4
        self.rng = np.random.default_rng(seed)
        self.state: np.ndarray | None = None

    def _sample_email(self) -> EmailSpec:
        return EmailSpec(
            urgency=float(self.rng.beta(2.2, 2.8)),
            sentiment=float(self.rng.uniform(-1.0, 1.0)),
            client_importance=float(self.rng.beta(2.5, 2.2)),
            risk=float(self.rng.beta(2.0, 3.2)),
            delay=float(self.rng.beta(2.1, 2.8)),
            confidence=float(self.rng.beta(2.8, 2.0)),
        )

    def reset(self) -> tuple[np.ndarray, dict]:
        e = self._sample_email()
        self.state = np.array(
            [e.urgency, e.sentiment, e.client_importance, e.risk, e.delay, e.confidence],
            dtype=np.float32,
        )
        return self.state.copy(), {}

    def estimate_reward(self, state: np.ndarray, action: int) -> float:
        urgency, sentiment, importance, risk, delay, confidence = [float(v) for v in state]
        reward = 0.0

        if action == 0:  # repondre maintenant
            reward += 0.55 * urgency + 0.35 * importance + 0.20 * confidence
            reward -= 0.25 * risk
            reward += 0.10 if sentiment < -0.2 else 0.0
        elif action == 1:  # ignorer
            reward -= 0.55 * urgency + 0.45 * importance + 0.20 * risk
            reward += 0.10 if urgency < 0.2 and importance < 0.2 else -0.15
        elif action == 2:  # demander validation
            reward += 0.50 * risk + 0.20 * importance
            reward -= 0.20 * urgency + 0.10 * delay
            reward += 0.05 if confidence < 0.5 else 0.0
        elif action == 3:  # relancer plus tard
            reward += 0.20 * importance
            reward += 0.18 if urgency < 0.5 else -0.28
            reward -= 0.22 * delay + 0.12 * risk
        else:
            reward -= 1.0

        return float(reward)

    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]:
        if self.state is None:
            raise RuntimeError("Environment must be reset() before step().")

        next_state = self.state.copy()

        if action == 0:
            next_state[0] *= 0.45
            next_state[3] *= 0.70
            next_state[5] = min(1.0, next_state[5] + 0.10)
        elif action == 1:
            next_state[0] = min(1.0, next_state[0] + 0.22)
            next_state[3] = min(1.0, next_state[3] + 0.18)
            next_state[5] = max(0.0, next_state[5] - 0.12)
        elif action == 2:
            next_state[3] *= 0.55
            next_state[5] = min(1.0, next_state[5] + 0.20)
            next_state[4] = min(1.0, next_state[4] + 0.06)
        elif action == 3:
            next_state[0] = min(1.0, next_state[0] + 0.10)
            next_state[4] = min(1.0, next_state[4] + 0.12)
            next_state[1] = np.clip(next_state[1] - 0.05, -1.0, 1.0)

        noise = self.rng.normal(0.0, 0.02, size=self.state_dim)
        next_state = np.clip(next_state + noise, [-0.0, -1.0, 0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]).astype(np.float32)

        reward = self.estimate_reward(self.state, action)
        self.state = next_state
        done = False
        return next_state.copy(), reward, done, {}
