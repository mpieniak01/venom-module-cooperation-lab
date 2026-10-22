"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { failureCode, request } from "./api";
import { evaluationActive, isEvaluationCapabilities, isEvaluationPreflight, isEvaluationSnapshot, type EvaluationCapabilities, type EvaluationPreflight, type EvaluationRequest, type EvaluationSnapshot } from "./evaluation-protocol";

const invalid = () => new Error("invalid_response");
const code = (error: unknown) => error instanceof Error && error.message === "invalid_response" ? "invalid_response" : failureCode(error);
export function useEvaluations() {
  const [capabilities, setCapabilities] = useState<EvaluationCapabilities | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationSnapshot[]>([]);
  const [selected, setSelected] = useState<EvaluationSnapshot | null>(null);
  const [checked, setChecked] = useState<{ key: string; value: EvaluationPreflight } | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const locked = useRef(false);
  const alive = useRef(true);
  const selectedId = useRef<string | null>(null);
  const selectionEpoch = useRef(0);
  const mutationKey = useRef({input:"", id:""});
  const rootAbort = useRef(new AbortController());
  useEffect(() => {
    alive.current = true;
    rootAbort.current = new AbortController();
    return () => { alive.current = false; rootAbort.current.abort(); };
  }, []);
  const get = useCallback(<T,>(path: string, init?: RequestInit) => request<T>(path, { ...init, signal: rootAbort.current.signal }), []);
  const update = useCallback((snapshot: EvaluationSnapshot) => {
    if (!alive.current) return;
    setSelected(snapshot);
    setEvaluations(previous => [snapshot, ...previous.filter(item => item.id !== snapshot.id)]);
  }, []);
  const refresh = useCallback(async () => {
    setRefreshing(true);
    const epoch = selectionEpoch.current;
    try {
      const [caps, listing] = await Promise.all([get<unknown>("/evaluations/capabilities"), get<{evaluations:unknown[]}>("/evaluations")]);
      if (!isEvaluationCapabilities(caps) || !listing || !Array.isArray(listing.evaluations) || !listing.evaluations.every(isEvaluationSnapshot)) throw invalid();
      if (!alive.current) return;
      setCapabilities(caps); setEvaluations(listing.evaluations); setError("");
      const id = selectedId.current;
      if (id) {
        const body = await get<{evaluation:unknown}>(`/evaluations/${encodeURIComponent(id)}`);
        if (!isEvaluationSnapshot(body?.evaluation)) throw invalid();
        if (selectionEpoch.current === epoch) update(body.evaluation);
      }
    } catch (error) { if (alive.current) setError(code(error)); }
    finally { if (alive.current) setRefreshing(false); }
  }, [get, update]);
  useEffect(() => { void refresh(); }, [refresh]);
  const active = !!selected && evaluationActive(selected.status);
  const pollingId = selected?.id;
  useEffect(() => {
    if (!pollingId || !active) return;
    const id = pollingId;
    let disposed = false;
    let timeout: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const body = await get<{evaluation:unknown}>(`/evaluations/${encodeURIComponent(id)}`);
        // A terminal snapshot confirms cleanup. Read readiness after it so an
        // earlier busy response cannot strand START once polling stops.
        const caps = await get<unknown>("/evaluations/capabilities");
        if (!isEvaluationSnapshot(body?.evaluation) || !isEvaluationCapabilities(caps)) throw invalid();
        if (!disposed && alive.current && selectedId.current === id) {
          update(body.evaluation); setCapabilities(caps); setError("");
        }
      } catch (error) { if (!disposed && alive.current) setError(code(error)); }
      finally { if (!disposed) timeout = setTimeout(() => { void poll(); }, 2000); }
    };
    timeout = setTimeout(() => { void poll(); }, 2000);
    return () => { disposed = true; clearTimeout(timeout); };
  }, [pollingId, active, get, update]);
  const check = useCallback(async (input: EvaluationRequest) => {
    if (locked.current) return;
    locked.current = true; setPending(true); setChecked(null); setError("");
    try {
      const body = await get<unknown>("/evaluations/preflight", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(input)});
      if (!isEvaluationPreflight(body)) throw invalid();
      if (alive.current) setChecked({key:JSON.stringify(input), value:body});
    } catch (error) { if (alive.current) setError(code(error)); }
    finally { locked.current = false; if (alive.current) setPending(false); }
  }, [get]);
  const start = useCallback(async (input: EvaluationRequest) => {
    const key = JSON.stringify(input);
    if (locked.current || !checked?.value.supported || checked.key !== key) return;
    locked.current = true; setPending(true); setError("");
    if (mutationKey.current.input !== key) mutationKey.current = {input:key, id:crypto.randomUUID()};
    try {
      const body = await get<{evaluation:unknown}>("/evaluations", {method:"POST", headers:{"Content-Type":"application/json", "Idempotency-Key":mutationKey.current.id}, body:key});
      if (!isEvaluationSnapshot(body?.evaluation)) throw invalid();
      selectedId.current = body.evaluation.id; selectionEpoch.current++;
      update(body.evaluation); setChecked(null); mutationKey.current = {input:"", id:""};
    } catch (error) { if (alive.current) setError(code(error)); }
    finally { locked.current = false; if (alive.current) setPending(false); }
  }, [checked, get, update]);
  const mutate = useCallback(async (action: "cancel" | "resume") => {
    if (!selectedId.current || locked.current) return;
    locked.current = true; setPending(true); setError("");
    try {
      const body = await get<{evaluation:unknown}>(`/evaluations/${encodeURIComponent(selectedId.current)}/${action}`, {method:"POST"});
      if (!isEvaluationSnapshot(body?.evaluation)) throw invalid();
      update(body.evaluation); setChecked(null);
    } catch (error) { if (alive.current) setError(code(error)); }
    finally { locked.current = false; if (alive.current) setPending(false); }
  }, [get, update]);
  const remove = useCallback(async () => {
    const id = selectedId.current;
    if (!id || locked.current) return;
    locked.current = true; setPending(true); setError("");
    try {
      const body = await get<{deleted:unknown}>(`/evaluations/${encodeURIComponent(id)}`, {method:"DELETE"});
      if (body?.deleted !== true) throw invalid();
      selectedId.current = null; selectionEpoch.current++;
      if (alive.current) {
        setSelected(null); setChecked(null);
        setEvaluations(previous => previous.filter(item=>item.id !== id));
      }
      await refresh();
    } catch (error) { if (alive.current) setError(code(error)); }
    finally { locked.current = false; if (alive.current) setPending(false); }
  }, [get, refresh]);
  const saveBudgets = useCallback(async (model:string,budgets:{max_context_tokens:number;max_new_tokens:number;decision_timeout_s:number}) => {
    if(locked.current)return;
    locked.current=true;setPending(true);setError("");
    try {
      await get("/evaluations/model-settings/"+encodeURIComponent(model),{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(budgets)});
      const caps=await get<unknown>("/evaluations/capabilities");
      if(!isEvaluationCapabilities(caps))throw invalid();
      if(alive.current)setCapabilities(caps);
    } catch(error) {if(alive.current)setError(code(error));}
    finally {locked.current=false;if(alive.current)setPending(false);}
  },[get]);
  const select = useCallback((id: string) => {
    const snapshot = evaluations.find(item => item.id === id) ?? null;
    selectedId.current = snapshot?.id ?? null; selectionEpoch.current++;
    setSelected(snapshot); setChecked(null); setError("");
  }, [evaluations]);
  return { capabilities, evaluations, selected, checked, error, pending, refreshing, active, refresh, check, start, mutate, select, remove, saveBudgets };
}
