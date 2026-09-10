"""
StudyFlow/sample_data.py
SAMPLE DATA for the dashboard while the UI is being designed.

Nothing in this file comes from the StudyFlow engine. It exists so the
dashboard has something realistic to show before it is connected to
the real backend (storage.py, study_plan.py, schedule_analyzer.py,
schedule_optimizer.py). When that connection is made, the dashboard
state will load real values and this file can be deleted.

Every value is a string, because the page only displays them.
"""

# The four overview cards.
SAMPLE_OVERVIEW = {
    "assignments": "3",
    "required_hours": "12.5",
    "scheduled_hours": "9.0",
    "completion": "72",
}

# Upcoming assignments, most urgent first.
# "due_in_days" is the bare number so the card can show it large;
# "due" is the same fact as a sentence.
SAMPLE_ASSIGNMENTS = [
    {
        "name": "Mathematics IA",
        "subject": "Pure Mathematics",
        "due": "Due in 3 days",
        "due_in_days": "3",
        "hours": "5 hours",
        "priority": "HIGH",
        "risk": "HIGH RISK",
    },
    {
        "name": "Computer Science Project",
        "subject": "Computer Science",
        "due": "Due in 6 days",
        "due_in_days": "6",
        "hours": "4 hours",
        "priority": "MEDIUM",
        "risk": "MODERATE RISK",
    },
    {
        "name": "Physics Lab Report",
        "subject": "Physics",
        "due": "Due in 8 days",
        "due_in_days": "8",
        "hours": "2 hours",
        "priority": "LOW",
        "risk": "LOW RISK",
    },
]

# Today's study plan, in time order. "is_break" marks rest periods.
SAMPLE_TODAY_PLAN = [
    {"time": "4:00 PM – 5:30 PM", "label": "Mathematics IA", "is_break": "no"},
    {"time": "5:30 PM – 5:45 PM", "label": "Break", "is_break": "yes"},
    {"time": "5:45 PM – 7:00 PM", "label": "Computer Science Project", "is_break": "no"},
]

# The progress section.
SAMPLE_PROGRESS = {
    "percent": "72",
    "scheduled_hours": "9.0",
    "remaining_hours": "3.5",
}
