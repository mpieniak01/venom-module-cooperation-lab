"use client";
import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { diagnosticCode, modeLabel, reasonLabel, statusLabel, texts } from "./lib/i18n";
import { modelId, type Json, type LabEvent } from "./lib/protocol";
import { useLab } from "./lib/use-lab";

const button = "rounded-lg border border-white/20 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40";
const field = "min-w-0 rounded-lg border border-white/20 bg-slate-950 p-2";
function value(event: LabEvent, key: string) {
  const item = event.payload[key];
  return typeof item === "string" || typeof item === "number" ? String(item) : "";
}
export default function CooperationLabPage() {
  const { language } = useLanguage();
  const t = texts(language);
  const lab = useLab();
  const [settings, setSettings] = useState(true);
  const [selectedModel, setSelectedModel] = useState("");
  const [scenario, setScenario] = useState("split_facts");
  const [mode, setMode] = useState("dialog_encouraged");
  const [turns, setTurns] = useState(8);
  const [tokens, setTokens] = useState(128);
  const [seed, setSeed] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const models = lab.capabilities?.models ?? [];
  const chosen = selectedModel || modelId(models.find((m) => m.qualified) ?? models[0] ?? {});
  const canStart = lab.capabilities?.ready && models.some((m) => modelId(m) === chosen && m.qualified);
  const messageEvents = lab.events.filter((event) => event.kind === "message");
  const reason = lab.error || (lab.capabilities && !lab.capabilities.ready ? lab.capabilities.reason_code ?? "request_failed" : undefined);
  const noticeCode = diagnosticCode(reason);
  const notice = reason ? reasonLabel(t, reason) : !lab.capabilities ? t.loading : "";
  const organizations = lab.events.filter((event) => event.kind === "organization");
  const usage = lab.events.filter((event) => event.kind === "usage").at(-1);
  const start = () => {
    const input: Record<string, Json> = { model_id: chosen, scenario_id: scenario, mode, seed, max_turns: turns, max_new_tokens: tokens };
    setConfirmDelete(null); setSettings(false); void lab.start(input);
  };
  return <section aria-labelledby="cooperation-lab-title" className="mx-auto flex h-[calc(100dvh-12rem)] min-h-[30rem] max-w-7xl flex-col gap-3 p-3">
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-2">
      <div><h1 id="cooperation-lab-title" className="text-xl font-semibold">{t.title}</h1><p className="text-xs text-slate-400">{t.description}</p></div>
      <button type="button" className={button} onClick={lab.refresh} disabled={lab.pending}>{t.refresh}</button>
    </header>
    <div className="sticky top-0 z-10 flex shrink-0 flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-slate-950/95 p-3" role="group" aria-label={t.title}>
      <button type="button" className={button + " border-emerald-400 bg-emerald-800"} disabled={!canStart || lab.active || lab.pending} onClick={start}>{t.start}</button>
      <button type="button" className={button + " border-rose-400 bg-rose-800"} disabled={!lab.active && !lab.starting} onClick={() => { void lab.stop(); }}>{t.stop}</button>
      <button type="button" className={button} aria-expanded={settings} onClick={() => setSettings((v) => !v)}>{t.settings}</button>
      {!lab.active && lab.run && <button type="button" className={button} onClick={() => { setConfirmDelete(null); lab.select(null); }}>{t.newRun}</button>}
      <div className="ml-auto text-xs" aria-live="polite">
        <span>{t.runStatus}: <strong>{lab.stopQueued ? t.cancelPending : lab.run ? statusLabel(t, lab.run.status) : lab.capabilities?.ready ? t.ready : t.notReady}</strong></span>
        <span className="ml-3">{t.connection}: {statusLabel(t, lab.connection)}</span>
      </div>
      {lab.connection === "disconnected" && lab.run && <button type="button" className={button} onClick={lab.reconnect}>{t.reconnect}</button>}
    </div>
    <div role="status" className="h-5 shrink-0 truncate text-xs text-amber-300" title={notice || undefined}>
      {notice}
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto">
      {settings && <fieldset disabled={lab.active || lab.pending} className="mb-3 grid grid-cols-2 gap-3 rounded-xl border border-white/10 p-3 lg:grid-cols-6">
        <legend className="px-1 text-sm">{t.settings}</legend>
        <label className="flex min-w-0 flex-col gap-1 text-xs lg:col-span-2">{t.model}
          <select className={field} value={chosen} onChange={(event) => setSelectedModel(event.target.value)}>
            {models.map((model) => <option value={modelId(model)} key={modelId(model)} disabled={!model.qualified}>{modelId(model)}{model.qualified ? "" : " — " + t.notReady}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs lg:col-span-2">{t.scenario}
          <select className={field} value={scenario} onChange={(event) => setScenario(event.target.value)}>
            {(lab.capabilities?.scenarios ?? []).map((item) => <option value={item.scenario_id} key={item.scenario_id}>{item.title ?? item.scenario_id}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs lg:col-span-2">{t.mode}
          <select className={field} value={mode} onChange={(event) => setMode(event.target.value)}>
            {(lab.capabilities?.modes ?? []).map((item) => <option value={item} key={item}>{modeLabel(t, item)}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs">{t.turns}<input className={field} type="number" min={1} max={8} value={turns} onChange={(event) => setTurns(Number(event.target.value))} /></label>
        <label className="flex flex-col gap-1 text-xs">{t.tokens}<input className={field} type="number" min={1} max={256} value={tokens} onChange={(event) => setTokens(Number(event.target.value))} /></label>
        <label className="flex flex-col gap-1 text-xs">{t.seed}<input className={field} type="number" min={0} max={2147483647} value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
      </fieldset>}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 items-center gap-2 text-xs">{t.history}
          <select className={field + " max-w-72"} disabled={lab.active || lab.starting || lab.pending} value={lab.run?.id ?? ""} onChange={(event) => { const found = lab.runs.find((r) => r.id === event.target.value); if (found) { setConfirmDelete(null); lab.select(found); } }}>
            <option value="">{t.select}</option>
            {lab.runs.map((r) => <option key={r.id} value={r.id}>{new Date(r.created * 1000).toLocaleString(language)} · {statusLabel(t, r.id === lab.run?.id ? lab.run.status : r.status)}</option>)}
          </select>
        </label>
        {lab.run && <><button type="button" className={button} disabled={lab.pending} onClick={() => { void lab.exportRun(); }}>{t.export}</button>
          <button type="button" className={button} disabled={lab.active || lab.pending} onClick={() => setConfirmDelete((v) => v === lab.run?.id ? null : lab.run?.id ?? null)}>{t.remove}</button></>}
        {confirmDelete === lab.run?.id && lab.run && <span className="flex gap-2"><button type="button" className={button + " bg-rose-900"} disabled={lab.active || lab.pending} onClick={() => { setConfirmDelete(null); void lab.remove(); }}>{t.confirmRemove}</button><button type="button" className={button} onClick={() => setConfirmDelete(null)}>{t.cancel}</button></span>}
      </div>
      <div className="grid min-h-64 gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 space-y-3">
          <div className="grid grid-cols-2 gap-3" role="group" aria-label={t.participants}>
            {["A", "B"].map((participant) => {
              const last = messageEvents.filter((event) => value(event, "sender") === participant).at(-1);
              return <div key={participant} className="rounded-xl border border-white/10 p-3">
                <strong className="text-lg">{participant}</strong><span className="ml-2 text-xs text-slate-400">{t.local}</span>
                <p className="mt-1 truncate text-xs">{last ? value(last, "kind") : t.waiting}</p>
              </div>;
            })}
          </div>
          <section className="rounded-xl border border-white/10 p-3" aria-label={t.dialog}>
            <h2 className="mb-2 font-semibold">{t.dialog}</h2>
            {!messageEvents.length && <p className="text-sm text-slate-400">{lab.run ? t.noMessages : t.noRuns}</p>}
            <ol className="space-y-3">
              {messageEvents.map((event) => <li key={event.seq} className="rounded-lg bg-slate-900 p-3">
                <div className="mb-1 text-xs text-slate-400">#{event.seq} · {value(event, "sender")} → {value(event, "recipient")} · {value(event, "kind")}</div>
                <p className="whitespace-pre-wrap break-words text-sm">{value(event, "content")}</p>
                {value(event, "in_reply_to") && <p className="mt-1 break-all text-xs text-slate-500">↳ {value(event, "in_reply_to")}</p>}
                {value(event, "kind") === "complete" && <p className="mt-1 text-xs text-amber-300">{t.claimedComplete}</p>}
              </li>)}
            </ol>
          </section>
        </div>
        <aside className="min-w-0 space-y-3">
          <section className="rounded-xl border border-white/10 p-3" aria-label={t.organization}>
            <h2 className="mb-2 font-semibold">{t.organization}</h2>
            {!organizations.length && <p className="text-sm text-slate-400">{t.noProposals}</p>}
            {organizations.map((event) => <p key={event.seq} className="mb-2 whitespace-pre-wrap break-words text-sm"><strong>{value(event, "sender")}</strong> · {value(event, "content")}</p>)}
          </section>
          <section className="rounded-xl border border-white/10 p-3" aria-label={t.usage}><h2 className="font-semibold">{t.usage}</h2>
            <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
              <dt>{t.input}</dt><dd>{usage ? value(usage, "input_tokens") || t.unknown : t.unknown}</dd>
              <dt>{t.output}</dt><dd>{usage ? value(usage, "output_tokens") || t.unknown : t.unknown}</dd>
              <dt>{t.charged}</dt><dd>{usage ? value(usage, "charged_input_tokens") + " / " + value(usage, "charged_output_tokens") : t.unknown}</dd>
            </dl>
          </section>
          <p className="text-xs text-slate-400">{t.shared}</p>
          <details className="rounded-xl border border-white/10 p-3"><summary className="cursor-pointer text-sm">{t.details}</summary>
            {noticeCode && <p className="mt-2 text-xs">{t.diagnosticCode}: <code>{noticeCode}</code></p>}
            <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(lab.run?.config ?? {}, null, 2)}</pre>
          </details>
        </aside>
      </div>
    </div>
  </section>;
}
