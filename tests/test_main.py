"""
tests/test_main.py
Pytest suite for the CLI.

The CLI reads from storage and prints, so these tests point storage
at a fresh temporary database, add rows through the real storage
layer or through the menus themselves, run a flow or the whole
program with scripted answers, and read what was printed.
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


def scripted_input(monkeypatch, answers):
    """Replace input() with a script; fail loudly if the script runs dry."""
    it = iter(answers)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise AssertionError(f"CLI asked for more input after the script ended: {prompt!r}")

    monkeypatch.setattr("builtins.input", fake_input)


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


# ---------- The two pipeline flows ----------

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


# ---------- The menus ----------

def test_main_menu_lists_the_six_areas_and_exits(monkeypatch, capsys):
    scripted_input(monkeypatch, ["0"])
    main.main()
    out = capsys.readouterr().out
    for line in ("1. Manage classes", "2. Manage assignments", "3. Manage tests",
                 "4. Manage study time", "5. Generate study plan", "6. View schedule analysis",
                 "0. Exit"):
        assert line in out
    assert out.rstrip().endswith("Goodbye!")


def test_invalid_choice_is_rejected_and_the_menu_returns(monkeypatch, capsys):
    scripted_input(monkeypatch, ["9", "0"])
    main.main()
    assert "Invalid option, try again." in capsys.readouterr().out


def test_submenu_returns_to_the_main_menu(monkeypatch, capsys):
    scripted_input(monkeypatch, ["1", "2", "0", "0"])   # classes -> view -> back -> exit
    main.main()
    out = capsys.readouterr().out
    assert "MANAGE CLASSES" in out
    assert "No classes yet." in out
    assert out.count("1. Manage classes") == 2        # main menu shown before and after


def test_end_to_end_a_student_enters_data_and_generates_a_plan(monkeypatch, capsys):
    """
    The manual test from the brief, scripted: add study time, add an
    assignment through the menus, generate the plan, exit.
    """
    today = date.today()
    weekday = Weekday(today.weekday()).name.lower()
    due = (today + timedelta(days=2)).isoformat()
    scripted_input(monkeypatch, [
        "4", "1", weekday, "16", "18", "0",                 # study time: today 4-6 PM
        "2", "1", "Physics", "Physics", due, "3", "3", "0",  # assignment: 3h, HIGH
        "5",                                                 # generate study plan
        "6",                                                 # view schedule analysis
        "0",                                                 # exit
    ])
    main.main()
    out = capsys.readouterr().out
    assert "Added time slot." in out
    assert "Added assignment: Physics" in out
    assert "WEEKLY STUDY PLAN" in out
    assert "4 PM–6 PM  Physics" in out
    assert "Required work:      3.0h" in out
    assert "Scheduled work:     2.0h" in out
    assert "Physics\n1.0h remaining" in out
    assert "67% scheduled   PARTIAL" in out
    assert out.rstrip().endswith("Goodbye!")
