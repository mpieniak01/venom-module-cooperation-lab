import type { Model } from "./protocol";

export function outputTokenLimit(model: Model | undefined): number {
  const limit = model?.max_new_tokens;
  return Number.isSafeInteger(limit) && Number(limit) > 0 && Number(limit) <= 1024 ? Number(limit) : 256;
}
