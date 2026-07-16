"""User management database operations using SQLite."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent / "users.db"


def _hash_password(password: str) -> str:
    """Return a SHA-256 hex digest of the password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db() -> None:
    """Initialize the SQLite database and create users table if it does not exist."""
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            employee_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            domain TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'trainee',
            password_plain TEXT
        )
        """
    )
    
    # Check if table needs password_plain column (migration for existing db)
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if "password_plain" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN password_plain TEXT")
    if "last_active" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP")
    
    # Delete demo user if it exists (clean migration)
    cursor.execute("DELETE FROM users WHERE employee_id = 'demo'")
    
    # Check if table is empty, if so, seed default accounts
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Seed admin user only
        cursor.execute(
            """
            INSERT INTO users (employee_id, email, full_name, domain, password_hash, role, password_plain)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                "admin@company.com",
                "Administrator",
                "general",
                _hash_password("admin123"),
                "admin",
                "admin123",
            ),
        )
    
    conn.commit()
    conn.close()


def add_user(
    employee_id: str,
    email: str,
    full_name: str,
    domain: str,
    password_plain: str,
    role: str = "trainee",
) -> tuple[bool, str]:
    """Add a new user to the database. Returns (success, message)."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO users (employee_id, email, full_name, domain, password_hash, role, password_plain)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_id.strip(),
                email.strip().lower(),
                full_name.strip(),
                domain.strip().lower(),
                _hash_password(password_plain),
                role,
                password_plain.strip(),
            ),
        )
        conn.commit()
        conn.close()
        return True, "User created successfully."
    except sqlite3.IntegrityError as e:
        err_msg = str(e)
        if "employee_id" in err_msg or "PRIMARY KEY" in err_msg:
            return False, f"Employee ID '{employee_id}' is already registered."
        if "email" in err_msg:
            return False, f"Email '{email}' is already registered."
        return False, f"Registration failed: {err_msg}"
    except Exception as e:
        return False, f"Database error: {e}"


def delete_user(employee_id: str) -> bool:
    """Delete a user from the database by Employee ID."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE employee_id = ?", (employee_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0
    except Exception:
        return False


def get_all_users() -> list[dict[str, Any]]:
    """Return all users in the database (excluding administrators)."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT employee_id, email, full_name, domain, role, password_plain, last_active FROM users WHERE role != 'admin'")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def verify_user(username_or_email: str, password_plain: str) -> dict[str, Any] | None:
    """Verify user credentials. Returns user dict if valid, else None."""
    try:
        init_db()  # Ensure DB is ready
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Match against employee_id or email
        cursor.execute(
            """
            SELECT employee_id, email, full_name, domain, role, password_hash 
            FROM users 
            WHERE LOWER(employee_id) = ? OR LOWER(email) = ?
            """,
            (username_or_email.lower(), username_or_email.lower()),
        )
        row = cursor.fetchone()
        conn.close()
        
        if row and row["password_hash"] == _hash_password(password_plain):
            user_data = dict(row)
            del user_data["password_hash"]
            # Update last_active on login verification
            update_user_activity(user_data["employee_id"])
            return user_data
    except Exception:
        pass
    return None


def update_user_activity(employee_id: str) -> None:
    """Update the last_active timestamp for a user to CURRENT_TIMESTAMP."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_active = datetime('now', 'localtime') WHERE employee_id = ?",
            (employee_id,)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_active_users_count(hours: int = 1) -> int:
    """Count the number of users who have been active within the last N hours."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE last_active >= datetime('now', 'localtime', ?)",
            (f"-{hours} hours",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        # Always return at least 1 if an active session exists
        return max(count, 1)
    except Exception:
        return 1
