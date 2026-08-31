"use client";

import { useEffect, useState } from "react";
import { processNewFiles, processingNewFilesStatus, type NewFilesJob } from "../lib/api";

export function ProcessNewCalls() {
  const [job, setJob] = useState<NewFilesJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 7000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (job?.status !== "RUNNING") return;
    const timer = window.setInterval(async () => {
      try {
        const next = await processingNewFilesStatus();
        setJob(next);
        if (next.status === "COMPLETE") window.location.reload();
      } catch {
        setJob(null);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.status]);

  async function run() {
    setSubmitting(true);
    setToast(null);
    try {
      const next = await processNewFiles();
      setJob(next);
      if (next.action === "already_running") {
        setToast(`Processing already in progress (${next.remaining ?? next.queued} discovered files being analysed)`);
      } else if (next.action === "new_files") {
        setToast(`Discovered ${next.discovered} new files - starting the processing`);
      } else if (next.action === "resumed") {
        setToast(`Resumed parsing ${next.resumed} of discovered files`);
      } else if (next.action === "nothing_to_process") {
        setToast("No new or resumable files found");
      } else {
        setToast(next.error || "Processing could not be started");
      }
    } catch {
      setJob(null);
      setToast("Processing could not be started");
    } finally {
      setSubmitting(false);
    }
  }

  const running = job?.status === "RUNNING";
  return <>
    <button className="button button-primary" type="button" onClick={run} disabled={submitting || running}>
      {submitting && <span className="button-loader" aria-hidden="true" />}
      {submitting ? "Checking…" : running ? "Processing…" : "Process new files / Resume processing"}
    </button>
    {toast && <div className="processing-toast" role="status" aria-live="polite">
      {toast}
      <button type="button" aria-label="Dismiss notification" onClick={() => setToast(null)}>×</button>
    </div>}
  </>;
}
