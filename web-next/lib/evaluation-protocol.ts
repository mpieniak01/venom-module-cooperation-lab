import type { Json, Model } from "./protocol";

export type EvaluationRequest = {
  model_id: string;
  case_ids: string[];
  repetitions: number;
  observation_mode: "history_replay" | "native_incremental";
  episode_memory: "fresh" | "carry";
  reflection: "off" | "episode_note";
  decoding: "greedy" | "sampled";
  response_mode: "strict_json" | "mapped";
  temperature: number;
  top_p: number;
  seed: number;
  num_steps: 8 | 16 | 32 | 64;
  legal_moves: "hidden" | "listed";
  opponent: "optimal" | "random" | "remembering" | "model";
  swap_sides: boolean;
  max_new_tokens: number;
  decision_timeout_s: number;
  max_context_tokens: number;
};
export type EvaluationCase = { id: string; game: string; max_actions: number; config?: Record<string, Json>; seed?: number };
export type EvaluationModel = Model & { observation_modes?: string[]; episode_memories?: string[]; compute_steps?: number[]; num_steps?: number[]; max_context_tokens?: number; capabilities?: Record<string, Json> };
export type EvaluationCapabilities = {
  cases: EvaluationCase[];
  models: EvaluationModel[];
  games: string[];
  limits: Record<string, Json>;
  manifest_version: string;
  storage?: { series_used: number; max_series: number; retention_days: number };
  ready?: boolean;
  reason_code?: string;
};
export type EvaluationPreflight = {
  supported: boolean;
  reason_codes: string[];
  planned_episodes: number;
  planned_blocks: number;
  planned_decisions: number;
  configuration: Record<string, Json>;
  items: Record<string, Json>[];
};
export type EvaluationDecision = {
  player: string;
  observation: Json;
  response: Json;
  action?: Json;
  valid?: boolean;
  can_resume?: boolean;
  error?: string | null;
  seconds?: number | null;
  usage?: Record<string, Json>;
  assessment?: Record<string, Json>;
  response_mapping?: Record<string, Json>;
};
export type EvaluationEpisode = {
  case_id: string;
  episode: number;
  block_id: string;
  attempt: number;
  status: string;
  reason_code?: string | null;
  result: Record<string, Json> | null;
  decisions: EvaluationDecision[];
};
export type EvaluationSnapshot = {
  id: string;
  status: string;
  config: Record<string, Json>;
  progress: { planned: number; started: number; terminal: number; success: number; skipped: number };
  episodes: EvaluationEpisode[];
  summary: Record<string, Json>;
  can_resume?: boolean;
  error?: string | null;
  updated: number | string;
};
export const evaluationActive = (status: string) => ["created", "queued", "preparing", "loading", "running", "cancelling", "cancel_requested", "resuming", "cleanup_pending"].includes(status);
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const safeId = (value: unknown) => typeof value === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(value);
export function isEvaluationCapabilities(value: unknown): value is EvaluationCapabilities {
  return object(value) && Array.isArray(value.cases) && value.cases.every(item => object(item) && safeId(item.id) && typeof item.game === "string" && Number.isInteger(item.max_actions) && Number(item.max_actions) > 0) &&
    Array.isArray(value.models) && value.models.every(item => object(item) && safeId(item.model_id ?? item.id)) &&
    Array.isArray(value.games) && value.games.every(item => typeof item === "string") && object(value.limits) && typeof value.manifest_version === "string";
}
export function isEvaluationPreflight(value: unknown): value is EvaluationPreflight {
  return object(value) && typeof value.supported === "boolean" && Array.isArray(value.reason_codes) && value.reason_codes.every(item => typeof item === "string") &&
    [value.planned_episodes, value.planned_blocks, value.planned_decisions].every(item => Number.isSafeInteger(item) && Number(item) >= 0) && object(value.configuration) && Array.isArray(value.items);
}
export function isEvaluationSnapshot(value: unknown): value is EvaluationSnapshot {
  return object(value) && safeId(value.id) && typeof value.status === "string" && object(value.config) && object(value.progress) &&
    ["planned", "started", "terminal", "success", "skipped"].every(key => Number.isSafeInteger((value.progress as Record<string, unknown>)[key]) && Number((value.progress as Record<string, unknown>)[key]) >= 0) &&
    Array.isArray(value.episodes) && value.episodes.every(episode => object(episode) && typeof episode.case_id === "string" && typeof episode.status === "string" && Array.isArray(episode.decisions)) && object(value.summary);
}
export function evaluationDefaults(): EvaluationRequest {
  return { model_id:"", case_ids:[], repetitions:1, observation_mode:"history_replay", episode_memory:"fresh", reflection:"off", decoding:"greedy", response_mode:"mapped", temperature:0.8, top_p:0.9, seed:17, num_steps:8, legal_moves:"listed", opponent:"optimal", swap_sides:true, max_new_tokens:64, decision_timeout_s:30, max_context_tokens:2048 };
}
export function validEvaluationRequest(input: EvaluationRequest): boolean {
  return typeof input.model_id === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(input.model_id) &&
    Array.isArray(input.case_ids) && input.case_ids.length > 0 && input.case_ids.length <= 32 && input.case_ids.every(id=>typeof id === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(id)) && new Set(input.case_ids).size === input.case_ids.length &&
    ["history_replay", "native_incremental"].includes(input.observation_mode) && ["fresh", "carry"].includes(input.episode_memory) && ["off", "episode_note"].includes(input.reflection) &&
    ["strict_json", "mapped"].includes(input.response_mode) && ["greedy", "sampled"].includes(input.decoding) && [8,16,32,64].includes(input.num_steps) && ["hidden", "listed"].includes(input.legal_moves) &&
    ["optimal", "random", "remembering", "model"].includes(input.opponent) && typeof input.swap_sides === "boolean" && Number.isInteger(input.repetitions) && input.repetitions >= 1 && input.repetitions <= 10 &&
    Number.isInteger(input.max_context_tokens) && input.max_context_tokens >= 128 && input.max_context_tokens <= 8192 && Number.isInteger(input.seed) && input.seed >= 0 && input.seed <= 2147483647 && Number.isInteger(input.max_new_tokens) && input.max_new_tokens >= 8 && input.max_new_tokens <= 256 &&
    Number.isInteger(input.decision_timeout_s) && input.decision_timeout_s >= 1 && input.decision_timeout_s <= 90 && Number.isFinite(input.temperature) && input.temperature >= 0 && input.temperature <= 2 && (input.decoding !== "sampled" || input.temperature > 0) &&
    Number.isFinite(input.top_p) && input.top_p > 0 && input.top_p <= 1;
}

export function savedEvaluationRequest(config: Record<string, Json>): EvaluationRequest | null {
  const source = object(config.request) ? config.request : config;
  const defaults = {...evaluationDefaults(), response_mode:"strict_json" as const};
  // Restore only the public form contract, never metadata or backend-only keys.
  const candidate = Object.fromEntries(Object.entries(defaults).map(([key, fallback])=>[key, Object.hasOwn(source,key) ? source[key] : fallback])) as EvaluationRequest;
  return validEvaluationRequest(candidate) ? {...candidate, case_ids:[...candidate.case_ids]} : null;
}
