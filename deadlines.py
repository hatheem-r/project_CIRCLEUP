"""Upcoming Moodle deadlines, read from the user's private iCal feed.

    from deadlines import fetch_deadlines
    for d in fetch_deadlines():
        print(d.due_at, d.course, d.name)

The feed URL carries an auth token, so it is never echoed in errors or output.
"""

import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from icalendar import Calendar
from pydantic import BaseModel, Field, computed_field

load_dotenv()

COLOMBO = ZoneInfo("Asia/Colombo")
WINDOW_DAYS = 14

# Trailing padding Moodle puts on event names. Stripped repeatedly, so
# "Quiz 1 See grades section to view grades is due" comes back as "Quiz 1".
BOILERPLATE = (
    "is due",
    "closes",
    "opens",
    "See grades section to view grades",
)
# punctuation left dangling once a phrase comes off
_TRAILING = " -\u2013\u2014:;,."
# CATEGORIES looks like "In23-S5-CS3501 (130134)" -- CS3501 is the course code
# the timetable uses; the number in brackets is Moodle's own course id
_COURSE_CODE = re.compile(r"\b([A-Z]{2,4}\d{3,4})\b")
_MOODLE_ID = re.compile(r"\s*\(\d+\)\s*$")


class DeadlineError(RuntimeError):
    """The feed could not be fetched or read."""


class MissingFeedURL(DeadlineError):
    """MOODLE_ICAL_URL is not configured."""


class Deadline(BaseModel):
    name: str
    due_at: datetime  # always Asia/Colombo
    course: str | None = None
    all_day: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def urgency_at(self) -> datetime:
        """When this actually bites. A whole-day deadline bites at end of day,
        so a midnight one does not look like the most urgent thing on its date."""
        if self.all_day:
            return self.due_at.replace(hour=23, minute=59, second=59, microsecond=0)
        return self.due_at


class Deadlines(BaseModel):
    deadlines: list[Deadline] = Field(default_factory=list)


def feed_url() -> str:
    url = os.getenv("MOODLE_ICAL_URL", "").strip()
    if not url:
        raise MissingFeedURL("MOODLE_ICAL_URL is not set (put it in .env)")
    return url


def fetch_ical(url: str | None = None, *, timeout: float = 20.0) -> str:
    """GET the iCal feed. Errors name the host, never the tokenised URL."""
    url = url or feed_url()
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        raise DeadlineError(
            f"{httpx.URL(url).host} returned {err.response.status_code} for the iCal feed"
        ) from err
    except httpx.HTTPError as err:
        raise DeadlineError(f"could not reach {httpx.URL(url).host}: {err}") from err
    return response.text


def _due_at(value: datetime | date) -> tuple[datetime, bool]:
    """A VEVENT start in Asia/Colombo, plus whether it is a whole-day deadline."""
    all_day = not isinstance(value, datetime)
    if all_day:
        value = datetime(value.year, value.month, value.day)
    if value.tzinfo is None:
        # RFC 5545 floating time -- read it as local
        value = value.replace(tzinfo=COLOMBO)

    due_at = value.astimezone(COLOMBO)
    # Moodle stores a whole-day deadline as a timestamp; 18:30Z is midnight here,
    # and midnight means "any time that day", not "the first second of it"
    return due_at, all_day or due_at.time() == time(0, 0)


def _categories(event) -> list[str]:
    """CATEGORIES as plain strings; the property may repeat or hold a list."""
    raw = event.get("CATEGORIES")
    if raw is None:
        return []

    out: list[str] = []
    for item in raw if isinstance(raw, list) else [raw]:
        cats = getattr(item, "cats", None)
        out += [str(c) for c in cats] if cats else [str(item)]
    return [c.strip() for c in out if c.strip()]


def clean_summary(summary: str) -> str:
    """The bare task name: "Quiz 1 See grades section to view grades is due" -> "Quiz 1"."""
    name = summary.strip()

    stripping = True
    while stripping:
        stripping = False
        for phrase in BOILERPLATE:
            # never strip the whole name away -- an event called "Attendance"
            # or just "is due" keeps what it has
            if name.lower().endswith(phrase.lower()) and len(name) > len(phrase):
                name = name[: -len(phrase)].rstrip(_TRAILING)
                stripping = True

    return name or summary.strip()


def course_of(event) -> str | None:
    """The course code behind an event, or None if it cannot be worked out."""
    categories = _categories(event)
    for category in categories:
        if match := _COURSE_CODE.search(category):
            return match.group(1)
    # no recognisable code anywhere, but a category still beats nothing
    for category in categories:
        if label := _MOODLE_ID.sub("", category).strip():
            return label
    return None


def parse_deadlines(
    ical_text: str,
    *,
    now: datetime | None = None,
    within_days: int = WINDOW_DAYS,
) -> list[Deadline]:
    """Every VEVENT falling due between now and `within_days` from now, soonest first."""
    try:
        calendar = Calendar.from_ical(ical_text)
    except ValueError as err:
        raise DeadlineError(f"feed is not valid iCalendar: {err}") from err

    now = (now or datetime.now(COLOMBO)).astimezone(COLOMBO)
    cutoff = now + timedelta(days=within_days)

    found: list[Deadline] = []
    for event in calendar.walk("VEVENT"):
        start = event.get("DTSTART")
        summary = str(event.get("SUMMARY") or "").strip()
        if start is None or not summary:
            continue  # nothing useful to show

        due_at, all_day = _due_at(start.dt)
        deadline = Deadline(
            name=clean_summary(summary),
            due_at=due_at,
            course=course_of(event),
            all_day=all_day,
        )
        # windowed on urgency, so a whole-day deadline stays listed all day
        # instead of dropping out at one minute past midnight
        if not now <= deadline.urgency_at <= cutoff:
            continue

        found.append(deadline)

    found.sort(key=lambda d: (d.urgency_at, d.name))
    return found


def fetch_deadlines(*, within_days: int = WINDOW_DAYS) -> list[Deadline]:
    """Fetch the configured feed and return its upcoming deadlines."""
    return parse_deadlines(fetch_ical(), within_days=within_days)


def main() -> None:
    try:
        found = fetch_deadlines()
    except DeadlineError as err:
        sys.exit(str(err))

    print(json.dumps([d.model_dump(mode="json") for d in found], indent=2))


if __name__ == "__main__":
    main()
