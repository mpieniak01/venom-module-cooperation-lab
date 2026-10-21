import { request } from "./api";
import { isLabEvent, mergeEvents, type LabEvent, type Run } from "./protocol";

export async function readReplay(runId: string, signal: AbortSignal, isLive: () => boolean) {
  let events: LabEvent[] = [];
  let cursor = 0;
  for (let page = 0; page < 4; page += 1) {
    const result = await request<{ events: LabEvent[]; resync?: boolean }>(
      "/runs/" + encodeURIComponent(runId) + "/events?after=" + cursor, {signal});
    if (!isLive()) return null;
    if (result.resync || result.events.some((event) => !isLabEvent(event))) throw new Error("resync");
    events = mergeEvents(events, result.events, runId);
    cursor = events.at(-1)?.seq ?? 0;
    if (result.events.length < 100) break;
  }
  return {events, cursor};
}

export function replayedRun(snapshot: Run, events: LabEvent[], cursor: number): Run {
  const latest = events.findLast((event) => (event.kind === "run" || event.kind === "end") && typeof event.payload.status === "string");
  const status = latest?.payload.status;
  return {...snapshot, status:typeof status === "string" ? status : snapshot.status, last_seq:Math.max(snapshot.last_seq, cursor)};
}
