"""
StudyFlow/StudyFlow.py
The StudyFlow dashboard, built with Reflex.

This is the first real screen of the app. It shows SAMPLE data from
sample_data.py so the design can be judged before the page is wired
to the StudyFlow engine. None of the scheduling logic lives here; it
stays in scheduler.py, schedule_builder.py, schedule_analyzer.py and
schedule_optimizer.py, and will be reached through study_plan.py.

Page structure (top to bottom):
    header            title, subtitle, navigation
    welcome           greeting and one-line explanation
    overview cards    assignments / required / scheduled / completion
    upcoming          one card per assignment with priority and risk
    today's plan      the day's study blocks in time order
    progress          how much of the required work is scheduled
    actions           Generate Study Plan (primary), Add Assignment

Run with:  reflex run
"""

from datetime import datetime

import reflex as rx

from StudyFlow.sample_data import (
    SAMPLE_ASSIGNMENTS,
    SAMPLE_OVERVIEW,
    SAMPLE_PROGRESS,
    SAMPLE_TODAY_PLAN,
)

# Badge colours for the two labels a student scans first.
PRIORITY_COLORS = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
RISK_COLORS = {"HIGH RISK": "red", "MODERATE RISK": "orange", "LOW RISK": "green", "CRITICAL RISK": "crimson"}

NAV_ITEMS = ["Dashboard", "Assignments", "Schedule", "Progress"]


# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------

class DashboardState(rx.State):
    """
    What the dashboard shows. Today the values are the sample data;
    connecting the engine means replacing how these are loaded, not
    how the page renders them.
    """

    overview: dict[str, str] = SAMPLE_OVERVIEW
    assignments: list[dict[str, str]] = SAMPLE_ASSIGNMENTS
    today_plan: list[dict[str, str]] = SAMPLE_TODAY_PLAN
    progress: dict[str, str] = SAMPLE_PROGRESS

    @rx.var
    def greeting(self) -> str:
        hour = datetime.now().hour
        if hour < 12:
            return "Good morning!"
        if hour < 18:
            return "Good afternoon!"
        return "Good evening!"

    @rx.var
    def progress_value(self) -> int:
        return int(self.progress["percent"])

    def generate_study_plan(self):
        """Not connected yet. The engine hook-up is the next step."""
        return rx.toast.info("Generating a plan will connect to the StudyFlow engine next.")

    def add_assignment(self):
        """Not connected yet."""
        return rx.toast.info("Adding assignments is coming soon.")


# ---------------------------------------------------------------------
# 1. Header
# ---------------------------------------------------------------------

def nav_link(label: str, active: bool = False) -> rx.Component:
    return rx.link(
        label,
        href="#",
        weight="medium",
        color=rx.cond(active, rx.color("accent", 11), rx.color("gray", 11)),
        underline="none",
        padding_x="3",
        padding_y="1",
        border_radius="6px",
        background=rx.cond(active, rx.color("accent", 3), "transparent"),
    )


def header() -> rx.Component:
    return rx.flex(
        rx.vstack(
            rx.hstack(
                rx.icon("book_open", size=28, color=rx.color("accent", 9)),
                rx.heading("StudyFlow", size="7"),
                align="center", spacing="2",
            ),
            rx.text("Your Personal Study Planner", color_scheme="gray"),
            spacing="0", align="start",
        ),
        rx.spacer(),
        rx.hstack(
            *[nav_link(item, active=(item == "Dashboard")) for item in NAV_ITEMS],
            spacing="1", wrap="wrap",
        ),
        width="100%", align="center", wrap="wrap", gap="4",
        padding_y="4",
        border_bottom=f"1px solid {rx.color('gray', 5)}",
    )


# ---------------------------------------------------------------------
# 2. Welcome
# ---------------------------------------------------------------------

def welcome() -> rx.Component:
    return rx.vstack(
        rx.heading(DashboardState.greeting, " Here's your study overview.", size="6"),
        rx.text(
            "StudyFlow keeps your assignments, deadlines and free time in one place, "
            "and turns them into a study plan you can actually follow.",
            color_scheme="gray", size="3",
        ),
        spacing="1", align="start",
    )


# ---------------------------------------------------------------------
# 3. Overview cards
# ---------------------------------------------------------------------

def overview_card(label: str, value: rx.Var, unit: str, icon: str, color: str) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=22, color=rx.color(color, 9)),
                padding="3", border_radius="10px", background=rx.color(color, 3),
            ),
            rx.vstack(
                rx.text(label, size="2", color_scheme="gray"),
                rx.heading(value, unit, size="6"),
                spacing="0", align="start",
            ),
            spacing="3", align="center",
        ),
        size="3",
    )


