"""
tests/test_storage.py
Pytest suite for StudyFlow's storage layer.

Run with: pytest
(pytest picks up sys.path from the rootdir, so this relies on a
conftest.py in the project root that adds the project to sys.path —
see conftest.py alongside this file's parent directory.)
"""

from datetime import date, timedelta

import pytest

import storage
from models import Assignment, Class, Priority, Test, TimeSlot, Weekday


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """Point storage at a fresh temp database for every test."""
    storage.set_db_path(tmp_path / "test_studyflow.db")
    storage.init_db()
    yield


# ---------- Classes ----------

def test_add_and_list_class():
    storage.add_class(Class(name="Mathematics", code="MATH-201"))
    classes = storage.list_classes()
    assert len(classes) == 1
    assert classes[0].name == "Mathematics"
    assert classes[0].code == "MATH-201"


def test_update_class():
    class_id = storage.add_class(Class(name="Physics", code="PHYS-101"))
    storage.update_class(Class(id=class_id, name="Physics II", code="PHYS-102"))
    classes = storage.list_classes()
    assert classes[0].name == "Physics II"
    assert classes[0].code == "PHYS-102"


def test_delete_class():
    class_id = storage.add_class(Class(name="Chemistry"))
    assert storage.delete_class(class_id) is True
    assert storage.list_classes() == []
    assert storage.delete_class(class_id) is False  # already gone


# ---------- Assignments ----------

def test_add_and_list_assignment():
    storage.add_assignment(Assignment(
        name="Essay 1", subject="English", due_date=date.today(),
        estimated_hours=3, priority=Priority.MEDIUM,
    ))
    assignments = storage.list_assignments()
    assert len(assignments) == 1
    assert assignments[0].name == "Essay 1"
    assert assignments[0].completed is False


def test_update_assignment():
    a_id = storage.add_assignment(Assignment(
        name="Lab Report", subject="Physics", due_date=date.today(),
        estimated_hours=2, priority=Priority.LOW,
    ))
    storage.update_assignment(Assignment(
        id=a_id, name="Lab Report v2", subject="Physics",
        due_date=date.today(), estimated_hours=4, priority=Priority.HIGH,
        completed=False,
    ))
    updated = storage.list_assignments()[0]
    assert updated.name == "Lab Report v2"
    assert updated.estimated_hours == 4
    assert updated.priority == Priority.HIGH


def test_delete_assignment():
    a_id = storage.add_assignment(Assignment(name="To Delete", subject="Art", due_date=date.today()))
    assert storage.delete_assignment(a_id) is True
    assert storage.list_assignments() == []


def test_mark_assignment_complete():
    a_id = storage.add_assignment(Assignment(name="HW", subject="Math", due_date=date.today()))
    storage.mark_assignment_complete(a_id, True)
    assert storage.list_assignments()[0].completed is True
    storage.mark_assignment_complete(a_id, False)
    assert storage.list_assignments()[0].completed is False


def test_upcoming_assignments_filters_by_window_and_completion():
    today = date.today()
    storage.add_assignment(Assignment(name="Due soon", subject="Math",
                                       due_date=today + timedelta(days=2)))
    storage.add_assignment(Assignment(name="Due later", subject="Math",
                                       due_date=today + timedelta(days=30)))
    completed_id = storage.add_assignment(Assignment(name="Already done", subject="Math",
                                                       due_date=today + timedelta(days=1)))
    storage.mark_assignment_complete(completed_id, True)

    upcoming = storage.upcoming_assignments(days=7)
    names = {a.name for a in upcoming}
    assert names == {"Due soon"}  # "Due later" out of window, "Already done" excluded


# ---------- Tests ----------

def test_add_update_delete_test():
    t_id = storage.add_test(Test(subject="Biology", date=date.today(),
                                  topics="Cells", importance=Priority.HIGH))
    assert len(storage.list_tests()) == 1

    storage.update_test(Test(id=t_id, subject="Biology", date=date.today(),
                              topics="Cells, Genetics", importance=Priority.MEDIUM))
    updated = storage.list_tests()[0]
    assert updated.topics == "Cells, Genetics"
    assert updated.importance == Priority.MEDIUM

    assert storage.delete_test(t_id) is True
    assert storage.list_tests() == []


# ---------- Time Slots ----------

def test_add_update_delete_time_slot():
    slot_id = storage.add_time_slot(TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=19))
    assert storage.list_time_slots()[0].duration_hours == 3

    storage.update_time_slot(TimeSlot(id=slot_id, weekday=Weekday.TUESDAY,
                                       start_hour=17, end_hour=20))
    updated = storage.list_time_slots()[0]
    assert updated.weekday == Weekday.TUESDAY
    assert updated.start_hour == 17

    assert storage.delete_time_slot(slot_id) is True
    assert storage.list_time_slots() == []
