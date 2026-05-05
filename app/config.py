import os
from dotenv import load_dotenv

# ── Charge le .env AVANT tout os.getenv() ─────────────────
load_dotenv()

# ── Mode production ───────────────────────────────────────
ENV = os.getenv("OPENCHAWN_ENV", "development")  # development | production
IS_PROD = ENV == "production"

# ── Secret key (OBLIGATOIRE en production) ────────────────
SECRET_KEY = os.getenv("OPENCHAWN_SECRET_KEY", "dev-secret-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("OPENCHAWN_JWT_HOURS", "24"))

# ── CORS — origines autorisées ────────────────────────────
ALLOWED_ORIGINS = os.getenv(
    "OPENCHAWN_CORS_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

# ── Rate limiting ─────────────────────────────────────────
RATE_LIMIT_CHAT = int(os.getenv("OPENCHAWN_RATE_CHAT", "30"))
RATE_LIMIT_AUTH = int(os.getenv("OPENCHAWN_RATE_AUTH", "10"))
MAX_MESSAGE_LENGTH = int(os.getenv("OPENCHAWN_MAX_MSG_LEN", "4000"))

# ── Profil actif ─────────────────────────────────────────
PROFILE = os.getenv("OPENCHAWN_PROFILE", "default")

# ── Template langue ───────────────────────────────────────
LANG_INSTRUCTION = "Réponds UNIQUEMENT en {lang_name}. Ne mélange JAMAIS les langues dans ta réponse."

# ── Provider principal ────────────────────────────────────
# "auto" = sélection par priorité | ou forcer un nom
PROVIDER = os.getenv("OPENCHAWN_PROVIDER", "auto")

# ── LLM gateway (MODEL_PROVIDER=openrouter → OpenRouter si clé présente) ──
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "").strip().lower()

# ── Ollama config (local) ────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")

# ── MiniMax API ───────────────────────────────────────────
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")

# ── Mistral API (cloud) ──────────────────────────────────
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

# ── OpenAI API (dernier recours) ─────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ── Fallback (legacy, ignoré — fallback toujours actif) ──
FALLBACK_ENABLED = True

# ── Guest mode ───────────────────────────────────────────
GUEST_DAILY_LIMIT = int(os.getenv("OPENCHAWN_GUEST_DAILY_LIMIT", "5"))

# ── Database ──────────────────────────────────────────────
DATABASE_PATH = os.getenv("OPENCHAWN_DB_PATH", "./data/openchawn.db")
