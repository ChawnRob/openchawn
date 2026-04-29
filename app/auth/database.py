"""
Base de données SQLite — users + métiers.
Zéro dépendance externe, stdlib uniquement.
"""
import sqlite3
import os
from app.config import DATABASE_PATH


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Crée les tables si elles n'existent pas."""
    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            business_type TEXT NOT NULL DEFAULT 'default',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    conn.commit()
    conn.close()


def create_user(email: str, password_hash: str, display_name: str, business_type: str = "default") -> dict | None:
    """Insère un user. Retourne le user ou None si email déjà pris."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, display_name, business_type) VALUES (?, ?, ?, ?)",
            (email, password_hash, display_name, business_type),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(user)
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = _get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = _get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_business(user_id: int, business_type: str) -> bool:
    conn = _get_connection()
    cursor = conn.execute(
        "UPDATE users SET business_type = ? WHERE id = ?",
        (business_type, user_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
