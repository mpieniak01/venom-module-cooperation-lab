"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API, ApiError, failureCode, request } from "./api";
import { readReplay, replayedRun } from "./replay";
import { isLabEvent, mergeEvents, terminal, type Capabilities, type Json, type LabEvent, type Run } from "./protocol";

export function useLab() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<LabEvent[]>([]);
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [stopQueued, setStopQueued] = useState(false);
  const cancelQueued = useRef(false);
  const [revision, setRevision] = useState(0);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const busy = useRef(false);
  const source = useRef<EventSource | null>(null);
  const idempotency = useRef<{ body: string; key: string } | null>(null);
  const runId = run?.id ?? null;

  const select = useCallback((value: Run | null) => {
    source.current?.close();
    source.current = null;
    setEvents([]);
    setRun(value);
    setError("");
    setRevision((v) => v + 1);
    try {
      if (value) localStorage.setItem("cooperation-lab.run", value.id);
      else localStorage.removeItem("cooperation-lab.run");
    } catch { /* Storage availability does not control computation. */ }
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      request<Capabilities>("/capabilities", { signal: abort.signal }),
      request<{ runs: Run[] }>("/runs?limit=100", { signal: abort.signal }),
    ]).then(([caps, result]) => {
      if (abort.signal.aborted) return;
      if (!caps || !Array.isArray(caps.models) || !Array.isArray(caps.scenarios) || !Array.isArray(caps.modes) || !Array.isArray(result.runs)) throw new ApiError("invalid_response", 502);
      setCapabilities(caps); setRuns(result.runs); setError("");
      setRun((current) => {
        if (current) {
          const fresh = result.runs.find((r) => r.id === current.id);
          if (fresh && fresh.last_seq >= current.last_seq && !(terminal(current.status) && !terminal(fresh.status))) return fresh;
          return current;
        }
        let saved: string | null = null;
        try { saved = localStorage.getItem("cooperation-lab.run"); } catch { /* Optional UI persistence. */ }
        return result.runs.find((r) => !terminal(r.status)) ??
          result.runs.find((r) => r.id === saved) ?? null;
      });
      if (!source.current && !result.runs.some((r) => !terminal(r.status))) setConnection("connected");
    }).catch((reason: unknown) => {
      if (!abort.signal.aborted) { setError(failureCode(reason)); setConnection("disconnected"); }
    });
    return () => abort.abort();
  }, [refreshIndex]);

  useEffect(() => {
    if (!runId) return;
    let live = true;
    let cursor = 0;
    let failures = 0;
    const abort = new AbortController();
    let stream: EventSource | null = null;
    setConnection("resync");
    const receive = (raw: MessageEvent<string>) => {
      if (!live || typeof raw.data !== "string") return;
      let value: unknown;
      try { value = JSON.parse(raw.data); } catch { setError("invalid_event"); return; }
      if (!isLabEvent(value) || value.run_id !== runId) { setError("invalid_event"); return; }
      if (value.seq <= cursor) return;
      if (value.seq > cursor + 1) {
        setError("resync_required"); setConnection("disconnected"); stream?.close(); return;
      }
      cursor = Math.max(cursor, value.seq);
      setEvents((before) => mergeEvents(before, [value], runId));
      const status = value.payload.status;
      if ((value.kind === "run" || value.kind === "end") && typeof status === "string") {
        setRun((before) => before?.id === runId ? { ...before, status, last_seq: cursor } : before);
      }
      if (value.kind === "error") {
        const code = value.payload.code ?? value.payload.reason_code;
        setError(typeof code === "string" && /^[a-z0-9_]{1,80}$/.test(code) ? code : "experiment_failed");
      }
      if (value.kind === "end") { stream?.close(); setConnection("connected"); }
    };
    async function connect() {
      try {
        const snapshot = await request<{ run: Run }>("/runs/" + encodeURIComponent(runId!), { signal: abort.signal });
        if (!live) return;
        const replay = await readReplay(runId!, abort.signal, () => live);
        if (!replay) return;
        const all = replay.events;
        cursor = replay.cursor;
        setEvents(all);
        const replayed = replayedRun(snapshot.run, all, cursor);
        setRun((before) => before?.id === runId && replayed.last_seq >= before.last_seq && !(terminal(before.status) && !terminal(replayed.status)) ? replayed : before);
        if (terminal(replayed.status) || all.some((e) => e.kind === "end")) {
          setConnection("connected"); return;
        }
        if (typeof EventSource === "undefined") {
          setError("event_stream_unavailable"); setConnection("disconnected"); return;
        }
        stream = new EventSource(API + "/runs/" + encodeURIComponent(runId!) + "/events/stream?after=" + cursor);
        source.current = stream;
        for (const type of ["run", "turn", "message", "organization", "usage", "game", "error", "end"]) {
          stream.addEventListener(type, receive as EventListener);
        }
        stream.onopen = () => { if (live) { failures = 0; setConnection("connected"); } };
        stream.onerror = () => {
          if (!live) return;
          failures += 1; setConnection("connecting");
          if (failures >= 3 || stream?.readyState === EventSource.CLOSED) {
            stream?.close(); setConnection("disconnected");
          }
        };
      } catch (reason) {
        if (live && !abort.signal.aborted) { setError(failureCode(reason)); setConnection("disconnected"); }
      }
    }
    void connect();
    return () => { live = false; abort.abort(); stream?.close(); if (source.current === stream) source.current = null; };
  }, [runId, revision]);

  const action = useCallback(async (work: () => Promise<void>) => {
    if (busy.current) return;
    busy.current = true; setPending(true); setError("");
    try { await work(); } catch (reason) { setError(failureCode(reason)); }
    finally { busy.current = false; setPending(false); }
  }, []);

  const start = useCallback((input: Record<string, Json>) => action(async () => {
    const body = JSON.stringify(input);
    if (idempotency.current?.body !== body) idempotency.current = { body, key: crypto.randomUUID() };
    setStarting(true);
    try {
    const result = await request<{ run: Run }>("/runs", {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotency.current.key }, body,
    });
    idempotency.current = null;
    select(result.run); setRuns((before) => [result.run, ...before.filter((r) => r.id !== result.run.id)]);
    if (cancelQueued.current) {
      const stopped = await request<{ run: Run }>("/runs/" + encodeURIComponent(result.run.id) + "/cancel", { method: "POST" });
      setRun((before) => before?.id === result.run.id && !terminal(before.status) ? stopped.run : before);
      cancelQueued.current = false; setStopQueued(false);
    }
    } finally { setStarting(false); }
  }), [action, select]);

  const stop = useCallback(async () => {
    try {
    let target = runId;
    if (starting) {
      target = null;
      cancelQueued.current = true; setStopQueued(true);
      const current = await request<{ runs: Run[] }>("/runs?limit=100");
      target = current.runs.find((item) => !terminal(item.status))?.id ?? null;
    }
    if (!target) return;
    const result = await request<{ run: Run }>("/runs/" + encodeURIComponent(target) + "/cancel", { method: "POST" });
    setRun((before) => before?.id === target && !terminal(before.status) ? result.run : before);
    } catch (reason) { setError(failureCode(reason)); }
  }, [runId, starting]);
  const remove = useCallback(() => action(async () => {
    if (!runId) return;
    await request<void>("/runs/" + encodeURIComponent(runId), { method: "DELETE" });
    setRuns((before) => before.filter((r) => r.id !== runId));
    setRun((before) => before?.id === runId ? null : before);
    setEvents((before) => before.filter((event) => event.run_id !== runId));
    try { if (localStorage.getItem("cooperation-lab.run") === runId) localStorage.removeItem("cooperation-lab.run"); } catch { /* Optional UI persistence. */ }
  }), [action, runId]);
  const exportRun = useCallback(() => action(async () => {
    if (!runId) return;
    const data = await request<Json>("/runs/" + encodeURIComponent(runId) + "/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "cooperation-" + runId + ".json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }), [action, runId]);
  return {
    capabilities, runs, run, events, connection, error, pending, starting, stopQueued,
    active: !!run && !terminal(run.status), start, stop, remove, exportRun, select,
    refresh: () => setRefreshIndex((v) => v + 1),
    reconnect: () => setRevision((v) => v + 1),
  };
}
