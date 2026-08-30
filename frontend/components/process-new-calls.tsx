"use client";

import { useEffect, useState } from "react";
import { processNewFiles, processingNewFilesStatus, type NewFilesJob } from "../lib/api";

export function ProcessNewCalls() {
  const [job, setJob] = useState<NewFilesJob | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
    try {
      const next = await processNewFiles();
      setJob(next);
      if (next.status === "COMPLETE") window.location.reload();
    } catch {
      setJob(null);
    } finally {
      setSubmitting(false);
    }
  }

  const running = submitting || job?.status === "RUNNING";
  return <button className="button button-primary" type="button" onClick={run} disabled={running}>
      {running ? "Processing…" : "Process new files"}
  </button>;
}
