export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Model = { model_id?: string; id?: string; qualified?: boolean; engine_id?: string; provider?: string; display_name?: string; can_qualify?: boolean; availability_reason?: string; digest?: string; runtime?: string };
export type Scenario = { scenario_id: string; version: string; title?: string; goal?: string };
export type Capabilities = { ready: boolean; state: string; reason_code?: string; catalog_error?: string | null; engines?: {engine_id:string; name:string; status:string; supported:boolean}[]; models: Model[]; scenarios: Scenario[]; modes: string[]; preset?: Record<string, Json> };
export type Run = { id: string; status: string; created: number; last_seq: number; bytes: number; config: Record<string, Json> };
export type LabEvent = { run_id: string; seq: number; kind: string; timestamp: number; payload: Record<string, Json> };
export const terminal = (status: string) => ["completed", "failed", "cancelled", "interrupted"].includes(status);
export function modelId(model: Model) { return model.model_id ?? model.id ?? ""; }
export function mergeEvents(previous: LabEvent[], incoming: LabEvent[], runId: string): LabEvent[] {
  const indexed = new Map(previous.filter((e) => e.run_id === runId).map((e) => [e.seq, e]));
  for (const event of incoming) {
    if (event.run_id !== runId || !Number.isSafeInteger(event.seq) || event.seq < 1) continue;
    indexed.set(event.seq, event);
  }
  return [...indexed.values()].sort((a, b) => a.seq - b.seq).slice(-256);
}
export function isLabEvent(value: unknown): value is LabEvent {
  if (!value || typeof value !== "object") return false;
  const e = value as Partial<LabEvent>;
  return typeof e.run_id === "string" && typeof e.seq === "number" && Number.isSafeInteger(e.seq) &&
    e.seq > 0 && typeof e.kind === "string" && typeof e.timestamp === "number" &&
    !!e.payload && typeof e.payload === "object" && !Array.isArray(e.payload);
}
