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
    add assignment    a dialog; validated by StudyFlow/assignments.py,
                      new rows are held in State (storage comes next)

Design notes: due date and risk are the first things on each
assignment card because they are what a student scans for; every
colour comes from the theme palette (rx.color) so light and dark
modes both work; cards lift slightly on hover to feel interactive.

Run with:  reflex run
"""

from datetime import date, datetime

import reflex as rx

from storage import (
    add_assignment,
    delete_assignment,
    init_db,
    list_assignments,
    mark_assignment_complete,
    update_assignment,
)
from StudyFlow import assignments as forms
from StudyFlow.sample_data import (
    SAMPLE_OVERVIEW,
    SAMPLE_PROGRESS,
    SAMPLE_TODAY_PLAN,
)

# Make sure the SQLite database and its tables exist before the first
# assignment is added. init_db() is CREATE TABLE IF NOT EXISTS, so
# running it on every start is safe.
init_db()

# Badge and accent colours for the two labels a student scans first.
PRIORITY_COLORS = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
RISK_COLORS = {"CRITICAL RISK": "crimson", "HIGH RISK": "red", "MODERATE RISK": "orange", "LOW RISK": "green"}
RISK_BORDERS = {risk: f"4px solid var(--{color}-9)" for risk, color in RISK_COLORS.items()}
RISK_TINTS = {risk: f"var(--{color}-3)" for risk, color in RISK_COLORS.items()}    # strip background
RISK_INK = {risk: f"var(--{color}-11)" for risk, color in RISK_COLORS.items()}     # strip text

# Navigation: label -> route. Schedule and Progress are visual only until
# those pages exist.
NAV_ITEMS = {"Dashboard": "/", "Assignments": "/assignments", "Schedule": "#", "Progress": "#"}

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

    # Assignments come from the database (storage.py) and are loaded
    # when the page opens; see load_assignments. The other three are
    # still sample data until the scheduler is connected.
    assignments: list[dict[str, str]] = []
    overview: dict[str, str] = SAMPLE_OVERVIEW
    today_plan: list[dict[str, str]] = SAMPLE_TODAY_PLAN
    progress: dict[str, str] = SAMPLE_PROGRESS

    def load_assignments(self):
        """Read the active assignments from the database, soonest due first."""
        self.assignments = forms.rows_from(list_assignments(include_completed=False), date.today())

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

    # ---- Add Assignment form ----
    #
    # The form's values live here so the page can bind to them, and so
    # Cancel can clear them. Validation and row building are delegated
    # to StudyFlow/assignments.py, which has no Reflex in it and is
    # unit-tested on its own.

    form_open: bool = False
    form_name: str = ""
    form_subject: str = ""
    form_due: str = ""
    form_hours: str = ""
    form_priority: str = "MEDIUM"
    form_errors: dict[str, str] = forms.no_errors()

    @rx.var
    def assignment_count(self) -> str:
        return str(len(self.assignments))

    @rx.var
    def required_hours(self) -> str:
        return f"{forms.total_hours(self.assignments):g}"

    # Setters the inputs bind to (Reflex 0.9 no longer generates these).
    def set_form_name(self, value: str):
        self.form_name = value

    def set_form_subject(self, value: str):
        self.form_subject = value

    def set_form_due(self, value: str):
        self.form_due = value

    def set_form_hours(self, value: str):
        self.form_hours = value

    def set_form_priority(self, value: str):
        self.form_priority = value

    def open_form(self):
        self.form_errors = forms.no_errors()
        self.form_open = True

    def close_form(self):
        """Cancel: close and forget whatever was typed."""
        self.form_open = False
        self.form_name = ""
        self.form_subject = ""
        self.form_due = ""
        self.form_hours = ""
        self.form_priority = "MEDIUM"
        self.form_errors = forms.no_errors()
        self.form_save_error = ""
        self.editing_id = ""

    def set_form_open(self, is_open: bool):
        """Called when the dialog is dismissed by clicking outside or pressing Escape."""
        if is_open:
            self.open_form()
        else:
            self.close_form()

    # Set when saving to the database fails; shown at the top of the form.
    form_save_error: str = ""

    # The same dialog edits an existing assignment. When editing_id is
    # set, submit calls update_assignment() instead of add_assignment().
    editing_id: str = ""

    @rx.var
    def is_editing(self) -> bool:
        return self.editing_id != ""

    def open_edit(self, assignment_id: str):
        """Load the stored assignment into the form and open it in edit mode."""
        stored = next((a for a in list_assignments() if str(a.id) == assignment_id), None)
        if stored is None:
            return rx.toast.error("That assignment no longer exists.")
        self.open_form()
        self.editing_id = assignment_id
        self.form_name = stored.name
        self.form_subject = stored.subject
        self.form_due = stored.due_date.isoformat()
        self.form_hours = f"{stored.estimated_hours:g}"
        self.form_priority = stored.priority.name

    def submit_form(self):
        """
        Validate, build a real Assignment, save it through storage.py
        (add or update), reload the list from the database, and close.
        If saving fails, keep the form open with a plain message
        instead of a traceback.
        """
        values = (self.form_name, self.form_subject, self.form_due, self.form_hours, self.form_priority)
        self.form_errors = forms.validate_form(*values)
        self.form_save_error = ""
        if not forms.is_valid(self.form_errors):
            return
        assignment = forms.to_assignment(*values)
        try:
            if self.is_editing:
                assignment.id = int(self.editing_id)
                update_assignment(assignment)
                message = f"Saved changes to {assignment.name}."
            else:
                add_assignment(assignment)
                message = f"Added {assignment.name}."
        except Exception:
            self.form_save_error = "StudyFlow could not save that assignment. Please try again."
            return
        self.load_assignments()
        self.close_form()
        return rx.toast.success(message)

    # ---- Complete and delete ----

    def complete_assignment(self, assignment_id: str):
        """Mark it done; it leaves the active list but stays in the database."""
        mark_assignment_complete(int(assignment_id), True)
        self.load_assignments()
        return rx.toast.success("Marked complete. Nice work.")

    # Delete asks first. These hold what the confirmation is about.
    delete_open: bool = False
    delete_id: str = ""
    delete_name: str = ""

    def ask_delete(self, assignment_id: str, name: str):
        self.delete_id = assignment_id
        self.delete_name = name
        self.delete_open = True

    def cancel_delete(self):
        self.delete_open = False
        self.delete_id = ""
        self.delete_name = ""

    def set_delete_open(self, is_open: bool):
        """Escape or clicking outside the confirmation counts as cancel."""
        if not is_open:
            self.cancel_delete()

    def confirm_delete(self):
        name = self.delete_name
        deleted = delete_assignment(int(self.delete_id))
        self.cancel_delete()
        self.load_assignments()
        if not deleted:
            return rx.toast.info(f"{name} was already gone.")
        return rx.toast.success(f"Deleted {name}.")


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

def nav_link(label: str, href: str, active: bool = False) -> rx.Component:
    """A navigation pill. The active one is solid accent so it is unmistakable."""
    return rx.link(
        label, href=href, size="2", weight="medium", underline="none",
        color="white" if active else rx.color("gray", 12),
        background=rx.color("accent", 9) if active else "transparent",
        padding_x="4", padding_y="2", border_radius="999px",
        white_space="nowrap", display="inline-block",
        style={} if active else {"_hover": {"background": rx.color("gray", 4)}},
    )


def header(active: str = "Dashboard") -> rx.Component:
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
            rx.flex(
                *[nav_link(label, href, active=(label == active)) for label, href in NAV_ITEMS.items()],
                spacing="2", wrap="wrap", align="center",
                padding="1", border_radius="999px", background=rx.color("gray", 2),
            ),
            rx.color_mode.button(size="2", variant="ghost"),
            spacing="3", align="center",
        ),
        width="100%", align="center", wrap="wrap", spacing="4", padding_y="4",
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
        # Count and required hours come from the assignment list, so
        # adding an assignment updates them; the other two stay sample
        # until the scheduler is connected.
        overview_card("Assignments", DashboardState.assignment_count, "", "active this week", "book_open", "blue"),
        overview_card("Required", DashboardState.required_hours, "h", "of work remaining", "clock", "orange"),
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
                          size="3", width=TAP_WIDTH, variant="soft", on_click=DashboardState.open_form),
                spacing="3", wrap="wrap", width=TAP_WIDTH,
            ),
            width="100%", align="center", wrap="wrap", spacing="4",
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
        # Both are allowed to wrap onto their own line in a narrow card
        # rather than run into each other.
        rx.flex(
            rx.hstack(
                rx.heading(a["due_in_days"], size="7", line_height="1", color=ink),
                rx.text("days left", size="2", weight="bold", color=ink, white_space="nowrap"),
                spacing="2", align="baseline", min_width="7em",
            ),
            rx.spacer(),
            risk_badge(a["risk"]),
            width="100%", align="center", wrap="wrap", spacing="3",
            padding_x="4", padding_y="3",
            background=rx.match(a["risk"], *RISK_TINTS.items(), "var(--gray-3)"),
        ),
        # Body: what it is. Long names wrap instead of overflowing.
        rx.vstack(
            rx.heading(a["name"], size="4", line_height="1.3", style={"overflow_wrap": "anywhere"}),
            rx.text(a["subject"], size="2", color_scheme="gray"),
            spacing="1", align="start", width="100%",
            padding_x="4", padding_top="4", padding_bottom="3",
        ),
        # Footer: the detail, hours left and priority right, wrapping if tight.
        rx.flex(
            rx.hstack(rx.icon("clock", size=14, color=rx.color("gray", 10)),
                      rx.text(a["hours"], size="2", color_scheme="gray", white_space="nowrap"),
                      spacing="2", align="center"),
            rx.spacer(),
            priority_badge(a["priority"]),
            width="100%", align="center", wrap="wrap", spacing="3",
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
        "What's due next, most urgent first. Edit, complete or delete them on the Assignments page.",
        rx.cond(
            DashboardState.assignments.length() > 0,
            rx.grid(
                rx.foreach(DashboardState.assignments, assignment_card),
                columns=rx.breakpoints(initial="1", md="2", lg="3"),
                spacing="4", width="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.icon("inbox", size=28, color=rx.color("gray", 9)),
                    rx.text("No upcoming assignments yet.", weight="medium"),
                    rx.text("Add one with the button above and it will appear here.",
                            size="2", color_scheme="gray"),
                    spacing="2", align="center", padding_y="6",
                ),
                width="100%",
            ),
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
# 8. Add Assignment form
# ---------------------------------------------------------------------

def form_field(label: str, control: rx.Component, error: rx.Var) -> rx.Component:
    """A labelled input with its validation message underneath."""
    return rx.vstack(
        rx.text(label, size="2", weight="medium"),
        control,
        rx.cond(error != "", rx.text(error, size="1", color=rx.color("red", 11))),
        spacing="1", align="start", width="100%",
    )


def assignment_form() -> rx.Component:
    """
    The Add Assignment dialog. Every input is bound to the State, so
    the values survive a failed validation and Cancel can clear them.
    """
    s = DashboardState
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(rx.cond(s.is_editing, "Edit Assignment", "Add Assignment")),
            rx.dialog.description(
                rx.cond(s.is_editing,
                        "Change anything that is different now and save.",
                        "Tell StudyFlow what is due and how long it will take."),
                size="2",
            ),
            rx.cond(
                s.form_save_error != "",
                rx.callout(s.form_save_error, icon="triangle_alert", color_scheme="red", size="1",
                           margin_top="3"),
            ),
            rx.vstack(
                form_field("Assignment name",
                           rx.input(value=s.form_name, on_change=s.set_form_name,
                                    placeholder="Mathematics IA", width="100%"),
                           s.form_errors["name"]),
                form_field("Subject",
                           rx.input(value=s.form_subject, on_change=s.set_form_subject,
                                    placeholder="Pure Mathematics", width="100%"),
                           s.form_errors["subject"]),
                rx.grid(
                    form_field("Due date",
                               rx.input(value=s.form_due, on_change=s.set_form_due, type="date", width="100%"),
                               s.form_errors["due"]),
                    form_field("Estimated hours",
                               rx.input(value=s.form_hours, on_change=s.set_form_hours,
                                        type="number", step="0.25", min="0", placeholder="1.5", width="100%"),
                               s.form_errors["hours"]),
                    columns=rx.breakpoints(initial="1", sm="2"), spacing="3", width="100%",
                ),
                form_field("Priority",
                           rx.select(forms.PRIORITIES, value=s.form_priority, on_change=s.set_form_priority,
                                     width="100%"),
                           s.form_errors["priority"]),
                rx.flex(
                    rx.button("Cancel", variant="soft", color_scheme="gray", size="3",
                              width=TAP_WIDTH, on_click=s.close_form),
                    rx.button(rx.cond(s.is_editing, rx.icon("check", size=18), rx.icon("plus", size=18)),
                              rx.cond(s.is_editing, "Save changes", "Add Assignment"), size="3",
                              width=TAP_WIDTH, on_click=s.submit_form),
                    spacing="3", wrap="wrap", justify="end", width="100%", padding_top="2",
                ),
                spacing="4", width="100%", padding_top="3",
            ),
            max_width="480px",
        ),
        open=s.form_open,
        on_open_change=s.set_form_open,
    )


# ---------------------------------------------------------------------
# 9. Assignments page: manage every active assignment
# ---------------------------------------------------------------------

def assignment_row(a: dict) -> rx.Component:
    """One assignment with its details and the three actions."""
    s = DashboardState
    return rx.card(
        rx.flex(
            rx.vstack(
                rx.hstack(
                    rx.heading(a["name"], size="4", style={"overflow_wrap": "anywhere"}),
                    priority_badge(a["priority"]),
                    risk_badge(a["risk"]),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.text(a["subject"], size="2", color_scheme="gray"),
                rx.hstack(
                    rx.icon("calendar", size=14, color=rx.color("gray", 10)),
                    rx.text("Due ", a["due_pretty"], " · ", a["due"].lower(), size="2", color_scheme="gray"),
                    rx.text("·", size="2", color_scheme="gray"),
                    rx.icon("clock", size=14, color=rx.color("gray", 10)),
                    rx.text(a["hours"], size="2", color_scheme="gray"),
                    spacing="1", align="center", wrap="wrap",
                ),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.flex(
                rx.button(rx.icon("pencil", size=16), "Edit", size="2", variant="soft",
                          on_click=s.open_edit(a["id"])),
                rx.button(rx.icon("check", size=16), "Complete", size="2", variant="soft", color_scheme="green",
                          on_click=s.complete_assignment(a["id"])),
                rx.button(rx.icon("trash_2", size=16), "Delete", size="2", variant="soft", color_scheme="red",
                          on_click=s.ask_delete(a["id"], a["name"])),
                spacing="2", wrap="wrap", align="center",
            ),
            width="100%", align="center", wrap="wrap", spacing="4",
        ),
        size="3", width="100%",
        border_left=rx.match(a["risk"], *RISK_BORDERS.items(), "4px solid var(--gray-6)"),
        style=CARD_STYLE,
    )


def delete_dialog() -> rx.Component:
    """Ask before deleting; deleting is the one action that cannot be undone."""
    s = DashboardState
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Delete assignment?"),
            rx.alert_dialog.description(
                rx.text(s.delete_name, weight="bold", as_="span"),
                " will be removed permanently. Use Complete instead if it is done.",
                size="2",
            ),
            rx.flex(
                rx.button("Cancel", variant="soft", color_scheme="gray", size="3", width=TAP_WIDTH,
                          on_click=s.cancel_delete),
                rx.button(rx.icon("trash_2", size=18), "Delete", color_scheme="red", size="3", width=TAP_WIDTH,
                          on_click=s.confirm_delete),
                spacing="3", wrap="wrap", justify="end", width="100%", padding_top="4",
            ),
            max_width="420px",
        ),
        open=s.delete_open,
        on_open_change=s.set_delete_open,
    )


def assignments_page() -> rx.Component:
    s = DashboardState
    return rx.box(
        rx.container(
            rx.vstack(
                header(active="Assignments"),
                rx.flex(
                    rx.vstack(
                        rx.heading("Assignments", size="7"),
                        rx.text(s.assignment_count, " active · ", s.required_hours, "h of work",
                                size="2", color_scheme="gray"),
                        spacing="1", align="start",
                    ),
                    rx.spacer(),
                    rx.button(rx.icon("plus", size=18), "Add Assignment", size="3", width=TAP_WIDTH,
                              on_click=s.open_form),
                    width="100%", align="center", wrap="wrap", spacing="4",
                ),
                rx.cond(
                    s.assignments.length() > 0,
                    rx.vstack(rx.foreach(s.assignments, assignment_row), spacing="3", width="100%"),
                    rx.card(
                        rx.vstack(
                            rx.icon("inbox", size=28, color=rx.color("gray", 9)),
                            rx.text("No upcoming assignments.", weight="medium"),
                            rx.button(rx.icon("plus", size=18), "Add Assignment", size="3", on_click=s.open_form),
                            spacing="3", align="center", padding_y="6",
                        ),
                        width="100%",
                    ),
                ),
                spacing=SECTION_GAP, width="100%", padding_bottom="9",
            ),
            size="4", padding_x=PAGE_PADDING_X,
        ),
        assignment_form(),
        delete_dialog(),
        background=rx.color("gray", 1), min_height="100vh",
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
        assignment_form(),   # the dialog; invisible until form_open is True
        background=rx.color("gray", 1), min_height="100vh",
    )


app = rx.App(
    theme=rx.theme(accent_color="indigo", gray_color="slate", radius="large", scaling="100%"),
)
app.add_page(index, title="StudyFlow", on_load=DashboardState.load_assignments)
app.add_page(assignments_page, route="/assignments", title="Assignments · StudyFlow",
             on_load=DashboardState.load_assignments)
