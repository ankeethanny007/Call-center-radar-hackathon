export type Speaker = "agent" | "customer" | "system" | string;

export type Evidence = {
  id?: string;
  claim?: string;
  quote: string;
  speaker?: Speaker;
  startMs: number;
  endMs?: number;
  turnId?: string | number;
  confidence?: number;
};

export type CustomerRef = {
  id: string;
  displayName?: string | null;
  callCount?: number;
  unresolvedCount?: number;
  averageMood?: string | null;
  lastContactAt?: string | null;
};

export type AgentRef = {
  id: string;
  displayName?: string | null;
};

export type CallListItem = {
  id: string;
  status: string;
  customer?: CustomerRef | null;
  agent?: AgentRef | null;
  attentionScore?: number | null;
  attentionBand?: string | null;
  intent?: string | null;
  resolution?: string | null;
  mood?: string | null;
  createdAt?: string | null;
  durationMs?: number | null;
};

export type TranscriptTurn = {
  id: string | number;
  speaker: Speaker;
  startMs: number;
  endMs: number;
  text: string;
};

export type Finding = {
  label?: string | null;
  description?: string | null;
  value?: string | null;
  evidence?: Evidence[];
};

export type AttentionContribution = {
  id?: string;
  label: string;
  points: number;
  explanation?: string | null;
  evidence?: Evidence[];
};

export type MoodEvent = {
  id?: string;
  mood: string;
  score?: number | null;
  startMs: number;
  endMs?: number;
  explanation?: string | null;
  evidence?: Evidence[];
};

export type CallAnalysis = {
  intent?: Finding | null;
  resolution?: Finding | null;
  summary?: Finding | null;
  attention?: {
    score: number;
    band?: string | null;
    contributions: AttentionContribution[];
  } | null;
  moodShift?: {
    from?: string | null;
    to?: string | null;
    atMs?: number | null;
    evidence?: Evidence[];
  } | null;
};

export type CallDetail = CallListItem & {
  audioUrl?: string | null;
  metadata: Record<string, unknown>;
  transcript: TranscriptTurn[];
  analysis?: CallAnalysis | null;
  moodTimeline: MoodEvent[];
  evidence: Evidence[];
};

export type TrendItem = {
  label: string;
  count: number;
  delta?: number | null;
};

export type Trends = {
  processedCalls: number;
  totalCalls?: number;
  intentCounts: TrendItem[];
  resolutionCounts: TrendItem[];
  moodCounts: TrendItem[];
};

export type AgentMetric = AgentRef & {
  callCount: number;
  averageAttentionScore?: number | null;
  averageHandleTimeMs?: number | null;
  resolutionRate?: number | null;
  escalationRate?: number | null;
  commonIssues?: string[];
  commonIssueTypes?: TrendItem[];
  reviewCallCount?: number | null;
  callsNeedingReview?: CallListItem[];
};

export type ProcessingProgress = {
  total: number;
  ready: number;
  failed: number;
  processing: number;
  queued: number;
  stages: Array<{ label: string; count: number }>;
};
