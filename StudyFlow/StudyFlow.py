"""
StudyFlow/StudyFlow.py
The StudyFlow dashboard, built with Reflex.

Three pages: the dashboard, an Assignments page and a Schedule page.
Assignments and study time come from the database through storage.py;
Generate Study Plan runs the existing engine through
study_plan.generate_study_plan() and shows the result. None of the
scheduling logic lives here; it stays in scheduler.py,
schedule_builder.py, schedule_analyzer.py and schedule_optimizer.py,
and StudyFlow/plan_view.py turns the engine's result into page data.

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

import asyncio
import time
from datetime import date, datetime

import reflex as rx

from storage import (
    add_assignment,
    add_time_slot,
    delete_assignment,
    delete_time_slot,
    init_db,
    list_assignments,
    list_time_slots,
    mark_assignment_complete,
    update_assignment,
)
from schedule_builder import DEFAULT_BREAK_MINUTES
from StudyFlow import assignments as forms
from StudyFlow import focus
from StudyFlow import plan_view
from StudyFlow import study_time
from StudyFlow.focus import Session
from StudyFlow.plan_view import Block, Day, StatusRow
from study_plan import generate_study_plan

# Make sure the SQLite database and its tables exist before the first
# assignment is added. init_db() is CREATE TABLE IF NOT EXISTS, so
# running it on every start is safe.
init_db()

# Badge and accent colours for the two labels a student scans first.
PRIORITY_COLORS = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
# Risk words are exactly what schedule_optimizer.risk_level() returns;
# anything else (such as NOT RATED before a plan exists) falls to grey.
RISK_COLORS = {"CRITICAL": "red", "HIGH": "orange", "MODERATE": "yellow", "LOW": "green"}
RISK_BORDERS = {risk: f"4px solid var(--{color}-9)" for risk, color in RISK_COLORS.items()}
RISK_TINTS = {risk: f"var(--{color}-3)" for risk, color in RISK_COLORS.items()}    # strip background
RISK_INK = {risk: f"var(--{color}-11)" for risk, color in RISK_COLORS.items()}     # strip text

# Navigation: label -> route. Schedule and Progress are visual only until
# those pages exist.
NAV_ITEMS = {"Dashboard": "/", "Assignments": "/assignments", "Schedule": "/schedule",
             "Progress": "/progress", "Focus": "/focus"}

# Shown wherever a plan would be, once its inputs have changed.
STALE_MESSAGE = "Your study plan needs to be regenerated. Your {what} changed since it was made."

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
    # when the page opens; see load_assignments.
    assignments: list[dict[str, str]] = []

    # The generated plan, flattened by StudyFlow/plan_view.py. It lives
    # in State until the student generates again or reloads; nothing
    # about it is stored in the database yet.
    has_plan: bool = False
    plan_message: str = ""                      # why there is no plan, or what went wrong
    plan_stale: bool = False                    # a plan existed, then its inputs changed
    plan_fingerprint: str = ""                  # plan_view.plan_input_fingerprint() of the data the plan was built from

    def _invalidate_plan(self, what: str):
        """
        The scheduling inputs changed, so the generated plan no longer
        describes them. Clear every generated value and say why; the
        student regenerates explicitly, so their schedule never changes
        under them. Callers invoke this only after storage reports a
        real change (a saved row, a completed row, a deleted row); a
        failed or no-op operation leaves the plan alone.
        """
        had_plan = self.has_plan
        self.has_plan = False
        self.plan_fingerprint = ""
        self.plan_days = []
        self.today_plan = []
        self.today_sessions = []
        self.plan_statuses = []
        self.plan_required = "0.0"
        self.plan_scheduled = "0.0"
        self.plan_unscheduled = "0.0"
        self.plan_completion = "0"
        # The cards' risk badges came from the plan too.
        self.assignments = [{**row, "risk": forms.RISK_NOT_RATED} for row in self.assignments]
        if had_plan:
            self.plan_stale = True
            self.plan_message = STALE_MESSAGE.format(what=what)
        elif self.plan_stale and what not in self.plan_message:
            # Already stale for the other reason; now both have changed.
            self.plan_message = STALE_MESSAGE.format(what="assignments and study times")
    plan_days: list[Day] = []
    today_plan: list[dict[str, str]] = []
    today_sessions: list[Session] = []          # today's work blocks, for the Focus page
    plan_statuses: list[StatusRow] = []
    plan_required: str = "0.0"
    plan_scheduled: str = "0.0"
    plan_unscheduled: str = "0.0"
    plan_completion: str = "0"

    # Completed assignments are not unfinished work, so they stay out of
    # every list and total; the Progress page shows them separately.
    completed_names: list[str] = []

    @rx.var
    def completed_count(self) -> str:
        return str(len(self.completed_names))

    def load_assignments(self):
        """Read the assignments from the database: active ones soonest due first, completed ones by name."""
        stored = list_assignments(include_completed=True)
        self.assignments = forms.rows_from([a for a in stored if not a.completed], date.today())
        self.completed_names = [a.name for a in stored if a.completed]

    # ---- Study time: the student's recurring weekly availability ----
    #
    # Rows come from storage.list_time_slots(); the form's labels
    # ("4:00 PM") are translated to the model's 24-hour integers by
    # StudyFlow/study_time.py, which is unit-tested on its own.

    slots: list[dict[str, str]] = []
    slot_hours: str = "0"

    def load_slots(self):
        stored = list_time_slots()
        self.slots = study_time.rows_from(stored)
        self.slot_hours = f"{study_time.total_hours(stored):g}"

    def load_data(self):
        """
        Everything a page needs from the database; runs on page load.

        Then the freshness check (v1.2): a plan is shown only if the
        database still holds exactly the data it was built from. The
        mutation handlers invalidate explicitly; this is the safety net
        for everything they cannot see, such as edits from another tab
        or the CLI, or a state that came back older than the data.
        """
        self.load_assignments()
        self.load_slots()
        if not self.has_plan:
            return
        current = plan_view.plan_input_fingerprint(
            list_assignments(include_completed=False), list_time_slots())
        if current != self.plan_fingerprint:
            self._invalidate_plan("assignments or study times")
            return
        # Same data: the plan stands, so the cards get its risk back
        # (load_assignments() had reset them to NOT RATED).
        risk = plan_view.risk_by_name(self.plan_statuses)
        self.assignments = [
            {**row, "risk": risk.get(row["name"], row["risk"])} for row in self.assignments
        ]

    slot_form_open: bool = False
    slot_weekday: str = "Monday"
    slot_start: str = "4:00 PM"
    slot_end: str = "6:00 PM"
    slot_errors: dict[str, str] = study_time.no_errors()
    slot_save_error: str = ""

    def set_slot_weekday(self, value: str):
        self.slot_weekday = value

    def set_slot_start(self, value: str):
        self.slot_start = value

    def set_slot_end(self, value: str):
        self.slot_end = value

    def open_slot_form(self):
        self.slot_errors = study_time.no_errors()
        self.slot_save_error = ""
        self.slot_form_open = True

    def close_slot_form(self):
        self.slot_form_open = False
        self.slot_weekday = "Monday"
        self.slot_start = "4:00 PM"
        self.slot_end = "6:00 PM"
        self.slot_errors = study_time.no_errors()
        self.slot_save_error = ""

    def set_slot_form_open(self, is_open: bool):
        if is_open:
            self.open_slot_form()
        else:
            self.close_slot_form()

    def submit_slot_form(self):
        """Validate, build the model's TimeSlot, save it, reload, close."""
        self.slot_errors = study_time.validate_form(self.slot_weekday, self.slot_start, self.slot_end)
        self.slot_save_error = ""
        if not study_time.is_valid(self.slot_errors):
            return
        slot = study_time.to_time_slot(self.slot_weekday, self.slot_start, self.slot_end)
        try:
            add_time_slot(slot)
        except Exception:
            self.slot_save_error = "StudyFlow could not save that study time. Please try again."
            return
        self.load_slots()
        self._invalidate_plan("study times")
        label = f"{self.slot_weekday} {self.slot_start} – {self.slot_end}"
        self.close_slot_form()
        return rx.toast.success(f"Added {label}.")

    slot_delete_open: bool = False
    slot_delete_id: str = ""
    slot_delete_label: str = ""

    def ask_delete_slot(self, slot_id: str, label: str):
        self.slot_delete_id = slot_id
        self.slot_delete_label = label
        self.slot_delete_open = True

    def cancel_delete_slot(self):
        self.slot_delete_open = False
        self.slot_delete_id = ""
        self.slot_delete_label = ""

    def set_slot_delete_open(self, is_open: bool):
        if not is_open:
            self.cancel_delete_slot()

    def confirm_delete_slot(self):
        label = self.slot_delete_label
        deleted = delete_time_slot(int(self.slot_delete_id))
        self.cancel_delete_slot()
        self.load_slots()
        if not deleted:
            return rx.toast.info(f"{label} was already gone.")
        self._invalidate_plan("study times")
        return rx.toast.success(f"Removed {label}.")

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
        return int(self.plan_completion)

    def generate_study_plan(self):
        """
        The whole pipeline, through the existing engine:

            list_assignments() + list_time_slots()
                -> study_plan.generate_study_plan()
                -> plan_view (strings and lists for the page)

        With no assignments or no study time there is nothing to plan,
        so a message explains what to add. If the engine raises, the
        dashboard stays usable and shows a plain message.
        """
        assignments = list_assignments(include_completed=False)
        slots = list_time_slots()
        self.plan_message = plan_view.guard_message(assignments, slots)
        if self.plan_message:
            self.has_plan = False
            return rx.toast.warning(self.plan_message)

        today = date.today()
        try:
            plan = generate_study_plan(assignments, slots, today=today)
            statuses = plan_view.status_rows(plan, slots, today)
            days = plan_view.days_of(plan)
        except Exception:
            self.has_plan = False
            self.plan_message = "StudyFlow could not build a plan from that data. Please try again."
            return rx.toast.error(self.plan_message)

        self.plan_days = days
        self.today_plan = plan_view.today_blocks(plan, today)
        self.today_sessions = focus.sessions_for_today(plan, assignments, today)
        self.plan_statuses = statuses
        numbers = plan_view.totals(plan)
        self.plan_required = numbers["required"]
        self.plan_scheduled = numbers["scheduled"]
        self.plan_unscheduled = numbers["unscheduled"]
        self.plan_completion = numbers["completion"]
        self.has_plan = True
        self.plan_stale = False
        self.plan_message = ""
        self.plan_fingerprint = plan_view.plan_input_fingerprint(assignments, slots)

        # Stamp the real risk onto the assignment cards.
        risk = plan_view.risk_by_name(statuses)
        self.assignments = [
            {**row, "risk": risk.get(row["name"], row["risk"])} for row in self.assignments
        ]

        if plan_view.has_unscheduled(plan):
            return rx.toast.warning(f"Plan ready. {self.plan_unscheduled}h could not fit before its due date.")
        return rx.toast.success("Plan ready. Every assignment fits.")

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
    form_notice: str = ""                       # the chosen due date has passed (information, not an error)

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
        self.form_notice = forms.due_notice(value, date.today())

    def set_form_hours(self, value: str):
        self.form_hours = value

    def set_form_priority(self, value: str):
        self.form_priority = value

    def open_form(self):
        self.form_errors = forms.no_errors()
        self.form_notice = ""
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
        self.form_notice = ""
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
        self.form_notice = forms.due_notice(self.form_due, date.today())
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
        overdue = " (overdue)" if assignment.due_date < date.today() else ""
        try:
            if self.is_editing:
                assignment.id = int(self.editing_id)
                if not update_assignment(assignment):
                    # No row changed, so nothing the plan depends on did:
                    # the plan stays, the list refreshes, the form stays open.
                    self.load_assignments()
                    self.form_save_error = "That assignment no longer exists. Close the form and add it again."
                    return
                message = f"Saved changes to {assignment.name}{overdue}."
            else:
                add_assignment(assignment)
                message = f"Added {assignment.name}{overdue}."
        except Exception:
            self.form_save_error = "StudyFlow could not save that assignment. Please try again."
            return
        self.load_assignments()
        self._invalidate_plan("assignments")
        self.close_form()
        return rx.toast.success(message)

    # ---- Complete and delete ----

    def complete_assignment(self, assignment_id: str):
        """
        Mark it done; it leaves the active list but stays in the
        database. The plan is invalidated only if a row really changed.
        """
        updated = mark_assignment_complete(int(assignment_id), True)
        self.load_assignments()
        if not updated:
            return rx.toast.info("That assignment was already gone.")
        self._invalidate_plan("assignments")
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
        self._invalidate_plan("assignments")
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
# Focus: one session, one countdown (v1.2)
# ---------------------------------------------------------------------

