"""
Base de données SQLite — users + métiers.
Zéro dépendance externe, stdlib uniquement.
"""
import os
import sqlite3
import tempfile
from pathlib import Path

from app.config import DATABASE_PATH


def _configured_database_path() -> Path:
    raw = (DATABASE_PATH or "").strip() or "./data/openchawn.db"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        repo_root = Path(__file__).resolve().parents[2]
        path = (repo_root / path).resolve()
    return path


def _temporary_database_path() -> Path:
    raw = (os.getenv("OPENCHAWN_TEST_DB_PATH") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    return Path(tempfile.gettempdir()) / "openchawn" / "openchawn-test.db"


def _candidate_database_paths() -> list[Path]:
    primary = _configured_database_path()
    candidates = [primary]
    test_mode = bool(os.getenv("PYTEST_CURRENT_TEST")) or (os.getenv("OPENCHAWN_ENV", "").lower() == "test")
    if test_mode:
        temp_path = _temporary_database_path()
        if temp_path != primary:
            candidates.insert(0, temp_path)
    elif os.getenv("OPENCHAWN_ENV", "").lower() != "production":
        temp_path = _temporary_database_path()
        if temp_path != primary:
            candidates.append(temp_path)
    return candidates


def _get_connection() -> sqlite3.Connection:
    errors: list[str] = []
    for path in _candidate_database_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.OperationalError as e:
            errors.append(f"{path}: {e}")
    detail = " | ".join(errors) if errors else "no database candidates"
    raise sqlite3.OperationalError(f"unable to open database file ({detail})")


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
