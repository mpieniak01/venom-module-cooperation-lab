import { diagnosticCode, reasonLabel, statusLabel, type texts } from "./i18n";
import type { Capabilities, Run } from "./protocol";
type Texts = ReturnType<typeof texts>;

export function noticePresentation(t: Texts, capabilities: Capabilities | null, error: string) {
  let reason: string | undefined = error || undefined;
  if (!reason && capabilities && !capabilities.ready) reason = capabilities.reason_code ?? "request_failed";
  if (reason) return { code: diagnosticCode(reason), text: reasonLabel(t, reason) };
  return { code: undefined, text: capabilities ? "" : t.loading };
}
export function computationLabel(t: Texts, capabilities: Capabilities | null, run: Run | null, stopQueued: boolean, operatorWaiting = false): string {
  if (stopQueued) return t.cancelPending;
  if (run?.status === "running" && operatorWaiting) return t.awaitOperator;
  if (run) return statusLabel(t, run.status);
  return capabilities?.ready ? t.ready : t.notReady;
}
