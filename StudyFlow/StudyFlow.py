"""
StudyFlow/StudyFlow.py
The StudyFlow dashboard, built with Reflex.

This is the first real screen of the app. It shows SAMPLE data from
sample_data.py so the design can be judged before the page is wired
to the StudyFlow engine. None of the scheduling logic lives here; it
stays in scheduler.py, schedule_builder.py, schedule_analyzer.py and
schedule_optimizer.py, and will be reached through study_plan.py.

Page structure (top to bottom):
    header            logo, title, navigation pills, theme toggle
    welcome           greeting, today's date, one-line explanation
    overview cards    assignments / required / scheduled / completion
    call to action    Generate Study Plan (primary), Add Assignment
    upcoming          one card per assignment with priority and risk
    today's plan      the day's study blocks as a timeline
    progress          how much of the required work is scheduled

Design notes: due date and risk are the first things on each
assignment card because they are what a student scans for; every
colour comes from the theme palette (rx.color) so light and dark
modes both work; cards lift slightly on hover to feel interactive.

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

# Badge and accent colours for the two labels a student scans first.
PRIORITY_COLORS = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
RISK_COLORS = {"CRITICAL RISK": "crimson", "HIGH RISK": "red", "MODERATE RISK": "orange", "LOW RISK": "green"}
RISK_BORDERS = {risk: f"4px solid var(--{color}-9)" for risk, color in RISK_COLORS.items()}
RISK_TINTS = {risk: f"var(--{color}-3)" for risk, color in RISK_COLORS.items()}    # strip background
RISK_INK = {risk: f"var(--{color}-11)" for risk, color in RISK_COLORS.items()}     # strip text

NAV_ITEMS = ["Dashboard", "Assignments", "Schedule", "Progress"]

# Shared card styling: a subtle border that brightens on hover. No motion.
CARD_STYLE = {
    "border": "1px solid var(--gray-5)",
    "transition": "border-color 0.15s ease",
    "_hover": {"border_color": "var(--gray-8)"},
}

# Responsive helpers: phones get tighter spacing and smaller type.
PAGE_PADDING_X = rx.breakpoints(initial="3", md="5")
SECTION_GAP = rx.breakpoints(initial="6", md="8")
GRID_GAP = rx.breakpoints(initial="3", md="4")
BIG_NUMBER = rx.breakpoints(initial="6", md="8")
TAP_WIDTH = rx.breakpoints(initial="100%", sm="auto")


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
            return "Good morning"
        if hour < 18:
            return "Good afternoon"
        return "Good evening"

    @rx.var
    def today_label(self) -> str:
        return datetime.now().strftime("%A, %d %B")

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
# Small reusable pieces
# ---------------------------------------------------------------------

def eyebrow(text: str) -> rx.Component:
    """A small, spaced-out label above a value or section."""
    return rx.text(text, size="1", weight="medium", color_scheme="gray",
                   letter_spacing="0.08em", style={"text_transform": "uppercase"})


def section(title: str, subtitle: str, body: rx.Component) -> rx.Component:
    """A titled block of the dashboard with a one-line subtitle."""
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5"),
            rx.text(subtitle, size="2", color_scheme="gray"),
            spacing="0", align="start",
        ),
        body,
        spacing="4", align="start", width="100%",
    )


def priority_badge(priority: rx.Var) -> rx.Component:
    return rx.badge(priority, variant="soft", radius="full",
                    color_scheme=rx.match(priority, *PRIORITY_COLORS.items(), "gray"))


def risk_badge(risk: rx.Var) -> rx.Component:
    return rx.badge(risk, variant="solid", radius="full",
                    color_scheme=rx.match(risk, *RISK_COLORS.items(), "gray"))


# ---------------------------------------------------------------------
# 1. Header
# ---------------------------------------------------------------------

def nav_link(label: str, active: bool = False) -> rx.Component:
    """A navigation pill. The active one is solid accent so it is unmistakable."""
    return rx.link(
        label, href="#", size="2", weight="medium", underline="none",
        color="white" if active else rx.color("gray", 12),
        background=rx.color("accent", 9) if active else "transparent",
        padding_x="3", padding_y="1", border_radius="999px",
        style={} if active else {"_hover": {"background": rx.color("gray", 4)}},
    )


def header() -> rx.Component:
    return rx.flex(
        rx.hstack(
            rx.box(
                rx.icon("book_open", size=20, color="white"),
                padding="2", border_radius="10px", background=rx.color("accent", 9),
                display="flex", align_items="center",
            ),
            rx.vstack(
                rx.heading("StudyFlow", size="6", line_height="1"),
                rx.text("Your Personal Study Planner", size="1", color_scheme="gray"),
                spacing="1", align="start",
            ),
            align="center", spacing="3",
        ),
        rx.spacer(),
        rx.hstack(
            rx.hstack(
                *[nav_link(item, active=(item == "Dashboard")) for item in NAV_ITEMS],
                spacing="1", wrap="wrap",
                padding="1", border_radius="999px", background=rx.color("gray", 2),
            ),
            rx.color_mode.button(size="2", variant="ghost"),
            spacing="3", align="center",
        ),
        width="100%", align="center", wrap="wrap", gap="4", padding_y="4",
        border_bottom=f"1px solid {rx.color('gray', 4)}",
    )


# ---------------------------------------------------------------------
# 2. Welcome
# ---------------------------------------------------------------------

def welcome() -> rx.Component:
    return rx.flex(
        rx.vstack(
            eyebrow(DashboardState.today_label),
            rx.heading(DashboardState.greeting, "! Here's your study overview.",
                       size=rx.breakpoints(initial="6", md="8")),
            rx.text(
                "StudyFlow keeps your assignments, deadlines and free time in one place, "
                "and turns them into a study plan you can actually follow.",
                size=rx.breakpoints(initial="2", md="3"), color_scheme="gray", max_width="40em",
            ),
            spacing="2", align="start",
        ),
        width="100%",
    )


# ---------------------------------------------------------------------
# 3. Overview cards
# ---------------------------------------------------------------------

def overview_card(label: str, value: rx.Var, unit: str, hint: str, icon: str, color: str) -> rx.Component:
    """
    One statistic. Compact on phones (two per row, smaller number, hint
    hidden) and roomier on desktop (four per row, hint shown).
    """
    return rx.card(
        rx.vstack(
            rx.hstack(
                eyebrow(label),
                rx.spacer(),
                rx.box(
                    rx.icon(icon, size=16, color=rx.color(color, 9)),
                    padding="1", border_radius="6px", background=rx.color(color, 3),
                    display="flex", align_items="center",
                ),
                width="100%", align="center",
            ),
            rx.heading(value, unit, size=BIG_NUMBER, line_height="1"),
            rx.text(hint, size="1", color_scheme="gray", display=rx.breakpoints(initial="none", md="block")),
            spacing="2", align="start", width="100%",
        ),
        size=rx.breakpoints(initial="2", md="3"), style=CARD_STYLE,
    )


def overview_cards() -> rx.Component:
    o = DashboardState.overview
    return rx.grid(
        overview_card("Assignments", o["assignments"], "", "active this week", "book_open", "blue"),
        overview_card("Required", o["required_hours"], "h", "of work remaining", "clock", "orange"),
        overview_card("Scheduled", o["scheduled_hours"], "h", "placed in your plan", "calendar", "green"),
        overview_card("Completion", o["completion"], "%", "of required work scheduled", "trending_up", "purple"),
        columns=rx.breakpoints(initial="2", lg="4"),
        spacing=GRID_GAP, width="100%",
    )


# ---------------------------------------------------------------------
# 4. Call to action
# ---------------------------------------------------------------------

def call_to_action() -> rx.Component:
    """The primary action, given its own highlighted band so it is the focus of the page."""
    return rx.card(
        rx.flex(
            rx.vstack(
                rx.heading("Ready to plan your week?", size="5"),
                rx.text("StudyFlow places your work around your free time and flags anything at risk.",
                        size="2", color_scheme="gray"),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.flex(
                rx.button(rx.icon("sparkles", size=18), "Generate Study Plan",
                          size="3", width=TAP_WIDTH, on_click=DashboardState.generate_study_plan),
                rx.button(rx.icon("plus", size=18), "Add Assignment",
                          size="3", width=TAP_WIDTH, variant="soft", on_click=DashboardState.add_assignment),
                gap="3", wrap="wrap", width=TAP_WIDTH,
            ),
            width="100%", align="center", wrap="wrap", gap="4",
        ),
        size="3", width="100%",
        background=rx.color("accent", 2),
        border=f"1px solid {rx.color('accent', 5)}",
    )


# ---------------------------------------------------------------------
# 5. Upcoming assignments
# ---------------------------------------------------------------------

def assignment_card(a: dict) -> rx.Component:
    """
    Built to be scanned, not read. The top strip is tinted in the
    risk colour and holds the two things a student looks for first:
    how many days are left, large, and the risk badge. The body is
    the name and subject. The footer is the detail: hours and priority.
    """
    ink = rx.match(a["risk"], *RISK_INK.items(), "var(--gray-11)")
    return rx.box(
        # Strip: due countdown on the left, risk badge on the right.
        rx.hstack(
            rx.hstack(
                rx.heading(a["due_in_days"], size="8", line_height="1", color=ink),
                rx.vstack(
                    rx.text("days", size="2", weight="bold", color=ink, line_height="1"),
                    rx.text("left", size="2", weight="bold", color=ink, line_height="1"),
                    spacing="1", align="start",
                ),
                spacing="2", align="center",
            ),
            rx.spacer(),
            risk_badge(a["risk"]),
            width="100%", align="center",
            padding_x="4", padding_y="3",
            background=rx.match(a["risk"], *RISK_TINTS.items(), "var(--gray-3)"),
        ),
        # Body: what it is.
        rx.vstack(
            rx.heading(a["name"], size="4"),
            rx.text(a["subject"], size="2", color_scheme="gray"),
            spacing="0", align="start", width="100%",
            padding_x="4", padding_top="3", padding_bottom="2",
        ),
        # Footer: the detail.
        rx.hstack(
            rx.hstack(rx.icon("clock", size=14, color=rx.color("gray", 10)),
                      rx.text(a["hours"], size="2", color_scheme="gray"), spacing="1", align="center"),
            rx.spacer(),
            priority_badge(a["priority"]),
            width="100%", align="center",
            padding_x="4", padding_bottom="4",
        ),
        width="100%",
        background=rx.color("gray", 2),
        border=f"1px solid {rx.color('gray', 5)}",
        border_left=rx.match(a["risk"], *RISK_BORDERS.items(), "4px solid var(--gray-6)"),
        border_radius="12px", overflow="hidden",
        style=CARD_STYLE,
    )


def upcoming_assignments() -> rx.Component:
    return section(
        "Upcoming Assignments",
        "What's due next, most urgent first.",
        rx.grid(
            rx.foreach(DashboardState.assignments, assignment_card),
            columns=rx.breakpoints(initial="1", md="2", lg="3"),
            spacing="4", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 6. Today's study plan
# ---------------------------------------------------------------------

def plan_row(item: dict) -> rx.Component:
    """
    One block of the day. Time sits in its own fixed column so the
    activities line up; breaks are tinted and labelled so they read
    as rest, not as work.
    """
    is_break = item["is_break"] == "yes"
    return rx.hstack(
        rx.text(item["time"], size="1", weight="medium", color_scheme="gray",
                min_width="10.5em", style={"font_variant_numeric": "tabular-nums"}),
        rx.box(
            width="3px", height="1.6em", border_radius="999px", flex_shrink="0",
            background=rx.cond(is_break, rx.color("gray", 6), rx.color("accent", 9)),
        ),
        rx.cond(
            is_break,
            rx.hstack(rx.icon("coffee", size=14, color=rx.color("gray", 10)),
                      rx.text("Break", size="2", color_scheme="gray"), spacing="1", align="center"),
            rx.text(item["label"], size="3", weight="bold"),
        ),
        spacing="3", align="center", width="100%",
        padding_x="3", padding_y="2", border_radius="8px",
        background=rx.cond(is_break, rx.color("gray", 3), "transparent"),
    )


def todays_plan() -> rx.Component:
    return section(
        "Today's Study Plan",
        "Your blocks for today, in order.",
        rx.card(
            rx.vstack(rx.foreach(DashboardState.today_plan, plan_row), spacing="0", width="100%"),
            size="3", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 7. Progress
# ---------------------------------------------------------------------

def progress_stat(label: str, value: rx.Var) -> rx.Component:
    return rx.vstack(eyebrow(label), rx.heading(value, " h", size="5"), spacing="1", align="start")


def progress_section() -> rx.Component:
    p = DashboardState.progress
    return section(
        "Progress",
        "How much of your required work has a place in the plan.",
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading(p["percent"], "%", size=BIG_NUMBER, line_height="1",
                               color=rx.color("accent", 11)),
                    rx.text("of required study work scheduled", size="2", color_scheme="gray"),
                    spacing="3", align="end",
                ),
                rx.progress(value=DashboardState.progress_value, size="3", width="100%"),
                rx.hstack(
                    rx.text("0%", size="1", color_scheme="gray"),
                    rx.spacer(),
                    rx.text("100%", size="1", color_scheme="gray"),
                    width="100%",
                ),
                rx.hstack(
                    progress_stat("Scheduled", p["scheduled_hours"]),
                    progress_stat("Remaining", p["remaining_hours"]),
                    spacing="8",
                ),
                spacing="3", align="start", width="100%",
            ),
            size="3", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------

def index() -> rx.Component:
    return rx.box(
        rx.container(
            rx.vstack(
                header(),
                welcome(),
                overview_cards(),
                call_to_action(),
                upcoming_assignments(),
                # Side by side on wide screens, stacked on narrow ones.
                rx.grid(
                    todays_plan(),
                    progress_section(),
                    columns=rx.breakpoints(initial="1", lg="2"),
                    spacing=SECTION_GAP, width="100%",
                ),
                spacing=SECTION_GAP, width="100%", padding_bottom="9",
            ),
            size="4", padding_x=PAGE_PADDING_X,
        ),
        background=rx.color("gray", 1), min_height="100vh",
    )


app = rx.App(
    theme=rx.theme(accent_color="indigo", gray_color="slate", radius="large", scaling="100%"),
)
app.add_page(index, title="StudyFlow")
