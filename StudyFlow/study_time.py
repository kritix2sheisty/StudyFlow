"""
StudyFlow/study_time.py
The logic behind the Study Time form, kept out of the page and the
State so it can be tested on its own.

A TimeSlot (models.py) is a recurring weekly period on the 24-hour
clock: weekday, start_hour, end_hour, whole hours only. The page
shows friendly labels such as "4:00 PM"; these functions translate
between those labels and the integers the model expects, so the
stored value is always exactly what models.py defines.
"""

from typing import Dict, Iterable, List

from models import TimeSlot, Weekday

WEEKDAYS = [d.name.title() for d in Weekday]          # "Monday" ... "Sunday"
FIELDS = ["weekday", "start", "end"]


def hour_label(hour: int) -> str:
    """24-hour integer -> '4:00 PM'. 0 and 24 are midnight, 12 is noon."""
    if hour % 24 == 0:
        return "12:00 AM"
    if hour == 12:
        return "12:00 PM"
    return f"{hour % 12}:00 {'AM' if hour < 12 else 'PM'}"


# Start can be any hour of the day; end must come after the start, so it
# runs one hour later and can reach midnight (24).
START_CHOICES = [hour_label(h) for h in range(0, 24)]
END_CHOICES = [hour_label(h) for h in range(1, 25)]
_HOUR_BY_LABEL = {**{hour_label(h): h for h in range(0, 24)}, hour_label(24): 24}
_HOUR_BY_LABEL["12:00 AM"] = 0   # as a start; ends resolve midnight to 24 below


def label_to_hour(label: str, as_end: bool = False) -> int:
    """'4:00 PM' -> 16. As an end time, '12:00 AM' means the end of the day (24)."""
    hour = _HOUR_BY_LABEL[label]
    if as_end and hour == 0:
        return 24
    return hour


def no_errors() -> Dict[str, str]:
    return {field: "" for field in FIELDS}


def is_valid(errors: Dict[str, str]) -> bool:
    return not any(errors.values())


def validate_form(weekday: str, start: str, end: str) -> Dict[str, str]:
    """A message per field that is wrong; every field is always a key."""
    errors = no_errors()
    if weekday not in WEEKDAYS:
        errors["weekday"] = "Choose a day."
    if start not in START_CHOICES:
        errors["start"] = "Choose a start time."
    if end not in END_CHOICES:
        errors["end"] = "Choose an end time."
    if not errors["start"] and not errors["end"]:
        if label_to_hour(end, as_end=True) <= label_to_hour(start):
            errors["end"] = "The end time must be later than the start time."
    return errors


def to_time_slot(weekday: str, start: str, end: str) -> TimeSlot:
    """Validated labels -> the model's TimeSlot. Call validate_form() first."""
    return TimeSlot(
        weekday=Weekday.from_name(weekday),
        start_hour=label_to_hour(start),
        end_hour=label_to_hour(end, as_end=True),
    )


def row_from_slot(slot: TimeSlot) -> Dict[str, str]:
    """The page's row for one stored slot: every value a string."""
    return {
        "id": str(slot.id) if slot.id is not None else "",
        "weekday": slot.weekday.name.title(),
        "time": f"{hour_label(slot.start_hour)} – {hour_label(slot.end_hour)}",
        "hours": f"{slot.duration_hours}h",
    }


def rows_from(slots: Iterable[TimeSlot]) -> List[Dict[str, str]]:
    """Rows in week order: Monday first, earlier start first within a day."""
    ordered = sorted(slots, key=lambda s: (int(s.weekday), s.start_hour))
    return [row_from_slot(s) for s in ordered]


def total_hours(slots: Iterable[TimeSlot]) -> float:
    return float(sum(s.duration_hours for s in slots))
