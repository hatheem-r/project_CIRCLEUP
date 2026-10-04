"""Places proxy -- the only part of this project that talks to a third party.

It is deliberately dumb. It accepts a location string and a time window and
nothing else: the query parameters are a closed set, so a course code, a
deadline or anything else off the timetable is rejected rather than forwarded.
Of what it does accept, only the location is ever sent on to SerpAPI.

    uvicorn app:app --reload --port 8001
    curl "http://127.0.0.1:8001/places?location=cafes+in+Colombo&start=19:00&end=22:00"
"""

import os
from typing import Annotated, Any
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

load_dotenv()

SERPAPI_URL = "https://serpapi.com/search.json"
MAX_PLACES = 10
TIMEOUT = 20.0

# Comma separated, e.g. "https://circleup.onrender.com,http://localhost:3000".
# The fallback only covers local development; a deployed frontend must be named
# explicitly, so forgetting to set this fails closed rather than opening up.
DEFAULT_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:8000,http://127.0.0.1:8000"
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",")
    if origin.strip()
]

# the service is told the time of day and nothing more -- not even which day
TimeOfDay = Annotated[str, StringConstraints(pattern=r"^\d{2}:\d{2}$")]

app = FastAPI(title="CircleUp places proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def no_duplicates(request: Request) -> None:
    """One value per parameter.

    A repeated name is not caught by extra="forbid" -- the last value simply
    wins -- so ?location=a&location=b would quietly search for b.
    """
    names = [name for name, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)):
        repeated = sorted({n for n in names if names.count(n) > 1})
        raise HTTPException(
            status_code=422, detail=f"repeated query parameter: {', '.join(repeated)}"
        )


class PlacesQuery(BaseModel):
    """The complete set of parameters this service accepts.

    extra="forbid" is the point of this model: an unknown query parameter is a
    422, not something quietly passed along.
    """

    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1, max_length=120)
    start: TimeOfDay
    end: TimeOfDay


class Place(BaseModel):
    name: str
    address: str | None = None
    rating: float | None = None
    maps_url: str


class Places(BaseModel):
    places: list[Place] = Field(default_factory=list)


def _place(result: dict[str, Any]) -> Place:
    """One SerpAPI local result, trimmed to the four fields we publish."""
    place_id = result.get("place_id")
    return Place(
        name=result["title"],
        address=result.get("address"),
        rating=result.get("rating"),
        # built here rather than passed through: SerpAPI's own links point back
        # at serpapi.com, which is not a map and not ours to hand out
        maps_url=(
            f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            if place_id
            else f"https://www.google.com/maps/search/?api=1&query={quote_plus(result['title'])}"
        ),
    )


@app.get("/places", response_model=Places, dependencies=[Depends(no_duplicates)])
async def places(query: Annotated[PlacesQuery, Query()]) -> Places:
    """Up to ten places near a location. `start` and `end` never leave this process."""
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="SERPAPI_KEY is not set")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                SERPAPI_URL,
                params={
                    "engine": "google_maps",
                    "type": "search",
                    "q": query.location,  # the only thing forwarded
                    "api_key": key,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as err:
        raise HTTPException(
            status_code=502, detail=f"serpapi returned {err.response.status_code}"
        ) from err
    except httpx.HTTPError as err:
        # the url carries the key, so report the failure without it
        raise HTTPException(
            status_code=502, detail=f"could not reach serpapi: {type(err).__name__}"
        ) from err

    body = response.json()
    if error := body.get("error"):
        raise HTTPException(status_code=502, detail=f"serpapi: {error}")

    results = [r for r in body.get("local_results") or [] if r.get("title")]
    return Places(places=[_place(r) for r in results[:MAX_PLACES]])
