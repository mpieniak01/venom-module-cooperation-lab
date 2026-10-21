export type HealthState = "loading" | "disabled" | "not_ready" | "unavailable";
export function healthState(value: unknown): HealthState {
  if (!value || typeof value !== "object") return "unavailable";
  const candidate = value as { state?: unknown; ready?: unknown };
  if (candidate.state === "disabled") return "disabled";
  if (candidate.state === "not_ready" && candidate.ready === false) return "not_ready";
  return "unavailable";
}
