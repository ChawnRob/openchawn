"""
Configuration centrale OpenChawn — une seule source pour variables d’environnement.

- Production (OPENCHAWN_ENV=production) : uniquement les variables injectées
  (ex. Railway). Aucun chargement de fichier .env.
- Développement : charge `.env` à la racine du dépôt si présent (sans écraser
  l’environnement déjà défini).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.provider_runtime_config import DEEPSEEK_API_KEY_ENV_ALIASES, OPENROUTER_KEY_ENV_ALIASES

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DEV_SECRET = "dev-secret-change-me-in-production"
_DEEPSEEK_HOST = "https://api.deepseek.com"


def _deepseek_base_normalize(url: str) -> str:
    """Base sans segment /v1 — ex. https://api.deepseek.com (POST …/chat/completions)."""
    u = (url or "").strip().rstrip("/")
    if u.endswith("/v1"):
        u = u[:-3].rstrip("/")
    return u or _DEEPSEEK_HOST


def _str(
    key: str,
    *fallback_keys: str,
    default: str = "",
) -> str:
    for k in (key,) + fallback_keys:
        v = os.environ.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return default


def _bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _int_coalesce(*keys: str, default: int) -> int:
    """Premier ENV entier valide parmi ``keys``, sinon ``default``."""
    for key in keys:
        raw = os.environ.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            v = int(str(raw).strip())
            if v < 1:
                continue
            return v
        except ValueError:
            continue
    return default


def _load_dotenv_if_dev() -> None:
    """En prod, ne jamais lire un fichier .env."""
    env = _str("OPENCHAWN_ENV", default="development").lower()
    if env == "production":
        return
    path = _REPO_ROOT / ".env"
    if path.is_file():
        load_dotenv(path, override=False)


@dataclass(frozen=True)
class Settings:
    """Toutes les variables supportées — aucune clé en dur dans le code."""

    openchawn_env: str
    is_production: bool

    log_level: str

    secret_key: str
    jwt_expire_hours: int

    cors_origins_raw: str
    rate_limit_chat: int
    rate_limit_auth: int
    max_message_length: int
    profile: str
    guest_daily_limit: int

    default_provider: str
    model_provider: str
    openchawn_provider: str

    app_base_url: str
    frontend_url: str

    database_url: str
    database_path: str
    redis_url: str

    memory_backend: str
    memory_db_url: str

    ollama_enabled: bool
    ollama_url: str
    ollama_base_url: str
    ollama_model: str

    mistral_api_key: str
    mistral_model: str
    mistral_base_url: str

    minimax_api_key: str
    minimax_model: str
    minimax_base_url: str

    kimi_api_key: str
    kimi_model: str
    kimi_base_url: str

    openai_api_key: str
    openai_model: str
    openai_base_url: str
    openai_prompt_id: str
    openai_prompt_version: str

    anthropic_api_key: str
    anthropic_model: str
    anthropic_base_url: str

    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str

    infomaniak_api_key: str
    infomaniak_model: str
    infomaniak_base_url: str

    qwen_api_key: str
    qwen_model: str
    qwen_base_url: str

    perplexity_api_key: str
    perplexity_model: str
    perplexity_base_url: str

    # Legacy / compat
    openrouter_api_key: str
    openrouter_base_url: str
    openrouter_model: str
    moonshot_api_key: str
    moonshot_base_url: str
    moonshot_model: str
    moonshot_timeout: float

    kimi_temperature: float
    kimi_timeout: float
    kimi_max_tokens: int

    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_model_provider(self) -> str:
        """Préfère DEFAULT_PROVIDER, puis MODEL_PROVIDER (legacy)."""
        d = (self.default_provider or "").strip().lower()
        if d:
            return d
        return (self.model_provider or "").strip().lower()

    @property
    def kimi_effective_key(self) -> str:
        return self.kimi_api_key or self.moonshot_api_key

    @property
    def kimi_effective_base(self) -> str:
        return self.kimi_base_url or self.moonshot_base_url

    @property
    def kimi_effective_model(self) -> str:
        return self.kimi_model or self.moonshot_model


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _load_dotenv_if_dev()
        _settings = _build_settings()
    return _settings


def reload_settings() -> Settings:
    """Pour les tests uniquement."""
    global _settings
    _settings = None
    return get_settings()


