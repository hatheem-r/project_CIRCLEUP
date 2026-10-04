"""HTTP front end for the timetable parser.

    uvicorn app:app --reload
    curl -F file=@timetable.png http://127.0.0.1:8000/parse
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from extract_schedule import Timetable, TimetableParseError, parse_timetable

app = FastAPI(title="CircleUp timetable parser")

# wide open while the frontend is still moving around
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

    return Timetable(classes=blocks)
