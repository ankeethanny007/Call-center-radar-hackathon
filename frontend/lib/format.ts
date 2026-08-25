export function formatClock(milliseconds?: number | null): string {
  if (milliseconds === undefined || milliseconds === null || !Number.isFinite(milliseconds)) return "—";
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  const hours = Math.floor(minutes / 60);
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function formatDuration(milliseconds?: number | null): string {
  if (milliseconds === undefined || milliseconds === null || !Number.isFinite(milliseconds)) return "—";
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function formatPercent(value?: number | null): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return `${Math.round(value <= 1 ? value * 100 : value)}%`;
}

export function humanize(value?: string | null): string {
  if (!value) return "Unknown";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function displayName(id?: string | null, name?: string | null): string {
  return name || id || "Unassigned";
}

export function scoreBand(score?: number | null, suppliedBand?: string | null): string {
  if (suppliedBand) return suppliedBand;
  if (score === undefined || score === null) return "Not scored";
  if (score >= 85) return "Immediate attention";
  if (score >= 70) return "Critical";
  if (score >= 50) return "High";
  if (score >= 30) return "Moderate";
  return "Low";
}

export function scoreTone(score?: number | null, suppliedBand?: string | null): string {
  const band = (suppliedBand || scoreBand(score)).toLowerCase();
  if (band.includes("immediate") || band.includes("critical") || (score ?? 0) >= 70) return "danger";
  if (band.includes("high") || (score ?? 0) >= 50) return "warning";
  if (band.includes("moderate") || (score ?? 0) >= 30) return "caution";
  return "success";
}

export function moodTone(mood?: string | null): string {
  const value = (mood || "").toLowerCase();
  if (/(angry|distressed|frustrated|negative)/.test(value)) return "danger";
  if (/(concerned|confused|neutral)/.test(value)) return "caution";
  if (/(positive|satisfied)/.test(value)) return "success";
  return "muted";
}
