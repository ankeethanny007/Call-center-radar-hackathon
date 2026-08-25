"use client";

import { useMemo, useState } from "react";
import type { TrendItem, Trends } from "../lib/types";
import { humanize } from "../lib/format";
import { EmptyState } from "./ui";

type View = "issues" | "outcomes" | "mood";

export function TrendExplorer({ trends }: { trends: Trends }) {
  const [view, setView] = useState<View>("issues");
  const items = useMemo<TrendItem[]>(() => {
    if (view === "outcomes") return trends.resolutionCounts;
    if (view === "mood") return trends.moodCounts;
    return trends.intentCounts;
  }, [trends, view]);
  const sorted = items.slice().sort((left, right) => right.count - left.count);
  const max = Math.max(...sorted.map((item) => item.count), 1);
  const descriptor = view === "issues" ? "controlled issue category" : view === "outcomes" ? "evidence-backed outcome" : "observed customer mood";
  return <>
    <div className="segmented-control" role="tablist" aria-label="Trend measure">
      <button type="button" className={view === "issues" ? "selected" : ""} onClick={() => setView("issues")} role="tab" aria-selected={view === "issues"}>Issue categories</button>
      <button type="button" className={view === "outcomes" ? "selected" : ""} onClick={() => setView("outcomes")} role="tab" aria-selected={view === "outcomes"}>Resolutions</button>
      <button type="button" className={view === "mood" ? "selected" : ""} onClick={() => setView("mood")} role="tab" aria-selected={view === "mood"}>Customer mood</button>
    </div>
    {sorted.length ? <div className="trend-chart" role="list" aria-label={`${descriptor} trend`}>
      {sorted.map((item) => <div className="trend-row" role="listitem" key={item.label}>
        <div className="trend-label"><strong>{humanize(item.label)}</strong><span>{item.count} calls</span></div>
        <div className="trend-bar"><i style={{ width: `${Math.max(4, (item.count / max) * 100)}%` }} /></div>
        <div className={item.delta === undefined || item.delta === null ? "trend-change muted" : item.delta > 0 ? "trend-change up" : "trend-change down"}>{item.delta === undefined || item.delta === null ? "No comparison" : `${item.delta > 0 ? "+" : ""}${item.delta}%`}</div>
      </div>)}
    </div> : <EmptyState icon="chart" title="No trend data yet" description={`This view will populate after calls have persisted ${descriptor} analysis.`} />}
  </>;
}
