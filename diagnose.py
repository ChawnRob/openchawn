"""Diagnostic complet — vérifie .env, providers, fallback."""
import os
import sys

print("=" * 60)
print("DIAGNOSTIC OPENCHAWN")
print("=" * 60)

# 1. python-dotenv installé ?
try:
    from dotenv import load_dotenv
    print("[OK] python-dotenv installé")
except ImportError:
    print("[FAIL] python-dotenv MANQUANT → pip install python-dotenv")
    sys.exit(1)

# 2. .env présent ?
env_path = os.path.join(os.path.dirname(__file__), ".env")
if not os.path.exists(env_path):
    print(f"[FAIL] .env introuvable à {env_path}")
    sys.exit(1)
print(f"[OK] .env trouvé: {env_path}")

# 3. Import config (doit déclencher load_dotenv)
from app.config import (
    MINIMAX_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY,
    PROVIDER, OLLAMA_BASE_URL, OLLAMA_MODEL,
)

def mask(key: str) -> str:
    if not key: return "(VIDE)"
    return f"{key[:6]}...{key[-4:]} ({len(key)} chars)"

print(f"\n--- Clés chargées ---")
print(f"MINIMAX_API_KEY : {mask(MINIMAX_API_KEY)}")
print(f"MISTRAL_API_KEY : {mask(MISTRAL_API_KEY)}")
print(f"OPENAI_API_KEY  : {mask(OPENAI_API_KEY)}")
print(f"PROVIDER        : {PROVIDER}")
print(f"OLLAMA_BASE_URL : {OLLAMA_BASE_URL}")
print(f"OLLAMA_MODEL    : {OLLAMA_MODEL}")

# 4. Chaîne de providers
from app.providers.selector import select_providers
print(f"\n--- Chaîne de providers ---")
providers = select_providers()
for i, (name, _) in enumerate(providers, 1):
    print(f"  {i}. {name}")

if len(providers) < 2:
    print("\n[PROBLEME] Moins de 2 providers → pas de fallback possible")

# 5. Test is_available() de chaque provider
print(f"\n--- Disponibilité ---")
for name, prov in providers:
    try:
        ok = prov.is_available()
        print(f"  {name}: {'DISPO' if ok else 'INDISPO'}")
    except Exception as e:
        print(f"  {name}: ERROR ({e})")

# 6. Test réel : envoyer un prompt à chaque provider
print(f"\n--- Test réel de chaque provider ---")
for name, prov in providers:
    try:
        resp = prov.generate("Dis bonjour en un mot.", user_id="diag", system_prompt="")
        preview = resp[:100].replace("\n", " ")
        status = "OK" if not resp.startswith("[ERREUR") else "FAIL"
        print(f"  [{status}] {name}: {preview}")
    except Exception as e:
        print(f"  [EXC]  {name}: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("FIN DIAGNOSTIC")
print("=" * 60)
