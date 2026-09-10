"""
studyflow_web/studyflow_web.py
The StudyFlow web app, built with Reflex.

One page, three areas: the student's assignments, their weekly study
time, and the generated plan. The page holds no logic; every event
handler calls studyflow_web/service.py, which calls the engine.

Run with:  reflex run
"""

from dataclasses import dataclass

import reflex as rx

from studyflow_web import service

RISK_COLORS = {"CRITICAL": "red", "HIGH": "orange", "MODERATE": "yellow", "LOW": "green"}
STATUS_COLORS = {"COMPLETE": "green", "PARTIAL": "orange", "UNSCHEDULED": "red"}


@dataclass
class Block:
    """One entry on a day of the plan."""
    time: str
    label: str
    is_break: str


@dataclass
class Day:
    """One day of the plan and its entries, in order."""
    label: str
    blocks: list[Block]


class State(rx.State):
    """Everything the page shows, and the events that change it."""

    assignments: list[dict[str, str]] = []
    slots: list[dict[str, str]] = []
    error: str = ""

    # The generated plan, flattened into plain vars the page can render.
    has_plan: bool = False
    plan_today: str = ""
    plan_days: list[Day] = []
    progress: dict[str, str] = {}
    statuses: list[dict[str, str]] = []
    at_risk: list[str] = []

    # ---- loading ----

    def load(self):
        self.assignments = service.list_assignments()
        self.slots = service.list_slots()

    # ---- assignments ----

    def add_assignment(self, form: dict):
        self.error = service.add_assignment(
            form.get("name", ""), form.get("subject", ""), form.get("due", ""),
            form.get("hours", ""), form.get("priority", ""),
        ) or ""
        self.load()

    def toggle_assignment(self, assignment_id: str):
        service.toggle_assignment(assignment_id)
        self.load()

    def delete_assignment(self, assignment_id: str):
        service.delete_assignment(assignment_id)
        self.load()

    # ---- study time ----

    def add_slot(self, form: dict):
        self.error = service.add_slot(
            form.get("weekday", ""), form.get("start", ""), form.get("end", ""),
        ) or ""
        self.load()

    def delete_slot(self, slot_id: str):
        service.delete_slot(slot_id)
        self.load()

    # ---- the plan ----

    def generate(self):
        plan = service.build_plan()
        self.plan_today = plan["today"]
        self.plan_days = [
            Day(label=d["label"], blocks=[Block(**b) for b in d["blocks"]])
            for d in plan["days"]
        ]
        self.progress = plan["progress"]
        self.statuses = plan["statuses"]
        self.at_risk = plan["at_risk"]
        self.has_plan = True
        self.error = "" if plan["has_slots"] else "Add some study time first, then generate again."


# ---------------------------------------------------------------------
# Pieces of the page
# ---------------------------------------------------------------------

def assignment_row(a: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(a["name"], weight="bold"), rx.text(a["subject"], size="1", color_scheme="gray")),
        rx.table.cell(rx.text(a["due"]), rx.text(a["due_in"], size="1", color_scheme="gray")),
        rx.table.cell(a["hours"], "h"),
        rx.table.cell(rx.badge(a["priority"], variant="soft")),
        rx.table.cell(
            rx.cond(a["completed"] == "yes", rx.badge("Done", color_scheme="green"), rx.badge("Active", color_scheme="blue")),
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.cond(a["completed"] == "yes", "Reopen", "Mark done"),
                    size="1", variant="soft", on_click=State.toggle_assignment(a["id"]),
                ),
                rx.button("Delete", size="1", variant="soft", color_scheme="red",
                          on_click=State.delete_assignment(a["id"])),
                spacing="2",
            ),
        ),
    )


def assignments_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading("Assignments", size="5"),
            rx.cond(
                State.assignments.length() > 0,
                rx.table.root(
                    rx.table.header(rx.table.row(
                        rx.table.column_header_cell("Assignment"),
                        rx.table.column_header_cell("Due"),
                        rx.table.column_header_cell("Effort"),
                        rx.table.column_header_cell("Priority"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell(""),
                    )),
                    rx.table.body(rx.foreach(State.assignments, assignment_row)),
                    width="100%",
                ),
                rx.text("No assignments yet. Add one below.", color_scheme="gray"),
            ),
            rx.form(
                rx.hstack(
                    rx.input(name="name", placeholder="Assignment", required=True),
                    rx.input(name="subject", placeholder="Subject"),
                    rx.input(name="due", type="date", required=True),
                    rx.input(name="hours", type="number", step="0.25", min="0", placeholder="Hours", width="6em"),
                    rx.select(
                        items=list(service.PRIORITIES.values()),
                        default_value="Medium", name="priority", width="8em",
                    ),
                    rx.button("Add", type="submit"),
                    spacing="2", wrap="wrap", align="end",
                ),
                on_submit=State.add_assignment, reset_on_submit=True,
            ),
            spacing="4", width="100%",
        ),
        width="100%",
    )


