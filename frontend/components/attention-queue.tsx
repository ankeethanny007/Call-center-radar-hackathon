"use client";

import { useMemo, useState } from "react";
import type { CallListItem } from "../lib/types";
import { CallRow, EmptyState } from "./ui";
import { Icon } from "./icons";

type Filter = "all" | "immediate" | "critical" | "high" | "moderate" | "low";

export function AttentionQueue({ calls }: { calls: CallListItem[] }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const filtered = useMemo(() => calls.filter((call) => {
    const haystack = [call.id, call.customer?.id, call.customer?.displayName, call.agent?.id, call.intent].filter(Boolean).join(" ").toLowerCase();
    const band = (call.attentionBand || "").toLowerCase();
    const score = call.attentionScore || 0;
    const matchesBand = filter === "all" || (filter === "immediate" ? score >= 85 || band.includes("immediate") : filter === "critical" ? (score >= 70 && score < 85) || band.includes("critical") : filter === "high" ? score >= 50 && score < 70 : filter === "moderate" ? score >= 30 && score < 50 : score < 30);
    return matchesBand && haystack.includes(query.trim().toLowerCase());
  }), [calls, filter, query]);
  return (
    <>
      <div className="filter-toolbar">
        <label className="search-input"><Icon name="search" size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search call, customer, agent or issue" aria-label="Search attention queue" /></label>
        <div className="filter-pills" aria-label="Priority filter">{(["all", "immediate", "critical", "high", "moderate", "low"] as Filter[]).map((item) => <button type="button" className={filter === item ? "filter-pill selected" : "filter-pill"} onClick={() => setFilter(item)} key={item}>{item === "all" ? "All priorities" : item}</button>)}</div>
      </div>
      <p className="result-count">{filtered.length} of {calls.length} calls shown</p>
      {filtered.length ? <div className="call-list full-list">{filtered.map((call) => <CallRow call={call} key={call.id} />)}</div> : <EmptyState icon={calls.length ? "search" : "warning"} title={calls.length ? "No calls match these filters" : "No calls are ready for manager review"} description={calls.length ? "Try a broader search or priority band." : "Attention-ranked calls appear after evidence-backed analysis is complete."} />}
    </>
  );
}
