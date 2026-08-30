# Call-Centre Radar

Call-Centre Radar is an evidence-first conversation-intelligence product for consumer-bank support calls. It ingests stereo recordings offline, persists speaker-attributed transcripts and validated analysis, and serves a fast manager dashboard. It never transcribes or analyzes a call during an API request.

The supplied dataset has been verified locally: 1,441 stereo, 8 kHz MP3s pair cleanly with 1,441 JSON files under `audio/` and `metadata/`. The source mapping is fixed: **left channel → agent** and **right channel → customer**.

## Product coverage

- Resumable states: `DISCOVERED → VALIDATED → TRANSCRIBING → TRANSCRIBED → ANALYZING → ANALYZED → READY`, plus retryable `FAILED`.
- FFmpeg channel extraction and faster-whisper transcription for deterministic speaker attribution.
- Persisted transcript turns, controlled intent taxonomy, resolution, generated ≤40-word narrative summary, customer mood events, mood shift, topics, and a 0–100 attention score.
- Every retained intent, resolution, summary, mood event, and attention contribution has an exact quoted transcript span, timestamp, speaker, and segment ID. Unsupported claims are omitted.
- FastAPI v1 API, PostgreSQL/Supabase-compatible persistence, local or private Supabase audio storage, and a Next.js/TypeScript dashboard.
- Dashboard routes: Overview, Manager Attention, Customers and history, Calls and filters, Trends, Agents, and a seekable call-review screen.

The attention score uses fixed, auditable weights. Repeat-contact and long-wait signals are included only when the caller explicitly says so in the recording; source metadata alone is never used as claim evidence. Scores are capped at 100.

## Repository and data handling

Raw recordings, extracted data, local databases, Whisper cache, `.env`, and working files are all ignored by Git. Do not commit bank recordings or credentials.

The expected local source layout is:

```text
data/callradar-data/
├── audio/<call-id>.mp3
└── metadata/<call-id>.json
```

If starting from the provided archive:

```bash
mkdir -p data
unzip data/callradar-data.zip -d data
```

This produces `data/callradar-data/`. The archive and the extracted files remain local only.

## Quick start with Docker

Prerequisites: Docker Desktop and the locally extracted dataset above.

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY for production analysis, and replace the default
# PostgreSQL password before using a shared environment. Set
# COMPOSE_DATABASE_URL only when using a managed Postgres database.

docker compose up --build -d
curl --fail http://localhost:8000/health
```

Open the dashboard at `http://localhost:3000` and the API documentation at `http://localhost:8000/docs`.

Ingest and validate the real dataset before running the full job:

```bash
docker compose exec api python -m app.cli ingest-dataset \
  --dataset-root /data/callradar-data --media-root /data

docker compose exec api python -m app.cli validate --media-root /data --limit 20
docker compose exec api python -m app.cli process --media-root /data --limit 20
```

Review the sample in the dashboard and the golden-set worksheet. Then resume every non-terminal call with the opt-in worker:

```bash
docker compose --profile worker run --rm worker
```

The worker exits after the current queue is empty. It is intentionally single-worker/resumable; rerun it to continue after an interruption. To retry only known failures after inspecting their stored errors:

```bash
docker compose exec api python -m app.cli retry --media-root /data
```

After initial setup, the Calls page also provides a **Process new files** button. Place new stereo MP3 files in `data/callradar-data/audio/` and their same-named metadata JSON files in `data/callradar-data/metadata/`, then use the button. The API ingests previously unseen call IDs and sends only those IDs through the persistent pipeline; existing calls are not reprocessed.

## Supabase-backed handoff

To rebuild the complete application on another computer without reprocessing existing calls, share two items separately:

1. This GitHub repository (with the required feature branch merged or checked out).
2. The configured root `.env` file through a secure channel. Never commit it to Git.

The Supabase-backed `.env` must contain `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET=call-audio`, and `STORAGE_PROVIDER=supabase`. `OPENAI_API_KEY` is needed only to process additional calls. Use `NEXT_PUBLIC_API_URL=http://localhost:8000`, `API_INTERNAL_URL=http://127.0.0.1:8000`, and include `http://localhost:3000` in `CORS_ORIGINS` for the standard local ports.

From a fresh clone:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend

# Put the securely shared .env in the repository root, then export it.
set -a
source .env
set +a

# Safe to rerun against the existing Supabase database.
PYTHONPATH=backend .venv/bin/alembic -c backend/alembic.ini upgrade head

# Build the dashboard with the browser-visible local API origin.
npm run build --prefix frontend
```

Run the following in separate terminals after sourcing `.env` in each:

```bash
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
npm run start --prefix frontend -- --port 3000
```

Open `http://localhost:3000`. Existing calls, transcripts, analyses, and recordings load directly from Supabase; the local SQLite file and original dataset are not required for viewing. To add calls, create `data/callradar-data/audio/` and `data/callradar-data/metadata/`, add same-named MP3/JSON pairs, and use **Process new files**.

## Native development