def overview_cards() -> rx.Component:
    o = DashboardState.overview
    return rx.grid(
        overview_card("Assignments", o["assignments"], "", "book_open", "blue"),
        overview_card("Required Hours", o["required_hours"], "h", "clock", "orange"),
        overview_card("Scheduled Hours", o["scheduled_hours"], "h", "calendar", "green"),
        overview_card("Completion", o["completion"], "%", "trending_up", "purple"),
        columns=rx.breakpoints(initial="1", sm="2", lg="4"),
        spacing="4", width="100%",
    )


# ---------------------------------------------------------------------
# 4. Upcoming assignments
# ---------------------------------------------------------------------

def priority_badge(priority: rx.Var) -> rx.Component:
    return rx.badge(priority, variant="soft", color_scheme=rx.match(priority, *PRIORITY_COLORS.items(), "gray"))


def risk_badge(risk: rx.Var) -> rx.Component:
    return rx.badge(risk, variant="solid", color_scheme=rx.match(risk, *RISK_COLORS.items(), "gray"))


def assignment_card(a: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            # Due date and risk first: they are what a student scans for.
            rx.hstack(
                rx.text(a["due"], weight="bold", color=rx.color("accent", 11)),
                rx.spacer(),
                risk_badge(a["risk"]),
                width="100%", align="center",
            ),
            rx.heading(a["name"], size="4"),
            rx.text(a["subject"], size="2", color_scheme="gray"),
            rx.hstack(
                rx.hstack(rx.icon("clock", size=14), rx.text(a["hours"], size="2"), spacing="1", align="center"),
                rx.spacer(),
                priority_badge(a["priority"]),
                width="100%", align="center",
            ),
            spacing="2", align="start", width="100%",
        ),
        size="3",
    )


def upcoming_assignments() -> rx.Component:
    return section(
        "Upcoming Assignments",
        rx.grid(
            rx.foreach(DashboardState.assignments, assignment_card),
            columns=rx.breakpoints(initial="1", md="2", lg="3"),
            spacing="4", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 5. Today's study plan
# ---------------------------------------------------------------------

def plan_row(item: dict) -> rx.Component:
    return rx.hstack(
        rx.text(item["time"], size="2", color_scheme="gray", min_width="10em"),
        rx.cond(
            item["is_break"] == "yes",
            rx.badge("Break", variant="outline", color_scheme="gray"),
            rx.text(item["label"], weight="medium"),
        ),
        spacing="4", align="center", width="100%",
        padding_y="2",
        border_bottom=f"1px solid {rx.color('gray', 4)}",
    )


def todays_plan() -> rx.Component:
    return section(
        "Today's Study Plan",
        rx.card(
            rx.vstack(rx.foreach(DashboardState.today_plan, plan_row), spacing="0", width="100%"),
            size="3", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 6. Progress
# ---------------------------------------------------------------------

def progress_section() -> rx.Component:
    p = DashboardState.progress
    return section(
        "Progress",
        rx.card(
            rx.vstack(
                rx.text(p["percent"], "% of required study work scheduled", weight="medium"),
                rx.progress(value=DashboardState.progress_value, size="3", width="100%"),
                rx.hstack(
                    rx.text(p["scheduled_hours"], " hours scheduled", size="2", color_scheme="gray"),
                    rx.text("·", size="2", color_scheme="gray"),
                    rx.text(p["remaining_hours"], " hours remaining", size="2", color_scheme="gray"),
                    spacing="2", wrap="wrap",
                ),
                spacing="3", align="start", width="100%",
            ),
            size="3", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 7 and 8. Actions
# ---------------------------------------------------------------------

def actions() -> rx.Component:
    return rx.flex(
        rx.button(
            rx.icon("sparkles", size=18), "Generate Study Plan",
            size="3", on_click=DashboardState.generate_study_plan,
        ),
        rx.button(
            rx.icon("plus", size=18), "Add Assignment",
            size="3", variant="soft", on_click=DashboardState.add_assignment,
        ),
        gap="3", wrap="wrap", justify="center", width="100%",
    )


# ---------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------

def section(title: str, body: rx.Component) -> rx.Component:
    """A titled block of the dashboard."""
    return rx.vstack(rx.heading(title, size="5"), body, spacing="3", align="start", width="100%")


def index() -> rx.Component:
    return rx.container(
        rx.vstack(
            header(),
            welcome(),
            overview_cards(),
            actions(),
            upcoming_assignments(),
            # Side by side on wide screens, stacked on narrow ones.
            rx.grid(
                todays_plan(),
                progress_section(),
                columns=rx.breakpoints(initial="1", lg="2"),
                spacing="5", width="100%",
            ),
            spacing="7", width="100%", padding_bottom="8",
        ),
        size="4", padding_x="4",
    )


app = rx.App(
    theme=rx.theme(accent_color="indigo", radius="large"),
)
app.add_page(index, title="StudyFlow")
