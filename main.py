"""
main.py
Command-line interface for StudyFlow — AI Student Scheduler.

Run with: python main.py
"""

from datetime import date, datetime

import storage
from models import Assignment, Class, Priority, Test, TimeSlot, Weekday
from scheduler import prioritize_assignments
from schedule_builder import build_schedule, format_schedule

MENU = """
==============================
   StudyFlow — CLI
==============================
1. Add a class
2. Add an assignment
3. Add a test
4. Add available study time
5. View all classes
6. View all assignments
7. View assignments due in the next 7 days
8. View all tests
9. View available time slots
16. View prioritized assignment list
17. Build weekly schedule
10. Edit an assignment
11. Delete an assignment
12. Mark an assignment complete / incomplete
13. Delete a class
14. Delete a test
15. Delete a time slot
0. Exit
"""


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
    storage.add_assignment(Assignment(
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
    storage.add_time_slot(TimeSlot(weekday=weekday, start_hour=start_hour, end_hour=end_hour))
    print("Added time slot.")


def prompt_id(label: str) -> int:
    while True:
        raw = input(f"{label} id: ").strip()
        if raw.isdigit():
            return int(raw)
        print("  Please enter a numeric id (see the view list for ids).")


def edit_assignment_flow() -> None:
    view_list(storage.list_assignments(), "No assignments to edit.")
    assignment_id = prompt_id("Assignment")
    existing = next((a for a in storage.list_assignments() if a.id == assignment_id), None)
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
    storage.update_assignment(updated)
    print("Assignment updated.")


def delete_assignment_flow() -> None:
    view_list(storage.list_assignments(), "No assignments to delete.")
    assignment_id = prompt_id("Assignment")
    if storage.delete_assignment(assignment_id):
        print("Assignment deleted.")
    else:
        print("  No assignment with that id.")


def toggle_assignment_complete_flow() -> None:
    view_list(storage.list_assignments(), "No assignments yet.")
    assignment_id = prompt_id("Assignment")
    existing = next((a for a in storage.list_assignments() if a.id == assignment_id), None)
    if not existing:
        print("  No assignment with that id.")
        return
    storage.mark_assignment_complete(assignment_id, not existing.completed)
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
    view_list(storage.list_time_slots(), "No time slots to delete.")
    slot_id = prompt_id("Time slot")
    if storage.delete_time_slot(slot_id):
        print("Time slot deleted.")
    else:
        print("  No time slot with that id.")


def view_list(items, empty_message: str) -> None:
    if not items:
        print(empty_message)
        return
    for item in items:
        print(f"  - {item}")


def build_schedule_flow() -> None:
    assignments = storage.list_assignments(include_completed=False)
    slots = storage.list_time_slots()
    if not slots:
        print("No available time slots yet — add some first (option 4).")
        return
    result = build_schedule(assignments, slots)
    output = format_schedule(result)
    print(output if output else "Nothing to schedule.")


def main() -> None:
    storage.init_db()
    actions = {
        "1": add_class_flow,
        "2": add_assignment_flow,
        "3": add_test_flow,
        "4": add_time_slot_flow,
        "5": lambda: view_list(storage.list_classes(), "No classes yet."),
        "6": lambda: view_list(storage.list_assignments(), "No assignments yet."),
        "7": lambda: view_list(storage.upcoming_assignments(7), "Nothing due in the next 7 days."),
        "8": lambda: view_list(storage.list_tests(), "No tests yet."),
        "9": lambda: view_list(storage.list_time_slots(), "No time slots yet."),
        "16": lambda: view_list(
            prioritize_assignments(storage.list_assignments()),
            "No active assignments to prioritize."
        ),
        "17": lambda: build_schedule_flow(),
        "10": edit_assignment_flow,
        "11": delete_assignment_flow,
        "12": toggle_assignment_complete_flow,
        "13": delete_class_flow,
        "14": delete_test_flow,
        "15": delete_time_slot_flow,
    }

    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Goodbye!")
            break
        action = actions.get(choice)
        if action:
            action()
        else:
            print("Invalid option, try again.")


if __name__ == "__main__":
    main()
