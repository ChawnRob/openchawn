"""
Compatibilité ascendante : réexporte tous les paramètres depuis `app.settings`.
Les modules existants importent `app.config` sans changement de nom de variable.
"""
from __future__ import annotations

from app.settings import get_settings

_s = get_settings()

ENV = _s.openchawn_env
IS_PROD = _s.is_production

SECRET_KEY = _s.secret_key
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = _s.jwt_expire_hours

ALLOWED_ORIGINS = [x.strip() for x in _s.cors_origins_raw.split(",") if x.strip()]

RATE_LIMIT_CHAT = _s.rate_limit_chat
RATE_LIMIT_AUTH = _s.rate_limit_auth
MAX_MESSAGE_LENGTH = _s.max_message_length

PROFILE = _s.profile

LANG_INSTRUCTION = (
    "Réponds UNIQUEMENT en {lang_name}. Ne mélange JAMAIS les langues dans ta réponse."
)

PROVIDER = _s.openchawn_provider
MODEL_PROVIDER = _s.effective_model_provider

OLLAMA_BASE_URL = _s.ollama_base_url
OLLAMA_MODEL = _s.ollama_model

MINIMAX_API_KEY = _s.minimax_api_key
MINIMAX_MODEL = _s.minimax_model
MINIMAX_BASE_URL = _s.minimax_base_url

MISTRAL_API_KEY = _s.mistral_api_key
MISTRAL_MODEL = _s.mistral_model
MISTRAL_BASE_URL = _s.mistral_base_url

OPENAI_API_KEY = _s.openai_api_key
OPENAI_MODEL = _s.openai_model
OPENAI_BASE_URL = _s.openai_base_url
OPENAI_PROMPT_ID = _s.openai_prompt_id
OPENAI_PROMPT_VERSION = _s.openai_prompt_version

ANTHROPIC_API_KEY = _s.anthropic_api_key
ANTHROPIC_MODEL = _s.anthropic_model
ANTHROPIC_BASE_URL = _s.anthropic_base_url

DEEPSEEK_API_KEY = _s.deepseek_api_key
DEEPSEEK_MODEL = _s.deepseek_model
DEEPSEEK_BASE_URL = _s.deepseek_base_url

INFOMANIAK_API_KEY = _s.infomaniak_api_key
INFOMANIAK_MODEL = _s.infomaniak_model
INFOMANIAK_BASE_URL = _s.infomaniak_base_url

QWEN_API_KEY = _s.qwen_api_key
QWEN_MODEL = _s.qwen_model
QWEN_BASE_URL = _s.qwen_base_url

PERPLEXITY_API_KEY = _s.perplexity_api_key
PERPLEXITY_MODEL = _s.perplexity_model
PERPLEXITY_BASE_URL = _s.perplexity_base_url

KIMI_API_KEY = _s.kimi_api_key
KIMI_MODEL = ((_s.kimi_model or "").strip()) or "kimi-k2-0905-preview"
KIMI_BASE_URL = _s.kimi_base_url or "https://api.moonshot.ai/v1"
KIMI_TEMPERATURE = _s.kimi_temperature
KIMI_TIMEOUT = _s.kimi_timeout
KIMI_MAX_TOKENS = _s.kimi_max_tokens

FALLBACK_ENABLED = True
GUEST_DAILY_LIMIT = _s.guest_daily_limit

DATABASE_PATH = _s.database_path
DATABASE_URL = _s.database_url
REDIS_URL = _s.redis_url
MEMORY_BACKEND = _s.memory_backend
MEMORY_DB_URL = _s.memory_db_url
APP_BASE_URL = _s.app_base_url
FRONTEND_URL = _s.frontend_url
LOG_LEVEL = _s.log_level

OPENROUTER_API_KEY = _s.openrouter_api_key
OPENROUTER_BASE_URL = _s.openrouter_base_url
OPENROUTER_MODEL = _s.openrouter_model

OLLAMA_ENABLED = _s.ollama_enabled
DEFAULT_PROVIDER = _s.default_provider
