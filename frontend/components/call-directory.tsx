"use client";

import { useMemo, useState } from "react";
import type { CallListItem } from "../lib/types";
import { CallRow, EmptyState } from "./ui";
import { Icon } from "./icons";

function values(calls: CallListItem[], field: (call: CallListItem) => string | null | undefined): string[] {
  return Array.from(new Set(calls.map(field).filter((item): item is string => Boolean(item)))).sort();
}

export type CallDirectoryFilters = {
  query?: string;
  status?: string;
  resolution?: string;
  minimumScore?: string;
};

export function CallDirectory({ calls, initialFilters = {} }: { calls: CallListItem[]; initialFilters?: CallDirectoryFilters }) {
  const [query, setQuery] = useState(initialFilters.query || "");
  const [customer, setCustomer] = useState("all");
  const [agent, setAgent] = useState("all");
  const [intent, setIntent] = useState("all");
  const [resolution, setResolution] = useState(initialFilters.resolution || "all");
  const [mood, setMood] = useState("all");
  const [status, setStatus] = useState(initialFilters.status || "all");
  const [minimumScore, setMinimumScore] = useState(initialFilters.minimumScore || "all");
  const [maximumDuration, setMaximumDuration] = useState("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const visible = useMemo(() => calls.filter((call) => {
    const queryText = [call.id, call.customer?.id, call.customer?.displayName, call.agent?.id, call.agent?.displayName, call.intent].filter(Boolean).join(" ").toLowerCase();
    const date = call.createdAt ? new Date(call.createdAt) : null;
    const min = minimumScore === "all" ? null : Number(minimumScore);
    const maxMs = maximumDuration === "all" ? null : Number(maximumDuration) * 60 * 1000;
    return queryText.includes(query.trim().toLowerCase())
      && (customer === "all" || call.customer?.id === customer)
      && (agent === "all" || call.agent?.id === agent)
      && (intent === "all" || call.intent === intent)
      && (resolution === "all" || call.resolution === resolution)
      && (mood === "all" || call.mood === mood)
      && (status === "all" || call.status === status)
      && (min === null || (call.attentionScore || 0) >= min)
      && (maxMs === null || (call.durationMs || 0) <= maxMs)
      && (!fromDate || (date && date >= new Date(`${fromDate}T00:00:00`)))
      && (!toDate || (date && date <= new Date(`${toDate}T23:59:59`)));
  }), [agent, calls, customer, fromDate, intent, maximumDuration, minimumScore, mood, query, resolution, status, toDate]);
  const clear = () => { setQuery(""); setCustomer("all"); setAgent("all"); setIntent("all"); setResolution("all"); setMood("all"); setStatus("all"); setMinimumScore("all"); setMaximumDuration("all"); setFromDate(""); setToDate(""); };
  const select = (label: string, value: string, setValue: (value: string) => void, options: string[]) => <label className="filter-select" key={label}><span>{label}</span><select value={value} onChange={(event) => setValue(event.target.value)}><option value="all">All</option>{options.map((option) => <option value={option} key={option}>{option}</option>)}</select></label>;
  return <>
    <div className="filter-toolbar call-filter-toolbar">
      <label className="search-input"><Icon name="search" size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search call, customer, agent or issue" aria-label="Search calls" /></label>
      <button className="button button-quiet" type="button" onClick={clear}><Icon name="filter" size={16} />Clear filters</button>
    </div>
    <details className="filter-panel" open>
      <summary><Icon name="filter" size={16} />Filters <span>Customer, agent, date, classification and duration</span></summary>
      <div className="filter-grid">
        {select("Customer", customer, setCustomer, values(calls, (call) => call.customer?.id))}
        {select("Agent", agent, setAgent, values(calls, (call) => call.agent?.id))}
        {select("Issue category", intent, setIntent, values(calls, (call) => call.intent))}
        {select("Resolution", resolution, setResolution, values(calls, (call) => call.resolution))}
        {select("Customer mood", mood, setMood, values(calls, (call) => call.mood))}
        {select("Processing status", status, setStatus, values(calls, (call) => call.status))}
        <label className="filter-select"><span>Minimum score</span><select value={minimumScore} onChange={(event) => setMinimumScore(event.target.value)}><option value="all">Any score</option><option value="1">Any attention signal</option><option value="30">30+ Moderate</option><option value="50">50+ High</option><option value="70">70+ Critical</option><option value="85">85+ Immediate</option></select></label>
        <label className="filter-select"><span>Maximum duration</span><select value={maximumDuration} onChange={(event) => setMaximumDuration(event.target.value)}><option value="all">Any duration</option><option value="5">Under 5 minutes</option><option value="10">Under 10 minutes</option><option value="20">Under 20 minutes</option></select></label>
        <label className="filter-select"><span>From date</span><input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} /></label>
        <label className="filter-select"><span>To date</span><input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} /></label>
      </div>
    </details>
    <p className="result-count">{visible.length} of {calls.length} calls shown</p>
    {visible.length ? <div className="call-list full-list">{visible.map((call) => <CallRow call={call} key={call.id} />)}</div> : <EmptyState icon={calls.length ? "search" : "headphones"} title={calls.length ? "No calls match these filters" : "No calls discovered yet"} description={calls.length ? "Clear a filter or use a broader search." : "Calls become available after the dataset is ingested."} />}
  </>;
}
