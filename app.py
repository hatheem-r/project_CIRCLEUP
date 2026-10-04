"""HTTP front end: the page itself, timetable parsing, deadlines and advice.

    uvicorn app:app --reload          # then open http://127.0.0.1:8000/
    curl -F file=@timetable.png http://127.0.0.1:8000/parse
    curl http://127.0.0.1:8000/deadlines
    curl http://127.0.0.1:8000/windows
    curl -X POST http://127.0.0.1:8000/suggest
"""

import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from deadlines import Deadlines, DeadlineError, MissingFeedURL, fetch_deadlines
from extract_schedule import ClassBlock, Timetable, TimetableParseError, parse_timetable
from gaps import Windows, free_windows
from suggest import (
    Place,
    PlacePicks,
    SuggestError,
    Suggestions,
    Verdict,
    rank_places,
    suggest_windows,
)

app = FastAPI(title="CircleUp API")

# wide open while the frontend is still moving around
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC = Path(__file__).parent / "static"

# The last timetable POSTed to /parse, so /windows has something to work from.
# In memory only: it is lost on restart and is not shared between workers.
_timetable: list[ClassBlock] = []


@app.post("/parse", response_model=Timetable)
async def parse(file: UploadFile = File(...)) -> Timetable:
    """Read an uploaded timetable image or PDF and return its rows."""
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty upload")

    # parse_timetable works on a path, and the suffix is how PDFs are detected.
    # Keep the caller's own filename so it shows up in any error we report back.
    name = Path(file.filename or "").name or "upload.png"
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / name
        path.write_bytes(payload)
        try:
            # the model call blocks for a while; keep the event loop free
            blocks = await run_in_threadpool(parse_timetable, path)
        except TimetableParseError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err
        except RuntimeError as err:  # e.g. pymupdf rejecting a corrupt PDF
            raise HTTPException(status_code=400, detail=f"could not read {name}: {err}") from err

    global _timetable
    _timetable = blocks
    return Timetable(classes=blocks)


@app.get("/deadlines", response_model=Deadlines)
async def deadlines() -> Deadlines:
    """Moodle deadlines falling due in the next 14 days, soonest first."""
    try:
        # fetching the feed blocks; keep the event loop free
        found = await run_in_threadpool(fetch_deadlines)
    except MissingFeedURL as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    except DeadlineError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    return Deadlines(deadlines=found)


@app.get("/windows", response_model=Windows)
async def windows() -> Windows:
    """Free windows of 2h+ between 08:00 and 22:00 over the next 7 days."""
    if not _timetable:
        raise HTTPException(
            status_code=404, detail="no timetable yet -- POST an image to /parse first"
        )

    return Windows(windows=free_windows(_timetable))


@app.post("/suggest", response_model=Suggestions)
async def suggest() -> Suggestions:
    """A verdict per free window on whether it is a good time to go out, best first."""
    if not _timetable:
        raise HTTPException(
            status_code=404, detail="no timetable yet -- POST an image to /parse first"
        )

    try:
        # one model call per window, so this is the slow one
        found = await run_in_threadpool(
            lambda: suggest_windows(free_windows(_timetable), fetch_deadlines())
        )
    except MissingFeedURL as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    except (DeadlineError, SuggestError) as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    return Suggestions(suggestions=found)


class PlacesToRank(BaseModel):
    """One free window, its verdict, and the places the proxy found for it."""

    day: str = Field(min_length=1, max_length=40)
    start: datetime
    end: datetime
    verdict: Verdict
    # straight off /places, which caps itself at 10
    places: list[Place] = Field(default_factory=list, max_length=20)


@app.post("/suggest-places", response_model=PlacePicks)
async def suggest_places(body: PlacesToRank) -> PlacePicks:
    """Rank places for one window and say why. Takes the list, does not fetch it.

    `verdict` is accepted so the caller can send the whole window, but it is not
    put in front of the model: the prompt covers the day, the times and the length.
    """
    picks = await run_in_threadpool(
        rank_places, body.day, body.start, body.end, body.places
    )

    # nothing may come back that was not sent in
    offered = {place.name for place in body.places}
    assert all(pick.name in offered for pick in picks), (
        "a pick escaped the input list"
    )

    return PlacePicks(picks=picks)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """The single page that drives all of the above."""
    return FileResponse(STATIC / "index.html")


# anything else the page wants to load later (icons, split-out js) goes in static/
app.mount("/static", StaticFiles(directory=STATIC), name="static")
