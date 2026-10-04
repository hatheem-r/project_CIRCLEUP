"""Free windows between classes -- plain python, no model involved.

    from gaps import free_windows
    for w in free_windows(classes):
        print(w.start, w.duration_hours)
"""

import json
import sys
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Iterable
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # keeps this module importable without the VLM stack
    from extract_schedule import ClassBlock

COLOMBO = ZoneInfo("Asia/Colombo")
DAY_START = time(8, 0)
DAY_END = time(22, 0)
MIN_HOURS = 2.0
HORIZON_DAYS = 7

# weekday() -> the day name the timetable uses. Not strftime("%A"), which is
# locale-dependent; Saturday and Sunday are here so dates still map to a name,
# but no class block can carry them, so weekends come back wholly free.
WEEKDAY_NAMES = (
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
)
CLASS_DAYS = frozenset(WEEKDAY_NAMES[:5])


class FreeWindow(BaseModel):
    start: datetime
    end: datetime
    duration_hours: float


class Windows(BaseModel):
    windows: list[FreeWindow] = Field(default_factory=list)


def _at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=COLOMBO)


def _by_weekday(classes: Iterable["ClassBlock"]) -> dict[str, list["ClassBlock"]]:
    grouped: dict[str, list[ClassBlock]] = {}
    for block in classes:
        name = str(block.day).upper()
        if name in CLASS_DAYS:  # weekends never carry classes
            grouped.setdefault(name, []).append(block)
    return grouped


def busy_blocks(
    classes: Iterable["ClassBlock"],
    *,
    today: date | None = None,
    days: int = HORIZON_DAYS,
    day_start: time = DAY_START,
    day_end: time = DAY_END,
) -> list[tuple[datetime, datetime]]:
    """The weekly timetable projected onto the next `days` dates, overlaps merged.

    Every row counts as busy. That deliberately includes "University Research Hour"
    and "Union Hour": they carry no course code, but they are still time spent.
    Saturday and Sunday contribute nothing, so they come back entirely free.
    """
    today = today or datetime.now(COLOMBO).date()
    grouped = _by_weekday(classes)

    spans: list[tuple[datetime, datetime]] = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        for block in grouped.get(WEEKDAY_NAMES[day.weekday()], []):
            start = _at(day, time.fromisoformat(block.start))
            end = _at(day, time.fromisoformat(block.end))
            # clip to the day's bounds and drop anything outside them
            start = max(start, _at(day, day_start))
            end = min(end, _at(day, day_end))
            if start < end:
                spans.append((start, end))

    return _merge(spans)


def _merge(spans: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Sorted, non-overlapping spans. Back-to-back classes become one block."""
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def free_windows(
    classes: Iterable["ClassBlock"],
    *,
    today: date | None = None,
    days: int = HORIZON_DAYS,
    min_hours: float = MIN_HOURS,
    day_start: time = DAY_START,
    day_end: time = DAY_END,
) -> list[FreeWindow]:
    """Gaps of at least `min_hours` between classes, within `day_start`-`day_end`.

    Covers the next `days` dates starting today, weekends included.
    """
    today = today or datetime.now(COLOMBO).date()
    busy = busy_blocks(
        classes, today=today, days=days, day_start=day_start, day_end=day_end
    )

    found: list[FreeWindow] = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        opens, closes = _at(day, day_start), _at(day, day_end)

        cursor = opens
        for start, end in busy:
            if end <= opens or start >= closes:
                continue  # a different day
            found += _window(cursor, start, min_hours)
            cursor = max(cursor, end)
        found += _window(cursor, closes, min_hours)

    return found


def _window(start: datetime, end: datetime, min_hours: float) -> list[FreeWindow]:
    """One window, or nothing if the gap is too short."""
    hours = (end - start).total_seconds() / 3600
    if hours < min_hours:
        return []
    return [FreeWindow(start=start, end=end, duration_hours=round(hours, 2))]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <classes.json>")

    from extract_schedule import ClassBlock  # noqa: PLC0415 -- CLI only

    raw = json.loads(open(sys.argv[1]).read())
    classes = [ClassBlock.model_validate(row) for row in raw]
    found = free_windows(classes)
    print(json.dumps([w.model_dump(mode="json") for w in found], indent=2))


if __name__ == "__main__":
    main()
