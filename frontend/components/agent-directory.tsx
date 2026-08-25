"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { AgentMetric } from "../lib/types";
import { displayName, formatDuration, formatPercent } from "../lib/format";
import { Icon } from "./icons";
import { EmptyState, ScoreBadge } from "./ui";

type Sort = "calls" | "attention" | "resolution" | "name";

export function AgentDirectory({ agents }: { agents: AgentMetric[] }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("calls");
  const visible = useMemo(() => agents.filter((agent) => `${agent.id} ${agent.displayName || ""}`.toLowerCase().includes(query.trim().toLowerCase())).sort((left, right) => {
    if (sort === "name") return displayName(left.id, left.displayName).localeCompare(displayName(right.id, right.displayName));
    if (sort === "attention") return (right.averageAttentionScore || -1) - (left.averageAttentionScore || -1);
    if (sort === "resolution") return (right.resolutionRate || -1) - (left.resolutionRate || -1);
    return right.callCount - left.callCount;
  }), [agents, query, sort]);
  return <>
    <div className="filter-toolbar compact-toolbar"><label className="search-input"><Icon name="search" size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search agent name or ID" aria-label="Search agents" /></label><label className="select-input">Sort <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="calls">Most calls</option><option value="attention">Highest attention</option><option value="resolution">Resolution rate</option><option value="name">Name</option></select></label></div>
    {visible.length ? <div className="agent-list" role="list">{visible.map((agent) => <Link href={`/agents/${encodeURIComponent(agent.id)}`} className="agent-row" role="listitem" key={agent.id}>
      <div className="agent-avatar">{displayName(agent.id, agent.displayName).slice(0, 1).toUpperCase()}</div><div className="agent-main"><strong>{displayName(agent.id, agent.displayName)}</strong><span>{agent.id}</span></div><div className="agent-stat"><span>Calls</span><strong>{agent.callCount}</strong></div><div className="agent-stat"><span>Avg. handle time</span><strong>{formatDuration(agent.averageHandleTimeMs)}</strong></div><div className="agent-stat"><span>Resolution</span><strong>{formatPercent(agent.resolutionRate)}</strong></div><div className="agent-score"><ScoreBadge score={agent.averageAttentionScore} compact /></div><Icon name="chevron-right" size={18} /></Link>)}</div> : <EmptyState icon={agents.length ? "search" : "briefcase"} title={agents.length ? "No agent matches" : "No agent metadata found"} description={agents.length ? "Try a different name or identifier." : "Agent analytics appear only when a source record provides an agent ID."} />}
  </>;
}