def slot_row(s: dict) -> rx.Component:
    return rx.hstack(
        rx.text(s["weekday"], weight="bold", width="7em"),
        rx.text(s["time"]),
        rx.spacer(),
        rx.button("Delete", size="1", variant="soft", color_scheme="red", on_click=State.delete_slot(s["id"])),
        width="100%",
    )


def study_time_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading("Weekly study time", size="5"),
            rx.cond(
                State.slots.length() > 0,
                rx.vstack(rx.foreach(State.slots, slot_row), width="100%", spacing="2"),
                rx.text("No study time yet. Add the hours you are free each week.", color_scheme="gray"),
            ),
            rx.form(
                rx.hstack(
                    rx.select(items=[d.title() for d in service.WEEKDAYS], default_value="Monday", name="weekday"),
                    rx.input(name="start", type="number", min="0", max="23", placeholder="Start (24h)", width="8em"),
                    rx.input(name="end", type="number", min="1", max="24", placeholder="End (24h)", width="8em"),
                    rx.button("Add", type="submit"),
                    spacing="2", wrap="wrap", align="end",
                ),
                on_submit=State.add_slot, reset_on_submit=True,
            ),
            spacing="4", width="100%",
        ),
        width="100%",
    )


def block_line(b: Block) -> rx.Component:
    return rx.hstack(
        rx.text(b.time, width="10em", color_scheme="gray"),
        rx.cond(
            b.is_break == "yes",
            rx.text("Break", color_scheme="gray", style={"font_style": "italic"}),
            rx.text(b.label, weight="bold"),
        ),
    )


def day_card(day: Day) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading(day.label, size="3"),
            rx.foreach(day.blocks, block_line),
            spacing="1", align="start",
        ),
    )


def stat(label: str, value: rx.Var, unit: str) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color_scheme="gray"),
        rx.heading(value, unit, size="6"),
        spacing="0", align="start",
    )


def status_row(s: dict) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(s["name"], weight="bold"),
            rx.text(s["scheduled"], " / ", s["required"], "h scheduled, due ", s["due"], size="1", color_scheme="gray"),
            spacing="0", align="start",
        ),
        rx.spacer(),
        rx.badge(s["status"], color_scheme=rx.match(s["status"], *STATUS_COLORS.items(), "gray")),
        rx.cond(
            s["risk"] != "",
            rx.badge("Risk: ", s["risk"], color_scheme=rx.match(s["risk"], *RISK_COLORS.items(), "gray")),
        ),
        width="100%", align="center",
    )


def plan_section() -> rx.Component:
    return rx.cond(
        State.has_plan,
        rx.vstack(
            rx.heading("Your study plan", size="6"),
            rx.text("Week of ", State.plan_today, color_scheme="gray"),
            rx.cond(
                State.plan_days.length() > 0,
                rx.grid(rx.foreach(State.plan_days, day_card), columns="3", spacing="3", width="100%"),
                rx.callout("Nothing could be scheduled this week.", icon="info"),
            ),
            rx.card(
                rx.hstack(
                    stat("Required", State.progress["required"], "h"),
                    stat("Scheduled", State.progress["scheduled"], "h"),
                    stat("Unscheduled", State.progress["unscheduled"], "h"),
                    stat("Completion", State.progress["completion"], "%"),
                    spacing="8", wrap="wrap",
                ),
                width="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("Assignment status", size="4"),
                    rx.cond(
                        State.statuses.length() > 0,
                        rx.vstack(rx.foreach(State.statuses, status_row), width="100%", spacing="3"),
                        rx.text("No active assignments.", color_scheme="gray"),
                    ),
                    spacing="3", width="100%",
                ),
                width="100%",
            ),
            spacing="4", width="100%",
        ),
    )


def index() -> rx.Component:
    return rx.container(
        rx.vstack(
            rx.heading("StudyFlow", size="8"),
            rx.text("Enter what is due and when you are free. StudyFlow plans the week and tells you what is at risk.",
                    color_scheme="gray"),
            rx.cond(State.error != "", rx.callout(State.error, icon="triangle_alert", color_scheme="red")),
            assignments_card(),
            study_time_card(),
            rx.button("Generate study plan", size="3", on_click=State.generate),
            plan_section(),
            spacing="5", width="100%", padding_y="6",
        ),
        size="4",
    )


app = rx.App()
app.add_page(index, title="StudyFlow", on_load=State.load)
