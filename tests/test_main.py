"""
tests/test_main.py
Pytest suite for the CLI flows that run the StudyFlow pipeline.

The CLI reads from storage and prints, so these tests point storage
at a fresh temporary database, add real rows through it, run the
flow, and read what was printed.
"""

from datetime import date, timedelta

import pytest

import main
import storage
from models import Assignment, Priority, TimeSlot, Weekday


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "cli_test.db")
    storage.init_db()
    yield


def add_week_of_work():
    """Two 2-hour slots this week and 7 hours of work, one item done."""
    today = date.today()
    storage.add_time_slot(TimeSlot(weekday=Weekday(today.weekday()), start_hour=16, end_hour=18))
    storage.add_time_slot(TimeSlot(weekday=Weekday((today.weekday() + 1) % 7), start_hour=16, end_hour=18))
    storage.add_assignment(Assignment(name="Physics", subject="Physics", due_date=today + timedelta(days=1),
                                      estimated_hours=3, priority=Priority.HIGH))
    storage.add_assignment(Assignment(name="Math", subject="Math", due_date=today + timedelta(days=2),
                                      estimated_hours=2, priority=Priority.MEDIUM))
    storage.add_assignment(Assignment(name="CS", subject="CS", due_date=today + timedelta(days=4),
                                      estimated_hours=2, priority=Priority.LOW))
    storage.add_assignment(Assignment(name="Essay", subject="English", due_date=today + timedelta(days=4),
                                      estimated_hours=4, completed=True))


def test_menu_offers_generate_study_plan_and_analysis():
    assert "17. Generate study plan" in main.MENU
    assert "18. View schedule analysis" in main.MENU
    assert "Build weekly schedule" not in main.MENU


def test_generate_study_plan_flow_prints_the_full_report(capsys):
    add_week_of_work()
    main.generate_study_plan_flow()
    out = capsys.readouterr().out
    for heading in ("STUDYFLOW", "WEEKLY STUDY PLAN", "THIS WEEK", "PROGRESS", "AT-RISK ASSIGNMENTS"):
        assert heading in out
    assert "Physics" in out
    assert "Required work:      7.0h" in out       # the completed essay is not required work
    assert "CS\n2.0h remaining" in out
    assert "Essay" not in out


def test_generate_study_plan_flow_with_no_study_time_still_reports_and_hints(capsys):
    today = date.today()
    storage.add_assignment(Assignment(name="Physics", subject="Physics",
                                      due_date=today + timedelta(days=2), estimated_hours=2))
    main.generate_study_plan_flow()
    out = capsys.readouterr().out
    assert "Nothing scheduled." in out
    assert "Physics\n2.0h remaining" in out
    assert "add some with option 4" in out


def test_generate_study_plan_flow_with_nothing_at_all(capsys):
    main.generate_study_plan_flow()
    out = capsys.readouterr().out
    assert "Nothing scheduled." in out
    assert "Completion:       100.0%" in out
    assert "None. Every assignment is fully scheduled." in out


def test_schedule_analysis_flow_prints_the_per_assignment_table(capsys):
    add_week_of_work()
    main.schedule_analysis_flow()
    out = capsys.readouterr().out
    assert "StudyFlow Schedule Analysis" in out
    assert "100% scheduled   COMPLETE" in out      # Physics
    assert "UNSCHEDULED" in out                    # CS
    assert "Essay" not in out


def test_schedule_analysis_flow_with_no_assignments(capsys):
    main.schedule_analysis_flow()
    assert "No active assignments to analyse." in capsys.readouterr().out
