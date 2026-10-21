"use client";
import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { messageKindLabel, modeLabel, scenarioLabel, statusLabel, texts } from "./lib/i18n";
import { modelId, type Json, type LabEvent } from "./lib/protocol";
import { useLab } from "./lib/use-lab";
import { computationLabel, noticePresentation } from "./lib/presentation";
import { savedSettings, useWorkspaceViewport, workspaceStyles, type SavedSettings } from "./lib/workspace";

import { Conversation } from "./lib/chat";

const button = "coop-button";
const field = "coop-field";
function value(event: LabEvent, key: string) {
  const item = event.payload[key];
  return typeof item === "string" || typeof item === "number" ? String(item) : "";
}
export default function CooperationLabPage() {
  const { language } = useLanguage();
  const t = texts(language);
  const lab = useLab();
  const viewport = useWorkspaceViewport();
  const [settings, setSettings] = useState(true);
  const [form, setForm] = useState<SavedSettings & { runId: string | null }>({
    model:"", scenario:"split_facts", mode:"dialog_encouraged", turns:8, tokens:128, seed:0, communicationLanguage:language === "pl" ? "pl" : "en", runId:null,
  });
  const runId = lab.run?.id ?? null;
  // Adjust the draft when selection changes, before committing a render. An
  // effect would briefly display the previous run's model and require a second paint.
  if (form.runId !== runId) {
    setForm({ ...form, ...(lab.run ? { communicationLanguage:"en" as const, ...savedSettings(lab.run.config) } : {}), runId });
  }
  const { model:selectedModel, scenario, mode, turns, tokens, seed, communicationLanguage } = form;
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const models = lab.capabilities?.models ?? [];
  const chosen = selectedModel || modelId(models.find((m) => m.qualified) ?? models[0] ?? {});
  const canStart = lab.capabilities?.ready && models.some((m) => modelId(m) === chosen && m.qualified);
  const messageEvents = lab.events.filter((event) => event.kind === "message");
  const { code:noticeCode, text:notice } = noticePresentation(t, lab.capabilities, lab.error);
  const computation = computationLabel(t, lab.capabilities, lab.run, lab.stopQueued);
  const organizations = lab.events.filter((event) => event.kind === "organization");
  const usage = lab.events.findLast((event) => event.kind === "usage");
  const start = () => {
    const input: Record<string, Json> = { model_id: chosen, scenario_id: scenario, mode, seed, max_turns: turns, max_new_tokens: tokens, communication_language:communicationLanguage };
    setConfirmDelete(null); setSettings(false); void lab.start(input);
  };
  return <section aria-labelledby="cooperation-lab-title" className="coop-workspace" ref={viewport}>
    <style>{workspaceStyles}</style>
    <header className="coop-header">
      <div><h1 id="cooperation-lab-title" className="text-xl font-semibold">{t.title}</h1><p className="text-xs text-slate-400">{t.description}</p></div>
      <button type="button" className={button} onClick={lab.refresh} disabled={lab.pending}>{t.refresh}</button>
    </header>
    <fieldset className="coop-controls" aria-label={t.title}>
      <button type="button" className={button + " coop-start"} disabled={!canStart || lab.active || lab.pending} onClick={start}>{t.start}</button>
      <button type="button" className={button + " coop-stop"} disabled={!lab.active && !lab.starting} onClick={() => { void lab.stop(); }}>{t.stop}</button>
      <button type="button" className={button} aria-expanded={settings} onClick={() => setSettings((v) => !v)}>{t.settings}</button>
      {!lab.active && lab.run && <button type="button" className={button} onClick={() => { setConfirmDelete(null); lab.select(null); }}>{t.newRun}</button>}
      <div className="coop-run-state" aria-live="polite">
        <span>{t.runStatus}: <strong>{computation}</strong></span>
        <span className="ml-3">{t.connection}: {statusLabel(t, lab.connection)}</span>
      </div>
      {lab.connection === "disconnected" && lab.run && <button type="button" className={button} onClick={lab.reconnect}>{t.reconnect}</button>}
    </fieldset>
    <output aria-live="polite" className="coop-notice h-5" title={notice || undefined}>
      {notice}
    </output>
    <div className="coop-body">
      {settings && <fieldset disabled={lab.active || lab.pending} className="coop-settings">
        <legend className="px-1 text-sm">{t.settings}</legend>
        <label className="coop-setting coop-setting-wide">{t.model}
          <select className={field} value={chosen} onChange={(event) => setForm({...form, model:event.target.value})}>
            {chosen && !models.some((model) => modelId(model) === chosen) && <option value={chosen}>{chosen} — {t.notReady}</option>}
            {models.map((model) => <option value={modelId(model)} key={modelId(model)} disabled={!model.qualified}>{modelId(model)}{model.qualified ? "" : " — " + t.notReady}</option>)}
          </select>
        </label>
        <label className="coop-setting coop-setting-wide">{t.scenario}
          <select className={field} value={scenario} onChange={(event) => setForm({...form, scenario:event.target.value})}>
            {(lab.capabilities?.scenarios ?? []).map((item) => <option value={item.scenario_id} key={item.scenario_id}>{scenarioLabel(t, item.scenario_id, item.title)}</option>)}
          </select>
        </label>
        <label className="coop-setting coop-setting-wide">{t.mode}
          <select className={field} value={mode} onChange={(event) => setForm({...form, mode:event.target.value})}>
            {(lab.capabilities?.modes ?? []).map((item) => <option value={item} key={item}>{modeLabel(t, item)}</option>)}
          </select>
        </label>
        <label className="coop-setting coop-setting-wide">{t.communicationLanguage}
          <select className={field} value={communicationLanguage} onChange={(event) => setForm({...form, communicationLanguage:event.target.value === "pl" ? "pl" : "en"})}>
            <option value="pl">{t.polish}</option><option value="en">{t.english}</option>
          </select>
        </label>
        <label className="coop-setting">{t.turns}<input className={field} type="number" min={1} max={8} value={turns} onChange={(event) => setForm({...form, turns:Number(event.target.value)})} /></label>
        <label className="coop-setting">{t.tokens}<input className={field} type="number" min={1} max={256} value={tokens} onChange={(event) => setForm({...form, tokens:Number(event.target.value)})} /></label>
        <label className="coop-setting">{t.seed}<input className={field} type="number" min={0} max={2147483647} value={seed} onChange={(event) => setForm({...form, seed:Number(event.target.value)})} /></label>
      </fieldset>}
      <div className="coop-history">
        <label className="coop-history-picker">{t.history}
          <select className={field + " coop-history-select"} disabled={lab.active || lab.starting || lab.pending} value={lab.run?.id ?? ""} onChange={(event) => { const found = lab.runs.find((r) => r.id === event.target.value); if (found) { setConfirmDelete(null); lab.select(found); } }}>
            <option value="">{t.select}</option>
            {lab.runs.map((r) => <option key={r.id} value={r.id}>{new Date(r.created * 1000).toLocaleString(language)} · {statusLabel(t, r.id === lab.run?.id ? lab.run.status : r.status)}</option>)}
          </select>
        </label>
        {lab.run && <><button type="button" className={button} disabled={lab.pending} onClick={() => { void lab.exportRun(); }}>{t.export}</button>
          <button type="button" className={button} disabled={lab.active || lab.pending} onClick={() => setConfirmDelete((v) => v === lab.run?.id ? null : lab.run?.id ?? null)}>{t.remove}</button></>}
        {confirmDelete === lab.run?.id && lab.run && <span className="coop-confirmation"><button type="button" className={button + " coop-danger"} disabled={lab.active || lab.pending} onClick={() => { setConfirmDelete(null); void lab.remove(); }}>{t.confirmRemove}</button><button type="button" className={button} onClick={() => setConfirmDelete(null)}>{t.cancel}</button></span>}
      </div>
      <div className="coop-main">
        <div className="coop-column">
          <fieldset className="coop-participants" aria-label={t.participants}>
            {["A", "B"].map((participant) => {
              const last = messageEvents.findLast((event) => value(event, "sender") === participant);
              return <div key={participant} className="coop-panel">
                <strong className="text-lg">{participant}</strong><span className="ml-2 text-xs text-slate-400">{t.local}</span>
                <p className="mt-1 truncate text-xs">{last ? messageKindLabel(t, value(last, "kind")) : t.waiting}</p>
              </div>;
            })}
          </fieldset>
          <section className="coop-panel" aria-label={t.dialog}>
            <h2 className="mb-2 font-semibold">{t.dialog}</h2>
            {!messageEvents.length && <p className="text-sm text-slate-400">{lab.run ? t.noMessages : t.noRuns}</p>}
            <Conversation events={messageEvents} language={language} />
          </section>
        </div>
        <aside className="coop-column">
          <section className="coop-panel" aria-label={t.organization}>
            <h2 className="mb-2 font-semibold">{t.organization}</h2>
            {!organizations.length && <p className="text-sm text-slate-400">{t.noProposals}</p>}
            {organizations.map((event) => <p key={event.seq} className="mb-2 whitespace-pre-wrap break-words text-sm"><strong>{value(event, "sender")}</strong> · {value(event, "content")}</p>)}
          </section>
          <section className="coop-panel" aria-label={t.usage}><h2 className="font-semibold">{t.usage}</h2>
            <dl className="coop-usage">
              <dt>{t.input}</dt><dd>{usage ? value(usage, "input_tokens") || t.unknown : t.unknown}</dd>
              <dt>{t.output}</dt><dd>{usage ? value(usage, "output_tokens") || t.unknown : t.unknown}</dd>
              <dt>{t.charged}</dt><dd>{usage ? value(usage, "charged_input_tokens") + " / " + value(usage, "charged_output_tokens") : t.unknown}</dd>
            </dl>
          </section>
          <p className="text-xs text-slate-400">{t.shared}</p>
          <details className="coop-panel"><summary className="cursor-pointer text-sm">{t.details}</summary>
            {noticeCode && <p className="mt-2 text-xs">{t.diagnosticCode}: <code>{noticeCode}</code></p>}
            <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(lab.run?.config ?? {}, null, 2)}</pre>
          </details>
        </aside>
      </div>
    </div>
  </section>;
}
