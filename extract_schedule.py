"""Read a university timetable image (or PDF) with a local VLM and validate the result.

    from extract_schedule import parse_timetable
    blocks = parse_timetable("timetable.png")
"""

import json
import re
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import ollama
from pydantic import BaseModel, Field, StringConstraints, ValidationError, field_validator

# MODEL = "gemma3:12b"
MODEL = "gemma3:4b"
# MODEL = "qwen3-vl:4b"

PROMPT = """You are reading a university timetable. It is organized as separate tables, one per weekday.

Each table has a day name as its header (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY),
then rows with four columns: TIME, CODE, COURSE / ACTIVITY, VENUE.

For every data row output one object:
{
  "day": "<the day header this row sits under>",
  "start": "HH:MM",
  "end": "HH:MM",
  "code": "<CODE column, spaces removed, e.g. CS3621>",
  "name": "<COURSE / ACTIVITY text without the trailing (L), (P) or (L & P)>",
  "type": "lecture" | "practical" | "both" | "other",
  "venue": "<VENUE column without square brackets>"
}

Rules:
- Times are printed with a period (13.15). Convert to colons (13:15).
- "(L)" -> lecture, "(P)" -> practical, "(L & P)" -> both, no marker -> other.
- A CODE of "—" or blank means no code: use null.
- Blank VENUE -> null.
- Skip header rows (TIME / CODE / COURSE / ACTIVITY / VENUE).
- Transcribe exactly. Do not invent rows or guess missing values.

Output JSON only:
{"classes": [ ... ]}"""

RETRY_PROMPT = """Your reply could not be used:

{error}

Look at the image again and send the whole timetable back, corrected.
Output JSON only -- no markdown fences, no commentary:
{{"classes": [ ... ]}}"""


class TimetableParseError(RuntimeError):
    """The model never produced output matching the schema."""


class Day(StrEnum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"


class ClassType(StrEnum):
    LECTURE = "lecture"
    PRACTICAL = "practical"
    BOTH = "both"
    OTHER = "other"


_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
_SHORT_HOUR = re.compile(r"\d:\d\d")
# what the model writes when a cell is empty
_BLANK = {"", "-", "--", "—", "–", "n/a", "na", "none", "null", "tbd"}


class ClassBlock(BaseModel):
    """One row of the timetable."""

    day: Day
    start: str
    end: str
    code: str | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    type: ClassType
    venue: str | None = None

    @field_validator("day", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("type", mode="before")
    @classmethod
    def _lower(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("start", "end", mode="before")
    @classmethod
    def _time(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        # the prompt asks for 13:15, but the model sometimes echoes the printed
        # 13.15 or drops the leading zero on a morning time
        text = value.strip().replace(".", ":")
        if _SHORT_HOUR.fullmatch(text):
            text = f"0{text}"
        if not _TIME.fullmatch(text):
            raise ValueError(f"{value!r} is not a 24-hour HH:MM time")
        return text

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = "".join(value.split())
        return None if text.lower() in _BLANK else text

    @field_validator("venue", mode="before")
    @classmethod
    def _venue(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip().strip("[]").strip()
        return None if text.lower() in _BLANK else text


class Timetable(BaseModel):
    classes: list[ClassBlock] = Field(default_factory=list)


def to_images(path: Path) -> list[bytes]:
    """PNG bytes for each page (PDF) or the image itself."""
    if path.suffix.lower() != ".pdf":
        return [path.read_bytes()]

    import pymupdf

    with pymupdf.open(path) as doc:
        # 200 dpi: small timetable text stays readable after the model downscales
        return [page.get_pixmap(dpi=200).tobytes("png") for page in doc]


def strip_fences(text: str) -> str:
    """Unwrap a ```json ... ``` block, if the model used one."""
    body = text.strip()
    if not body.startswith("```"):
        return body

    body = "\n".join(body.splitlines()[1:]).strip()  # drop ``` or ```json
    if body.endswith("```"):
        body = body[:-3].rstrip()
    return body


def _read_image(image: bytes, model: str, label: str) -> list[ClassBlock]:
    """One image -> validated rows, with a single corrective retry."""
    messages: list[dict] = [{"role": "user", "content": PROMPT, "images": [image]}]
    reply = ""

    for attempt in (1, 2):
        reply = ollama.chat(
            model=model,
            messages=messages,
            options={"temperature": 0},
        ).message.content or ""

        try:
            return Timetable.model_validate_json(strip_fences(reply)).classes
        except (ValidationError, ValueError) as err:
            if attempt == 2:
                raise TimetableParseError(
                    f"{model} could not produce valid timetable JSON for {label}, "
                    f"even after one corrective retry.\n\n"
                    f"Last error:\n{err}\n\n"
                    f"Last reply:\n{reply.strip()[:2000] or '(empty)'}"
                ) from err

            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": RETRY_PROMPT.format(error=err)},
            ]

    raise AssertionError("unreachable")  # pragma: no cover


def parse_timetable(image_path: str | Path, *, model: str = MODEL) -> list[ClassBlock]:
    """Read a timetable image or PDF and return its rows, pages concatenated.

    Raises FileNotFoundError if the path is not a file, and TimetableParseError if
    the model's output still fails validation after one retry.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")

    images = to_images(path)
    blocks: list[ClassBlock] = []
    for i, image in enumerate(images, 1):
        label = path.name if len(images) == 1 else f"{path.name} page {i}"
        blocks += _read_image(image, model, label)
    return blocks


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <image-or-pdf>")

    try:
        blocks = parse_timetable(sys.argv[1])
    except (FileNotFoundError, TimetableParseError) as err:
        sys.exit(str(err))

    print(json.dumps([b.model_dump() for b in blocks], indent=2))


if __name__ == "__main__":
    main()
