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
* Automated test suite pinning every prioritization promise (`tests/test_scheduler.py`)

#### How prioritization decides

StudyFlow's rule of thumb: **deadlines first, importance second, size is a nudge, never a veto.**

Missing a deadline is the one outcome a scheduler must never cause, and the
schedule builder works through the prioritized list in order anyway. So a
small task due tomorrow goes ahead of a big task due next week: the big task
loses an hour or two of lead time, whereas the other order could cost the
small task its deadline.

The score is a weighted blend, not an exact optimum:

```
score = urgency × 5  +  priority × 3  +  min(hours, 5) × 1
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
7. Up to four days out, a deadline still beats anything due much later. From
   five days out, deadline pressure has faded and importance and size decide,
   so a big high-priority project due next term outranks a small low-priority
   worksheet due in a month.

The full rationale, including the alternatives that were rejected, is in the
module docstring of `scheduler.py`.

### Future Development

* Phase 3: Generate study schedules from available time slots
* Detect scheduling conflicts
* Distribute large assignments across multiple study sessions
* Improve schedule optimization
* Add a graphical/web interface
* Introduce AI-assisted study recommendations

## Running the tests

```
pip install pytest
pytest
```

Tests live in `tests/`. A `conftest.py` at the project root puts the project
on the import path, so `pytest` works from the project root without any
packaging.

## Technologies

* Python
* SQLite
* Streamlit *(planned/under development)*
* Algorithms and data structures
* AI/LLM integration *(future phase)*

## Project Goal

The long-term goal of StudyFlow is to create a practical academic scheduling tool that can intelligently prioritize and organize a student's workload while providing understandable recommendations about why certain tasks should be completed first.