def _build_settings() -> Settings:
    env = _str("OPENCHAWN_ENV", default="development").lower()
    is_prod = env == "production"

    secret = _str("SECRET_KEY", "OPENCHAWN_SECRET_KEY", default=_DEFAULT_DEV_SECRET)

    # OpenChawn n’appelle pas Ollama (Railway : OLLAMA_ENABLED=false).
    _ = _bool("OLLAMA_ENABLED", default=False)
    ollama_enabled = False
    ollama_url = ""
    ollama_base = ""

    deepseek_base = _deepseek_base_normalize(_str("DEEPSEEK_BASE_URL", default=_DEEPSEEK_HOST))

    db_path = _str("OPENCHAWN_DB_PATH", default="./data/openchawn.db")
    database_url = _str("DATABASE_URL", default="")

    return Settings(
        openchawn_env=env,
        is_production=is_prod,
        log_level=_str("LOG_LEVEL", default="INFO" if is_prod else "DEBUG"),
        secret_key=secret,
        jwt_expire_hours=_int("OPENCHAWN_JWT_HOURS", 24),
        cors_origins_raw=_str(
            "CORS_ORIGINS",
            "OPENCHAWN_CORS_ORIGINS",
            default="http://localhost:8000,http://127.0.0.1:8000",
        ),
        rate_limit_chat=_int("OPENCHAWN_RATE_CHAT", 30),
        rate_limit_auth=_int("OPENCHAWN_RATE_AUTH", 10),
        max_message_length=_int("OPENCHAWN_MAX_MSG_LEN", 4000),
        profile=_str("OPENCHAWN_PROFILE", default="default"),
        guest_daily_limit=_int_coalesce(
            "GUEST_DAILY_MESSAGE_LIMIT",
            "OPENCHAWN_GUEST_DAILY_LIMIT",
            default=15,
        ),
        default_provider=_str("DEFAULT_PROVIDER", default="deepseek").strip().lower(),
        model_provider=_str("MODEL_PROVIDER", default="").strip().lower(),
        openchawn_provider=_str("OPENCHAWN_PROVIDER", default="auto").strip().lower(),
        app_base_url=_str("APP_BASE_URL", default="").rstrip("/"),
        frontend_url=_str("FRONTEND_URL", default="").rstrip("/"),
        database_url=database_url,
        database_path=db_path,
        redis_url=_str("REDIS_URL", default=""),
        memory_backend=_str("MEMORY_BACKEND", default="json").strip().lower(),
        memory_db_url=_str("MEMORY_DB_URL", "DATABASE_URL", default=""),
        ollama_enabled=ollama_enabled,
        ollama_url=ollama_url,
        ollama_base_url=ollama_base,
        ollama_model=_str("OLLAMA_MODEL", default="mistral:7b"),
        mistral_api_key=_str("MISTRAL_API_KEY", default=""),
        mistral_model=_str("MISTRAL_MODEL", default="mistral-small-latest"),
        mistral_base_url=_str("MISTRAL_BASE_URL", default="https://api.mistral.ai/v1").rstrip("/"),
        minimax_api_key=_str("MINIMAX_API_KEY", default=""),
        minimax_model=_str("MINIMAX_MODEL", default="MiniMax-M2.7"),
        minimax_base_url=_str("MINIMAX_BASE_URL", default="https://api.minimax.io/v1").rstrip("/"),
        kimi_api_key=_str("KIMI_API_KEY", default=""),
        kimi_model=_str("KIMI_MODEL", default=""),
        kimi_base_url=_str("KIMI_BASE_URL", default="https://api.moonshot.ai/v1").rstrip("/"),
        openai_api_key=_str("OPENAI_API_KEY", default=""),
        openai_model=_str("OPENAI_MODEL", default="gpt-4o-mini"),
        openai_base_url=_str("OPENAI_BASE_URL", default="https://api.openai.com/v1").rstrip("/"),
        openai_prompt_id=_str("OPENAI_PROMPT_ID", default=""),
        openai_prompt_version=_str("OPENAI_PROMPT_VERSION", default="1"),
        anthropic_api_key=_str("ANTHROPIC_API_KEY", default=""),
        anthropic_model=_str("ANTHROPIC_MODEL", default="claude-3-5-sonnet-20241022"),
        anthropic_base_url=_str("ANTHROPIC_BASE_URL", default="https://api.anthropic.com/v1").rstrip(
            "/"
        ),
        deepseek_api_key=_str(*DEEPSEEK_API_KEY_ENV_ALIASES, default=""),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro",
        deepseek_base_url=deepseek_base,
        infomaniak_api_key=_str("INFOMANIAK_API_KEY", default=""),
        infomaniak_model=_str("INFOMANIAK_MODEL", default=""),
        infomaniak_base_url=_str("INFOMANIAK_BASE_URL", default="").rstrip("/"),
        qwen_api_key=_str("QWEN_API_KEY", default=""),
        qwen_model=_str("QWEN_MODEL", default="qwen-max"),
        qwen_base_url=_str(
            "QWEN_BASE_URL", default="https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/"),
        perplexity_api_key=_str("PERPLEXITY_API_KEY", default=""),
        perplexity_model=_str("PERPLEXITY_MODEL", default="llama-3.1-sonar-large-128k-online"),
        perplexity_base_url=_str("PERPLEXITY_BASE_URL", default="https://api.perplexity.ai").rstrip(
            "/"
        ),
        openrouter_api_key=_str(*OPENROUTER_KEY_ENV_ALIASES, default=""),
        openrouter_base_url=_str(
            "OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1"
        ).rstrip("/"),
        openrouter_model=_str("OPENROUTER_MODEL", default="openrouter/auto"),
        moonshot_api_key=_str("MOONSHOT_API_KEY", default=""),
        moonshot_base_url=_str("MOONSHOT_BASE_URL", default="https://api.moonshot.cn/v1").rstrip("/"),
        moonshot_model=_str("MOONSHOT_MODEL", default="moonshot-v1-8k"),
        moonshot_timeout=float(_str("MOONSHOT_TIMEOUT", default="120")),
        kimi_temperature=float(_str("KIMI_TEMPERATURE", default="0.6")),
        kimi_timeout=float(_str("KIMI_TIMEOUT", default="120")),
        kimi_max_tokens=_int("KIMI_MAX_TOKENS", 2048),
    )


def apply_logging_level() -> None:
    s = get_settings()
    level = getattr(logging, s.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers:
        h.setLevel(level)
