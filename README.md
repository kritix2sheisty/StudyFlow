# StudyFlow — AI Student Scheduler

StudyFlow is a student-focused scheduling application designed to help students organize their academic workload and make better decisions about what to study next.

The project currently uses a Python command-line interface and includes functionality for managing classes, assignments, tests, and available study time. It also includes a prioritization system that evaluates assignments based on factors such as due date, priority, estimated effort, and completion status.

The project is being developed in multiple phases, with the goal of eventually generating personalized study schedules and incorporating AI-assisted recommendations.

## Current Progress

### Phase 1 — Academic Data Management

* Add, view, edit, and delete classes
* Add, view, edit, and delete assignments
* Add, view, and delete tests
* Add and delete available study-time slots
* View assignments due within the next 7 days
* Mark assignments as complete/incomplete
* Store and manage academic data

### Phase 2 — Assignment Prioritization

* Exclude completed assignments
* Identify overdue and due-today assignments
* Calculate assignment urgency
* Consider assignment priority
* Consider estimated workload (capped, so size never outranks a deadline)
* Rank assignments using a weighted scoring system
* Automated test suite: 13 scenarios plus every prioritization promise (`tests/test_scheduler.py`)

#### How prioritization decides

StudyFlow's rule of thumb: **deadlines first, importance second, size is a nudge, never a veto.**

Missing a deadline is the one outcome a scheduler must never cause, and the
schedule builder works through the prioritized list in order anyway. So a
small task due tomorrow goes ahead of a big task due next week: the big task
loses an hour or two of lead time, whereas the other order could cost the
small task its deadline.

The score is a weighted blend, not an exact optimum:

```
score = urgency × 5  +  priority × 3  +  min(hours, 5) × 0.5
```

where urgency is `10 / days_left`. Overdue and due-today items are a separate
tier that always sorts first. The weights and the 5-hour effort cap are chosen
so that these promises hold, and each one has a test:

1. Completed assignments are never listed.
2. Overdue or due-today work comes before everything else. Among those,
   priority decides, then size. How late something is does not matter.
3. Anything due tomorrow comes before anything due later, whatever its
   priority or size.
4. On the same due date, higher priority wins no matter the size.
5. On the same due date and priority, the bigger task goes first, because it
   needs to be started sooner.
6. From two days out, importance and size can pull a task ahead of one due a
   day or two sooner. A 10-hour high-priority exam prep due in four days
   starts before a 1-hour low-priority worksheet due in three.
7. Up to five days out, a deadline still beats anything due much later. From
   six days out, deadline pressure has faded and importance and size decide,
   so a big high-priority project due next term outranks a small low-priority
   worksheet due in a month.

The full rationale, including the alternatives that were rejected, is in the
module docstring of `scheduler.py`.

### Phase 3 — Schedule Generation (in progress)

* Turn recurring weekly study slots into concrete, dated study blocks
* Place work on or before its due date, never after
* Fill by earliest deadline first, with the Phase 2 ranking breaking ties
* Split large assignments across several blocks and days
* Insert breaks between study periods
* Report any work that could not fit before its due date
* Test suite for deadlines, allocation and break behaviour (`tests/test_schedule_builder.py`)
* Schedule quality: scheduled, unscheduled and required hours, and a completion percentage (`schedule_analyzer.py`)
* Assignment-level analysis: hours scheduled, hours remaining and a COMPLETE / PARTIAL / UNSCHEDULED status per assignment
* Analysis report: `format_analysis()` prints the totals and, per assignment, status, hours and deadline risk (CLI: View schedule analysis)
* At-risk detection: assignments that are not completed and not fully scheduled
* One workflow: `generate_study_plan()` prioritizes, schedules, analyzes and flags in one call, and `format_study_plan()` renders the weekly report (`study_plan.py`; CLI: Generate study plan)

### Phase 3 milestone — End-to-end workflow

* `python main.py` opens a grouped menu: manage classes, assignments, tests and study time, then
  **Generate study plan** runs the whole pipeline and prints the weekly report
* Scripted end-to-end test drives the menus like a student would (`tests/test_main.py`)

