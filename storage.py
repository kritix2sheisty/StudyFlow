"""
storage.py
SQLite persistence layer for StudyFlow.

Wraps sqlite3 directly (no ORM) so the schema and queries are
explicit and easy to follow. All functions take/return the
dataclasses defined in models.py.

Ownership (v1.2). Every assignment and study slot belongs to one
student, identified by a user id (a UUID string) from the `users`
table. Every function that reads or changes a student's rows takes
that id as its first argument and touches nothing else: a student
cannot list, edit, delete or complete another student's records, and
an update or delete on someone else's row simply reports False.

Until accounts exist, the web app and the CLI act as one built-in
student, DEFAULT_USER_ID, which init_db() creates. A database from
before ownership existed is migrated in place: the user_id column is
added and every existing row is given to that built-in student.

The API layer must derive the user id from authentication, never
from anything a client sends.
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from models import Assignment, Class, Priority, Test, TimeSlot, Weekday

DB_PATH = Path(__file__).parent / "data" / "studyflow.db"

# The one student a StudyFlow without accounts belongs to: the person
# at this computer. A fixed id, so the same rows are theirs across runs.
DEFAULT_USER_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_USER_EMAIL = "student@local"


@dataclass
class User:
    id: str
    email: str
    created_at: str


@dataclass
class UserCredentials:
    """A user plus their password hash; only api/auth.py should ask for this."""
    id: str
    email: str
    created_at: str
    password_hash: Optional[str]


@dataclass
class Session:
    """A login. The database holds the token's hash, never the token."""
    id: int
    user_id: str
    expires_at: str
    revoked_at: Optional[str]


@dataclass
class StoredPlan:
    """
    A student's last generated plan, as the JSON the API served, with
    the fingerprint of the inputs it was built from. Not a second
    schedule schema: the engine's output is kept whole and served only
    while the fingerprint still matches the student's data.
    """
    user_id: str
    fingerprint: str
    generated_at: str
    plan_json: str


def set_db_path(path: Path) -> None:
    """Point storage at a different database file (used by tests)."""
    global DB_PATH
    DB_PATH = path


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def init_db() -> None:
    """
    Create tables if they don't already exist, make sure the built-in
    student exists, and migrate a pre-ownership database in place.
    Safe to run any number of times.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            password_hash TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            user_id TEXT PRIMARY KEY REFERENCES users(id),
            fingerprint TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            plan_json TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            due_date TEXT NOT NULL,
            estimated_hours REAL NOT NULL,
            priority INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            date TEXT NOT NULL,
            topics TEXT,
            importance INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS time_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            weekday INTEGER NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL
        )
    """)

    # The built-in student.
    cur.execute(
        "INSERT OR IGNORE INTO users (id, email, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, DEFAULT_USER_EMAIL, datetime.now().isoformat(timespec="seconds")),
    )

    # Migration: a database made before ownership has no user_id
    # column. SQLite cannot add a NOT NULL column to a populated table,
    # so the added column is nullable; every function filters by
    # user_id anyway, and the backfill leaves no row without an owner.
    if "password_hash" not in _columns(conn, "users"):          # users table from PR #41
        cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

    for table in ("assignments", "time_slots"):
        if "user_id" not in _columns(conn, table):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT REFERENCES users(id)")
        cur.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (DEFAULT_USER_ID,))
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)")

    conn.commit()
    conn.close()


# ---------- Users ----------

def add_user(email: str) -> str:
    """Create a student and return their id. Emails are unique."""
    user_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (id, email, created_at) VALUES (?, ?, ?)",
            (user_id, email, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return user_id


def get_user(user_id: str) -> Optional[User]:
    conn = get_connection()
    row = conn.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return User(id=row[0], email=row[1], created_at=row[2]) if row else None


def get_user_by_email(email: str) -> Optional[UserCredentials]:
    """The user behind a login name, with their password hash, for the auth layer only."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, created_at, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return UserCredentials(id=row[0], email=row[1], created_at=row[2], password_hash=row[3]) if row else None


def set_password(user_id: str, password_hash: str) -> bool:
    """Store a password hash (never a password). Returns True if the user exists."""
    conn = get_connection()
    cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


# ---------- Sessions ----------

def create_session(user_id: str, token_hash: str, expires_at: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, token_hash, datetime.now().isoformat(timespec="seconds"), expires_at),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def find_session(token_hash: str) -> Optional[Session]:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, user_id, expires_at, revoked_at FROM sessions WHERE token_hash = ?", (token_hash,)
    ).fetchone()
    conn.close()
    return Session(id=row[0], user_id=row[1], expires_at=row[2], revoked_at=row[3]) if row else None


def touch_session(token_hash: str, expires_at: str) -> bool:
    """Extend a session's expiry (activity keeps a login alive)."""
    conn = get_connection()
    cur = conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                       (expires_at, token_hash))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def revoke_session(token_hash: str) -> bool:
    """Log a session out. Revoking an unknown or already revoked token is harmless."""
    conn = get_connection()
    cur = conn.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                       (datetime.now().isoformat(timespec="seconds"), token_hash))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


