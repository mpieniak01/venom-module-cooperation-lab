"use client";
import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { messageKindLabel, modeLabel, scenarioLabel, statusLabel, texts } from "./lib/i18n";
import { modelId, terminal, type Json, type LabEvent } from "./lib/protocol";
import { useLab } from "./lib/use-lab";
import { scenarioPolicy, selectScenario, selectMode } from "./lib/experiment-settings";
import { computationLabel, noticePresentation } from "./lib/presentation";
import { savedSettings, useWorkspaceViewport, workspaceStyles, type SavedSettings } from "./lib/workspace";

import { Conversation } from "./lib/chat";
import { OperatorComposer } from "./lib/operator-composer";
import { GameBoard } from "./lib/game-board";
import { engineId, modelState } from "./lib/model-selection";

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
    const restored = lab.run ? savedSettings(lab.run.config) : {};
    const qualification = lab.run?.config.scenario_id==="model_qualification";
    setForm({ ...form, ...(qualification ? {model:restored.model??form.model} : lab.run ? { communicationLanguage:"en" as const, ...restored } : {}), runId });
  }
  const { model:selectedModel, scenario, mode, turns, tokens, seed, communicationLanguage } = form;
  const [engineFilter, setEngineFilter] = useState<{runId:string|null; engine:string}|null>(null);
  const models = lab.capabilities?.models ?? [];
  const fallback = selectedModel || modelId(models.find((m) => m.qualified) ?? models[0] ?? {});
  const stored = lab.run?.config.model;
  const storedProvider = stored && typeof stored==="object" && !Array.isArray(stored) && typeof stored.provider==="string" ? stored.provider : undefined;
  const selectedEngine = engineFilter?.runId===runId ? engineFilter.engine : engineId(models.find(m=>modelId(m)===fallback) ?? {provider:storedProvider});
  const engineModels = models.filter(m=>engineId(m)===selectedEngine);
  const missingSavedModel = !!selectedModel&&!models.some(m=>modelId(m)===selectedModel)&&engineFilter?.runId!==runId;
  const chosen = missingSavedModel?selectedModel:engineModels.some(m=>modelId(m)===fallback)?fallback:modelId(engineModels[0]??{});
  const selected = models.find(m=>modelId(m)===chosen);
  const engines = lab.capabilities?.engines ?? [...new Set(models.map(engineId))].map(engine_id=>({engine_id,name:engine_id,status:"unknown",supported:true}));
  const qualifying = lab.run?.config.scenario_id==="model_qualification";
  const policy = scenarioPolicy(scenario);
  const availableModes = (lab.capabilities?.modes ?? []).filter(item=>policy?.modes.includes(item));
  const validSettings = !!policy&&availableModes.includes(mode)&&Number.isInteger(turns)&&turns>=policy.min&&turns<=policy.max&&turns%policy.step===0;
  const canStart = validSettings&&lab.capabilities?.ready && models.some((m) => modelId(m) === chosen && (m.can_run??m.qualified));
  const messageEvents = lab.events.filter((event) => event.kind === "message");
  const lastFailure = lab.events.findLast(event=>event.kind==="error");
  const persistedError=typeof lastFailure?.payload.code==="string"?lastFailure.payload.code:"";
  const { code:noticeCode, text:notice } = noticePresentation(t, lab.capabilities, lab.error||persistedError);
  const blocked = !validSettings?t.problemSettings:!canStart && selected ? modelState(selected,t) : "";
  const resultScenario = lab.run?.config.scenario_id??scenario;
  const resultMode = lab.run?.config.mode??mode;
  const organizations = lab.events.filter((event) => event.kind === "organization");
  const isGame = !qualifying && resultScenario === "tic_tac_toe";
  const gameEvent = lab.events.findLast(event => event.kind === "game");
  const isReview = resultMode === "operator_review";
  const operatorChat = !qualifying && (resultMode === "operator_chat" || resultMode === "operator_relay" || isReview);
  const operatorEvent = lab.events.findLast(event=>event.kind==="operator"||event.kind==="message"&&event.payload.sender==="operator");
  const operatorWaiting = operatorEvent?.kind==="operator"&&operatorEvent.payload.waiting===true;
  const computation = computationLabel(t, lab.capabilities, lab.run, lab.stopQueued, operatorWaiting);
  const usage = lab.events.findLast((event) => event.kind === "usage");
  const start = () => {
    const input: Record<string, Json> = { model_id: chosen, scenario_id: scenario, mode, seed, max_turns: turns, max_new_tokens: tokens, communication_language:communicationLanguage };
     setSettings(false); void lab.start(input);
  };
  return <section aria-labelledby="cooperation-lab-title" className="coop-workspace" data-operator={operatorChat} ref={viewport}>
    <style>{workspaceStyles}</style>
    <header className="coop-header">
      <div><h1 id="cooperation-lab-title" className="text-xl font-semibold">{t.title}</h1><p className="text-xs text-slate-400">{t.description}</p></div>
      <button type="button" className={button} onClick={lab.refresh} disabled={lab.refreshing}>{lab.refreshing?t.refreshing:t.refresh}</button>
    </header>
    <fieldset className="coop-controls" aria-label={t.title}>
      <button type="button" className={button + " coop-start"} disabled={!canStart || lab.active || lab.pending} onClick={start}>{t.start}</button>
      <button type="button" className={button + " coop-stop"} disabled={!lab.active && !lab.starting} onClick={() => { void lab.stop(); }}>{t.stop}</button>
      <button type="button" className={button} aria-expanded={settings} onClick={() => setSettings((v) => !v)}>{t.settings}</button>
      {!lab.active && lab.run && <button type="button" className={button} onClick={() => {
        const next=models.find(m=>modelId(m)===chosen&&(m.can_run??m.qualified))??models.find(m=>m.can_run??m.qualified);
        setForm({...form,model:next?modelId(next):chosen,runId:null});
        setEngineFilter(null);setSettings(true);lab.select(null);
      }}>{t.newRun}</button>}
      <div className="coop-run-state" aria-live="polite">
        <span>{t.runStatus}: <strong>{computation}</strong></span>
        <span className="ml-3">{t.connection}: {statusLabel(t, lab.connection)}</span>
      </div>
      {lab.connection === "disconnected" && lab.run && <button type="button" className={button} onClick={lab.reconnect}>{t.reconnect}</button>}
    </fieldset>
    <output aria-live="polite" className="coop-notice h-5" title={notice || undefined}>
      {lab.capabilities?.catalog_error?t.catalogError:notice || (!lab.active?blocked:"") || (lab.active&&operatorWaiting ? t.operatorInputHint : "")}
    </output>
    <div className="coop-body">
      {settings && <fieldset disabled={lab.active || lab.pending} className="coop-settings">
        <legend className="px-1 text-sm">{t.settings}</legend>
        <div className="coop-settings-group">
          <h3>{t.setupTask}</h3>
          <label className="coop-setting">{t.scenario}
            <select className={field} value={scenario} onChange={event=>setForm(selectScenario(form,event.target.value))}>
              {(lab.capabilities?.scenarios ?? []).map(item=><option value={item.scenario_id} key={item.scenario_id}>{scenarioLabel(t,item.scenario_id,item.title)}</option>)}
            </select>
          </label>
          <label className="coop-setting">{t.mode}
            <select className={field} value={mode} disabled={availableModes.length===1} onChange={event=>setForm(selectMode(form,event.target.value))}>
              {availableModes.map(item=><option value={item} key={item}>{scenario==="tic_tac_toe"?(item==="game_competitive"?t.gameCompetitive:t.gameAlternating):modeLabel(t,item)}</option>)}
            </select>
          </label>
          {availableModes.length===1&&<p className="coop-message-meta">{t.fixedWorkflow}</p>}
          <p className="coop-settings-hint">{policy?.entry==="operator"?t.startsWithInput:t.startsAutomatic}</p>
        </div>
        <div className="coop-settings-group">
          <h3>{t.setupRuntime}</h3>
          <label className="coop-setting">{t.engine}
            <select className={field} value={selectedEngine} onChange={event=>{setEngineFilter({runId,engine:event.target.value});setForm({...form,model:modelId(models.find(m=>engineId(m)===event.target.value)??{})});}}>
              {engines.map(engine=><option key={engine.engine_id} value={engine.engine_id}>{engine.name}</option>)}
            </select>
          </label>
          <label className="coop-setting">{t.model}
            <select className={field} value={chosen} onChange={event=>setForm({...form,model:event.target.value})}>
              {missingSavedModel&&<option value={chosen}>{chosen} — {t.modelOffline}</option>}
              {!engineModels.length&&!missingSavedModel&&<option value="">{t.modelOffline}</option>}
              {engineModels.map(model=><option value={modelId(model)} key={modelId(model)}>{model.display_name??modelId(model)} — {modelState(model,t)}</option>)}
            </select>
          </label>
          {selected&&<p className="coop-message-meta" role="status">{modelState(selected,t)}</p>}
          {selected?.can_qualify&&<><button type="button" className={button} onClick={()=>{setSettings(true);void lab.qualify(chosen);}}>{t.qualify}</button><p className="coop-message-meta">{t.qualificationHint}</p></>}
          <label className="coop-setting">{t.communicationLanguage}
            <select className={field} value={communicationLanguage} onChange={event=>setForm({...form,communicationLanguage:event.target.value==="pl"?"pl":"en"})}>
              <option value="pl">{t.polish}</option><option value="en">{t.english}</option>
            </select>
          </label>
          <p className="coop-message-meta">{t.sameWeights}</p>
        </div>
        <div className="coop-settings-group">
          <h3>{t.setupLimits}</h3>
          <label className="coop-setting">{t.turns}<input className={field} type="number" min={policy?.min??1} step={policy?.step??1} max={policy?.max??8} value={turns} onChange={event=>setForm({...form,turns:Number(event.target.value)})}/></label>
          {policy&&<p className="coop-message-meta">{operatorChat?t.roundsCount+": "+Math.floor(turns/policy.step):isGame?t.gameMoves+": "+turns:""}</p>}
          <label className="coop-setting">{t.tokens}<input className={field} type="number" min={1} max={256} value={tokens} onChange={event=>setForm({...form,tokens:Number(event.target.value)})}/></label>
          <label className="coop-setting">{t.seed}<input className={field} type="number" min={0} max={2147483647} value={seed} onChange={event=>setForm({...form,seed:Number(event.target.value)})}/></label>
        </div>
      </fieldset>}
      <div className="coop-history">
        <label className="coop-history-picker">{t.history}
          <select className={field + " coop-history-select"} disabled={lab.active || lab.starting || lab.pending} value={lab.run?.id ?? ""} onChange={(event) => { const found = lab.runs.find((r) => r.id === event.target.value); if (found) { lab.select(found); } }}>
            <option value="">{t.select}</option>
            {lab.runs.map((r) => <option key={r.id} value={r.id}>{new Date(r.created * 1000).toLocaleString(language)} · {statusLabel(t, r.id === lab.run?.id ? lab.run.status : r.status)}</option>)}
          </select>
        </label>
        {lab.run && <><button type="button" className={button} disabled={lab.pending} onClick={() => { void lab.exportRun(); }}>{t.export}</button>
          <button type="button" className={button} disabled={lab.active || lab.pending} onClick={() => { void lab.remove(); }}>{t.remove}</button></>}
      </div>
      <div className="coop-main">
        <div className="coop-column">
          <fieldset className="coop-participants" aria-label={t.participants}>
            {(operatorChat ? ["A", "B", "operator"] : ["A", "B"]).map((participant) => {
              const last = messageEvents.findLast((event) => value(event, "sender") === participant);
              return <div key={participant} className="coop-panel">
                <strong className="text-lg">{participant === "operator" ? t.operator : participant}</strong><span className="ml-2 text-xs text-slate-400">{participant === "operator" ? "" : t.local}</span>
                <p className="mt-1 truncate text-xs">{last ? messageKindLabel(t, value(last, "kind")) : t.waiting}</p>
              </div>;
            })}
          </fieldset>
          {isGame && <GameBoard event={gameEvent} ended={!!lab.run && terminal(lab.run.status)} language={language} />}
          <section className="coop-panel coop-dialog" aria-label={t.dialog}>
            <h2 className="mb-2 font-semibold">{qualifying?t.qualification:t.dialog}</h2>
            {!messageEvents.length && <p className="text-sm text-slate-400">{lab.run ? t.noMessages : t.noRuns}</p>}
            <Conversation events={messageEvents} language={language} />
            {operatorChat ? <OperatorComposer key={runId ?? "draft"} runId={runId} active={lab.active} waiting={operatorWaiting&&lab.connection==="connected"} sending={lab.sending} relay={resultMode==="operator_relay"} review={isReview} language={language} onSend={lab.sendMessage} /> : <p className="coop-message-meta">{t.operatorSetup}</p>}
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
