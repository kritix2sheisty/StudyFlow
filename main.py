"""
main.py
Command-line interface for StudyFlow — AI Student Scheduler.

Run with: python main.py
"""

from datetime import date, datetime

import storage

# The CLI has no login yet: it acts as the built-in student.
USER = storage.DEFAULT_USER_ID
from models import Assignment, Class, Priority, Test, TimeSlot, Weekday
from scheduler import prioritize_assignments
from schedule_analyzer import format_analysis
from study_plan import format_study_plan, generate_study_plan

BANNER = """
=============================
        STUDYFLOW
============================="""


def prompt_date(label: str) -> date:
    while True:
        raw = input(f"{label} (YYYY-MM-DD): ").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Invalid date format, try again (e.g. 2026-09-01).")


def prompt_priority(label: str) -> Priority:
    print(f"{label}: 1=Low  2=Medium  3=High")
    while True:
        raw = input("  Choice: ").strip()
        if raw in ("1", "2", "3"):
            return Priority(int(raw))
        print("  Please enter 1, 2, or 3.")


def prompt_float(label: str) -> float:
    while True:
        raw = input(f"{label}: ").strip()
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number.")


def prompt_int_range(label: str, lo: int, hi: int) -> int:
    while True:
        raw = input(f"{label} ({lo}-{hi}): ").strip()
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"  Please enter a number between {lo} and {hi}.")


def add_class_flow() -> None:
    name = input("Class name (e.g. Mathematics): ").strip()
    code = input("Class code (optional, e.g. MATH-201): ").strip()
    storage.add_class(Class(name=name, code=code))
    print(f"Added class: {name}")


def add_assignment_flow() -> None:
    name = input("Assignment name: ").strip()
    subject = input("Subject: ").strip()
    due = prompt_date("Due date")
    hours = prompt_float("Estimated time (hours)")
    priority = prompt_priority("Priority")
    storage.add_assignment(USER, Assignment(
        name=name, subject=subject, due_date=due,
        estimated_hours=hours, priority=priority,
    ))
    print(f"Added assignment: {name}")


def add_test_flow() -> None:
    subject = input("Subject: ").strip()
    test_date = prompt_date("Test date")
    topics = input("Topics (comma-separated): ").strip()
    importance = prompt_priority("Importance")
    storage.add_test(Test(
        subject=subject, date=test_date, topics=topics, importance=importance,
    ))
    print(f"Added test: {subject}")


def add_time_slot_flow() -> None:
    print("Weekdays: monday, tuesday, wednesday, thursday, friday, saturday, sunday")
    while True:
        raw_day = input("Weekday: ").strip()
        try:
            weekday = Weekday.from_name(raw_day)
            break
        except KeyError:
            print("  Not a valid weekday, try again.")
    start_hour = prompt_int_range("Start hour (24h clock)", 0, 23)
    end_hour = prompt_int_range("End hour (24h clock)", start_hour + 1, 24)
    storage.add_time_slot(USER, TimeSlot(weekday=weekday, start_hour=start_hour, end_hour=end_hour))
    print("Added time slot.")


def prompt_id(label: str) -> int:
    while True:
        raw = input(f"{label} id: ").strip()
        if raw.isdigit():
            return int(raw)
        print("  Please enter a numeric id (see the view list for ids).")


def edit_assignment_flow() -> None:
    view_list(storage.list_assignments(USER), "No assignments to edit.")
    assignment_id = prompt_id("Assignment")
    existing = next((a for a in storage.list_assignments(USER) if a.id == assignment_id), None)
    if not existing:
        print("  No assignment with that id.")
        return
    print("Leave a field blank to keep its current value.")
    name = input(f"Name [{existing.name}]: ").strip() or existing.name
    subject = input(f"Subject [{existing.subject}]: ").strip() or existing.subject
    raw_due = input(f"Due date [{existing.due_date.isoformat()}] (YYYY-MM-DD): ").strip()
    due = datetime.strptime(raw_due, "%Y-%m-%d").date() if raw_due else existing.due_date
    raw_hours = input(f"Estimated hours [{existing.estimated_hours}]: ").strip()
    hours = float(raw_hours) if raw_hours else existing.estimated_hours
    raw_priority = input(f"Priority 1=Low 2=Medium 3=High [{int(existing.priority)}]: ").strip()
    priority = Priority(int(raw_priority)) if raw_priority in ("1", "2", "3") else existing.priority
    updated = Assignment(id=assignment_id, name=name, subject=subject, due_date=due,
                          estimated_hours=hours, priority=priority, completed=existing.completed)
    storage.update_assignment(USER, updated)
    print("Assignment updated.")


def delete_assignment_flow() -> None:
    view_list(storage.list_assignments(USER), "No assignments to delete.")
    assignment_id = prompt_id("Assignment")
    if storage.delete_assignment(USER, assignment_id):
        print("Assignment deleted.")
    else:
        print("  No assignment with that id.")


