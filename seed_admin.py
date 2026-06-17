"""
Script one-shot : crée un compte admin via variables d'environnement.
Usage :
  OPENCHAWN_SEED_EMAIL=... OPENCHAWN_SEED_PASSWORD=... python seed_admin.py
"""
from __future__ import annotations

import os
import sys

from app.auth.database import init_db, create_user, get_user_by_email
from app.auth.security import hash_password

EMAIL = (os.environ.get("OPENCHAWN_SEED_EMAIL") or "").strip().lower()
PASSWORD = os.environ.get("OPENCHAWN_SEED_PASSWORD") or ""
NAME = (os.environ.get("OPENCHAWN_SEED_NAME") or "Admin").strip()
BUSINESS = (os.environ.get("OPENCHAWN_SEED_BUSINESS") or "default").strip()

if not EMAIL or not PASSWORD:
    print(
        "Définissez OPENCHAWN_SEED_EMAIL et OPENCHAWN_SEED_PASSWORD pour créer un compte admin.",
        file=sys.stderr,
    )
    sys.exit(1)

init_db()

existing = get_user_by_email(EMAIL)
if existing:
    print(f"Compte déjà existant pour user_id={existing['id']}")
else:
    pw_hash = hash_password(PASSWORD)
    user = create_user(EMAIL, pw_hash, NAME, BUSINESS)
    if not user:
        print("Échec de création du compte (email peut-être déjà utilisé).", file=sys.stderr)
        sys.exit(2)
    print(f"Compte créé user_id={user['id']} business_type={user['business_type']}")

print("Connectez-vous sur l'interface OpenChawn.")
