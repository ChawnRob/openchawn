from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class WorldModel(nn.Module):
    """Predicts next_state from (state, discrete action)."""

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 96) -> None:
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.net = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim),
        )

    def action_to_one_hot(self, actions: torch.Tensor) -> torch.Tensor:
        if actions.dim() > 1:
            actions = actions.squeeze(-1)
        return F.one_hot(actions.long(), num_classes=self.action_dim).float()

    def forward(self, states: torch.Tensor, actions: torch.Tensor) -> torch.Tensor:
        action_one_hot = self.action_to_one_hot(actions)
        model_input = torch.cat([states, action_one_hot], dim=-1)
        return self.net(model_input)

    @torch.no_grad()
    def predict_next_state(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        self.eval()
        return self.forward(state, action)
