# CircleUp

**When can we actually hang out this week — without wrecking a deadline?**

CircleUp reads your university timetable, pulls your Moodle deadlines, finds the gaps between them, and tells you whether each free window is actually a good time to go out. For the usable ones it suggests somewhere nearby to go.

All the personal data — your timetable, your deadlines — stays on your own machine. The model runs locally through Ollama. Nothing about your schedule is sent to a server.

**Live demo:** [add your Render frontend URL]
**Places service:** [add your Render web service URL]

---

## How it works

```
Your laptop (private)                 Render (public)
├─ Ollama + Gemma 3        ←───────→  ├─ Next.js frontend
│   └─ reads the timetable            └─ /places → SerpApi
│   └─ writes the reasons
├─ Moodle iCal → deadlines
└─ gap finder + verdicts
    (never leaves this box)
```

The split matters. The Render service only ever receives a **location string and a clock time** — never a course name, a deadline, or a date.

Inside the pipeline the rule is: **the model writes prose, Python owns the facts.**

| Job | Who does it | Why |
|---|---|---|
| Read the timetable image | Gemma 3 (vision) | Unstructured input — a real model task |
| Fetch deadlines | Python (`icalendar`) | Parsing a known format |
| Find free windows | Python | Interval arithmetic has one right answer |
| good / risky / avoid | Python threshold | Small models reason badly over numbers |
| Write the reason sentence | Gemma 3 | Language is the output |
| Rank nearby places | Gemma 3 (indices only) | Judgment, but it never sees place names |

---

## Requirements

- Python 3.11+
- Node 18+
- [Ollama](https://ollama.com) installed and running
- A Moodle calendar export URL (Calendar → Export → **Get calendar URL**)
- A [SerpApi](https://serpapi.com) key (free tier is enough)

---

## Running it locally

### 1. Pull the model

```bash
ollama pull gemma3:4b
```

Allow the frontend to call Ollama from the browser:

```bash
export OLLAMA_ORIGINS=http://localhost:3000
```

Restart Ollama after setting this.

### 2. Backend (stays on your machine)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then fill it in
uvicorn main:app --port 8000
```

`.env`:

```
MOODLE_ICAL_URL=https://your-moodle/calendar/export_execute.php?...
```

> ⚠️ That URL contains an auth token that can read your calendar. It is gitignored — keep it that way, and blur it in any screenshot.

### 3. Places service

```bash
cd render_service
pip install -r requirements.txt
uvicorn main:app --port 8001
```

`.env`:

```
SERPAPI_KEY=your_key
ALLOWED_ORIGINS=http://localhost:3000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

`.env.local`:

```
NEXT_PUBLIC_LOCAL_API=http://localhost:8000
NEXT_PUBLIC_PLACES_API=http://localhost:8001
```

Open <http://localhost:3000>, upload your timetable, and hit **find my free time**.

---

## Deploying

Only two of the three pieces are deployed. The backend stays on your laptop by design — that is what keeps the schedule private.

**Places service** → Render **Web Service**

| Setting | Value |
|---|---|
| Root Directory | `render_service` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Env vars | `SERPAPI_KEY`, `ALLOWED_ORIGINS` |

**Frontend** → Render **Static Site**

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm install && npm run build` |
| Publish Directory | `out` |

Set `NEXT_PUBLIC_*` **before** building — Next.js bakes them in at build time. Point `NEXT_PUBLIC_LOCAL_API` at `http://localhost:8000`; the browser resolves that on the viewer's own machine, which is the whole point.

Then allow the deployed origin:

```bash
export OLLAMA_ORIGINS=https://your-site.onrender.com
```

---

## API

**Local service — `:8000`**

| Endpoint | Does |
|---|---|
| `POST /parse` | Timetable image → structured classes |
| `GET /deadlines` | Moodle iCal → upcoming deadlines |
| `GET /windows` | Free windows for the next 7 days |
| `POST /suggest` | Verdict + reason per window |
| `POST /suggest-places` | Ranks places returned by the proxy |

**Places service — `:8001`**

| Endpoint | Does |
|---|---|
| `GET /places?location=&start=&end=` | Nearby places via SerpApi |

---

## Notes and limits

- Timetable parsing works best on a **simple per-day table**, not a merged-cell grid. Grid alignment is where small vision models fall over.
- The good/risky/avoid thresholds are constants in the backend — tune them to your own habits.
- Free-tier Render cold-starts after idling. Warm it before demoing.
- The model never emits a place name, only an index, so it cannot invent a café that doesn't exist.

## Built with

Gemma 3 · Ollama · FastAPI · Next.js · SerpApi · Render

Built for the [Hacktoberfest Weekend Challenge: Build for a Friend](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01).