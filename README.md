# Call-Centre Radar

Persistent, evidence-first analysis for stereo consumer-bank support recordings. It deliberately does **not** infer speakers: stereo channel 0/left is always the agent and channel 1/right is always the customer.

## Current data status

The supplied `callradar-data.zip` is stored locally at `data/callradar-data.zip` and excluded from Git. It contains 1,441 MP3 recordings and 1,441 matching JSON metadata files. The next implementation step is extracting the archive and mapping its verified metadata schema into the manifest.

## Five-day delivery plan

1. **Day 1:** confirm the source files and map their metadata into the manifest below; validate a small sample.
2. **Day 2:** process a representative batch; review timestamps, channel mapping, and evidence quality.
3. **Day 3:** run resumable batch processing across all 1,441 calls; investigate failures.
4. **Day 4:** validate dashboard metrics against sampled calls and deploy staging.
5. **Day 5:** complete all-call processing, QA, demo rehearsal, and production hand-off.

## Run locally

Install Docker, then start the services:

```bash
docker compose up --build
```

The dashboard is at `http://localhost:3000`; the API is at `http://localhost:8000/docs`. PostgreSQL persists through the `postgres_data` Docker volume. For Supabase, set `DATABASE_URL` on the API service to its PostgreSQL connection string.

## Data contract

Put recordings below `data/` and make a neutral adapter manifest—this is the only adapter needed once the actual metadata format is known:

```json
[
  {
    "call_id": "unique-call-id",
    "audio_path": "recordings/example.mp3",
    "customer_id": "stable-customer-id",
    "customer_name": "Optional display name",
    "metadata": {"source_fields": "preserve original metadata here"}
  }
]
```

`audio_path` is relative to `data/`. Do not add files to the database by hand; import the manifest:

```bash
docker compose exec api python -m app.cli ingest --manifest /data/manifest.json
docker compose exec api python -m app.cli process --limit 10
```

Repeat `process` with no limit to resume queued and failed records. A completed call is never re-transcribed on an API request. Processing marks calls `queued`, `processing`, `complete`, or `failed`; failures retain their error text for targeted retries.

## Evidence policy

Every returned intent, mood, resolution, summary, and attention-score contribution includes a transcript turn ID, timestamp range, and exact quote. If no matching supported evidence exists, that finding is omitted (`null`). The initial analyzer is deliberately conservative and deterministic; swap in an approved model only if its structured output is validated against transcript spans before persistence.

## Product coverage

- FastAPI API: calls/details, customers, and manager attention queue.
- PostgreSQL/Supabase-compatible persistence for calls, transcript turns, and analysis.
- ffmpeg channel split plus Faster-Whisper timestamped transcription.
- Next.js dashboard: attention queue, customer directory, playable call detail, transcript, and evidence-backed analysis.

Issue-trend and agent-metric aggregate endpoints are the next implementation increment once real metadata fields and reviewed analysis labels are available; inventing those mappings without the source data would make them unreliable.
