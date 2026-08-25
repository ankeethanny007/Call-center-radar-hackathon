import type {
  AgentMetric,
  AgentRef,
  AttentionContribution,
  CallAnalysis,
  CallDetail,
  CallListItem,
  CustomerRef,
  Evidence,
  Finding,
  MoodEvent,
  ProcessingProgress,
  TranscriptTurn,
  TrendItem,
  Trends,
} from "./types";

const apiBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const internalApiBase = (process.env.API_INTERNAL_URL || apiBase).replace(/\/$/, "");
const requestApiBase = typeof window === "undefined" ? internalApiBase : apiBase;

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function string(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function number(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}

function asArrayResponse(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const payload = record(value);
  return list(payload.items ?? payload.data ?? payload.results);
}

function prefixedUrl(path: string, base = requestApiBase): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const apiAccessToken = typeof window === "undefined" ? process.env.API_ACCESS_TOKEN : undefined;
  const response = await fetch(prefixedUrl(path), {
    cache: "no-store",
    headers: { Accept: "application/json", ...(apiAccessToken ? { "X-API-Key": apiAccessToken } : {}) },
  });
  if (!response.ok) throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

async function versioned<T>(path: string, legacyPath?: string): Promise<T> {
  try {
    return await fetchJson<T>(`/api/v1${path}`);
  } catch (error) {
    if (legacyPath && error instanceof ApiError && error.status === 404) return fetchJson<T>(legacyPath);
    throw error;
  }
}

function normalizeEvidence(value: unknown): Evidence[] {
  const raw = Array.isArray(value) ? value : value ? [value] : [];
  return raw
    .map((item): Evidence | null => {
      const itemRecord = record(item);
      const startMs = number(itemRecord.start_ms ?? itemRecord.startMs ?? itemRecord.timestamp_ms);
      const quote = string(itemRecord.quote ?? itemRecord.text ?? itemRecord.excerpt);
      if (startMs === undefined || !quote) return null;
      return {
        id: string(itemRecord.id),
        claim: string(itemRecord.claim),
        quote,
        speaker: string(itemRecord.speaker),
        startMs,
        endMs: number(itemRecord.end_ms ?? itemRecord.endMs),
        turnId: (itemRecord.turn_id ?? itemRecord.turnId ?? itemRecord.transcript_segment_id) as string | number | undefined,
        confidence: number(itemRecord.confidence),
      };
    })
    .filter((item): item is Evidence => item !== null);
}

function normalizeCustomer(value: unknown): CustomerRef | null {
  if (!value) return null;
  if (typeof value === "string") return { id: value };
  const item = record(value);
  const id = string(item.id ?? item.customer_id ?? item.customerId);
  if (!id) return null;
  return {
    id,
    displayName: string(item.display_name ?? item.displayName ?? item.name),
    callCount: number(item.call_count ?? item.callCount),
    unresolvedCount: number(item.unresolved_count ?? item.unresolvedCount),
    averageMood: string(item.average_mood ?? item.averageMood),
    lastContactAt: string(item.last_contact_at ?? item.lastContactAt ?? item.last_contact),
  };
}

function normalizeAgent(value: unknown): AgentRef | null {
  if (!value) return null;
  if (typeof value === "string") return { id: value };
  const item = record(value);
  const id = string(item.id ?? item.agent_id ?? item.agentId);
  return id ? { id, displayName: string(item.display_name ?? item.displayName ?? item.name) } : null;
}

function normalizeCall(value: unknown): CallListItem {
  const item = record(value);
  const metadata = record(item.metadata);
  const legacyAnalysis = record(item.analysis);
  const attention = record(item.attention ?? legacyAnalysis.attention);
  const intent = record(item.intent ?? legacyAnalysis.intent);
  const resolution = record(item.resolution ?? legacyAnalysis.resolution);
  const mood = record(item.mood ?? legacyAnalysis.mood);
  const id = string(item.id ?? item.call_id ?? item.callId) || "unknown-call";
  const attentionScore = number(item.attention_score ?? item.attentionScore ?? attention.score ?? legacyAnalysis.attention_score);
  return {
    id,
    status: string(item.processing_status ?? item.status) || "queued",
    customer: normalizeCustomer(item.customer ?? item.customer_id ?? item.customerId),
    agent: normalizeAgent(item.agent ?? item.agent_id ?? item.agentId ?? metadata.agent_id),
    attentionScore: attentionScore ?? null,
    attentionBand: string(item.attention_band ?? item.attentionBand ?? attention.band) ?? null,
    intent: string(item.intent_category ?? item.intent_label ?? intent.category ?? intent.label) ?? null,
    resolution: string(item.resolution_status ?? resolution.status ?? resolution.label) ?? null,
    mood: string(item.mood_label ?? mood.label) ?? null,
    createdAt: string(item.created_at ?? item.createdAt ?? item.started_at ?? metadata.start_time) ?? null,
    durationMs: number(item.duration_ms ?? item.durationMs ?? metadata.duration_ms ?? metadata.duration) ?? ((number(item.duration_seconds) ?? 0) * 1000 || undefined),
  };
}

function normalizeFinding(value: unknown, primaryKeys: string[]): Finding | null {
  if (!value) return null;
  if (typeof value === "string") return { value };
  const item = record(value);
  return {
    label: string(item.label ?? item.category ?? item.status),
    value: string(primaryKeys.map((key) => item[key]).find((candidate) => typeof candidate === "string")),
    description: string(item.description ?? item.detail),
    evidence: normalizeEvidence(item.evidence),
  };
}

function normalizeContribution(value: unknown): AttentionContribution | null {
  const item = record(value);
  const label = string(item.label ?? item.signal ?? item.name ?? item.reason);
  const points = number(item.points ?? item.score ?? item.weight);
  if (!label || points === undefined) return null;
  return {
    id: string(item.id),
    label,
    points,
    explanation: string(item.explanation ?? item.description),
    evidence: normalizeEvidence(item.evidence ?? item.supporting_evidence),
  };
}

function normalizeAnalysis(value: unknown): CallAnalysis | null {
  if (!value) return null;
  const item = record(value);
  const attentionValue = record(item.attention);
  const legacyEvidence = normalizeEvidence(item.attention_evidence);
  const score = number(attentionValue.score ?? item.attention_score);
  const contributions = list(attentionValue.contributions ?? item.attention_contributions)
    .map(normalizeContribution)
    .filter((entry): entry is AttentionContribution => Boolean(entry));
  const shift = record(item.mood_shift ?? item.moodShift);
  const shiftEvidence = normalizeEvidence(shift.evidence);
  const shiftAt = number(shift.at_ms ?? shift.atMs ?? shift.timestamp_ms ?? shiftEvidence[0]?.startMs);
  return {
    intent: normalizeFinding(item.intent, ["category", "label"]),
    resolution: normalizeFinding(item.resolution, ["status", "label"]),
    summary: normalizeFinding(item.summary, ["value", "text", "summary"]),
    attention:
      score === undefined
        ? null
        : {
            score,
            band: string(attentionValue.band ?? item.attention_band),
            contributions:
              contributions.length > 0
                ? contributions
                : legacyEvidence.map((evidence) => ({
                    label: "Evidence-backed attention signal",
                    points: 0,
                    evidence: [evidence],
                  })),
          },
    moodShift:
      Object.keys(shift).length === 0
        ? null
        : {
            from: string(shift.from ?? shift.previous_mood),
            to: string(shift.to ?? shift.new_mood),
            atMs: shiftAt,
            evidence: shiftEvidence,
          },
  };
}

function normalizeTranscript(value: unknown): TranscriptTurn[] {
  return list(value)
    .map((entry, index): TranscriptTurn | null => {
      const item = record(entry);
      const startMs = number(item.start_ms ?? item.startMs);
      const endMs = number(item.end_ms ?? item.endMs);
      const text = string(item.text ?? item.transcript);
      if (startMs === undefined || endMs === undefined || !text) return null;
      return {
        id: (item.id ?? item.turn_id ?? `turn-${index}`) as string | number,
        speaker: string(item.speaker) || "system",
        startMs,
        endMs,
        text,
      };
    })
    .filter((entry): entry is TranscriptTurn => entry !== null)
    .sort((left, right) => left.startMs - right.startMs);
}

function normalizeMoodTimeline(value: unknown): MoodEvent[] {
  return list(value)
    .map((entry): MoodEvent | null => {
      const item = record(entry);
      const evidence = normalizeEvidence(item.evidence);
      const startMs = number(item.start_ms ?? item.startMs ?? item.timestamp_ms ?? evidence[0]?.startMs);
      const mood = string(item.mood ?? item.label ?? item.state);
      if (startMs === undefined || !mood) return null;
      return {
        id: string(item.id),
        mood,
        score: number(item.score ?? item.sentiment_score),
        startMs,
        endMs: number(item.end_ms ?? item.endMs),
        explanation: string(item.explanation ?? item.description),
        evidence,
      };
    })
    .filter((entry): entry is MoodEvent => entry !== null)
    .sort((left, right) => left.startMs - right.startMs);
}

function normalizeDetail(value: unknown): CallDetail {
  const item = record(value);
  const base = normalizeCall(item);
  const analysis = normalizeAnalysis(item.analysis);
  const rawAudio = item.audio;
  const audio = record(rawAudio);
  const audioPath = string(audio.url ?? item.audio_url ?? item.audioUrl);
  const rawEvidence = normalizeEvidence(item.evidence);
  const analysisEvidence = analysis?.attention?.contributions.flatMap((contribution) => contribution.evidence || []) || [];
  return {
    ...base,
    // API reads can use the Compose-only internal address during SSR. Audio URLs must
    // remain browser-reachable, so always derive them from the public API address.
    audioUrl: audioPath ? prefixedUrl(audioPath, apiBase) : prefixedUrl(`/api/v1/calls/${encodeURIComponent(base.id)}/audio`, apiBase),
    metadata: record(item.metadata),
    transcript: normalizeTranscript(item.transcript ?? item.turns),
    analysis,
    moodTimeline: normalizeMoodTimeline(item.mood_timeline ?? item.moodTimeline),
    evidence: rawEvidence.length ? rawEvidence : analysisEvidence,
  };
}

function countsToItems(value: unknown): TrendItem[] {
  if (Array.isArray(value)) {
    return value
      .map((entry): TrendItem | null => {
        const item = record(entry);
        const label = string(item.label ?? item.name ?? item.category ?? item.intent ?? item.topic);
        const count = number(item.count ?? item.value ?? item.calls);
        return label && count !== undefined ? { label, count, delta: number(item.delta ?? item.change ?? item.change_percent) } : null;
      })
      .filter((entry): entry is TrendItem => entry !== null);
  }
  return Object.entries(record(value)).map(([label, count]) => ({ label, count: number(count) || 0 }));
}

function normalizeTrends(value: unknown): Trends {
  const item = record(value);
  return {
    processedCalls: number(item.processed_calls ?? item.processedCalls) || 0,
    totalCalls: number(item.total_calls ?? item.totalCalls),
    intentCounts: countsToItems(item.intent_counts ?? item.intents ?? item.top_issues ?? item.issues),
    resolutionCounts: countsToItems(item.resolution_counts ?? item.resolutions),
    moodCounts: countsToItems(item.mood_counts ?? item.moods),
  };
}

function normalizeAgentMetric(value: unknown): AgentMetric | null {
  const item = record(value);
  const agent = normalizeAgent(item.agent ?? item);
  if (!agent) return null;
  const commonIssueTypes = countsToItems(item.common_issue_types ?? item.commonIssues ?? item.common_issues);
  return {
    ...agent,
    callCount: number(item.call_count ?? item.callCount) || 0,
    averageAttentionScore: number(item.average_attention_score ?? item.averageAttentionScore),
    averageHandleTimeMs: number(item.average_handle_time_ms ?? item.averageHandleTimeMs) ?? ((number(item.average_handle_seconds) ?? 0) * 1000 || undefined),
    resolutionRate: number(item.resolution_rate ?? item.resolutionRate),
    escalationRate: number(item.escalation_rate ?? item.escalationRate),
    commonIssues: commonIssueTypes.map((entry) => entry.label),
    commonIssueTypes,
    reviewCallCount: number(item.review_call_count ?? item.reviewCallCount),
    callsNeedingReview: asArrayResponse(item.calls_needing_review ?? item.callsNeedingReview).map(normalizeCall).filter((call) => call.id !== "unknown-call"),
  };
}

function normalizeProgress(value: unknown): ProcessingProgress {
  const item = record(value);
  const counts = record(item.counts ?? item.by_status ?? item.stages);
  const stages = Array.isArray(item.stages)
    ? list(item.stages)
        .map((entry) => {
          const stage = record(entry);
          const label = string(stage.label ?? stage.status ?? stage.name);
          const count = number(stage.count ?? stage.value);
          return label && count !== undefined ? { label, count } : null;
        })
        .filter((entry): entry is { label: string; count: number } => Boolean(entry))
    : Object.entries(counts).map(([label, count]) => ({ label, count: number(count) || 0 }));
  const total = number(item.total ?? item.total_calls) || stages.reduce((sum, stage) => sum + stage.count, 0);
  const byLabel = (labels: string[]) => stages.filter((stage) => labels.includes(stage.label.toLowerCase())).reduce((sum, stage) => sum + stage.count, 0);
  return {
    total,
    ready: number(item.ready) ?? byLabel(["ready", "complete", "completed", "analyzed"]),
    failed: number(item.failed) ?? byLabel(["failed"]),
    processing: number(item.processing) ?? byLabel(["processing", "transcribing", "analyzing"]),
    queued: number(item.queued) ?? byLabel(["queued", "discovered", "validated"]),
    stages,
  };
}

export const api = {
  async calls(): Promise<CallListItem[]> {
    try {
      const pageSize = 500;
      const calls: CallListItem[] = [];
      for (let offset = 0; ; offset += pageSize) {
        const query = `?limit=${pageSize}&offset=${offset}`;
        const response = await versioned<unknown>(`/calls${query}`, `/calls${query}`);
        const page = asArrayResponse(response).map(normalizeCall).filter((call) => call.id !== "unknown-call");
        calls.push(...page);
        if (page.length < pageSize) return calls;
      }
    } catch {
      return [];
    }
  },

  async call(id: string): Promise<CallDetail | null> {
    try {
      const response = await versioned<unknown>(`/calls/${encodeURIComponent(id)}`, `/calls/${encodeURIComponent(id)}`);
      return normalizeDetail(response);
    } catch {
      return null;
    }
  },

  async attention(): Promise<CallListItem[]> {
    try {
      const response = await versioned<unknown>("/attention", "/attention");
      return asArrayResponse(response)
        .map(normalizeCall)
        .filter((call) => call.id !== "unknown-call")
        .sort((left, right) => (right.attentionScore || 0) - (left.attentionScore || 0));
    } catch {
      return [];
    }
  },

  async customers(): Promise<CustomerRef[]> {
    try {
      const response = await versioned<unknown>("/customers", "/customers");
      return asArrayResponse(response).map(normalizeCustomer).filter((customer): customer is CustomerRef => Boolean(customer));
    } catch {
      return [];
    }
  },

  async customer(id: string): Promise<CustomerRef | null> {
    try {
      return normalizeCustomer(await versioned<unknown>(`/customers/${encodeURIComponent(id)}`));
    } catch {
      return null;
    }
  },

  async customerCalls(id: string): Promise<CallListItem[]> {
    try {
      const response = await versioned<unknown>(`/customers/${encodeURIComponent(id)}/calls`);
      return asArrayResponse(response).map(normalizeCall);
    } catch {
      return (await this.calls()).filter((call) => call.customer?.id === id);
    }
  },

  async trends(): Promise<Trends> {
    try {
      return normalizeTrends(await versioned<unknown>("/trends", "/trends"));
    } catch {
      return { processedCalls: 0, intentCounts: [], resolutionCounts: [], moodCounts: [] };
    }
  },

  async agents(): Promise<AgentMetric[]> {
    try {
      return asArrayResponse(await versioned<unknown>("/agents", "/agents"))
        .map(normalizeAgentMetric)
        .filter((agent): agent is AgentMetric => Boolean(agent));
    } catch {
      return [];
    }
  },

  async agent(id: string): Promise<AgentMetric | null> {
    try {
      return normalizeAgentMetric(await versioned<unknown>(`/agents/${encodeURIComponent(id)}`));
    } catch {
      return null;
    }
  },

  async processingProgress(): Promise<ProcessingProgress | null> {
    try {
      return normalizeProgress(await versioned<unknown>("/processing/progress"));
    } catch {
      return null;
    }
  },
};

export { apiBase };
