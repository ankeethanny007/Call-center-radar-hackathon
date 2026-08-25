# Deployment runbook

Call-Centre Radar has two runtime paths:

- The FastAPI service is read-only with respect to analysis. It serves persisted calls, transcripts, evidence, metrics, and signed audio URLs.
- The offline worker ingests and processes recordings. It is resumable and never re-transcribes a call that is already `READY`.

Keep both paths connected to the same PostgreSQL database. Do not put the database URL, the OpenAI key, or a Supabase service-role key in the browser configuration.

## 1. Configure secrets and infrastructure

Copy the safe template and set values in the deployment platform's secret manager:

```bash
cp .env.example .env
```

Production needs:

- PostgreSQL or Supabase Postgres through `DATABASE_URL`.
- An OpenAI key in `OPENAI_API_KEY` when `ANALYSIS_PROVIDER=openai`; use `ANALYSIS_PROVIDER=rules` only for offline smoke tests.
- A private object-storage bucket for recordings when `STORAGE_PROVIDER=supabase`, plus `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `SUPABASE_BUCKET`.
- The public dashboard origin in `CORS_ORIGINS` and the public API origin in `NEXT_PUBLIC_API_URL`.
- `API_ACCESS_TOKEN` for the built-in API/audio gate, or an identity-aware proxy that enforces equivalent authentication and authorization. When the token gate is used, set the same value only in the API and Next.js server environments; never expose it as `NEXT_PUBLIC_*`.

Create the audio bucket as **private**. The API supplies time-limited URLs for playback, so the service-role key must remain API/worker-only. Rotate any key that was ever pasted into chat, a terminal, a log, or a committed file.

## 2. Apply database migrations

On a fresh database:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE' \
  alembic -c alembic.ini upgrade head
```

The API image runs the same idempotent migration before it starts. For a controlled release, run the command as a one-off release job before replacing the API service.

If an existing database was created by the pre-migration `Base.metadata.create_all` bootstrap and has already been compared with this initial schema, record the baseline instead of rerunning table creation:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE' \
  alembic -c alembic.ini stamp 0001_initial_schema
```

Only use `stamp` after verifying the schema matches the migration; it does not create or alter tables.

## 3. Local container deployment

The Compose stack includes PostgreSQL, API, dashboard, and an opt-in one-shot worker profile:

```bash
docker compose up --build -d
curl --fail http://localhost:8000/health
```

Compose uses its own `COMPOSE_DATABASE_URL` override so the native-development
`DATABASE_URL=sqlite:///...` in `.env` cannot accidentally point containers at
an unmounted SQLite path. Leave `COMPOSE_DATABASE_URL` empty for the bundled
Postgres service, or set it to a managed PostgreSQL URL.

The dashboard is available on port 3000 and API documentation on port 8000. `API_INTERNAL_URL=http://api:8000` is used by server-rendered dashboard pages inside Compose, while `NEXT_PUBLIC_API_URL` remains the browser-visible origin.

For the supplied archive, extract it below `data/` so its verified layout is `data/callradar-data/audio/*.mp3` and `data/callradar-data/metadata/*.json`. The data directory is intentionally ignored by Git.

```bash
docker compose exec api python -m app.cli ingest-dataset \
  --dataset-root /data/callradar-data --media-root /data

# Validate a representative batch before the full run.
docker compose exec api python -m app.cli validate --media-root /data --limit 20
docker compose exec api python -m app.cli process --media-root /data --limit 20

# Resume all non-terminal calls. This worker exits when the current queue is empty.
docker compose --profile worker run --rm worker

# Retry only calls marked FAILED after inspecting their stored error.
docker compose exec api python -m app.cli retry --media-root /data
```

The media mount is writable because the transcriber creates temporary per-call channel-split files under `data/.work`. Keep that work area out of backups if raw audio is already retained elsewhere.

## 4. Hosted deployment topology

Use a separate API/worker service and frontend service:

1. Provision PostgreSQL and execute the migration release job.
2. Deploy the API image with `DATABASE_URL`, storage credentials, model credentials, a restrictive `CORS_ORIGINS` list, and `API_ACCESS_TOKEN` (or place it behind an identity-aware authorization proxy).
3. Deploy the Next.js image with `NEXT_PUBLIC_API_URL=https://api.example.com` baked at build time and `API_INTERNAL_URL` set to a private API hostname if server rendering uses one.
4. Mount the source archive only for initial ingest, upload recordings with `python -m app.cli sync-storage`, then run workers with `STORAGE_PROVIDER=supabase` for ongoing playback.
5. Start one worker at a time against a given database unless a proper job queue/lease mechanism is added. The current CLI is intentionally resumable but not a multi-worker scheduler.

Do not expose PostgreSQL publicly. Terminate TLS at the platform/load balancer, restrict API and storage service credentials to server-side services, and set log retention so recordings, transcripts, and keys are never emitted to logs.

## 5. Operations and recovery

- Check `GET /health` for API/database availability and `GET /api/v1/processing/progress` for persisted batch status.
- Calls in `FAILED` retain an error string. Correct the cause and use `retry`; completed calls remain untouched.
- Back up PostgreSQL and the private audio bucket together. The database contains media paths and evidence references required to replay analysis.
- Before changing the model, prompt, taxonomy, or evidence validator, process a new controlled sample and review its golden-set worksheet. Do not silently overwrite previously reviewed analyses.

The full release gate is in [QA-RUNBOOK.md](QA-RUNBOOK.md).
