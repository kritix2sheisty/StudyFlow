"""
tests/test_dashboard.py
A smoke test for the Reflex pages: each one builds, and the state
exposes the vars the pages bind to. This does not start a browser;
it catches the errors that would stop reflex run before it serves
anything.
"""

from StudyFlow.StudyFlow import DashboardState, app, assignments_page, index, progress_page, schedule_page


def test_every_page_builds():
    for page in (index, assignments_page, schedule_page, progress_page):
        assert page() is not None
    assert app is not None


def test_state_exposes_the_vars_the_pages_bind_to():
    for name in (
        "assignments", "assignment_count", "required_hours", "greeting", "today_label",
        "completed_names", "completed_count",
        "slots", "slot_hours",
        "has_plan", "plan_stale", "plan_message", "plan_days", "today_plan", "plan_statuses",
        "plan_required", "plan_scheduled", "plan_unscheduled", "plan_completion", "progress_value",
    ):
        assert hasattr(DashboardState, name), name


def test_no_sample_data_module_remains():
    import importlib.util
    assert importlib.util.find_spec("StudyFlow.sample_data") is None
