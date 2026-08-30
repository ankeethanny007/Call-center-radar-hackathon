"use client";

import { useEffect, useState } from "react";
import { processNewFiles, processingNewFilesStatus, type NewFilesJob } from "../lib/api";

export function ProcessNewCalls() {
  const [job, setJob] = useState<NewFilesJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (job?.status !== "RUNNING") return;
    const timer = window.setInterval(async () => {
      try {
        const next = await processingNewFilesStatus();
        setJob(next);
        if (next.status === "COMPLETE") window.location.reload();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Unable to read processing status");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.status]);

  async function run() {
    setSubmitting(true);
    setError(null);
    try {
      const next = await processNewFiles();
      setJob(next);
      if (next.status === "COMPLETE") window.location.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start processing");
    } finally {
      setSubmitting(false);
    }
  }

  const running = submitting || job?.status === "RUNNING";
  return <section className="panel" style={{ marginBottom: 20, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 20 }}>
    <div>
      <h2 style={{ margin: 0 }}>New call recordings</h2>
      <p style={{ marginBottom: 0 }}>Add MP3 files to <code>data/callradar-data/audio</code> and matching JSON files to <code>data/callradar-data/metadata</code>. Existing calls will not be reprocessed.</p>
      {job && <p className="result-count" aria-live="polite">
        {job.status === "RUNNING" ? `Processing ${job.discovered} new call${job.discovered === 1 ? "" : "s"}…` :
          job.status === "FAILED" ? `Processing failed: ${job.error || "check the server log"}` :
          job.discovered === 0 ? "No new matched files were found." :
            `Completed ${job.processed} of ${job.discovered} new calls${job.failed ? `; ${job.failed} failed` : ""}.`}
      </p>}
      {error && <p className="result-count" role="alert">{error}</p>}
    </div>
    <button className="button button-primary" type="button" onClick={run} disabled={running}>
      {running ? "Processing…" : "Process new files"}
    </button>
  </section>;
}