### Phase 4 — Intelligent Scheduling (in progress)

* Time-remaining awareness: `available_hours_before_deadline()` measures the study time between today and an assignment's due date (`schedule_optimizer.py`)
* Deadline risk ratio: `deadline_risk_ratio()` divides that available time by the hours an assignment still needs (0.5 means half the time needed; infinity means nothing left to do)
* Risk level: `risk_level()` turns the ratio into CRITICAL (under 1), HIGH (1 to 1.5), MODERATE (1.5 to 2) or LOW (2 and above)

### Future Development

* Show assignment status and deadline risk in the study plan report
* Improve schedule optimization (spread work evenly, cap hours per day)
* Grow the web interface toward multi-student use (see the roadmap above)
* Introduce AI-assisted study recommendations

## Scheduling Algorithm

StudyFlow currently uses a **greedy, deadline-aware** scheduling approach.

1. Remove completed assignments.
2. Prioritize the remaining assignments using the Phase 2 scoring system.
3. Generate concrete study blocks from the student's recurring time slots.
4. Re-order the assignments by due date, earliest first, using the Phase 2
   ranking to break ties.
5. Assign each assignment's work to the earliest available blocks on or
   before its due date, splitting it across blocks when necessary.
6. Insert a break between study periods that share a block.
7. Record any work that could not be scheduled before its due date.

Greedy means each placement is decided once and never revisited. This approach
was chosen because it is simple, predictable, and computationally efficient.
It does not guarantee the mathematically optimal schedule.

**Why earliest deadline first?** The Phase 2 ranking answers "what should I
work on next?" and blends urgency, importance and size. Placing hours in that
order can let a large, important task due later swallow the time a small task
due sooner needed. Ordering placement by deadline instead is a classical
result: when work can be split, it meets every deadline whenever any order
can. Phase 2 still decides among assignments that share a due date.

**Known limitations.** Work is front-loaded into the earliest blocks rather
than spread evenly across the days before a deadline. Breaks can leave a few
minutes unused. There is no cap on hours per day and no preference for
variety. Future versions may explore more advanced scheduling and
optimization techniques once StudyFlow defines what "better" means.

## Running the tests

```
pip install pytest
pytest
```

Tests live in `tests/`. A `conftest.py` at the project root puts the project
on the import path, so `pytest` works from the project root without any
packaging.

## Web interface (Reflex)

StudyFlow's user interface is built with [Reflex](https://reflex.dev), a
Python framework that compiles to a real web app. One page lets a student
enter assignments and weekly study time, generate the plan, and see the
timetable, progress and per-assignment risk.

```
pip install -r requirements.txt
reflex run
```

Open http://localhost:3000. On an older Windows console `reflex run` can crash
with a `UnicodeEncodeError` from its progress spinner; use Windows Terminal or
set `PYTHONUTF8=1` first.

The page holds no logic. Every event calls `studyflow_web/service.py`, which
calls the engine and returns plain rows for the page to render. That file is
the seam for the long-term goal: use by schools, where many students each see
only their own data. When that arrives the service functions gain a student
argument and the pages stay the same.

**Decision: Reflex rather than Streamlit.** Streamlit is a single script
re-run top to bottom on every interaction, which suits a personal tool but
fights multi-user apps: per-user state, log-in, and separate pages all work
against it. Reflex gives an ordinary web app (state per session, routing,
authentication when needed, a normal deployment) while staying in Python and
reusing the engine unchanged.

## Roadmap to school use

1. Accounts: a student signs in and sees only their own assignments and time.
2. Storage: move from one SQLite file to a database with a student column,
   behind the same service functions.
3. Classes and tests in the web UI (the CLI already manages them).
4. Hosting: one deployment a school can point students at.

## Technologies

* Python
* SQLite
* Reflex (web interface)
* Algorithms and data structures
* AI/LLM integration *(future phase)*

## Project Goal

The long-term goal of StudyFlow is to create a practical academic scheduling tool that can intelligently prioritize and organize a student's workload while providing understandable recommendations about why certain tasks should be completed first.
