"""Rate each free window as a time to go out, and have a model word the verdict.

The verdict is arithmetic, so python decides it. The model is shown one window,
that verdict, and the single nearest deadline -- no list to miscount, no sums to
get wrong -- and is asked only for the sentence.

    from suggest import suggest_windows
    for s in suggest_windows(windows, deadlines):
        print(s.verdict, s.reason)
"""

import json
import sys
from datetime import datetime
from enum import StrEnum
from typing import Iterable
from zoneinfo import ZoneInfo

import ollama
from pydantic import BaseModel, Field, ValidationError

from deadlines import Deadline
from extract_schedule import strip_fences
from gaps import FreeWindow

MODEL = "gemma3:4b"
COLOMBO = ZoneInfo("Asia/Colombo")

# hours between the end of the window and the nearest deadline after it
GOOD_AFTER_HOURS = 72.0
AVOID_WITHIN_HOURS = 24.0

PROMPT = """Write one sentence telling a student why this window is {verdict}
for going out with friends.
Mention the deadline by name only if the verdict is risky or
avoid. Do not mention any other deadline. Do not state numbers
of days or hours. Do not give advice about time management."""

RETRY_PROMPT = "That reply was empty. Write the sentence now, as plain text, nothing else."

PLACES_PROMPT = """You are helping a university student pick where to go with
friends during a free window.
Below is a numbered list of nearby places.
Pick the 3 that best fit this window and write one short
sentence for each explaining why it fits.
Refer to each place ONLY by its number.
Do not invent places that are not in the list.
Do not mention opening hours, prices, distances or ratings -
you have not been given them.
Consider the time of day and how long the window is.
Output JSON only: {"picks": [{"index": 0, "why": "..."}]}"""


class SuggestError(RuntimeError):
    """The model never produced a usable sentence."""


class Verdict(StrEnum):
    GOOD = "good"
    RISKY = "risky"
    AVOID = "avoid"


# best first
VERDICT_ORDER = (Verdict.GOOD, Verdict.RISKY, Verdict.AVOID)


class DeadlineView(BaseModel):
    """A deadline with the distances worked out, both from now and from a window."""

    name: str
    course: str | None = None
    due_at: datetime
    urgency_at: datetime  # what the distances below are measured to
    all_day: bool = False
    hours_until_due: float
    days_until_due: int
    hours_after_window: float


class WindowContext(BaseModel):
    """One window, its computed verdict, and the deadlines behind it."""

    window: FreeWindow
    verdict: Verdict
    deadlines: list[DeadlineView] = Field(default_factory=list)

    @property
    def nearest(self) -> DeadlineView | None:
        """The only deadline the model is ever told about."""
        return self.deadlines[0] if self.deadlines else None


class Suggestion(BaseModel):
    start: datetime
    end: datetime
    verdict: Verdict
    reason: str


class Suggestions(BaseModel):
    suggestions: list[Suggestion] = Field(default_factory=list)


class Place(BaseModel):
    """A place as the places proxy hands it over."""

    name: str
    address: str | None = None
    rating: float | None = None
    maps_url: str


class PlacePick(BaseModel):
    """A chosen place. Everything but `why` is copied from the input, never the model."""

    name: str
    address: str | None = None
    rating: float | None = None
    maps_url: str
    why: str


class PlacePicks(BaseModel):
    picks: list[PlacePick] = Field(default_factory=list)


class _Pick(BaseModel):
    index: int
    why: str


class _Picks(BaseModel):
    picks: list[_Pick]


def verdict_for(hours_until_nearest: float | None) -> Verdict:
    """The verdict, from the gap between the window closing and the next deadline."""
    if hours_until_nearest is None:
        return Verdict.GOOD  # nothing due in the lookahead at all
    if hours_until_nearest > GOOD_AFTER_HOURS:
        return Verdict.GOOD
    if hours_until_nearest < AVOID_WITHIN_HOURS:
        return Verdict.AVOID
    return Verdict.RISKY


def window_contexts(
    windows: Iterable[FreeWindow],
    deadlines: Iterable[Deadline],
    *,
    now: datetime | None = None,
) -> list[WindowContext]:
    """Pair each window with the deadlines that land after it, soonest first.

    Distances are measured from `urgency_at`, so a whole-day deadline counts from
    the end of its day rather than from midnight.
    """
    now = (now or datetime.now(COLOMBO)).astimezone(COLOMBO)
    deadlines = list(deadlines)

    contexts: list[WindowContext] = []
    for window in windows:
        views: list[DeadlineView] = []
        for deadline in deadlines:
            bites = deadline.urgency_at
            if bites < window.end:
                continue  # already gone, or lands before this window closes

            views.append(
                DeadlineView(
                    name=deadline.name,
                    course=deadline.course,
                    due_at=deadline.due_at,
                    urgency_at=bites,
                    all_day=deadline.all_day,
                    hours_until_due=round((bites - now).total_seconds() / 3600, 1),
                    # calendar days, so "due tomorrow" reads as 1 whatever the clock
                    days_until_due=(bites.date() - now.date()).days,
                    hours_after_window=round(
                        (bites - window.end).total_seconds() / 3600, 1
                    ),
                )
            )

        views.sort(key=lambda v: v.hours_after_window)
        contexts.append(
            WindowContext(
                window=window,
                verdict=verdict_for(views[0].hours_after_window if views else None),
                deadlines=views,
            )
        )

    return contexts


