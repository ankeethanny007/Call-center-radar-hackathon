import { TrendExplorer } from "../../components/trend-explorer";
import { MetricCard, PageHeader } from "../../components/ui";
import { Icon } from "../../components/icons";
import { api } from "../../lib/api";

export default async function TrendsPage() {
  const trends = await api.trends();
  const topIssue = trends.intentCounts.slice().sort((left, right) => right.count - left.count)[0];
  return <>
    <PageHeader eyebrow="Operations intelligence" title="Issue trends" description="See what customers contact the bank about, how calls conclude, and which sentiments are surfacing—without introducing uncontrolled labels." />
    <section className="metric-grid trend-metrics">
      <MetricCard label="Processed calls" value={trends.processedCalls} detail={trends.totalCalls ? `${trends.totalCalls} total discovered` : "Calls with stored analysis"} tone="blue" icon={<Icon name="activity" />} />
      <MetricCard label="Top issue" value={topIssue?.label || "—"} detail={topIssue ? `${topIssue.count} calls` : "Awaiting analysis"} tone="warning" icon={<Icon name="trend" />} />
      <MetricCard label="Tracked outcomes" value={trends.resolutionCounts.length} detail="Resolution classifications" tone="success" icon={<Icon name="shield" />} />
      <MetricCard label="Mood signals" value={trends.moodCounts.length} detail="Timestamped customer states" tone="default" icon={<Icon name="activity" />} />
    </section>
    <section className="panel trend-panel"><TrendExplorer trends={trends} /></section>
  </>;
}