class FocusState(rx.State):
    """
    The Focus page's own state: which of today's sessions is on the
    screen and where its countdown stands.

    Modes:  none        nothing to study right now (or no plan yet)
            ready       a session is on, countdown not started
            running     counting down
            paused      countdown held
            complete    the countdown reached zero
            break       the break countdown is running
            break_over  the break ended
            marked      the assignment was marked complete from here

    The countdown is kept as a deadline on the server, so a missed
    update never drifts it: every tick recomputes what is left from
    the wall clock. A background task ticks once a second while
    something is counting.
    """
    mode: str = "none"
    has_plan: bool = False
    label: str = ""
    subject: str = ""
    time_label: str = ""
    session_minutes: int = 0
    next_label: str = ""
    next_time: str = ""
    total_seconds: int = 0
    remaining_seconds: int = 0
    completed_minutes: int = 0
    break_minutes: int = DEFAULT_BREAK_MINUTES
    _deadline: float = 0.0
    _timer_token: int = 0
    _finished: str = ""            # the session moved past by "Next session"

    @rx.var
    def clock(self) -> str:
        return focus.clock(self.remaining_seconds)

    @rx.var
    def counting(self) -> bool:
        return self.mode in ("running", "break")

    # ---- Loading

    def _apply(self, sessions: list, has_plan: bool, now_minute: int, after: str | None = None) -> None:
        """Choose the current and next session for this moment; keep a running countdown alive."""
        self.has_plan = has_plan
        if not has_plan:
            self.mode, self.label, self.subject, self.time_label = "none", "", "", ""
            self.next_label = self.next_time = ""
            self.session_minutes = self.total_seconds = self.remaining_seconds = 0
            return
        current, nxt = focus.pick(sessions, now_minute, after=after)
        self.next_label = nxt.label if nxt else ""
        self.next_time = nxt.time if nxt else ""
        if current is not None and current.label == self.label and self.mode in ("running", "paused", "complete", "break", "break_over"):
            return                                                   # a page load mid-session changes nothing
        if current is None:
            self.mode, self.label, self.subject, self.time_label = "none", "", "", ""
            self.session_minutes = self.total_seconds = self.remaining_seconds = 0
            return
        self.mode = "ready"
        self.label, self.subject, self.time_label = current.label, current.subject, current.time
        self.session_minutes = current.minutes
        self.total_seconds = self.remaining_seconds = current.minutes * 60

    async def load_focus(self):
        """On page load: read today's sessions from the dashboard state."""
        dash = await self.get_state(DashboardState)
        now = datetime.now()
        self._apply(list(dash.today_sessions), dash.has_plan, now.hour * 60 + now.minute)

    async def next_session(self):
        """After a session (and its break): move on to whatever follows today."""
        dash = await self.get_state(DashboardState)
        now = datetime.now()
        finished = self.label
        self._finished = finished
        self.label = ""
        self.mode = "none"
        self._apply(list(dash.today_sessions), dash.has_plan, now.hour * 60 + now.minute, after=finished or None)

    # ---- The countdown

    def tick(self):
        """Recompute what is left from the deadline; finish when it reaches zero."""
        if self.mode not in ("running", "break"):
            return
        self.remaining_seconds = max(0, round(self._deadline - time.time()))
        if self.remaining_seconds == 0:
            if self.mode == "running":
                self.mode = "complete"
                self.completed_minutes = self.total_seconds // 60
            else:
                self.mode = "break_over"

    def _arm(self, seconds: int):
        self._deadline = time.time() + seconds
        self._timer_token += 1
        return FocusState.run_timer

    def start_session(self):
        """Start, or resume after a pause."""
        if self.mode not in ("ready", "paused"):
            return
        self.mode = "running"
        return self._arm(self.remaining_seconds)

    def pause_session(self):
        if self.mode != "running":
            return
        self.tick()
        self.mode = "paused" if self.remaining_seconds > 0 else self.mode
        self._timer_token += 1

    def reset_session(self):
        if self.mode not in ("running", "paused", "complete"):
            return
        self.mode = "ready"
        self.remaining_seconds = self.total_seconds
        self._timer_token += 1

    def take_break(self):
        """The plan's own break length, counted down here."""
        if self.mode != "complete":
            return
        self.mode = "break"
        self.total_seconds = self.remaining_seconds = self.break_minutes * 60
        return self._arm(self.remaining_seconds)

    def skip_break(self):
        if self.mode != "break":
            return
        self.mode = "break_over"
        self.remaining_seconds = 0
        self._timer_token += 1

    async def mark_complete(self):
        """Mark the assignment complete through the dashboard's own handler."""
        dash = await self.get_state(DashboardState)
        row = next((r for r in dash.assignments if r["name"] == self.label), None)
        self.mode = "marked"
        self._timer_token += 1
        if row is None:
            return rx.toast.info("That assignment is no longer in your list.")
        return DashboardState.complete_assignment(row["id"])

    @rx.event(background=True)
    async def run_timer(self):
        """Tick once a second until the countdown ends or is stopped."""
        async with self:
            token = self._timer_token
        while True:
            await asyncio.sleep(1)
            async with self:
                if self._timer_token != token or self.mode not in ("running", "break"):
                    return
                self.tick()
                if self.mode not in ("running", "break"):
                    return


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
    s = DashboardState
    return rx.grid(
        # Count and required hours come from the assignment list; the
        # scheduled hours and completion come from the generated plan
        # and read 0 until one exists.
        overview_card("Assignments", s.assignment_count, "", "active this week", "book_open", "blue"),
        overview_card("Required", s.required_hours, "h", "of work remaining", "clock", "orange"),
        overview_card("Scheduled", s.plan_scheduled, "h", "placed in your plan", "calendar", "green"),
        overview_card("Completion", s.plan_completion, "%", "of required work scheduled", "trending_up", "purple"),
        columns=rx.breakpoints(initial="2", lg="4"),
        spacing=GRID_GAP, width="100%",
    )


