# QA and release runbook

This runbook is the release gate for Call-Centre Radar. It protects the product's core rule: an intent, mood, resolution, summary, or attention contribution is returned only when a timestamped transcript quote supports it.

## Preconditions

- The source archive has been extracted to `data/callradar-data/` with `audio/` and `metadata/` folders.
- `.env` has a valid server-side model key for an OpenAI run, or `ANALYSIS_PROVIDER=rules` is set for an offline pipeline smoke test.
- The database migration is at `0001_initial_schema`.
- The team has approval to process the bank-call data in the selected environment.

## 1. Automated checks

From the repository root, run the backend contract and evidence tests:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

Run the production dashboard compilation:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
```

Verify the initial migration on a clean disposable database:

```bash
cd backend
DATABASE_URL="sqlite:///$PWD/../work/qa-migration.db" \
  ../.venv/bin/alembic -c alembic.ini upgrade head
```

Delete the disposable database afterwards; `work/` is ignored by Git.

## 2. Source and channel smoke test

Ingest all source metadata but process only a representative sample first:

```bash
PYTHONPATH=backend .venv/bin/python scripts/process_dataset.py \
  --input data/callradar-data --media-root data --limit 20
```

For at least five calls, use the call-detail audio player and seek to transcript timestamps. Verify manually that:

- Left channel / `agent` segments contain the agent side of the call.
- Right channel / `customer` segments contain the customer side.
- Transcript timestamps are in audio time, not source metadata end-time.
- Each evidence chip seeks to the exact cited span.

Do not infer a different speaker mapping from metadata IDs; the source contract is fixed stereo attribution.

## 3. Evidence and analysis review

Export a balanced worksheet after there are `READY` records:

```bash
PYTHONPATH=backend .venv/bin/python scripts/export_golden_set.py \
  --size 25 --output work/golden-set-review.csv
```

An independent reviewer should fill `review_intent`, `review_resolution`, `review_mood_shift`, `review_evidence_correct`, `review_summary_correct`, and `reviewer_notes`. Review each cited quote against the source audio/transcript—not just the model's prose.

Reject or reprocess a call if any of these conditions occurs:

- An intent, resolution, mood event, summary, or score signal lacks a valid evidence quote and seekable timestamp.
- The quote is not an exact substring of its cited transcript segment.
- The cited speaker/channel is incorrect.
- The summary exceeds 40 words.
- The attention score is outside 0–100 or includes a signal that is not backed by evidence.

The sample may pass automated structural checks before human review. That is not a substitute for the reviewer sign-off.

## 4. Batch resilience check

Stop a short test batch partway through, then run it again. Confirm that processing resumes from the stored status and does not duplicate transcript or evidence rows:

```bash
PYTHONPATH=backend .venv/bin/python scripts/process_dataset.py --limit 5
PYTHONPATH=backend .venv/bin/python scripts/process_dataset.py --limit 5
PYTHONPATH=backend .venv/bin/python scripts/retry_failed.py
```

Inspect `/api/v1/processing/progress` and errors for failures. Triage an error before retrying it; a retry is deliberate rather than an API-request side effect.

## 5. API and dashboard smoke test

With the API and dashboard running, verify all routes return persisted data and that no request triggers transcription or analysis:

```bash
curl --fail http://localhost:8000/health
# If API_ACCESS_TOKEN is configured (required for a reachable deployment), set
# it in this shell. Omit the header only behind an identity-aware proxy that
# supplies equivalent authorization.
export API_ACCESS_TOKEN='set-from-secret-manager'
curl --fail -H "X-API-Key: ${API_ACCESS_TOKEN}" http://localhost:8000/api/v1/processing/progress
curl --fail -H "X-API-Key: ${API_ACCESS_TOKEN}" 'http://localhost:8000/api/v1/calls?limit=5'
curl --fail -H "X-API-Key: ${API_ACCESS_TOKEN}" 'http://localhost:8000/api/v1/attention?limit=5'
curl --fail -H "X-API-Key: ${API_ACCESS_TOKEN}" http://localhost:8000/api/v1/trends
curl --fail -H "X-API-Key: ${API_ACCESS_TOKEN}" http://localhost:8000/api/v1/agents
```

In the dashboard, test the attention queue, customer history, call detail transcript/audio playback, mood timeline, issue trends, and agent metrics. Test an empty/unprocessed state too; it must state that analysis is pending rather than inventing a conclusion.

## 6. Full-batch release gate

Before declaring the 1,441-call run complete:

- Processing progress shows all calls `READY`, or every remaining `FAILED` call has an owner and documented disposition.
- The golden-set reviewer has signed off on the sample.
- The API health check, migration, backend tests, and frontend build all pass from the release commit.
- The production CORS origin, public API URL, private audio-storage policy, backups, and secret rotation policy have been verified.
- A manager can open a high-attention call and trace every shown judgment back to audio-timestamped words.

Record the model version, prompt/evidence-validator version, dataset run date, reviewer, and failure count with the release. These details make future comparisons auditable.
