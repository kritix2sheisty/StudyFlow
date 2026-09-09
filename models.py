"""
models.py
Core data models for StudyFlow — AI Student Scheduler (Phase 1).

These are plain dataclasses that represent the entities a student
works with: Classes, Assignments, Tests, and available TimeSlots.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum
from typing import Optional


class Priority(IntEnum):
    """Priority/difficulty scale used by Assignments and Tests."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @classmethod
    def from_name(cls, name: str) -> "Weekday":
        return cls[name.strip().upper()]


@dataclass
class Class:
    """A course/subject the student is taking."""
    id: Optional[int] = None
    name: str = ""          # e.g. "Mathematics"
    code: str = ""          # e.g. "MATH-201" (optional short code)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})" if self.code else self.name


@dataclass
class Assignment:
    """A piece of coursework with a due date."""
    id: Optional[int] = None
    name: str = ""
    subject: str = ""              # links to a Class.name
    due_date: date = field(default_factory=date.today)
    estimated_hours: float = 1.0
    priority: Priority = Priority.MEDIUM
    completed: bool = False

    def __str__(self) -> str:
        return (f"[{self.priority.name}] {self.name} ({self.subject}) "
                f"— due {self.due_date.isoformat()}, "
                f"~{self.estimated_hours}h")


@dataclass
class Test:
    """An upcoming test/exam."""
    __test__ = False  # tells pytest this isn't a test class, despite the name
    id: Optional[int] = None
    subject: str = ""
    date: date = field(default_factory=date.today)
    topics: str = ""                # free-text list of topics, comma-separated
    importance: Priority = Priority.MEDIUM

    def __str__(self) -> str:
        return (f"[{self.importance.name}] {self.subject} test "
                f"on {self.date.isoformat()} — topics: {self.topics}")


@dataclass
class TimeSlot:
    """A recurring block of time the student is available to study."""
    id: Optional[int] = None
    weekday: Weekday = Weekday.MONDAY
    start_hour: int = 16   # 24h clock, e.g. 16 = 4 PM
    end_hour: int = 19     # e.g. 19 = 7 PM

    @property
    def duration_hours(self) -> int:
        return self.end_hour - self.start_hour

    def __str__(self) -> str:
        def fmt(h: int) -> str:
            suffix = "AM" if h < 12 else "PM"
            hour12 = h % 12 or 12
            return f"{hour12} {suffix}"
        return (f"{self.weekday.name.title()} "
                f"{fmt(self.start_hour)}–{fmt(self.end_hour)} "
                f"({self.duration_hours}h)")
