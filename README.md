# Call-Centre Radar

Call-Centre Radar turns consumer-bank support recordings into a searchable, evidence-backed manager dashboard. Processing happens once in a resumable offline pipeline; normal API requests only read persisted results.

The source contract is fixed: recordings are stereo 8 kHz MP3 files, the left channel is the agent, the right channel is the customer, and each recording has a matching metadata JSON file. Credentials, recordings, local databases, model caches, and `.env` are intentionally excluded from Git.

## 1. Run the project after cloning Git and adding `.env`

### Prerequisites

- Python 3.12+
- Node.js 22+
- FFmpeg available on `PATH`
- A root `.env` file shared separately from Git

The shared Supabase `.env` must include `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `STORAGE_PROVIDER=supabase`, `NEXT_PUBLIC_API_URL`, `API_INTERNAL_URL`, and `CORS_ORIGINS`. `OPENAI_API_KEY` is required only when processing additional recordings. Never commit `.env`.

### Install and build

From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend

# Place the securely shared .env in this repository root.
set -a
source .env
set +a

# Safe to rerun against the existing Supabase database.
PYTHONPATH=backend .venv/bin/alembic -c backend/alembic.ini upgrade head
npm run build --prefix frontend
```

### Start the application

Open two terminals in the repository root. Source `.env` in both terminals.

Terminal 1 — API:

```bash
set -a; source .env; set +a
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — dashboard:

```bash
set -a; source .env; set +a
npm run start --prefix frontend -- --port 3000
```

Open `http://localhost:3000`. API health is available at `http://localhost:8000/health`, and interactive API documentation is at `http://localhost:8000/docs`.

The supplied Supabase credentials load the existing calls, transcripts, analyses, and recordings. The original dataset and a local SQLite file are not required merely to view the application.

### Process new recordings

Create this local structure and add same-named MP3/JSON pairs:

```text
data/callradar-data/
├── audio/<call-id>.mp3
└── metadata/<call-id>.json
```

Open the **Calls** page and select **Process new files**. Only previously unseen call IDs are ingested and processed; completed calls are not reprocessed.

Useful CLI alternatives:

```bash
# Check and process resumable calls.
PYTHONPATH=backend .venv/bin/python -m app.cli validate --media-root data --limit 20
PYTHONPATH=backend .venv/bin/python -m app.cli process --media-root data

# Retry stored failures after inspecting their error messages.
PYTHONPATH=backend .venv/bin/python -m app.cli retry --media-root data

# Reprocess one call after a transcription or segmentation change.
PYTHONPATH=backend .venv/bin/python -m app.cli reprocess \
  --media-root data --call-id <call-id>
```

Run verification before sharing changes:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build --prefix frontend
```

For Docker-based setup, local SQLite development, migration recovery, and the complete QA procedure, see [Deployment](docs/DEPLOYMENT.md) and [QA runbook](docs/QA-RUNBOOK.md).

## 2. Technical architecture, contracts, and formats

### Runtime architecture

```text
Stereo MP3 + metadata JSON
          │
          ▼
Resumable Python worker
  validate → split channels → transcribe → reconstruct turns
  → analyze → validate evidence → persist
          │
          ├── PostgreSQL / Supabase: metadata, transcript, analysis, evidence
          └── Private Supabase Storage: original recordings
                         │
                         ▼
              FastAPI read API
                         │
                         ▼
              Next.js dashboard
```

- **Frontend:** Next.js 15, React 19, and TypeScript.
- **API:** FastAPI and SQLAlchemy.
- **Persistence:** PostgreSQL/Supabase with Alembic migrations. SQLite remains supported for isolated development and tests.
- **Audio:** local storage in development or a private Supabase bucket with short-lived signed playback URLs.
- **Transcription:** FFmpeg channel extraction plus faster-whisper. Channel separation provides deterministic speaker attribution without diarization.
- **Analysis:** OpenAI structured analysis followed by deterministic evidence validation and scoring.
- **Performance:** database-side filtering/pagination, lightweight projections, optimized relationship loading, short-lived read caching, signed-URL caching, and parallel dashboard requests.

FastAPI never transcribes or analyzes during a read request. The API and worker share the same persistent database, and only one worker should process a given database at a time.

### Input contract

Each call requires:

- `audio/<call-id>.mp3`: stereo, 8 kHz MP3; left = agent and right = customer.
- `metadata/<call-id>.json`: metadata paired by the exact same `<call-id>` filename.

The worker rejects missing or ambiguous pairs instead of guessing the dataset structure or speaker mapping.

### Processing states

```text
DISCOVERED → VALIDATED → TRANSCRIBING → TRANSCRIBED
           → ANALYZING → ANALYZED → READY
```

`FAILED` is retryable. Progress is persisted, so restarting a worker resumes non-terminal calls without duplicating completed transcript or evidence rows.

### Persisted output contract

Each ready call can contain:

- Timestamped transcript turns with `speaker`, `start_seconds`, `end_seconds`, and exact text.
- Intent and topics.
- Customer mood events and mood-shift time.
- Resolution status.
- A generated narrative summary of no more than 40 words.
- A deterministic manager-attention score from 0–100 with individual score contributions.
- Evidence references containing the exact transcript quote, segment ID, speaker, and timestamps.

Intent, resolution, mood, summary facts, and score signals are returned only when supported by timestamped transcript evidence. Unsupported claims are omitted. Metadata alone is not used as conversational evidence.

### API contract

All business endpoints use the `/api/v1` prefix:

```text
GET  /health
GET  /api/v1/calls
GET  /api/v1/calls/{call_id}
GET  /api/v1/calls/{call_id}/audio
GET  /api/v1/attention
GET  /api/v1/customers
GET  /api/v1/customers/{customer_id}
GET  /api/v1/customers/{customer_id}/calls
GET  /api/v1/trends
GET  /api/v1/agents
GET  /api/v1/agents/{agent_id}
GET  /api/v1/processing/progress
GET  /api/v1/processing/new-files
POST /api/v1/processing/new-files
```

`GET /api/v1/calls` supports customer, agent, date, intent, resolution, mood, minimum attention score, duration, processing status, text search, `limit`, and `offset` filters. The audio route returns a protected local stream or redirects to a time-limited private Supabase URL.

When `API_ACCESS_TOKEN` is configured, protected routes require:

```http
X-API-Key: <API_ACCESS_TOKEN>
```

Do not place database credentials, the OpenAI key, the Supabase service key, or `API_ACCESS_TOKEN` in any `NEXT_PUBLIC_*` variable.

## 3. Features and UI

- **Overview:** operational totals, resolution and mood indicators, high-attention calls, issue mix, and recent activity.
- **Calls:** searchable and filterable call archive with processing state and a single **Process new files** action.
- **Call detail:** playable recording, seekable agent/customer transcript, generated summary, intent, resolution, attention score, supporting evidence, and mood timeline.
- **Manager Attention:** ranked queue of calls requiring review, with transparent score contributions and timestamped evidence.
- **Customers:** customer directory, interaction history, repeat-call context, and unresolved-call visibility.
- **Trends:** issue volumes, resolution trends, mood patterns, and changes over time.
- **Agents:** handled-call volume, resolution rate, customer outcomes, and attention-related metrics.

The dashboard distinguishes pending analysis from a completed conclusion, does not display unsupported AI judgments, and lets a reviewer seek from any evidence item to the corresponding moment in the recording.