# ---------------------------------------------------------------------
# 4. Call to action
# ---------------------------------------------------------------------

def call_to_action() -> rx.Component:
    """The primary action, given its own highlighted band so it is the focus of the page."""
    s = DashboardState
    return rx.card(
        rx.flex(
            rx.vstack(
                rx.heading(rx.cond(s.plan_stale, "Your plan needs regenerating", "Ready to plan your week?"), size="5"),
                rx.text(rx.cond(s.plan_stale, s.plan_message,
                                "StudyFlow places your work around your free time and flags anything at risk."),
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
    how many days are left (or overdue, or "Today"), large, and the
    risk badge. The body is
    the name and subject. The footer is the detail: hours and priority.
    """
    ink = rx.match(a["risk"], *RISK_INK.items(), "var(--gray-11)")
    return rx.box(
        # Strip: due countdown on the left, risk badge on the right.
        # Both are allowed to wrap onto their own line in a narrow card
        # rather than run into each other.
        rx.flex(
            rx.hstack(
                rx.heading(a["due_number"], size="7", line_height="1", color=ink),
                rx.text(a["due_label"], size="2", weight="bold", color=ink, white_space="nowrap"),
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
    s = DashboardState
    return section(
        "Today's Study Plan",
        "Your blocks for today, in order.",
        rx.card(
            rx.cond(
                s.has_plan,
                rx.cond(
                    s.today_plan.length() > 0,
                    rx.vstack(rx.foreach(s.today_plan, plan_row), spacing="0", width="100%"),
                    rx.vstack(
                        rx.text("Nothing is scheduled for today.", weight="medium"),
                        rx.text("See the Schedule page for the rest of the week.", size="2", color_scheme="gray"),
                        spacing="1", align="center", padding_y="4", width="100%",
                    ),
                ),
                rx.vstack(
                    rx.text(rx.cond(s.plan_stale, "Your study plan needs to be regenerated.", "No plan yet."),
                            weight="medium"),
                    rx.text(rx.cond(s.plan_stale, s.plan_message,
                                    "Press Generate Study Plan to place your work into your study time."),
                            size="2", color_scheme="gray", text_align="center"),
                    spacing="1", align="center", padding_y="4", width="100%",
                ),
            ),
            size="3", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 7. Progress
# ---------------------------------------------------------------------

def progress_stat(label: str, value: rx.Var) -> rx.Component:
    return rx.vstack(eyebrow(label), rx.heading(value, " h", size="5"), spacing="1", align="start")


def progress_section() -> rx.Component:
    s = DashboardState
    return section(
        "Progress",
        "How much of your required work has a place in the plan.",
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading(s.plan_completion, "%", size=BIG_NUMBER, line_height="1",
                               color=rx.color("accent", 11)),
                    rx.text("of required study work scheduled", size="2", color_scheme="gray"),
                    spacing="3", align="end",
                ),
                rx.progress(value=s.progress_value, size="3", width="100%"),
                rx.hstack(
                    rx.text("0%", size="1", color_scheme="gray"),
                    rx.spacer(),
                    rx.text("100%", size="1", color_scheme="gray"),
                    width="100%",
                ),
                rx.hstack(
                    progress_stat("Required", s.plan_required),
                    progress_stat("Scheduled", s.plan_scheduled),
                    progress_stat("Unscheduled", s.plan_unscheduled),
                    spacing="7", wrap="wrap",
                ),
                rx.cond(
                    ~s.has_plan,
                    rx.text(rx.cond(s.plan_stale, s.plan_message, "Generate a study plan to fill these in."),
                            size="1", color_scheme="gray"),
                ),
                spacing="3", align="start", width="100%",
            ),
            size="3", width="100%",
        ),
    )


# ---------------------------------------------------------------------
# 8. Add Assignment form
# ---------------------------------------------------------------------

def form_field(label: str, control: rx.Component, error: rx.Var,
               notice: rx.Var | None = None) -> rx.Component:
    """
    A labelled input with its validation message underneath. An
    optional notice (information that does not block saving, such as
    a due date that has passed) is shown in amber below the error line.
    """
    children = [
        rx.text(label, size="2", weight="medium"),
        control,
        rx.cond(error != "", rx.text(error, size="1", color=rx.color("red", 11))),
    ]
    if notice is not None:
        children.append(rx.cond(notice != "", rx.text(notice, size="1", color=rx.color("amber", 11))))
    return rx.vstack(*children, spacing="1", align="start", width="100%")


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
                               s.form_errors["due"],
                               notice=s.form_notice),
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
# 10. Study time: when the student is free each week
# ---------------------------------------------------------------------

def slot_row(slot: dict) -> rx.Component:
    """One weekly study period with its Delete button."""
    s = DashboardState
    return rx.card(
        rx.flex(
            rx.hstack(
                rx.box(
                    rx.icon("clock", size=16, color=rx.color("accent", 9)),
                    padding="2", border_radius="8px", background=rx.color("accent", 3),
                    display="flex", align_items="center",
                ),
                rx.vstack(
                    rx.text(slot["weekday"], weight="bold"),
                    rx.text(slot["time"], size="2", color_scheme="gray"),
                    spacing="0", align="start",
                ),
                spacing="3", align="center",
            ),
            rx.spacer(),
            rx.hstack(
                rx.badge(slot["hours"], variant="soft", color_scheme="gray"),
                rx.button(rx.icon("trash_2", size=14), "Delete", size="1", variant="soft", color_scheme="red",
                          on_click=s.ask_delete_slot(slot["id"], slot["weekday"] + " " + slot["time"])),
                spacing="2", align="center",
            ),
            width="100%", align="center", wrap="wrap", spacing="3",
        ),
        size="2", width="100%", style=CARD_STYLE,
    )


def study_time_section() -> rx.Component:
    s = DashboardState
    return section(
        "Study Time",
        "Add your available study times so StudyFlow knows when to schedule your assignments.",
        rx.vstack(
            rx.cond(
                s.slots.length() > 0,
                rx.vstack(
                    rx.grid(rx.foreach(s.slots, slot_row),
                            columns=rx.breakpoints(initial="1", md="2"), spacing="3", width="100%"),
                    rx.text(s.slot_hours, " hours of study time each week", size="2", color_scheme="gray"),
                    spacing="3", width="100%", align="start",
                ),
                rx.card(
                    rx.vstack(
                        rx.icon("calendar_clock", size=28, color=rx.color("gray", 9)),
                        rx.text("No study time added yet.", weight="medium"),
                        spacing="2", align="center", padding_y="5",
                    ),
                    width="100%",
                ),
            ),
            rx.button(rx.icon("plus", size=18), "Add Study Time", size="3", variant="soft",
                      width=TAP_WIDTH, on_click=s.open_slot_form),
            spacing="4", width="100%", align="start",
        ),
    )


def slot_form() -> rx.Component:
    """The Add Study Time dialog. Times are chosen from whole-hour lists."""
    s = DashboardState
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Add Study Time"),
            rx.dialog.description("A weekly period when you are free to study.", size="2"),
            rx.cond(
                s.slot_save_error != "",
                rx.callout(s.slot_save_error, icon="triangle_alert", color_scheme="red", size="1", margin_top="3"),
            ),
            rx.vstack(
                form_field("Day",
                           rx.select(study_time.WEEKDAYS, value=s.slot_weekday, on_change=s.set_slot_weekday,
                                     width="100%"),
                           s.slot_errors["weekday"]),
                rx.grid(
                    form_field("Start time",
                               rx.select(study_time.START_CHOICES, value=s.slot_start, on_change=s.set_slot_start,
                                         width="100%"),
                               s.slot_errors["start"]),
                    form_field("End time",
                               rx.select(study_time.END_CHOICES, value=s.slot_end, on_change=s.set_slot_end,
                                         width="100%"),
                               s.slot_errors["end"]),
                    columns=rx.breakpoints(initial="1", sm="2"), spacing="3", width="100%",
                ),
                rx.flex(
                    rx.button("Cancel", variant="soft", color_scheme="gray", size="3", width=TAP_WIDTH,
                              on_click=s.close_slot_form),
                    rx.button(rx.icon("plus", size=18), "Add Study Time", size="3", width=TAP_WIDTH,
                              on_click=s.submit_slot_form),
                    spacing="3", wrap="wrap", justify="end", width="100%", padding_top="2",
                ),
                spacing="4", width="100%", padding_top="3",
            ),
            max_width="440px",
        ),
        open=s.slot_form_open,
        on_open_change=s.set_slot_form_open,
    )


def slot_delete_dialog() -> rx.Component:
    s = DashboardState
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Remove study time?"),
            rx.alert_dialog.description(
                rx.text(s.slot_delete_label, weight="bold", as_="span"),
                " will no longer be used when planning your week.",
                size="2",
            ),
            rx.flex(
                rx.button("Cancel", variant="soft", color_scheme="gray", size="3", width=TAP_WIDTH,
                          on_click=s.cancel_delete_slot),
                rx.button(rx.icon("trash_2", size=18), "Remove", color_scheme="red", size="3", width=TAP_WIDTH,
                          on_click=s.confirm_delete_slot),
                spacing="3", wrap="wrap", justify="end", width="100%", padding_top="4",
            ),
            max_width="420px",
        ),
        open=s.slot_delete_open,
        on_open_change=s.set_slot_delete_open,
    )


# ---------------------------------------------------------------------
# 11. Schedule page: the whole generated week, day by day
# ---------------------------------------------------------------------

def block_line(b: Block) -> rx.Component:
    """One block of a day, with breaks styled as rest rather than work."""
    is_break = b.is_break == "yes"
    return rx.hstack(
        rx.text(b.time, size="1", weight="medium", color_scheme="gray",
                min_width="9em", style={"font_variant_numeric": "tabular-nums"}),
        rx.box(
            width="3px", height="1.6em", border_radius="999px", flex_shrink="0",
            background=rx.cond(is_break, rx.color("gray", 6), rx.color("accent", 9)),
        ),
        rx.cond(
            is_break,
            rx.hstack(rx.icon("coffee", size=14, color=rx.color("gray", 10)),
                      rx.text("Break", size="2", color_scheme="gray"), spacing="1", align="center"),
            rx.text(b.label, size="3", weight="bold"),
        ),
        spacing="3", align="center", width="100%",
        padding_x="3", padding_y="2", border_radius="8px",
        background=rx.cond(is_break, rx.color("gray", 3), "transparent"),
    )


def day_card(day: Day) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading(day.label.upper(), size="3", letter_spacing="0.04em"),
            rx.vstack(rx.foreach(day.blocks, block_line), spacing="0", width="100%"),
            spacing="3", align="start", width="100%",
        ),
        size="3", width="100%", style=CARD_STYLE,
    )


def status_line(row: StatusRow) -> rx.Component:
    """One assignment's outcome in the plan: status, hours and risk."""
    return rx.flex(
        rx.vstack(
            rx.text(row.name, weight="bold"),
            rx.text(row.scheduled, " / ", row.required, "h scheduled · due ", row.due,
                    size="2", color_scheme="gray"),
            spacing="0", align="start",
        ),
        rx.spacer(),
        rx.hstack(
            rx.badge(row.status, variant="soft", radius="full",
                     color_scheme=rx.match(row.status, *STATUS_COLORS.items(), "gray")),
            rx.badge("Risk: ", row.risk, variant="solid", radius="full",
                     color_scheme=rx.match(row.risk, *RISK_COLORS.items(), "gray")),
            spacing="2", wrap="wrap",
        ),
        width="100%", align="center", wrap="wrap", spacing="3",
        padding_y="2", border_bottom=f"1px solid {rx.color('gray', 4)}",
    )


def schedule_page() -> rx.Component:
    s = DashboardState
    return rx.box(
        rx.container(
            rx.vstack(
                header(active="Schedule"),
                rx.flex(
                    rx.vstack(
                        rx.heading("Schedule", size="7"),
                        rx.text("Your work placed into your study time, by the StudyFlow engine.",
                                size="2", color_scheme="gray"),
                        spacing="1", align="start",
                    ),
                    rx.spacer(),
                    rx.button(rx.icon("sparkles", size=18), "Generate Study Plan", size="3", width=TAP_WIDTH,
                              on_click=s.generate_study_plan),
                    width="100%", align="center", wrap="wrap", spacing="4",
                ),
                rx.cond(
                    s.has_plan,
                    rx.vstack(
                        rx.cond(
                            s.plan_days.length() > 0,
                            rx.grid(rx.foreach(s.plan_days, day_card),
                                    columns=rx.breakpoints(initial="1", md="2", lg="3"),
                                    spacing="4", width="100%"),
                            rx.callout("Nothing could be placed before the due dates with the study time you have.",
                                       icon="info"),
                        ),
                        section(
                            "How each assignment fared",
                            "Status from the analyzer, deadline risk from the optimizer.",
                            rx.card(rx.vstack(rx.foreach(s.plan_statuses, status_line), spacing="0", width="100%"),
                                    size="3", width="100%"),
                        ),
                        spacing=SECTION_GAP, width="100%",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.icon("calendar_days", size=28, color=rx.color("gray", 9)),
                            rx.text(rx.cond(s.plan_stale, "Your study plan needs to be regenerated.", "No study plan yet."),
                                    weight="medium"),
                            rx.text(rx.cond(s.plan_message != "", s.plan_message,
                                            "Generate one and your week will appear here."),
                                    size="2", color_scheme="gray", text_align="center"),
                            spacing="2", align="center", padding_y="6",
                        ),
                        width="100%",
                    ),
                ),
                spacing=SECTION_GAP, width="100%", padding_bottom="9",
            ),
            size="4", padding_x=PAGE_PADDING_X,
        ),
        background=rx.color("gray", 1), min_height="100vh",
    )


# Badge colours for a plan's status words.
STATUS_COLORS = {"COMPLETE": "green", "PARTIAL": "orange", "UNSCHEDULED": "red"}


# ---------------------------------------------------------------------
# 12. Progress page: how much of the work has a place in the plan
# ---------------------------------------------------------------------

def overall_completion_card() -> rx.Component:
    s = DashboardState
    return rx.card(
        rx.vstack(
            eyebrow("Overall completion"),
            rx.hstack(
                rx.heading(s.plan_completion, "%", size=BIG_NUMBER, line_height="1", color=rx.color("accent", 11)),
                rx.text(s.plan_scheduled, "h scheduled / ", s.plan_required, "h required",
                        size="2", color_scheme="gray"),
                spacing="3", align="end", wrap="wrap",
            ),
            rx.progress(value=s.progress_value, size="3", width="100%"),
            rx.flex(
                progress_stat("Required", s.plan_required),
                progress_stat("Scheduled", s.plan_scheduled),
                progress_stat("Unscheduled", s.plan_unscheduled),
                rx.vstack(eyebrow("Assignments"),
                          rx.heading(s.assignment_count, " active · ", s.completed_count, " done", size="5"),
                          spacing="1", align="start"),
                spacing="7", wrap="wrap",
            ),
            spacing="4", align="start", width="100%",
        ),
        size="3", width="100%",
    )


def assignment_progress_row(row: StatusRow) -> rx.Component:
    """One assignment: hours, its own bar, status and risk."""
    return rx.card(
        rx.vstack(
            rx.flex(
                rx.vstack(
                    rx.text(row.name, weight="bold"),
                    rx.text(row.subject, " · due ", row.due, size="2", color_scheme="gray"),
                    spacing="0", align="start",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.badge(row.status, variant="soft", radius="full",
                             color_scheme=rx.match(row.status, *STATUS_COLORS.items(), "gray")),
                    rx.badge("Risk: ", row.risk, variant="solid", radius="full",
                             color_scheme=rx.match(row.risk, *RISK_COLORS.items(), "gray")),
                    spacing="2", wrap="wrap",
                ),
                width="100%", align="center", wrap="wrap", spacing="3",
            ),
            rx.hstack(
                rx.progress(value=row.percent, size="2", width="100%"),
                rx.text(row.percent, "%", size="2", weight="medium", min_width="3.5em", text_align="right"),
                spacing="3", align="center", width="100%",
            ),
            rx.text(row.scheduled, "h scheduled · ", row.remaining, "h remaining · ", row.required, "h required",
                    size="1", color_scheme="gray"),
            spacing="2", align="start", width="100%",
        ),
        size="2", width="100%", style=CARD_STYLE,
    )


def risk_line(row: StatusRow) -> rx.Component:
    return rx.hstack(
        rx.box(width="10px", height="10px", border_radius="999px", flex_shrink="0",
               background=rx.match(row.risk, *{k: f"var(--{v}-9)" for k, v in RISK_COLORS.items()}.items(),
                                   "var(--gray-8)")),
        rx.text(row.name, weight="medium"),
        rx.spacer(),
        rx.badge(row.risk, variant="soft", radius="full",
                 color_scheme=rx.match(row.risk, *RISK_COLORS.items(), "gray")),
        spacing="3", align="center", width="100%", padding_y="2",
        border_bottom=f"1px solid {rx.color('gray', 4)}",
    )


def completed_line(name: str) -> rx.Component:
    return rx.hstack(
        rx.icon("circle_check", size=16, color=rx.color("green", 9)),
        rx.text(name, size="2", style={"text_decoration": "line-through"}, color_scheme="gray"),
        spacing="2", align="center",
    )


def progress_page() -> rx.Component:
    s = DashboardState
    no_assignments = rx.card(
        rx.vstack(
            rx.icon("inbox", size=28, color=rx.color("gray", 9)),
            rx.text("No progress to show yet.", weight="medium"),
            rx.button(rx.icon("plus", size=18), "Add Assignment", size="3", on_click=s.open_form),
            spacing="3", align="center", padding_y="6",
        ),
        width="100%",
    )
    no_plan = rx.card(
        rx.vstack(
            rx.icon("sparkles", size=28, color=rx.color("gray", 9)),
            rx.text(rx.cond(s.plan_stale, "Your study plan needs to be regenerated.",
                            "Generate a study plan to see your progress."), weight="medium"),
            rx.cond(s.plan_stale, rx.text(s.plan_message, size="2", color_scheme="gray", text_align="center")),
            rx.button(rx.icon("sparkles", size=18), "Generate Study Plan", size="3", on_click=s.generate_study_plan),
            spacing="3", align="center", padding_y="6",
        ),
        width="100%",
    )
    with_plan = rx.vstack(
        overall_completion_card(),
        section("Assignments", "Each assignment's share of the plan.",
                rx.vstack(rx.foreach(s.plan_statuses, assignment_progress_row), spacing="3", width="100%")),
        rx.grid(
            section("Deadline risk", "From the optimizer: time available before each due date against work left.",
                    rx.card(rx.vstack(rx.foreach(s.plan_statuses, risk_line), spacing="0", width="100%"),
                            size="3", width="100%")),
            section("Completed", "Finished work stays out of every total.",
                    rx.card(
                        rx.cond(
                            s.completed_names.length() > 0,
                            rx.vstack(rx.foreach(s.completed_names, completed_line), spacing="2", align="start"),
                            rx.text("Nothing completed yet.", size="2", color_scheme="gray"),
                        ),
                        size="3", width="100%",
                    )),
            columns=rx.breakpoints(initial="1", lg="2"), spacing=SECTION_GAP, width="100%",
        ),
        spacing=SECTION_GAP, width="100%",
    )
    return rx.box(
        rx.container(
            rx.vstack(
                header(active="Progress"),
                rx.vstack(
                    rx.heading("Progress", size="7"),
                    rx.text("How much of your required work has a place in your plan.", size="2", color_scheme="gray"),
                    spacing="1", align="start",
                ),
                rx.cond(
                    s.assignments.length() > 0,
                    rx.cond(s.has_plan, with_plan, no_plan),
                    no_assignments,
                ),
                spacing=SECTION_GAP, width="100%", padding_bottom="9",
            ),
            size="4", padding_x=PAGE_PADDING_X,
        ),
        assignment_form(),
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
                study_time_section(),
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
        assignment_form(),   # the dialogs; invisible until their open flags are True
        slot_form(),
        slot_delete_dialog(),
        background=rx.color("gray", 1), min_height="100vh",
    )


app = rx.App(
    theme=rx.theme(accent_color="indigo", gray_color="slate", radius="large", scaling="100%"),
)

# ---------------------------------------------------------------------
# Focus page (v1.2)
# ---------------------------------------------------------------------

def focus_page() -> rx.Component:
    """
    One session, one countdown. Built to be left open while studying:
    no cards, no numbers competing with the clock, nothing that moves
    except the digits.
    """
    f = FocusState
    d = DashboardState

    def big_clock() -> rx.Component:
        return rx.text(
            f.clock, size="9", weight="bold", line_height="1", letter_spacing="-0.02em",
            font_family="ui-monospace, 'Cascadia Mono', Consolas, monospace",
            style={"fontVariantNumeric": "tabular-nums", "fontSize": "clamp(4rem, 14vw, 7.5rem)"},
        )

    def title_block(kicker: str) -> rx.Component:
        return rx.vstack(
            eyebrow(kicker),
            rx.text(f.subject, size="3", color_scheme="gray"),
            rx.heading(f.label, size=rx.breakpoints(initial="7", md="8"), text_align="center"),
            spacing="1", align="center",
        )

    def caption() -> rx.Component:
        return rx.text("Session: ", f.session_minutes, " minutes · ", f.time_label, size="2", color_scheme="gray")

    def up_next() -> rx.Component:
        return rx.cond(
            f.next_label != "",
            rx.vstack(
                rx.text("Up next", size="1", weight="bold", color_scheme="gray", letter_spacing="0.08em"),
                rx.text(f.next_label, size="4", weight="medium"),
                rx.text(f.next_time, size="2", color_scheme="gray"),
                spacing="1", align="center", padding_top="7",
                border_top=f"1px solid {rx.color('gray', 4)}", width="100%", margin_top="8",
            ),
            rx.box(),
        )

    nothing_now = rx.vstack(
        rx.cond(
            f.has_plan,
            rx.vstack(
                rx.heading("No study session right now.", size="6", text_align="center"),
                rx.text("Come back when your next block starts.", size="2", color_scheme="gray"),
                spacing="2", align="center",
            ),
            rx.vstack(
                rx.heading("No study plan yet.", size="6", text_align="center"),
                rx.text("Generate a plan and this page will show what to work on now.", size="2", color_scheme="gray"),
                rx.link(rx.button("Go to the dashboard", size="3"), href="/"),
                spacing="3", align="center",
            ),
        ),
        up_next(),
        spacing="4", align="center", width="100%",
    )

    ready = rx.vstack(
        title_block("Current study session"),
        big_clock(),
        rx.button("Start Session", on_click=f.start_session, size="4", width="min(100%, 20rem)"),
        caption(),
        up_next(),
        spacing="6", align="center", width="100%",
    )

    running = rx.vstack(
        title_block("Studying"),
        big_clock(),
        rx.hstack(
            rx.button("Pause", on_click=f.pause_session, size="3", variant="soft"),
            rx.button("Reset", on_click=f.reset_session, size="3", variant="ghost", color_scheme="gray"),
            spacing="3",
        ),
        caption(),
        up_next(),
        spacing="6", align="center", width="100%",
    )

    paused = rx.vstack(
        title_block("Paused"),
        big_clock(),
        rx.hstack(
            rx.button("Resume", on_click=f.start_session, size="3"),
            rx.button("Reset", on_click=f.reset_session, size="3", variant="ghost", color_scheme="gray"),
            spacing="3",
        ),
        caption(),
        up_next(),
        spacing="6", align="center", width="100%",
    )

    complete = rx.vstack(
        eyebrow("Session complete"),
        rx.heading(f.label, size=rx.breakpoints(initial="7", md="8"), text_align="center"),
        rx.text(f.completed_minutes, " minutes completed", size="4", color_scheme="gray"),
        rx.vstack(
            rx.button("Mark Complete", on_click=f.mark_complete, size="3", width="min(100%, 20rem)"),
            rx.button("Take Break", on_click=f.take_break, size="3", variant="soft", width="min(100%, 20rem)"),
            rx.button("Next session", on_click=f.next_session, size="3", variant="ghost", color_scheme="gray",
                      width="min(100%, 20rem)"),
            spacing="2", align="center", width="100%",
        ),
        up_next(),
        spacing="5", align="center", width="100%",
    )

    on_break = rx.vstack(
        eyebrow("Break"),
        rx.heading("Step away from the screen.", size="6", text_align="center"),
        big_clock(),
        rx.button("Skip break", on_click=f.skip_break, size="3", variant="ghost", color_scheme="gray"),
        rx.text(f.break_minutes, "-minute break, as in your plan", size="2", color_scheme="gray"),
        up_next(),
        spacing="6", align="center", width="100%",
    )

    break_over = rx.vstack(
        eyebrow("Break over"),
        rx.heading("Ready for the next one?", size="6", text_align="center"),
        rx.button("Next session", on_click=f.next_session, size="4", width="min(100%, 20rem)"),
        up_next(),
        spacing="5", align="center", width="100%",
    )

    marked = rx.vstack(
        eyebrow("Marked complete"),
        rx.heading("Nice work.", size="6", text_align="center"),
        rx.text("Your plan needs regenerating before the next session.", size="2", color_scheme="gray"),
        rx.link(rx.button("Go to the dashboard", size="3"), href="/"),
        spacing="3", align="center", width="100%",
    )

    body = rx.match(
        f.mode,
        ("ready", ready), ("running", running), ("paused", paused), ("complete", complete),
        ("break", on_break), ("break_over", break_over), ("marked", marked),
        nothing_now,
    )

    return rx.box(
        rx.container(
            rx.vstack(
                header(active="Focus"),
                rx.center(
                    rx.box(body, width="100%", max_width="40rem"),
                    width="100%", padding_y=rx.breakpoints(initial="8", md="9"), min_height="60vh",
                ),
                spacing=SECTION_GAP, width="100%", padding_bottom="9",
            ),
            size="4", padding_x=rx.breakpoints(initial="4", md="6"),
        ),
        width="100%", min_height="100vh",
    )

app.add_page(index, title="StudyFlow", on_load=DashboardState.load_data)
app.add_page(assignments_page, route="/assignments", title="Assignments · StudyFlow",
             on_load=DashboardState.load_data)
app.add_page(schedule_page, route="/schedule", title="Schedule · StudyFlow",
             on_load=DashboardState.load_data)
app.add_page(progress_page, route="/progress", title="Progress · StudyFlow",
             on_load=DashboardState.load_data)
app.add_page(focus_page, route="/focus", title="Focus · StudyFlow",
             on_load=[DashboardState.load_data, FocusState.load_focus])