Prerequisites: Python 3.12+, Node.js 22+, FFmpeg, and the source data. FFmpeg is installed in the API container; native development needs it on `PATH`.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
cp .env.example .env
```

Create a local database and apply the migration:

```bash
DATABASE_URL=sqlite:///./data/callradar.db \
PYTHONPATH=backend .venv/bin/alembic -c backend/alembic.ini upgrade head
```

Ingest and process a sample:

```bash
DATABASE_URL=sqlite:///./data/callradar.db \
PYTHONPATH=backend .venv/bin/python scripts/process_dataset.py \
  --input data/callradar-data --media-root data --limit 20
```

Run the API and dashboard in separate terminals:

```bash
DATABASE_URL=sqlite:///./data/callradar.db MEDIA_ROOT=data \
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev --prefix frontend
```

The pipeline defaults to OpenAI-backed structured analysis when `OPENAI_API_KEY` is set. For a no-network smoke test, set `ANALYSIS_PROVIDER=rules`; the evidence gate and persistent data contract remain active.

## Operational commands

All commands persist progress and are safe to rerun. Expensive processing happens only in these commands, never in FastAPI routes.

```bash
# Initialize the configured schema (the API also applies migrations in Docker)
PYTHONPATH=backend .venv/bin/python -m app.cli init-db

# Dataset-specific source adapter
PYTHONPATH=backend .venv/bin/python -m app.cli ingest-dataset \
  --dataset-root data/callradar-data --media-root data

# Validate source files, then process a bounded sample or all resumable records
PYTHONPATH=backend .venv/bin/python -m app.cli validate --media-root data --limit 20
PYTHONPATH=backend .venv/bin/python -m app.cli process --media-root data --limit 20
PYTHONPATH=backend .venv/bin/python -m app.cli process --media-root data
PYTHONPATH=backend .venv/bin/python -m app.cli retry --media-root data

# Re-run only persisted READY calls after intentionally changing the analysis
# prompt/model/evidence policy; transcripts are preserved.
PYTHONPATH=backend .venv/bin/python -m app.cli reanalyse --media-root data --limit 20

# Refresh only generated narrative summaries for existing analysed calls;
# transcripts, classifications, moods, and scores are left unchanged.
PYTHONPATH=backend .venv/bin/python -m app.cli regenerate-summaries --media-root data

# Re-transcribe and re-analyze one specific call after changing the speech model
# or timestamp segmentation policy.
PYTHONPATH=backend .venv/bin/python -m app.cli reprocess \
  --media-root data --call-id <call-id>

# Generate a human-review worksheet after READY calls exist
PYTHONPATH=backend .venv/bin/python scripts/export_golden_set.py \
  --size 25 --output work/golden-set-review.csv
```

Check progress at `GET /api/v1/processing/progress`. Failed records retain an error message and are never silently retried by a dashboard/API request.

## API

The versioned API is documented at `/docs`. Core routes are:

```text
GET /api/v1/calls
GET /api/v1/calls/{call_id}
GET /api/v1/calls/{call_id}/audio
GET /api/v1/attention
GET /api/v1/customers
GET /api/v1/customers/{customer_id}
GET /api/v1/customers/{customer_id}/calls
GET /api/v1/trends
GET /api/v1/agents
GET /api/v1/agents/{agent_id}
GET /api/v1/processing/progress
```

`GET /api/v1/calls` supports customer, agent, date, intent, resolution, mood, minimum attention score, duration, status, search, `limit`, and `offset` filters. The audio route redirects to a local restricted MP3 route in development or a time-limited private Supabase URL in production.

## Storage and hosted deployment

PostgreSQL/Supabase Postgres is the deployment database. For private Supabase Storage, create a **private** bucket and configure `STORAGE_PROVIDER=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `SUPABASE_BUCKET`. The service-role key must remain server-side.

After ingestion, upload the original recordings once:

```bash
PYTHONPATH=backend .venv/bin/python -m app.cli sync-storage --media-root data
```

Use a separate API service, worker service, and frontend service against the same PostgreSQL database. Set `NEXT_PUBLIC_API_URL` to the browser-reachable API origin, and use `API_INTERNAL_URL` only for the dashboard server's private API route. The Docker Compose stack demonstrates both values correctly.

Detailed deployment steps are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The QA/release gate and human evidence-review procedure are in [docs/QA-RUNBOOK.md](docs/QA-RUNBOOK.md).

## Tests and release gate

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build --prefix frontend
```

The GitHub Actions workflow runs backend tests, a clean Alembic migration, and the production dashboard build. Before marking the all-call run complete, review a 20–30-call golden set against the audio, ensure every remaining failure is triaged, and validate the exact evidence-to-audio interaction in the dashboard.

## Security note

Treat all recordings, transcripts, participant names, database URLs, OpenAI keys, and Supabase service-role keys as sensitive. In a deployment, set `API_ACCESS_TOKEN` (or use an identity-aware proxy) so API and audio routes are not public; the dashboard passes that token only from its server-rendering process. Use a secret manager, keep the audio bucket private, restrict `CORS_ORIGINS`, and rotate any key that has ever been pasted into a chat, terminal, or log.
