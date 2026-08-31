import Link from "next/link";
import { CallRow, EmptyState, MetricCard, PageHeader, SectionHeading } from "../components/ui";
import { Icon } from "../components/icons";
import { api } from "../lib/api";
import { formatPercent } from "../lib/format";

export default async function OverviewPage() {
  const [attention, calls, customers, trends, agents, progress] = await Promise.all([
    api.attention(),
    api.calls(),
    api.customers(),
    api.trends(),
    api.agents(),
    api.processingProgress(),
  ]);
  const urgent = attention.filter((call) => (call.attentionScore || 0) >= 70).length;
  const unresolved = calls.filter((call) => (call.resolution || "").toLowerCase().includes("unresolved")).length;
  const ready = progress?.ready ?? calls.filter((call) => /ready|complete/.test(call.status.toLowerCase())).length;
  const highestTrend = trends.intentCounts.slice().sort((left, right) => right.count - left.count)[0];
  const observedResolutionRate = calls.length
    ? calls.filter((call) => (call.resolution || "").toLowerCase().includes("resolved") && !(call.resolution || "").toLowerCase().includes("unresolved")).length / calls.length
    : null;
  return (
    <>
      <PageHeader
        eyebrow="Operations command center"
        title="See the calls that need a human next."
        description="Every priority signal is grounded in a seekable customer or agent statement—not a black-box score."
        action={<Link className="button button-primary" href="/attention"><Icon name="queue" size={17} />Review attention queue</Link>}
      />

      <section className="metric-grid" aria-label="Call centre overview">
        <MetricCard label="Needs attention" value={attention.length} detail={`${urgent} critical or immediate`} tone={urgent ? "danger" : "default"} icon={<Icon name="warning" />} href="/calls?minimumScore=1" />
        <MetricCard label="Processed calls" value={ready} detail={progress ? `${progress.total} discovered in batch` : "Stored analysis only"} tone="blue" icon={<Icon name="activity" />} href="/calls?status=READY" />
        <MetricCard label="Unresolved" value={unresolved} detail={calls.length ? `Across ${calls.length} available calls` : "Analysis will populate this"} tone={unresolved ? "warning" : "default"} icon={<Icon name="shield" />} href="/calls?resolution=UNRESOLVED" />
        <MetricCard label="Observed resolution" value={formatPercent(observedResolutionRate)} detail="From evidence-backed call outcomes" tone="success" icon={<Icon name="trend" />} href="/calls?resolution=RESOLVED" />
      </section>

      <section className="dashboard-grid dashboard-main-grid">
        <div className="panel panel-queue">
          <SectionHeading title="Manager attention" description="Highest evidence-backed scores first." action={<Link className="text-link" href="/attention">View all <Icon name="arrow-right" size={15} /></Link>} />
          {attention.length ? <div className="call-list">{attention.slice(0, 5).map((call) => <CallRow call={call} key={call.id} />)}</div> : <EmptyState icon="warning" title="No calls ranked yet" description="Completed analyses with manager-attention evidence will appear here." action={<Link className="button button-secondary" href="/calls">Browse calls</Link>} />}
        </div>

        <aside className="overview-aside">
          <div className="panel processing-card">
            <div className="processing-heading"><div><p className="eyebrow">Batch processing</p><h2>{progress ? "Pipeline progress" : "Pipeline status"}</h2></div><Icon name="activity" size={22} /></div>
            {progress ? <>
              <div className="progress-summary"><strong>{progress.total ? Math.round((progress.ready / progress.total) * 100) : 0}%</strong><span>ready for review</span></div>
              <div className="progress-track"><span style={{ width: `${progress.total ? Math.round((progress.ready / progress.total) * 100) : 0}%` }} /></div>
              <div className="progress-stat-list">
                <span><i className="dot dot-success" />{progress.ready} ready</span>
                <span><i className="dot dot-warning" />{progress.processing} running</span>
                <span><i className="dot dot-muted" />{progress.queued} queued</span>
                <span><i className="dot dot-danger" />{progress.failed} failed</span>
              </div>
            </> : <p className="muted-copy">Progress will appear as soon as the processing service publishes its first batch status.</p>}
          </div>
          <div className="panel compact-insight">
            <span className="insight-icon"><Icon name="sparkle" size={19} /></span>
            <div><p className="eyebrow">Top issue</p><h2>{highestTrend?.label || "No issue trend yet"}</h2><p>{highestTrend ? `${highestTrend.count} analyzed call${highestTrend.count === 1 ? "" : "s"} currently map to this controlled taxonomy.` : "Issue trends will appear after analyzed calls are available."}</p><Link href="/trends" className="text-link">Explore trends <Icon name="arrow-right" size={15} /></Link></div>
          </div>
        </aside>
      </section>

      <section className="dashboard-grid dashboard-bottom-grid">
        <div className="panel">
          <SectionHeading title="Issue signal" description="Only persisted, controlled labels are counted." action={<Link className="text-link" href="/trends">All trends <Icon name="arrow-right" size={15} /></Link>} />
          {trends.intentCounts.length ? <div className="mini-bars">{trends.intentCounts.slice().sort((left, right) => right.count - left.count).slice(0, 5).map((item) => {
            const max = Math.max(...trends.intentCounts.map((candidate) => candidate.count), 1);
            return <div className="mini-bar-row" key={item.label}><span>{item.label}</span><div><i style={{ width: `${(item.count / max) * 100}%` }} /></div><b>{item.count}</b></div>;
          })}</div> : <p className="muted-copy">No issue labels have been persisted yet.</p>}
        </div>
        <div className="panel">
          <SectionHeading title="Coverage" description="Customers and agents from source metadata." />
          <div className="coverage-grid"><div><strong>{customers.length}</strong><span>customers</span><Link href="/customers">Open customers <Icon name="arrow-right" size={14} /></Link></div><div><strong>{agents.length}</strong><span>agents</span><Link href="/agents">Open agents <Icon name="arrow-right" size={14} /></Link></div></div>
        </div>
      </section>
    </>
  );
}
