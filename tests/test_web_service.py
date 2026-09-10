"""
tests/test_web_service.py
Pytest suite for studyflow_web/service.py, the seam between the web
UI and the engine.

The service reads and writes through the real storage layer, so each
test gets a fresh temporary database. The page itself is not tested
here; what matters is that every value it renders is right.
"""

from datetime import date, timedelta

import pytest

import storage
from studyflow_web import service

TODAY = date(2026, 8, 17)  # a Monday


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "web_test.db")
    storage.init_db()
    yield


# ---------- Assignments ----------

def test_add_and_list_assignment():
    assert service.add_assignment("Physics Lab", "Physics", "2026-08-19", "3", "High") is None
    rows = service.list_assignments(today=TODAY)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Physics Lab"
    assert row["subject"] == "Physics"
    assert row["due"] == "2026-08-19"
    assert row["due_in"] == "in 2 days"
    assert row["hours"] == "3"
    assert row["priority"] == "High"
    assert row["completed"] == "no"
    assert row["id"].isdigit()


def test_priority_accepts_key_or_label():
    assert service.add_assignment("A", "S", "2026-08-19", "1", "3") is None
    assert service.add_assignment("B", "S", "2026-08-19", "1", "Low") is None
    assert [r["priority"] for r in service.list_assignments(today=TODAY)] == ["High", "Low"]


@pytest.mark.parametrize("name,due,hours,priority,message", [
    ("", "2026-08-19", "1", "2", "name"),
    ("A", "next friday", "1", "2", "YYYY-MM-DD"),
    ("A", "2026-08-19", "lots", "2", "number"),
    ("A", "2026-08-19", "-1", "2", "negative"),
    ("A", "2026-08-19", "1", "urgent", "priority"),
])
def test_add_assignment_validation(name, due, hours, priority, message):
    error = service.add_assignment(name, "S", due, hours, priority)
    assert error is not None and message in error
    assert service.list_assignments() == []


def test_due_in_words():
    for offset, words in [(-3, "3 days overdue"), (-1, "1 day overdue"), (0, "today"), (1, "tomorrow"), (5, "in 5 days")]:
        service.add_assignment(f"T{offset}", "S", (TODAY + timedelta(days=offset)).isoformat(), "1", "2")
    assert [r["due_in"] for r in service.list_assignments(today=TODAY)] == [
        "3 days overdue", "1 day overdue", "today", "tomorrow", "in 5 days",
    ]


def test_toggle_and_delete_assignment():
    service.add_assignment("A", "S", "2026-08-19", "1", "2")
    row = service.list_assignments()[0]
    service.toggle_assignment(row["id"])
    assert service.list_assignments()[0]["completed"] == "yes"
    service.toggle_assignment(row["id"])
    assert service.list_assignments()[0]["completed"] == "no"
    service.delete_assignment(row["id"])
    assert service.list_assignments() == []


# ---------- Study time ----------

def test_add_and_list_slot():
    assert service.add_slot("Wednesday", "16", "18") is None
    rows = service.list_slots()
    assert len(rows) == 1
    assert rows[0]["weekday"] == "Wednesday"
    assert rows[0]["time"] == "4 PM–6 PM (2h)"


@pytest.mark.parametrize("weekday,start,end,message", [
    ("Funday", "16", "18", "weekday"),
    ("Monday", "four", "18", "whole numbers"),
    ("Monday", "18", "16", "start before it ends"),
    ("Monday", "16", "25", "start before it ends"),
])
def test_add_slot_validation(weekday, start, end, message):
    error = service.add_slot(weekday, start, end)
    assert error is not None and message in error
    assert service.list_slots() == []


def test_delete_slot():
    service.add_slot("Monday", "16", "18")
    service.delete_slot(service.list_slots()[0]["id"])
    assert service.list_slots() == []


# ---------- The plan ----------

def add_week_of_work():
    """Two 2-hour slots and 7 hours of work; the essay is already done."""
    service.add_slot("Monday", "16", "18")
    service.add_slot("Tuesday", "16", "18")
    service.add_assignment("Physics", "Physics", "2026-08-18", "3", "High")
    service.add_assignment("Math", "Math", "2026-08-19", "2", "Medium")
    service.add_assignment("CS", "CS", "2026-08-21", "2", "Low")
    service.add_assignment("Essay", "English", "2026-08-21", "4", "Low")
    essay = [r for r in service.list_assignments() if r["name"] == "Essay"][0]
    service.toggle_assignment(essay["id"])


def test_build_plan_shapes_the_schedule_for_the_page():
    add_week_of_work()
    plan = service.build_plan(today=TODAY)
    assert plan["today"] == "Monday 17 August 2026"
    assert plan["has_slots"] and plan["has_assignments"]
    assert [d["label"] for d in plan["days"]] == ["Monday 17 August", "Tuesday 18 August"]
    monday = plan["days"][0]["blocks"]
    assert monday == [{"time": "4 PM–6 PM", "label": "Physics", "is_break": "no"}]
    tuesday_labels = [b["label"] for b in plan["days"][1]["blocks"]]
    assert tuesday_labels == ["Physics", "Break", "Math"]
    assert plan["days"][1]["blocks"][1]["is_break"] == "yes"


def test_build_plan_progress_and_statuses():
    add_week_of_work()
    plan = service.build_plan(today=TODAY)
    assert plan["progress"] == {"required": "7.0", "scheduled": "3.8", "unscheduled": "3.2", "completion": "54"}
    by_name = {s["name"]: s for s in plan["statuses"]}
    assert set(by_name) == {"Physics", "Math", "CS"}          # the completed essay is absent
    assert by_name["Physics"]["status"] == "COMPLETE" and by_name["Physics"]["risk"] == ""
    assert by_name["Math"]["status"] == "PARTIAL" and by_name["Math"]["remaining"] == "1.2"
    assert by_name["CS"]["status"] == "UNSCHEDULED" and by_name["CS"]["required"] == "2.0"
    assert by_name["CS"]["risk"] in ("CRITICAL", "HIGH", "MODERATE", "LOW")
    assert plan["at_risk"] == ["Math", "CS"]


def test_build_plan_with_nothing_stored():
    plan = service.build_plan(today=TODAY)
    assert plan["days"] == [] and plan["statuses"] == [] and plan["at_risk"] == []
    assert plan["progress"]["completion"] == "100"
    assert not plan["has_slots"] and not plan["has_assignments"]


def test_build_plan_values_are_strings_for_the_page():
    """Reflex renders typed vars; keeping every leaf a string keeps the page simple."""
    add_week_of_work()
    plan = service.build_plan(today=TODAY)
    rows = plan["statuses"] + [plan["progress"]] + [b for d in plan["days"] for b in d["blocks"]]
    for row in rows:
        assert all(isinstance(v, str) for v in row.values())
