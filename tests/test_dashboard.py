"""
tests/test_dashboard.py
A smoke test for the Reflex dashboard: the module imports, the page
builds, and the sample data has the shape the page expects. This does
not start a browser; it catches the errors that would stop reflex run
before it serves anything.
"""

from StudyFlow import sample_data
from StudyFlow.StudyFlow import DashboardState, app, index


def test_dashboard_page_builds():
    page = index()
    assert page is not None
    assert app is not None


def test_sample_data_has_the_fields_the_page_reads():
    for a in sample_data.SAMPLE_ASSIGNMENTS:
        assert set(a) == {"name", "subject", "due", "due_in_days", "hours", "priority", "risk"}
        assert a["due_in_days"].isdigit()
    for item in sample_data.SAMPLE_TODAY_PLAN:
        assert set(item) == {"time", "label", "is_break"}
    assert set(sample_data.SAMPLE_OVERVIEW) == {"assignments", "required_hours", "scheduled_hours", "completion"}
    assert set(sample_data.SAMPLE_PROGRESS) == {"percent", "scheduled_hours", "remaining_hours"}


def test_sample_data_values_are_strings():
    rows = sample_data.SAMPLE_ASSIGNMENTS + sample_data.SAMPLE_TODAY_PLAN
    rows += [sample_data.SAMPLE_OVERVIEW, sample_data.SAMPLE_PROGRESS]
    for row in rows:
        assert all(isinstance(v, str) for v in row.values())


def test_state_exposes_the_vars_the_page_binds_to():
    for name in ("overview", "assignments", "today_plan", "progress", "greeting", "progress_value"):
        assert hasattr(DashboardState, name)