def _due_label(view: DeadlineView) -> str:
    """How the due time is described to the model.

    A whole-day deadline is quoted as end of day, since quoting its raw 00:00 would
    read as if it fell before the window it actually follows.
    """
    if view.all_day:
        return f"due by the end of {view.due_at:%A %d %B}"
    return f"due on {view.due_at:%A %d %B} at {view.due_at:%H:%M}"


def summarise(context: WindowContext) -> str:
    """The briefing for one window: no counts, no durations, nothing to add up."""
    window = context.window
    # date and clock on separate lines: given them together, the model has read
    # "Sat 10 Oct from 08:00 to 22:00" as a range of dates
    lines = [
        f"Window: {window.start:%A %d %B}",
        f"Time: {window.start:%H:%M} until {window.end:%H:%M} the same day",
    ]
    # the verdict is not repeated here: the prompt already names it, and given it
    # twice the model quotes it back ("given the \"avoid\" verdict...")

    nearest = context.nearest
    if nearest is None:
        lines.append("Nearest deadline after it: none.")
    else:
        # quoted name, course in prose: bracketed "[MA2024]" got parroted verbatim
        course = f" for the course {nearest.course}" if nearest.course else ""
        lines.append(
            f'Nearest deadline after it: "{nearest.name}"{course}, {_due_label(nearest)}'
        )

    return "\n".join(lines)


def _clean_sentence(reply: str) -> str:
    """One tidy line: models like to fence a sentence, or wrap it in quotes."""
    text = " ".join(strip_fences(reply).split())
    return text.strip("\"'“”").strip()


def _ask(context: WindowContext, model: str) -> str:
    """The sentence for one window, with a single retry if nothing comes back."""
    prompt = PROMPT.format(verdict=context.verdict.value)
    messages = [{"role": "user", "content": f"{prompt}\n\n{summarise(context)}"}]

    for attempt in (1, 2):
        reply = ollama.chat(
            model=model,
            messages=messages,
            # a little warmth for the wording; the verdict is already settled
            options={"temperature": 0.3, "num_predict": 200},
        ).message.content or ""

        if sentence := _clean_sentence(reply):
            return sentence

        if attempt == 2:
            raise SuggestError(
                f"{model} returned nothing usable for the window at "
                f"{context.window.start:%a %d %b %H:%M}, even after one retry."
            )
        messages += [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": RETRY_PROMPT},
        ]

    raise AssertionError("unreachable")  # pragma: no cover


def suggest_windows(
    windows: Iterable[FreeWindow],
    deadlines: Iterable[Deadline],
    *,
    now: datetime | None = None,
    model: str = MODEL,
) -> list[Suggestion]:
    """A verdict per window, best first (good before risky before avoid, then soonest)."""
    found = [
        Suggestion(
            start=context.window.start,
            end=context.window.end,
            verdict=context.verdict,
            reason=_ask(context, model),
        )
        for context in window_contexts(windows, deadlines, now=now)
    ]

    found.sort(key=lambda s: (VERDICT_ORDER.index(s.verdict), s.start))
    return found


def _places_briefing(
    day: str, start: datetime, end: datetime, places: list[Place]
) -> str:
    """The window and a numbered list of names.

    Names only: the model is told not to talk about ratings, addresses or
    distances, so it is not given them in the first place.
    """
    hours = round((end - start).total_seconds() / 3600, 2)
    lines = [
        f"Day: {day}",
        f"Time: {start:%H:%M} to {end:%H:%M}",
        f"Length: {hours} hours",
        "",
        "Places:",
    ]
    lines += [f"{i}. {place.name}" for i, place in enumerate(places)]
    return "\n".join(lines)


def rank_places(
    day: str,
    start: datetime,
    end: datetime,
    places: list[Place],
    *,
    limit: int = 3,
    model: str = MODEL,
) -> list[PlacePick]:
    """Pick the best few places for a window, with a sentence each.

    The model returns nothing but an index and a sentence. Every other field is
    copied from the SerpAPI place, so it cannot invent a name, a rating or a link.
    Invalid and repeated indexes are dropped; whatever survives is what comes back,
    even if that is fewer than `limit` or nothing at all. There is no retry.
    """
    if not places:
        return []

    messages = [
        {
            "role": "user",
            "content": f"{PLACES_PROMPT}\n\n{_places_briefing(day, start, end, places)}",
        }
    ]
    reply = ollama.chat(
        model=model,
        messages=messages,
        options={"temperature": 0.3, "num_predict": 400},
    ).message.content or ""

    try:
        picked = _Picks.model_validate_json(strip_fences(reply)).picks
    except (ValidationError, ValueError):
        return []  # nothing usable, and we were asked not to retry

    chosen: list[PlacePick] = []
    taken: set[int] = set()
    for pick in picked:
        if not 0 <= pick.index < len(places) or pick.index in taken:
            continue  # off the end of the list, or the same place twice
        taken.add(pick.index)
        chosen.append(
            PlacePick(
                **places[pick.index].model_dump(),
                why=" ".join(pick.why.split()),
            )
        )

    return chosen[:limit]


def main() -> None:
    """Advise on the timetable in <classes.json> against the live Moodle feed."""
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <classes.json>")

    from deadlines import fetch_deadlines  # noqa: PLC0415 -- CLI only
    from extract_schedule import ClassBlock  # noqa: PLC0415
    from gaps import free_windows  # noqa: PLC0415

    classes = [ClassBlock.model_validate(r) for r in json.load(open(sys.argv[1]))]
    found = suggest_windows(free_windows(classes), fetch_deadlines())
    print(json.dumps([s.model_dump(mode="json") for s in found], indent=2))


if __name__ == "__main__":
    main()
