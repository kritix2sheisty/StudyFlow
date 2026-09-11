"""
tests/test_assignment_form.py
Pytest suite for the Add Assignment form logic in StudyFlow/assignments.py.

The Reflex State delegates validation and row building to these pure
functions, so the behaviour the mentor's manual tests exercise (valid
assignment, empty form, decimal hours, cancel) is pinned here without
a browser.
"""

from datetime import date

from StudyFlow.assignments import (
    FIELDS,
    OVERDUE_NOTICE,
    RISK_NOT_RATED,
    build_row,
    due_countdown,
    due_notice,
    is_valid,
    no_errors,
    sorted_by_urgency,
    total_hours,
    validate_form,
)

TODAY = date(2026, 9, 9)


# ---------- Test A: a valid assignment ----------

def test_valid_assignment_has_no_errors():
    errors = validate_form("Chemistry Lab", "Chemistry", "2026-09-15", "2.5", "HIGH")
    assert errors == no_errors()
    assert is_valid(errors)


def test_valid_assignment_builds_the_dashboard_row():
    row = build_row("Chemistry Lab", "Chemistry", "2026-09-15", "2.5", "HIGH", TODAY)
    assert row == {
        "id": "",                       # not saved yet, so no database id
        "name": "Chemistry Lab",
        "subject": "Chemistry",
        "due": "Due in 6 days",
        "due_date": "2026-09-15",
        "due_pretty": "15 Sep 2026",
        "due_in_days": "6",
        "due_number": "6",
        "due_label": "days left",
        "hours": "2.5 hours",
        "priority": "HIGH",
        "risk": RISK_NOT_RATED,
    }


# ---------- Test B: an empty form ----------

def test_empty_form_reports_every_field():
    errors = validate_form("", "", "", "", "")
    assert set(errors) == set(FIELDS)
    assert all(errors.values())
    assert not is_valid(errors)


def test_whitespace_only_counts_as_empty():
    errors = validate_form("   ", "  ", "2026-09-15", "1", "LOW")
    assert errors["name"] and errors["subject"]
    assert not errors["due"] and not errors["hours"] and not errors["priority"]


# ---------- Test C: decimal hours ----------

def test_decimal_hours_are_accepted():
    for hours, words in [("1", "1 hour"), ("1.5", "1.5 hours"), ("2", "2 hours"), ("5", "5 hours"), ("0.25", "0.25 hours")]:
        assert validate_form("A", "S", "2026-09-15", hours, "LOW")["hours"] == ""
        assert build_row("A", "S", "2026-09-15", hours, "LOW", TODAY)["hours"] == words


def test_hours_validation_messages():
    assert "number" in validate_form("A", "S", "2026-09-15", "lots", "LOW")["hours"]
    assert "negative" in validate_form("A", "S", "2026-09-15", "-1", "LOW")["hours"]
    assert validate_form("A", "S", "2026-09-15", "0", "LOW")["hours"] == ""   # zero is allowed


# ---------- The other fields ----------

def test_due_date_must_be_a_real_date():
    assert validate_form("A", "S", "next friday", "1", "LOW")["due"]
    assert validate_form("A", "S", "2026-13-40", "1", "LOW")["due"]
    assert validate_form("A", "S", "2026-09-15", "1", "LOW")["due"] == ""


def test_priority_must_be_one_of_the_three():
    assert validate_form("A", "S", "2026-09-15", "1", "urgent")["priority"]
    for p in ("LOW", "MEDIUM", "HIGH"):
        assert validate_form("A", "S", "2026-09-15", "1", p)["priority"] == ""


def test_due_wording_covers_today_tomorrow_and_overdue():
    assert build_row("A", "S", "2026-09-09", "1", "LOW", TODAY)["due"] == "Due today"
    assert build_row("A", "S", "2026-09-10", "1", "LOW", TODAY)["due"] == "Due tomorrow"
    assert build_row("A", "S", "2026-09-08", "1", "LOW", TODAY)["due"] == "Overdue by 1 day"
    assert build_row("A", "S", "2026-09-06", "1", "LOW", TODAY)["due"] == "Overdue by 3 days"
    assert build_row("A", "S", "2026-09-06", "1", "LOW", TODAY)["due_in_days"] == "0"


# ---------- Overdue dates (v1.1) ----------

def test_due_notice_only_for_dates_already_passed():
    assert due_notice("2026-09-08", TODAY) == OVERDUE_NOTICE            # yesterday
    assert due_notice("2026-08-01", TODAY) == OVERDUE_NOTICE            # long ago
    assert due_notice("2026-09-09", TODAY) == ""                        # today
    assert due_notice("2026-09-10", TODAY) == ""                        # tomorrow
    assert due_notice("", TODAY) == ""                                  # nothing chosen yet
    assert due_notice("not a date", TODAY) == ""                        # the error covers it
    assert "already passed" in OVERDUE_NOTICE and "as soon as possible" in OVERDUE_NOTICE


def test_due_notice_does_not_block_saving():
    errors = validate_form("Late essay", "History", "2026-09-06", "1", "HIGH")
    assert is_valid(errors)


def test_due_countdown_gives_a_number_and_a_label():
    assert due_countdown(-3) == ("3", "days overdue")
    assert due_countdown(-1) == ("1", "day overdue")
    assert due_countdown(0) == ("Today", "due")
    assert due_countdown(1) == ("1", "day left")
    assert due_countdown(6) == ("6", "days left")


def test_rows_carry_the_countdown_and_keep_the_old_wording():
    cases = {
        "2026-09-06": ("3", "days overdue", "Overdue by 3 days"),
        "2026-09-08": ("1", "day overdue", "Overdue by 1 day"),
        "2026-09-09": ("Today", "due", "Due today"),
        "2026-09-10": ("1", "day left", "Due tomorrow"),
        "2026-09-15": ("6", "days left", "Due in 6 days"),
    }
    for due, (number, label, words) in cases.items():
        row = build_row("A", "S", due, "1", "LOW", TODAY)
        assert (row["due_number"], row["due_label"]) == (number, label)
        assert row["due"] == words
        assert row["due_pretty"] == date.fromisoformat(due).strftime("%d %b %Y")
    # An overdue card never reads as "0 days left".
    row = build_row("A", "S", "2026-09-06", "1", "LOW", TODAY)
    assert (row["due_number"], row["due_label"]) != ("0", "days left")


# ---------- The list the dashboard shows ----------

def test_rows_are_sorted_soonest_first_and_stable():
    a = build_row("A", "S", "2026-09-15", "1", "LOW", TODAY)      # 6 days
    b = build_row("B", "S", "2026-09-11", "1", "LOW", TODAY)      # 2 days
    c = build_row("C", "S", "2026-09-15", "1", "LOW", TODAY)      # 6 days
    assert [r["name"] for r in sorted_by_urgency([a, b, c])] == ["B", "A", "C"]


def test_total_hours_sums_the_rows():
    rows = [
        build_row("A", "S", "2026-09-15", "2.5", "LOW", TODAY),
        build_row("B", "S", "2026-09-15", "1", "LOW", TODAY),
        build_row("C", "S", "2026-09-15", "0.25", "LOW", TODAY),
    ]
    assert total_hours(rows) == 3.75