def toggle_assignment_complete_flow() -> None:
    view_list(storage.list_assignments(USER), "No assignments yet.")
    assignment_id = prompt_id("Assignment")
    existing = next((a for a in storage.list_assignments(USER) if a.id == assignment_id), None)
    if not existing:
        print("  No assignment with that id.")
        return
    storage.mark_assignment_complete(USER, assignment_id, not existing.completed)
    state = "incomplete" if existing.completed else "complete"
    print(f"Marked as {state}.")


def delete_class_flow() -> None:
    view_list(storage.list_classes(), "No classes to delete.")
    class_id = prompt_id("Class")
    if storage.delete_class(class_id):
        print("Class deleted.")
    else:
        print("  No class with that id.")


def delete_test_flow() -> None:
    view_list(storage.list_tests(), "No tests to delete.")
    test_id = prompt_id("Test")
    if storage.delete_test(test_id):
        print("Test deleted.")
    else:
        print("  No test with that id.")


def delete_time_slot_flow() -> None:
    view_list(storage.list_time_slots(USER), "No time slots to delete.")
    slot_id = prompt_id("Time slot")
    if storage.delete_time_slot(USER, slot_id):
        print("Time slot deleted.")
    else:
        print("  No time slot with that id.")


def view_list(items, empty_message: str) -> None:
    if not items:
        print(empty_message)
        return
    for item in items:
        print(f"  - {item}")


def generate_study_plan_flow() -> None:
    """The whole pipeline: prioritize, schedule, analyze, flag, report."""
    assignments = storage.list_assignments(USER, include_completed=False)
    slots = storage.list_time_slots(USER)
    plan = generate_study_plan(assignments, slots)
    print(format_study_plan(plan))
    if not slots:
        print("\nNo available study time yet — add some with option 4 to get a schedule.")


def schedule_analysis_flow() -> None:
    """The analysis report: totals, then status, hours and risk per assignment."""
    assignments = storage.list_assignments(USER, include_completed=False)
    slots = storage.list_time_slots(USER)
    plan = generate_study_plan(assignments, slots)
    print(format_analysis(plan.schedule, assignments, slots, today=plan.today))


def run_menu(title: str, options: dict, back_label: str = "Back") -> None:
    """
    Show a numbered menu and run the chosen action until the user
    picks 0. `options` maps a key to (label, action).
    """
    while True:
        print(title)
        for key, (label, _) in options.items():
            print(f"{key}. {label}")
        print(f"0. {back_label}")
        choice = input("Choose an option: ").strip()
        if choice == "0":
            return
        entry = options.get(choice)
        if entry:
            entry[1]()
        else:
            print("Invalid option, try again.")


def manage_classes() -> None:
    run_menu("\nMANAGE CLASSES", {
        "1": ("Add a class", add_class_flow),
        "2": ("View all classes", lambda: view_list(storage.list_classes(), "No classes yet.")),
        "3": ("Delete a class", delete_class_flow),
    })


def manage_assignments() -> None:
    run_menu("\nMANAGE ASSIGNMENTS", {
        "1": ("Add an assignment", add_assignment_flow),
        "2": ("View all assignments", lambda: view_list(storage.list_assignments(USER), "No assignments yet.")),
        "3": ("View assignments due in the next 7 days",
              lambda: view_list(storage.upcoming_assignments(USER, 7), "Nothing due in the next 7 days.")),
        "4": ("View prioritized assignment list",
              lambda: view_list(prioritize_assignments(storage.list_assignments(USER)),
                                "No active assignments to prioritize.")),
        "5": ("Edit an assignment", edit_assignment_flow),
        "6": ("Mark an assignment complete / incomplete", toggle_assignment_complete_flow),
        "7": ("Delete an assignment", delete_assignment_flow),
    })


def manage_tests() -> None:
    run_menu("\nMANAGE TESTS", {
        "1": ("Add a test", add_test_flow),
        "2": ("View all tests", lambda: view_list(storage.list_tests(), "No tests yet.")),
        "3": ("Delete a test", delete_test_flow),
    })


def manage_study_time() -> None:
    run_menu("\nMANAGE STUDY TIME", {
        "1": ("Add available study time", add_time_slot_flow),
        "2": ("View available time slots", lambda: view_list(storage.list_time_slots(USER), "No time slots yet.")),
        "3": ("Delete a time slot", delete_time_slot_flow),
    })


MAIN_MENU = {
    "1": ("Manage classes", manage_classes),
    "2": ("Manage assignments", manage_assignments),
    "3": ("Manage tests", manage_tests),
    "4": ("Manage study time", manage_study_time),
    "5": ("Generate study plan", generate_study_plan_flow),
    "6": ("View schedule analysis", schedule_analysis_flow),
}


def main() -> None:
    storage.init_db()
    run_menu(BANNER, MAIN_MENU, back_label="Exit")
    print("Goodbye!")


if __name__ == "__main__":
    main()
