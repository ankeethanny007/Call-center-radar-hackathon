import Link from "next/link";
import { notFound } from "next/navigation";
import { CallRow, EmptyState, MetricCard, PageHeader, SectionHeading } from "../../../components/ui";
import { Icon } from "../../../components/icons";
import { api } from "../../../lib/api";
import { displayName, formatDuration, formatPercent } from "../../../lib/format";
import type { AgentMetric } from "../../../lib/types";

export default async function AgentProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [agent, calls] = await Promise.all([api.agent(id), api.calls()]);
  const agentCalls = calls.filter((call) => call.agent?.id === id);
  if (!agent && !agentCalls.length) notFound();
  const profile: AgentMetric = agent || { id, callCount: agentCalls.length };
  const commonIssueTypes = profile.commonIssueTypes || [];
  const callsNeedingReview = profile.callsNeedingReview || agentCalls.filter((call) => (call.attentionScore || 0) >= 50);
  return <>
    <Link className="back-link" href="/agents">← Agents</Link>
    <PageHeader eyebrow="Agent profile" title={displayName(profile.id, profile.displayName)} description={`Agent ID: ${profile.id}`} />
    <section className="metric-grid profile-metrics">
      <MetricCard label="Calls handled" value={profile.callCount} detail="Available persisted calls" tone="blue" icon={<Icon name="headphones" />} />
      <MetricCard label="Avg. handle time" value={formatDuration(profile.averageHandleTimeMs)} detail="From source call metadata" tone="default" icon={<Icon name="clock" />} />
      <MetricCard label="Resolution rate" value={formatPercent(profile.resolutionRate)} detail="Evidence-backed outcomes" tone="success" icon={<Icon name="shield" />} />
      <MetricCard label="Average attention" value={profile.averageAttentionScore === null || profile.averageAttentionScore === undefined ? "—" : `${Math.round(profile.averageAttentionScore)}/100`} detail={profile.reviewCallCount ? `${profile.reviewCallCount} calls need review` : "Priority scores where available"} tone={(profile.averageAttentionScore || 0) >= 50 ? "warning" : "default"} icon={<Icon name="activity" />} />
    </section>
    <section className="panel profile-panel"><SectionHeading title="Common issue types" description="Evidence-validated issue categories seen in this agent’s calls." />{commonIssueTypes.length ? <div className="mini-bars">{commonIssueTypes.map((issue) => <div className="mini-bar-row" key={issue.label}><span>{issue.label.replace(/_/g, " ")}</span><div><i style={{ width: `${Math.max(4, Math.round((issue.count / Math.max(...commonIssueTypes.map((entry) => entry.count), 1)) * 100))}%` }} /></div><b>{issue.count}</b></div>)}</div> : <EmptyState icon="chart" title="No issue categories yet" description="Issue types appear after evidence-backed analyses are persisted." />}</section>
    <section className="panel profile-panel"><SectionHeading title="Calls needing review" description="This agent’s calls with an attention score of 50 or above." />{callsNeedingReview.length ? <div className="call-list full-list">{callsNeedingReview.map((call) => <CallRow call={call} key={call.id} showAgent={false} />)}</div> : <EmptyState icon="briefcase" title="No calls currently need review" description="No persisted calls for this agent meet the high-attention threshold." />}</section>
    <section className="panel"><SectionHeading title="Calls handled" description="Calls associated through explicit source agent metadata." />{agentCalls.length ? <div className="call-list full-list">{agentCalls.map((call) => <CallRow call={call} key={call.id} showAgent={false} />)}</div> : <EmptyState icon="headphones" title="No agent calls available" description="The available call index contains no calls for this agent." />}</section>
  </>;
}
