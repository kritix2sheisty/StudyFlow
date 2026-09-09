"""
storage.py
SQLite persistence layer for StudyFlow (Phase 1).

Wraps sqlite3 directly (no ORM) so the schema and queries are
explicit and easy to follow. All functions take/return the
dataclasses defined in models.py.
"""

import sqlite3
from datetime import date
from pathlib import Path
from typing import List

from models import Assignment, Class, Priority, Test, TimeSlot, Weekday

DB_PATH = Path(__file__).parent / "data" / "studyflow.db"


def set_db_path(path: Path) -> None:
    """Point storage at a different database file (used by tests)."""
    global DB_PATH
    DB_PATH = path


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't already exist."""
    conn = get_connection()
    cur = conn.cursor()

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
            weekday INTEGER NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()


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


# ---------- Assignments ----------

def add_assignment(a: Assignment) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO assignments
           (name, subject, due_date, estimated_hours, priority, completed)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (a.name, a.subject, a.due_date.isoformat(), a.estimated_hours,
         int(a.priority), int(a.completed)),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_assignments(include_completed: bool = True) -> List[Assignment]:
    conn = get_connection()
    query = "SELECT id, name, subject, due_date, estimated_hours, priority, completed FROM assignments"
    if not include_completed:
        query += " WHERE completed = 0"
    query += " ORDER BY due_date ASC"
    rows = conn.execute(query).fetchall()
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


def update_assignment(a: Assignment) -> bool:
    """Update an assignment by id. Returns True if a row was updated."""
    conn = get_connection()
    cur = conn.execute(
        """UPDATE assignments
           SET name = ?, subject = ?, due_date = ?, estimated_hours = ?,
               priority = ?, completed = ?
           WHERE id = ?""",
        (a.name, a.subject, a.due_date.isoformat(), a.estimated_hours,
         int(a.priority), int(a.completed), a.id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_assignment(assignment_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def mark_assignment_complete(assignment_id: int, completed: bool = True) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE assignments SET completed = ? WHERE id = ?",
        (int(completed), assignment_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def upcoming_assignments(days: int = 7) -> List[Assignment]:
    """Assignments due within the next `days` days, soonest first."""
    from datetime import timedelta
    today = date.today()
    cutoff = today + timedelta(days=days)
    return [
        a for a in list_assignments(include_completed=False)
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


# ---------- Time Slots ----------

def add_time_slot(t: TimeSlot) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO time_slots (weekday, start_hour, end_hour) VALUES (?, ?, ?)",
        (int(t.weekday), t.start_hour, t.end_hour),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_time_slots() -> List[TimeSlot]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, weekday, start_hour, end_hour FROM time_slots ORDER BY weekday ASC"
    ).fetchall()
    conn.close()
    return [
        TimeSlot(id=r[0], weekday=Weekday(r[1]), start_hour=r[2], end_hour=r[3])
        for r in rows
    ]


def update_time_slot(t: TimeSlot) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE time_slots SET weekday = ?, start_hour = ?, end_hour = ? WHERE id = ?",
        (int(t.weekday), t.start_hour, t.end_hour, t.id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_time_slot(slot_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM time_slots WHERE id = ?", (slot_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
