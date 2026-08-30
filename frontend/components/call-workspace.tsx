"use client";

import Link from "next/link";
import { useMemo, useRef, useState, type CSSProperties } from "react";
import type { CallDetail, Evidence, Finding, MoodEvent, TranscriptTurn } from "../lib/types";
import { displayName, formatClock, formatDate, formatDuration, humanize, moodTone } from "../lib/format";
import { Icon } from "./icons";
import { EmptyState, EvidenceChip, ScoreBadge, StatusBadge } from "./ui";

function findingText(finding?: Finding | null): string {
  if (!finding) return "Not available";
  return finding.value || finding.label || "Not available";
}

function evidenceFromFinding(finding?: Finding | null): Evidence[] {
  return finding?.evidence || [];
}

export function CallWorkspace({ call }: { call: CallDetail }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const turnRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [currentMs, setCurrentMs] = useState(0);
  const [activeTurnId, setActiveTurnId] = useState<string | number | null>(null);
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [audioError, setAudioError] = useState(false);
  const [query, setQuery] = useState("");
  const duration = call.durationMs || Math.max(...call.transcript.map((turn) => turn.endMs), 1);
  const transcript = useMemo(() => call.transcript.filter((turn) => turn.text.toLowerCase().includes(query.trim().toLowerCase())), [call.transcript, query]);
  const attention = call.analysis?.attention;

  const seek = (milliseconds: number, turnId?: string | number) => {
    const audio = audioRef.current;
    const exactTurn = turnId !== undefined
      ? call.transcript.find((turn) => String(turn.id) === String(turnId))
      : call.transcript.find((turn) => turn.startMs <= milliseconds && turn.endMs >= milliseconds) || call.transcript.find((turn) => turn.startMs >= milliseconds);
    setCurrentMs(milliseconds);
    setActiveTurnId(exactTurn?.id ?? turnId ?? null);
    if (exactTurn) window.setTimeout(() => turnRefs.current[String(exactTurn.id)]?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
    if (audio) {
      audio.currentTime = milliseconds / 1000;
      void audio.play().catch(() => undefined);
    }
  };

  const activateEvidence = (evidence: Evidence) => {
    setActiveEvidence(evidence);
    seek(evidence.startMs, evidence.turnId);
  };

  return <>
    <Link className="back-link" href="/calls">← Calls</Link>
    <div className="call-hero">
      <div>
        <p className="eyebrow">Call detail</p>
        <h1>{call.id}</h1>
        <div className="call-identity">
          {call.customer ? <Link href={`/customers/${encodeURIComponent(call.customer.id)}`}><Icon name="user" size={16} />{displayName(call.customer.id, call.customer.displayName)}</Link> : <span><Icon name="user" size={16} />Customer unknown</span>}
          {call.agent ? <Link href={`/agents/${encodeURIComponent(call.agent.id)}`}><Icon name="briefcase" size={16} />{displayName(call.agent.id, call.agent.displayName)}</Link> : <span><Icon name="briefcase" size={16} />Agent unknown</span>}
          <span><Icon name="clock" size={16} />{formatDate(call.createdAt)} · {formatDuration(duration)}</span>
        </div>
      </div>
      <div className="call-hero-badges"><StatusBadge value={call.status} /><ScoreBadge score={attention?.score ?? call.attentionScore} band={attention?.band ?? call.attentionBand} /></div>
    </div>

    <div className="call-detail-layout">
      <div className="call-main-column">
        <section className="panel recording-panel">
          <div className="recording-header"><div><p className="eyebrow">Original recording</p><h2>Listen with the evidence</h2></div><span className="recording-time">{formatClock(currentMs)} <i>/</i> {formatClock(duration)}</span></div>
          {call.audioUrl ? <audio ref={audioRef} className="audio-player" controls preload="metadata" src={call.audioUrl} onTimeUpdate={(event) => setCurrentMs(event.currentTarget.currentTime * 1000)} onError={() => setAudioError(true)} /> : null}
          {audioError ? <p className="inline-warning"><Icon name="warning" size={16} />The recording could not be loaded. The persisted transcript and evidence remain available.</p> : null}
          {!call.audioUrl ? <p className="inline-warning"><Icon name="warning" size={16} />No playable audio URL is available for this call.</p> : null}
          <div className="recording-hint"><Icon name="play" size={15} />Click a transcript segment, mood event, or evidence marker to seek to that exact moment.</div>
        </section>

        <section className="panel transcript-panel">
          <div className="section-heading transcript-heading"><div><h2>Timestamped transcript</h2><p>Speakers are deterministically attributed from the stereo channels: agent left, customer right.</p></div><label className="transcript-search"><Icon name="search" size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find words in this call" aria-label="Find transcript text" /></label></div>
          {transcript.length ? <div className="transcript-list">{transcript.map((turn) => <TranscriptTurnCard key={turn.id} turn={turn} active={String(activeTurnId) === String(turn.id) || (currentMs >= turn.startMs && currentMs <= turn.endMs)} buttonRef={(node) => { turnRefs.current[String(turn.id)] = node; }} onSeek={() => seek(turn.startMs, turn.id)} />)}</div> : <EmptyState icon="search" title="No transcript segment matches" description="Try a different word or phrase from the conversation." />}
        </section>
      </div>

      <aside className="call-side-column">
        <section className="panel analysis-panel">
          <div className="section-heading"><div><p className="eyebrow">Analysis</p><h2>What happened</h2></div><Icon name="sparkle" size={20} /></div>
          {call.analysis ? <div className="finding-stack">
            <FindingCard title="Intent" finding={call.analysis.intent} onEvidence={activateEvidence} />
            <FindingCard title="Resolution" finding={call.analysis.resolution} onEvidence={activateEvidence} />
            <FindingCard title="Summary" finding={call.analysis.summary} onEvidence={activateEvidence} summary />
          </div> : <EmptyState icon="document" title="Analysis is pending" description="This call will become reviewable after its persisted transcript analysis completes." />}
        </section>

        <section className="panel mood-panel">
          <div className="section-heading"><div><p className="eyebrow">Customer journey</p><h2>Mood timeline</h2></div><Icon name="activity" size={20} /></div>
          {call.moodTimeline.length ? <MoodTimeline events={call.moodTimeline} duration={duration} onSelect={(event) => { const evidence = event.evidence?.[0]; if (evidence) activateEvidence(evidence); else seek(event.startMs); }} /> : <p className="muted-copy">No evidence-backed mood events have been persisted for this call.</p>}
          {call.analysis?.moodShift ? <div className="mood-shift-card"><span className="mood-shift-icon"><Icon name="trend" size={17} /></span><div><strong>{humanize(call.analysis.moodShift.from)} → {humanize(call.analysis.moodShift.to)}</strong><p>{call.analysis.moodShift.atMs !== undefined && call.analysis.moodShift.atMs !== null ? `Shift detected at ${formatClock(call.analysis.moodShift.atMs)}.` : "Mood shift detected."}</p>{call.analysis.moodShift.evidence?.[0] ? <EvidenceChip evidence={call.analysis.moodShift.evidence[0]} onClick={activateEvidence} /> : null}</div></div> : null}
        </section>

        <section className="panel attention-panel">
          <div className="section-heading"><div><p className="eyebrow">Manager rationale</p><h2>Attention score</h2></div><ScoreBadge score={attention?.score ?? call.attentionScore} band={attention?.band ?? call.attentionBand} /></div>
          {attention?.contributions.length ? <div className="contribution-list">{attention.contributions.map((contribution, index) => <div className="contribution" key={contribution.id || `${contribution.label}-${index}`}><div className="contribution-main"><b>+{contribution.points}</b><div><strong>{contribution.label}</strong>{contribution.explanation ? <p>{contribution.explanation}</p> : null}</div></div>{contribution.evidence?.map((evidence, evidenceIndex) => <button className="evidence-quote" type="button" onClick={() => activateEvidence(evidence)} key={`${evidence.turnId || evidence.startMs}-${evidenceIndex}`}><span><Icon name="play" size={13} />{formatClock(evidence.startMs)}</span><q>{evidence.quote}</q></button>)}</div>)}</div> : <p className="muted-copy">No itemized score contributions have been persisted yet.</p>}
        </section>

        {activeEvidence ? <section className="active-evidence"><div><span>Selected evidence · {formatClock(activeEvidence.startMs)}</span><strong>“{activeEvidence.quote}”</strong>{activeEvidence.claim ? <p>{activeEvidence.claim}</p> : null}</div><button type="button" onClick={() => setActiveEvidence(null)} aria-label="Dismiss selected evidence"><Icon name="x" size={17} /></button></section> : null}
      </aside>
    </div>
  </>;
}

function TranscriptTurnCard({ turn, active, onSeek, buttonRef }: { turn: TranscriptTurn; active: boolean; onSeek: () => void; buttonRef: (node: HTMLButtonElement | null) => void }) {
  return <button ref={buttonRef} className={`transcript-turn ${turn.speaker.toLowerCase()}${active ? " active" : ""}`} type="button" onClick={onSeek}>
    <span className="turn-speaker"><i>{turn.speaker === "agent" ? "A" : turn.speaker === "customer" ? "C" : "•"}</i>{humanize(turn.speaker)}</span><span className="turn-time">{formatClock(turn.startMs)}</span><span className="turn-text">{turn.text}</span><Icon name="play" size={15} className="turn-play" />
  </button>;
}

function FindingCard({ title, finding, onEvidence, summary = false }: { title: string; finding?: Finding | null; onEvidence: (evidence: Evidence) => void; summary?: boolean }) {
  const evidence = evidenceFromFinding(finding);
  return <article className={summary ? "finding-card summary-finding" : "finding-card"}><span>{title}</span><strong>{findingText(finding)}</strong>{finding?.description ? <p>{finding.description}</p> : null}{evidence.map((item, index) => <button type="button" className="finding-evidence" onClick={() => onEvidence(item)} key={`${item.turnId || item.startMs}-${index}`}><EvidenceChip evidence={item} /><q>{item.quote}</q></button>)}</article>;
}

function MoodTimeline({ events, duration, onSelect }: { events: MoodEvent[]; duration: number; onSelect: (event: MoodEvent) => void }) {
  return <div className="mood-timeline">{events.map((event, index) => <button className={`mood-event ${moodTone(event.mood)}`} type="button" onClick={() => onSelect(event)} key={event.id || `${event.mood}-${event.startMs}`} style={{ "--position": `${Math.min(96, Math.max(2, (event.startMs / duration) * 100))}%` } as CSSProperties}><span className="mood-dot" /><span><strong>{humanize(event.mood)}</strong><small>{formatClock(event.startMs)}</small></span>{event.explanation ? <em>{event.explanation}</em> : null}{index < events.length - 1 ? <i className="mood-connector" /> : null}</button>)}</div>;
}