# ---------- Plans (one per student) ----------

def save_plan(user_id: str, fingerprint: str, generated_at: str, plan_json: str) -> None:
    """Store the student's latest plan, replacing any earlier one."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO plans (user_id, fingerprint, generated_at, plan_json) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET fingerprint = excluded.fingerprint,
               generated_at = excluded.generated_at, plan_json = excluded.plan_json""",
        (user_id, fingerprint, generated_at, plan_json),
    )
    conn.commit()
    conn.close()


def get_plan(user_id: str) -> Optional[StoredPlan]:
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, fingerprint, generated_at, plan_json FROM plans WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return StoredPlan(user_id=row[0], fingerprint=row[1], generated_at=row[2], plan_json=row[3]) if row else None


# ---------- Classes ----------

def add_class(c: Class) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO classes (name, code) VALUES (?, ?)", (c.name, c.code)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_classes() -> List[Class]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name, code FROM classes").fetchall()
    conn.close()
    return [Class(id=r[0], name=r[1], code=r[2] or "") for r in rows]


def update_class(c: Class) -> bool:
    """Update a class by id. Returns True if a row was updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE classes SET name = ?, code = ? WHERE id = ?",
        (c.name, c.code, c.id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_class(class_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ---------- Assignments (owned by a student) ----------

def add_assignment(user_id: str, a: Assignment) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO assignments
           (user_id, name, subject, due_date, estimated_hours, priority, completed)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, a.name, a.subject, a.due_date.isoformat(), a.estimated_hours,
         int(a.priority), int(a.completed)),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_assignments(user_id: str, include_completed: bool = True) -> List[Assignment]:
    conn = get_connection()
    query = ("SELECT id, name, subject, due_date, estimated_hours, priority, completed "
             "FROM assignments WHERE user_id = ?")
    if not include_completed:
        query += " AND completed = 0"
    query += " ORDER BY due_date ASC"
    rows = conn.execute(query, (user_id,)).fetchall()
    conn.close()
    return [
        Assignment(
            id=r[0], name=r[1], subject=r[2],
            due_date=date.fromisoformat(r[3]),
            estimated_hours=r[4], priority=Priority(r[5]),
            completed=bool(r[6]),
        )
        for r in rows
    ]


def update_assignment(user_id: str, a: Assignment) -> bool:
    """Update one of the student's assignments by id. Returns True if a row was updated."""
    conn = get_connection()
    cur = conn.execute(
        """UPDATE assignments
           SET name = ?, subject = ?, due_date = ?, estimated_hours = ?,
               priority = ?, completed = ?
           WHERE id = ? AND user_id = ?""",
        (a.name, a.subject, a.due_date.isoformat(), a.estimated_hours,
         int(a.priority), int(a.completed), a.id, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_assignment(user_id: str, assignment_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM assignments WHERE id = ? AND user_id = ?", (assignment_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def mark_assignment_complete(user_id: str, assignment_id: int, completed: bool = True) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE assignments SET completed = ? WHERE id = ? AND user_id = ?",
        (int(completed), assignment_id, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def upcoming_assignments(user_id: str, days: int = 7) -> List[Assignment]:
    """The student's assignments due within the next `days` days, soonest first."""
    from datetime import timedelta
    today = date.today()
    cutoff = today + timedelta(days=days)
    return [
        a for a in list_assignments(user_id, include_completed=False)
        if today <= a.due_date <= cutoff
    ]


# ---------- Tests ----------

def add_test(t: Test) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO tests (subject, date, topics, importance) VALUES (?, ?, ?, ?)",
        (t.subject, t.date.isoformat(), t.topics, int(t.importance)),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_tests() -> List[Test]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, date, topics, importance FROM tests ORDER BY date ASC"
    ).fetchall()
    conn.close()
    return [
        Test(id=r[0], subject=r[1], date=date.fromisoformat(r[2]),
             topics=r[3] or "", importance=Priority(r[4]))
        for r in rows
    ]


def update_test(t: Test) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE tests SET subject = ?, date = ?, topics = ?, importance = ? WHERE id = ?",
        (t.subject, t.date.isoformat(), t.topics, int(t.importance), t.id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_test(test_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ---------- Time Slots (owned by a student) ----------

def add_time_slot(user_id: str, t: TimeSlot) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO time_slots (user_id, weekday, start_hour, end_hour) VALUES (?, ?, ?, ?)",
        (user_id, int(t.weekday), t.start_hour, t.end_hour),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_time_slots(user_id: str) -> List[TimeSlot]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, weekday, start_hour, end_hour FROM time_slots WHERE user_id = ? ORDER BY weekday ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        TimeSlot(id=r[0], weekday=Weekday(r[1]), start_hour=r[2], end_hour=r[3])
        for r in rows
    ]


def update_time_slot(user_id: str, t: TimeSlot) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE time_slots SET weekday = ?, start_hour = ?, end_hour = ? WHERE id = ? AND user_id = ?",
        (int(t.weekday), t.start_hour, t.end_hour, t.id, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_time_slot(user_id: str, slot_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM time_slots WHERE id = ? AND user_id = ?", (slot_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
