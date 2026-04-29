import json
import os
from datetime import datetime

QEI_LOG_DIR = os.getenv("OPENCHAWN_QEI_DIR", "./data/qei")


class QEILogger:
    """Log local des scores QEI. Un fichier JSON par jour."""

    def __init__(self, log_dir: str = QEI_LOG_DIR):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def _today_file(self) -> str:
        return os.path.join(self.log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.json")

    def log(self, user_id: str, prompt: str, provider: str, scores: dict):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "prompt_preview": prompt[:100],
            "provider": provider,
            "scores": scores,
        }

        path = self._today_file()
        entries = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)

        entries.append(entry)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def get_today(self) -> list[dict]:
        path = self._today_file()
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_average_today(self) -> dict:
        entries = self.get_today()
        if not entries:
            return {"count": 0, "avg_total": 0.0}
        totals = [e["scores"]["total"] for e in entries]
        return {
            "count": len(totals),
            "avg_total": round(sum(totals) / len(totals), 2),
        }
