"""
tests/test_ownership.py
Every assignment and study slot belongs to one student, and storage
never lets one student see or touch another's rows. Also: a database
from before accounts existed migrates cleanly, with everything it
held assigned to the built-in local student.
"""

import sqlite3
from datetime import date, timedelta

import pytest

import storage
from models import Assignment, Priority, TimeSlot, Weekday

DUE = date(2026, 9, 20)


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "ownership.db")
    storage.init_db()
    yield


@pytest.fixture
def two_students():
    return storage.add_user("ana@example.com"), storage.add_user("ben@example.com")


def assignment(name="Essay", hours=2.0):
    return Assignment(name=name, subject="English", due_date=DUE, estimated_hours=hours, priority=Priority.HIGH)


def slot(weekday=Weekday.MONDAY):
    return TimeSlot(weekday=weekday, start_hour=16, end_hour=18)


# ---------- Users ----------

def test_the_built_in_student_exists_after_init():
    user = storage.get_user(storage.DEFAULT_USER_ID)
    assert user is not None and user.id == storage.DEFAULT_USER_ID


def test_add_user_returns_a_fresh_id_and_get_user_finds_it():
    uid = storage.add_user("ana@example.com")
    assert isinstance(uid, str) and len(uid) == 36                 # a UUID string
    user = storage.get_user(uid)
    assert user.email == "ana@example.com" and user.id == uid
    assert storage.get_user("no-such-user") is None


def test_emails_are_unique():
    storage.add_user("ana@example.com")
    with pytest.raises(sqlite3.IntegrityError):
        storage.add_user("ana@example.com")


# ---------- Assignments: visibility ----------

def test_students_see_only_their_own_assignments(two_students):
    ana, ben = two_students
    storage.add_assignment(ana, assignment("Ana's essay"))
    storage.add_assignment(ben, assignment("Ben's essay"))
    assert [a.name for a in storage.list_assignments(ana)] == ["Ana's essay"]
    assert [a.name for a in storage.list_assignments(ben)] == ["Ben's essay"]
    assert storage.list_assignments(storage.DEFAULT_USER_ID) == []


def test_upcoming_assignments_are_per_student(two_students):
    ana, ben = two_students
    soon = Assignment(name="Soon", subject="S", due_date=date.today() + timedelta(days=2), estimated_hours=1)
    storage.add_assignment(ben, soon)
    assert storage.upcoming_assignments(ana) == []
    assert [a.name for a in storage.upcoming_assignments(ben)] == ["Soon"]


# ---------- Assignments: no cross-student writes ----------

def test_a_student_cannot_edit_another_students_assignment(two_students):
    ana, ben = two_students
    bens = storage.add_assignment(ben, assignment("Ben's essay", 2))
    stolen = Assignment(id=bens, name="Hacked", subject="X", due_date=DUE, estimated_hours=9, priority=Priority.LOW)
    assert storage.update_assignment(ana, stolen) is False
    kept = storage.list_assignments(ben)[0]
    assert (kept.name, kept.estimated_hours) == ("Ben's essay", 2)


def test_a_student_cannot_delete_another_students_assignment(two_students):
    ana, ben = two_students
    bens = storage.add_assignment(ben, assignment())
    assert storage.delete_assignment(ana, bens) is False
    assert len(storage.list_assignments(ben)) == 1
    assert storage.delete_assignment(ben, bens) is True


def test_a_student_cannot_complete_another_students_assignment(two_students):
    ana, ben = two_students
    bens = storage.add_assignment(ben, assignment())
    assert storage.mark_assignment_complete(ana, bens) is False
    assert storage.list_assignments(ben)[0].completed is False
    assert storage.mark_assignment_complete(ben, bens) is True
    assert storage.list_assignments(ben)[0].completed is True


# ---------- Study slots ----------

def test_students_see_only_their_own_slots(two_students):
    ana, ben = two_students
    storage.add_time_slot(ana, slot(Weekday.MONDAY))
    storage.add_time_slot(ben, slot(Weekday.FRIDAY))
    assert [s.weekday for s in storage.list_time_slots(ana)] == [Weekday.MONDAY]
    assert [s.weekday for s in storage.list_time_slots(ben)] == [Weekday.FRIDAY]


def test_a_student_cannot_edit_or_delete_another_students_slot(two_students):
    ana, ben = two_students
    bens = storage.add_time_slot(ben, slot(Weekday.FRIDAY))
    assert storage.update_time_slot(ana, TimeSlot(id=bens, weekday=Weekday.SUNDAY, start_hour=9, end_hour=10)) is False
    assert storage.delete_time_slot(ana, bens) is False
    kept = storage.list_time_slots(ben)[0]
    assert (kept.weekday, kept.start_hour, kept.end_hour) == (Weekday.FRIDAY, 16, 18)
    assert storage.delete_time_slot(ben, bens) is True


# ---------- Migration from the single-student database ----------

def test_a_database_from_before_accounts_is_migrated_to_the_local_student(tmp_path):
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.executescript("""
        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, subject TEXT NOT NULL,
            due_date TEXT NOT NULL, estimated_hours REAL NOT NULL, priority INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE time_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, weekday INTEGER NOT NULL,
            start_hour INTEGER NOT NULL, end_hour INTEGER NOT NULL);
        INSERT INTO assignments (name, subject, due_date, estimated_hours, priority, completed)
            VALUES ('Old essay', 'English', '2026-09-20', 2.0, 3, 0);
        INSERT INTO time_slots (weekday, start_hour, end_hour) VALUES (0, 16, 18);
    """)
    conn.commit(); conn.close()

    storage.set_db_path(old)
    storage.init_db()                                   # migrates in place

    me = storage.DEFAULT_USER_ID
    assert [a.name for a in storage.list_assignments(me)] == ["Old essay"]
    assert [(s.weekday, s.start_hour) for s in storage.list_time_slots(me)] == [(Weekday.MONDAY, 16)]
    other = storage.add_user("new@example.com")
    assert storage.list_assignments(other) == [] and storage.list_time_slots(other) == []
    storage.init_db()                                   # running it again is harmless
    assert len(storage.list_assignments(me)) == 1
    columns = [r[1] for r in sqlite3.connect(old).execute("PRAGMA table_info(users)")]
    assert "password_hash" in columns                   # the auth column arrives with the migration too
