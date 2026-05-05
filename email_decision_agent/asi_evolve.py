from __future__ import annotations

from collections import deque
import copy
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


class ASIEvolve:
    """Simple LR mutation strategy with bounded evaluation."""

    def __init__(self, model: nn.Module, env, base_lr: float = 1e-3) -> None:
        self.model = model
        self.env = env
        self.best_loss = float("inf")
        self.best_lr = base_lr
        self.history = deque(maxlen=24)
        self.optimizer: optim.Optimizer | None = None

    def bind_optimizer(self, optimizer: optim.Optimizer) -> None:
        self.optimizer = optimizer

    def _propose_lr(self) -> float:
        return float(np.random.uniform(1e-4, 8e-3))

    def _evaluate_lr(self, lr: float, episodes: int = 2, max_steps: int = 30) -> float:
        clone = copy.deepcopy(self.model)
        clone.train()
        optimizer = optim.Adam(clone.parameters(), lr=lr)
        criterion = nn.MSELoss()
        total_loss = 0.0
        updates = 0

        for _ in range(episodes):
            state_np, _ = self.env.reset()
            state = torch.tensor(state_np, dtype=torch.float32).unsqueeze(0)
            for _ in range(max_steps):
                action = np.random.randint(0, self.env.action_dim)
                next_np, _, _, _ = self.env.step(int(action))
                next_state = torch.tensor(next_np, dtype=torch.float32).unsqueeze(0)
                action_t = torch.tensor([action], dtype=torch.long)
                pred = clone(state, action_t)
                loss = criterion(pred, next_state)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += float(loss.item())
                updates += 1
                state = next_state

        return total_loss / max(1, updates)

    def evolve(self, current_loss: float | None) -> None:
        if current_loss is None:
            return
        self.history.append(float(current_loss))
        if len(self.history) < 10:
            return

        # trigger mutation only when training stagnates
        if float(np.std(self.history)) > 0.01:
            return

        candidate_lr = self._propose_lr()
        candidate_loss = self._evaluate_lr(candidate_lr)
        if candidate_loss < self.best_loss:
            self.best_loss = candidate_loss
            self.best_lr = candidate_lr
            if self.optimizer is not None:
                for group in self.optimizer.param_groups:
                    group["lr"] = self.best_lr
            self.history.clear()
