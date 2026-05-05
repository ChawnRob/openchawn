from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from email_env import EmailEnv
from world_model import WorldModel
from memory import VectorMemory
from asi_evolve import ASIEvolve


@dataclass
class ActionSimulation:
    action_id: int
    action_name: str
    predicted_next_state: np.ndarray
    score: float


class Orchestrator:
    def __init__(self, seed: int = 42) -> None:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

        self.env = EmailEnv(seed=seed)
        self.world_model = WorldModel(self.env.state_dim, self.env.action_dim, hidden_dim=96)
        self.memory = VectorMemory(dim=self.env.state_dim)
        self.replay = deque(maxlen=2000)
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(self.world_model.parameters(), lr=1e-3)

        self.asi = ASIEvolve(self.world_model, self.env, base_lr=1e-3)
        self.asi.bind_optimizer(self.optimizer)

    def collect_experience(self, steps: int = 120, max_steps: int = 120) -> None:
        state, _ = self.env.reset()
        steps_to_run = min(steps, max_steps)
        for _ in range(steps_to_run):
            action = random.randint(0, self.env.action_dim - 1)
            next_state, reward, _, _ = self.env.step(action)
            self.memory.add(state, action, next_state, reward)
            self.replay.append((state, action, next_state, reward))
            state = next_state

    def train_world_model(self, batch_size: int = 32, train_steps: int = 20, max_steps: int = 20) -> float | None:
        if len(self.replay) < batch_size:
            return None

        self.world_model.train()
        losses: list[float] = []
        for _ in range(min(train_steps, max_steps)):
            batch = random.sample(self.replay, batch_size)
            states = torch.tensor(np.array([b[0] for b in batch]), dtype=torch.float32)
            actions = torch.tensor([b[1] for b in batch], dtype=torch.long)
            next_states = torch.tensor(np.array([b[2] for b in batch]), dtype=torch.float32)

            pred = self.world_model(states, actions)
            loss = self.criterion(pred, next_states)

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            losses.append(float(loss.item()))

        return float(np.mean(losses)) if losses else None

    def _estimate_action_score(self, state: np.ndarray, action: int, predicted_next: np.ndarray) -> float:
        immediate = self.env.estimate_reward(state, action)
        # Add memory-informed adjustment from similar past rewards.
        similar = self.memory.retrieve_with_reward(state, k=5)
        bonus = float(np.mean([exp.reward for exp in similar])) if similar else 0.0
        future = self.env.estimate_reward(predicted_next, action) * 0.35
        return immediate + 0.25 * bonus + future

    def simulate_actions(self, state: np.ndarray) -> list[ActionSimulation]:
        state_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
        sims: list[ActionSimulation] = []
        for action in range(self.env.action_dim):
            action_t = torch.tensor([action], dtype=torch.long)
            pred_next = self.world_model.predict_next_state(state_t, action_t).squeeze(0).numpy()
            score = self._estimate_action_score(state, action, pred_next)
            sims.append(
                ActionSimulation(
                    action_id=action,
                    action_name=self.env.ACTIONS[action],
                    predicted_next_state=pred_next,
                    score=float(score),
                )
            )
        sims.sort(key=lambda x: x.score, reverse=True)
        return sims

    def run_epoch(
        self,
        epoch: int,
        collect_steps: int = 120,
        train_steps: int = 20,
        max_steps: int = 200,
    ) -> dict:
        # 1) collect_experience()
        self.collect_experience(steps=collect_steps, max_steps=max_steps)

        # 2) train_world_model()
        avg_loss = self.train_world_model(train_steps=train_steps, max_steps=max_steps)

        # 3) simulate_actions() on a test state
        test_state, _ = self.env.reset()
        simulations = self.simulate_actions(test_state)
        best = simulations[0]

        # 4) evolve()
        self.asi.evolve(avg_loss)

        lr = float(self.optimizer.param_groups[0]["lr"])
        print(f"[epoch {epoch}] avg_loss={avg_loss} | memory_size={self.memory.size()} | lr={lr:.6f}")
        print(
            f"Email urgent + client important -> action choisie : "
            f"{best.action_name} (score {best.score:.2f})"
        )

        return {
            "epoch": epoch,
            "avg_loss": avg_loss,
            "memory_size": self.memory.size(),
            "lr": lr,
            "best_action_id": best.action_id,
            "best_action_name": best.action_name,
            "best_score": best.score,
        }
