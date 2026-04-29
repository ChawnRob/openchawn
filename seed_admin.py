"""
Script one-shot : crée le compte admin Robert.
Usage : python seed_admin.py
"""
from app.auth.database import init_db, create_user, get_user_by_email
from app.auth.security import hash_password

EMAIL = "robert@fluxorca.com"
PASSWORD = "openchawn2026"
NAME = "Robert"
BUSINESS = "fluxorca"

init_db()

existing = get_user_by_email(EMAIL)
if existing:
    print(f"Compte deja existant : {EMAIL}")
else:
    pw_hash = hash_password(PASSWORD)
    user = create_user(EMAIL, pw_hash, NAME, BUSINESS)
    print(f"Compte cree !")
    print(f"  Email    : {EMAIL}")
    print(f"  Password : {PASSWORD}")
    print(f"  Metier   : {BUSINESS}")
    print(f"  ID       : {user['id']}")

print("\nConnecte-toi sur http://localhost:8000")
