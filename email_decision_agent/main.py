from __future__ import annotations

from orchestrator import Orchestrator


def main() -> None:
    print("OpenChawn Email Decision Agent V1")
    print("World Model + Vector Memory + Action Simulation")
    print("-" * 64)

    orch = Orchestrator(seed=42)
    max_epochs = 25
    max_steps = 200

    for epoch in range(1, max_epochs + 1):
        orch.run_epoch(
            epoch=epoch,
            collect_steps=120,
            train_steps=20,
            max_steps=max_steps,
        )

    print("-" * 64)
    print("Training completed without crash.")


if __name__ == "__main__":
    main()
