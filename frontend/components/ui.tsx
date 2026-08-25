import Link from "next/link";
import type { ReactNode } from "react";
import type { CallListItem, Evidence } from "../lib/types";
import { displayName, formatClock, formatDate, formatDuration, humanize, scoreBand, scoreTone } from "../lib/format";
import { Icon } from "./icons";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-action">{action}</div> : null}
    </div>
  );
}

export function MetricCard({ label, value, detail, tone = "default", icon }: { label: string; value: ReactNode; detail?: string; tone?: "default" | "danger" | "warning" | "success" | "blue"; icon?: ReactNode }) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <div className="metric-top"><span>{label}</span>{icon ? <span className="metric-icon">{icon}</span> : null}</div>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}

export function ScoreBadge({ score, band, compact = false }: { score?: number | null; band?: string | null; compact?: boolean }) {
  if (score === null || score === undefined) return <span className="badge badge-muted">Not scored</span>;
  const tone = scoreTone(score, band);
  return <span className={`score-badge ${tone} ${compact ? "compact" : ""}`}><b>{Math.round(score)}</b><span>{compact ? "/100" : scoreBand(score, band)}</span></span>;
}

export function StatusBadge({ value }: { value?: string | null }) {
  const status = (value || "unknown").toLowerCase();
  const tone = /ready|complete|resolved/.test(status) ? "success" : /failed|unresolved|error/.test(status) ? "danger" : /process|transcrib|analy/.test(status) ? "warning" : "muted";
  return <span className={`badge badge-${tone}`}>{humanize(value)}</span>;
}

export function EmptyState({ icon = "document", title, description, action }: { icon?: "document" | "search" | "warning" | "headphones" | "customer" | "chart" | "briefcase"; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><Icon name={icon} size={25} /></span>
      <h2>{title}</h2>
      <p>{description}</p>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

export function SectionHeading({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>{action ? <div>{action}</div> : null}</div>;
}

export function EvidenceChip({ evidence, onClick }: { evidence: Evidence; onClick?: (evidence: Evidence) => void }) {
  const content = <><Icon name="play" size={13} /><span>{formatClock(evidence.startMs)}</span></>;
  return onClick ? <button className="evidence-chip" type="button" onClick={() => onClick(evidence)}>{content}</button> : <span className="evidence-chip">{content}</span>;
}

export function CallRow({ call, showCustomer = true, showAgent = true }: { call: CallListItem; showCustomer?: boolean; showAgent?: boolean }) {
  return (
    <Link href={`/calls/${encodeURIComponent(call.id)}`} className="call-row">
      <div className="call-row-primary">
        <span className="call-id">{call.id}</span>
        <span className="call-topic">{humanize(call.intent || "Analysis pending")}</span>
      </div>
      {showCustomer ? <div className="call-row-person"><Icon name="user" size={15} />{displayName(call.customer?.id, call.customer?.displayName)}</div> : null}
      {showAgent ? <div className="call-row-person muted"><Icon name="briefcase" size={15} />{displayName(call.agent?.id, call.agent?.displayName)}</div> : null}
      <div className="call-row-meta"><span>{formatDate(call.createdAt)}</span><span>{formatDuration(call.durationMs)}</span></div>
      <div className="call-row-score"><ScoreBadge score={call.attentionScore} band={call.attentionBand} compact /></div>
      <Icon name="chevron-right" size={18} className="row-chevron" />
    </Link>
  );
}
