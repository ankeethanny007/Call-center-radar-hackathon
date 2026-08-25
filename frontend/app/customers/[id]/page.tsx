import Link from "next/link";
import { notFound } from "next/navigation";
import { CallRow, EmptyState, MetricCard, PageHeader, SectionHeading } from "../../../components/ui";
import { Icon } from "../../../components/icons";
import { api } from "../../../lib/api";
import { displayName, formatPercent, humanize } from "../../../lib/format";

export default async function CustomerProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [customer, calls] = await Promise.all([api.customer(id), api.customerCalls(id)]);
  if (!customer && !calls.length) notFound();
  const profile = customer || { id, callCount: calls.length };
  const unresolved = calls.filter((call) => (call.resolution || "").toLowerCase().includes("unresolved")).length;
  const scored = calls.filter((call) => call.attentionScore !== null && call.attentionScore !== undefined);
  const averageAttention = scored.length ? Math.round(scored.reduce((sum, call) => sum + (call.attentionScore || 0), 0) / scored.length) : null;
  const resolutionRate = calls.length ? calls.filter((call) => (call.resolution || "").toLowerCase() === "resolved").length / calls.length : null;
  return <>
    <Link className="back-link" href="/customers">← Customers</Link>
    <PageHeader eyebrow="Customer profile" title={displayName(profile.id, profile.displayName)} description={`Customer ID: ${profile.id}`} />
    <section className="metric-grid profile-metrics">
      <MetricCard label="Total calls" value={profile.callCount ?? calls.length} detail="Available call history" tone="blue" icon={<Icon name="headphones" />} />
      <MetricCard label="Unresolved calls" value={profile.unresolvedCount ?? unresolved} detail="Evidence-backed outcomes" tone={unresolved ? "warning" : "default"} icon={<Icon name="warning" />} />
      <MetricCard label="Resolution rate" value={formatPercent(resolutionRate)} detail="Across available calls" tone="success" icon={<Icon name="shield" />} />
      <MetricCard label="Average attention" value={averageAttention === null ? "—" : `${averageAttention}/100`} detail={profile.averageMood ? `Average mood: ${humanize(profile.averageMood)}` : "Scores when analysis is ready"} tone={averageAttention && averageAttention >= 50 ? "warning" : "default"} icon={<Icon name="activity" />} />
    </section>
    <section className="panel">
      <SectionHeading title="Call history" description="Open any call to hear the original recording and inspect the exact evidence behind its analysis." />
      {calls.length ? <div className="call-list full-list">{calls.map((call) => <CallRow call={call} key={call.id} showCustomer={false} />)}</div> : <EmptyState icon="headphones" title="No call history available" description="This customer record has not yet been associated with an available call." />}
    </section>
  </>;
}
