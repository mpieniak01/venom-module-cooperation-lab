"use client";
import { useState, type ReactNode } from "react";
import { API } from "./api";
import { diagnosticCode, reasonLabel, texts } from "./i18n";
import { modelId, type Json } from "./protocol";
import { workspaceStyles, useWorkspaceViewport } from "./workspace";
import { evaluationDefaults, savedEvaluationRequest, validEvaluationRequest, type EvaluationRequest, type EvaluationSnapshot } from "./evaluation-protocol";
import { evaluationTexts, evaluationLabel, gameLabel, type EvaluationTexts } from "./evaluation-i18n";
import { useEvaluations } from "./evaluation-use";

const button = "coop-button";
const field = "coop-field";
const styles = `
.coop-evaluation .evaluation-tabs, .coop-evaluation .evaluation-counts { display:flex; flex-wrap:wrap; gap:8px 16px; font-size:12px; }
.coop-evaluation .evaluation-plan { min-height:74px; padding:8px 0; font-size:12px; }
.coop-evaluation .evaluation-reasons { margin:4px 0; padding-left:18px; color:#fcd34d; }
.coop-evaluation .evaluation-case-list { display:flex; flex-direction:column; gap:8px; max-height:16rem; overflow-y:auto; border:1px solid #ffffff22; border-radius:8px; padding:10px; font-size:12px; }
.coop-evaluation .evaluation-case-list input { margin-right:6px; }
.coop-evaluation .evaluation-table-scroll { overflow:auto; max-width:100%; }
.coop-evaluation table { border-collapse:collapse; width:100%; font-size:12px; }
.coop-evaluation th, .coop-evaluation td { text-align:left; padding:8px; border-bottom:1px solid #ffffff22; vertical-align:top; }
.coop-evaluation th { color:#94a3b8; font-weight:500; white-space:nowrap; }
.coop-evaluation .evaluation-report { display:flex; flex-direction:column; gap:12px; }
.coop-evaluation .evaluation-report summary { cursor:pointer; font-size:13px; }
.coop-evaluation .evaluation-report pre { max-height:18rem; overflow:auto; overflow-wrap:anywhere; white-space:pre-wrap; font-size:12px; }
.coop-evaluation .evaluation-details { max-height:34rem; overflow:auto; }
.coop-evaluation .evaluation-history { max-width:24rem; }
.coop-evaluation .coop-controls a { text-decoration:none; }
`;
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="coop-setting">{label}{children}</label>;
}
function safeValue(value: Json | undefined, missing: string): string {
  if (value === null || value === undefined) return missing;
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? String(Number(value.toFixed(3))) : missing;
  return String(value);
}
function reasonText(t: EvaluationTexts, language: string, reason: string) {
  return Object.hasOwn(t, reason) ? evaluationLabel(t, reason) : reasonLabel(texts(language), reason);
}
function counters(snapshot: EvaluationSnapshot | null) {
  return snapshot?.progress ?? {planned:0, started:0, terminal:0, success:0, skipped:0};
}
function EvaluationReport({snapshot, language}: {snapshot: EvaluationSnapshot; language: string}) {
  const t = evaluationTexts(language);
  const byGame = Array.isArray(snapshot.summary.by_game) ? snapshot.summary.by_game.filter((item): item is Record<string, Json> => !!item && typeof item === "object" && !Array.isArray(item)) : [];
  const columns = ["episodes", "successes", "wins", "draws", "losses", "model_errors", "infrastructure_errors", "median_decision_s", "p95_decision_s", "input_tokens", "output_tokens", "peak_vram_bytes"];
  const headings = [t.planned, t.success, t.wins, t.draws, t.losses, t.modelErrors, t.infrastructureErrors, t.median, t.p95, t.inputTokens, t.outputTokens, t.peakVram];
  return <div className="evaluation-report">
    <section className="coop-panel" aria-label={t.results}>
      <h2>{t.results}</h2><p className="coop-message-meta">{t.resultHelp}</p>
      {byGame.length ? <div className="evaluation-table-scroll"><table><thead><tr><th>{t.game}</th>{headings.map(heading=><th key={heading}>{heading}</th>)}</tr></thead>
        <tbody>{byGame.map((row, index)=><tr key={String(row.game)+index}><th scope="row">{gameLabel(t, String(row.game))}</th>{columns.map(key=><td key={key}>{safeValue(row[key], t.noData)}</td>)}</tr>)}</tbody>
      </table></div> : <p>{t.noData}</p>}
      {byGame.map((row,index)=>{
        const metrics = row.metrics && typeof row.metrics === "object" && !Array.isArray(row.metrics) ? row.metrics : {};
        const keys = ["missed_win","missed_block","missed_fork","worse_move","lost_winning_position","missed_known_pair","introduced_deadlock","optimal_step"];
        return <details key={String(row.game)+index}><summary>{t.strategy} · {gameLabel(t,String(row.game))}</summary><div className="evaluation-table-scroll"><table><thead><tr><th>{t.metric}</th><th>{t.value}</th></tr></thead><tbody>{keys.map(key=><tr key={key}><th scope="row">{evaluationLabel(t,key)}</th><td>{safeValue(metrics[key],t.noData)}</td></tr>)}</tbody></table></div></details>;
      })}
      <details><summary>{t.metrics}</summary><pre>{JSON.stringify(snapshot.summary, null, 2)}</pre></details>
    </section>
    <section className="coop-panel" aria-label={t.episode}>
      <h2>{t.episode}</h2>
      <div className="evaluation-table-scroll"><table><thead><tr><th>{t.cases}</th><th>{t.episode}</th><th>{t.attempt}</th><th>{t.status}</th><th>{t.outcome}</th></tr></thead>
        <tbody>{snapshot.episodes.map((episode,index)=><tr key={`${episode.block_id}-${episode.episode}-${episode.attempt}-${index}`}>
          <td>{episode.case_id}</td><td>{episode.episode}</td><td>{episode.attempt}</td><td>{evaluationLabel(t, episode.status)}</td><td>{episode.reason_code ? <>{reasonText(t, language, episode.reason_code)} <code>{diagnosticCode(episode.reason_code)}</code></> : safeValue(episode.result, t.noData)}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <details className="coop-panel evaluation-details"><summary>{t.journal}</summary>
      {snapshot.episodes.map((episode,index)=><details key={`${episode.block_id}-${index}`}><summary>{episode.case_id} · {t.episode} {episode.episode} · {t.attempt} {episode.attempt}</summary>
        {episode.decisions.map((decision,number)=><details key={number}><summary>#{number+1} · {decision.player} · {t.seconds}: {safeValue(decision.seconds, t.noData)} {decision.error ? evaluationLabel(t, decision.error) : ""}</summary>
          <strong>{t.observationLabel}</strong><pre>{safeValue(decision.observation, t.noData)}</pre>
          <strong>{t.response}</strong><pre>{safeValue(decision.response, t.noData)}</pre>
          <strong>{t.action}</strong><pre>{safeValue(decision.action, t.noData)}</pre>
          <strong>{t.assessment}</strong><pre>{JSON.stringify({valid:decision.valid, error:decision.error, response_mapping:decision.response_mapping, usage:decision.usage, assessment:decision.assessment}, null, 2)}</pre>
        </details>)}
      </details>)}
    </details>
    <details className="coop-panel"><summary>{t.actual}</summary><pre>{JSON.stringify(snapshot.config, null, 2)}</pre></details>
  </div>;
}
export function EvaluationWorkspace({language}: {language:string}) {
  const t = evaluationTexts(language);
  const lab = useEvaluations();
  const viewport = useWorkspaceViewport();
  const [draft, setDraft] = useState<Partial<EvaluationRequest>>({});
  const [settings, setSettings] = useState(true);
  const models = lab.capabilities?.models ?? [];
  const cases = lab.capabilities?.cases ?? [];
  const input: EvaluationRequest = { ...evaluationDefaults(), ...draft, model_id:draft.model_id ?? modelId(models.find(item=>item.can_run ?? item.qualified) ?? models[0] ?? {}), case_ids:draft.case_ids ?? cases.slice(0,1).map(item=>item.id) };
  const model = models.find(item=>modelId(item) === input.model_id);
  const checked = lab.checked?.key === JSON.stringify(input) ? lab.checked.value : null;
  const editable = !lab.active && !lab.pending;
  const valid = validEvaluationRequest(input);
  const ready = lab.capabilities?.ready === true && !!model && (model.can_run ?? model.qualified) === true;
  const canStart = editable && valid && ready && checked?.supported === true;
  const counts = counters(lab.selected);
  const steps = model?.compute_steps ?? model?.num_steps ?? [];
  const patch = (value: Partial<EvaluationRequest>) => setDraft({...input,...value});
  const number = (key: "repetitions"|"temperature"|"top_p"|"seed"|"max_new_tokens"|"decision_timeout_s", title:string, min:number, max:number, step=1, disabled=false) => <Field label={title}><input className={field} type="number" min={min} max={max} step={step} value={input[key]} disabled={disabled} onInput={event=>patch({[key]:Number(event.currentTarget.value)})}/></Field>;
  const notice = lab.error ? reasonText(t, language, lab.error) : !valid ? t.invalid : !ready ? reasonText(t,language,lab.capabilities?.reason_code ?? "runtime_busy") : checked ? checked.supported ? t.checked : t.unsupported : t.needsCheck;
  return <section ref={viewport} className="coop-workspace coop-evaluation" aria-label={t.title}>
    <style>{workspaceStyles+styles}</style>
    <header className="coop-header"><div><h1>{t.title}</h1><p>{t.subtitle}</p></div><button className={button} disabled={lab.refreshing} onClick={()=>{void lab.refresh();}}>{t.refresh}</button></header>
    <div className="coop-controls" role="group" aria-label={t.title}>
      <button className={button+" coop-start"} disabled={!canStart} onClick={()=>{setSettings(false);void lab.start(input);}}>{t.start}</button>
      <button className={button+" coop-stop"} disabled={!lab.active || lab.pending} onClick={()=>{void lab.mutate("cancel");}}>{t.stop}</button>
      <button className={button} disabled={lab.pending || !lab.selected || lab.active || !(lab.selected.can_resume ?? ["cancelled","interrupted","failed"].includes(lab.selected.status))} onClick={()=>{void lab.mutate("resume");}} title={t.resumeHelp}>{t.resume}</button>
      <button className={button} aria-expanded={settings} onClick={()=>setSettings(value=>!value)}>{t.settings}</button>
      <button className={button+" coop-danger"} disabled={lab.pending || !lab.selected || lab.active} onClick={()=>{void lab.remove();}}>{t.remove}</button>
      {lab.selected && ["json","jsonl","csv"].map(format=><a className={button} key={format} href={`${API}/evaluations/${encodeURIComponent(lab.selected!.id)}/export?format=${format}`} download>{t.export} {format.toUpperCase()}</a>)}
      <span className="coop-run-state">{t.status}: {lab.selected ? evaluationLabel(t, lab.selected.status) : t.draft}</span>
    </div>
    <output className="coop-notice" aria-live="polite" title={notice}>{notice}{lab.error&&<> · <code>{diagnosticCode(lab.error)}</code></>}</output>
    <div className="coop-body">
      {settings && <fieldset className="coop-settings" disabled={!editable}><legend>{t.settings}</legend>
        <div className="coop-settings-group">
          <Field label={t.model}><select className={field} value={input.model_id} onChange={event=>patch({model_id:event.target.value,num_steps:8})}>
            {!models.length&&!input.model_id&&<option value="">{t.unavailable}</option>}
            {input.model_id&&!model&&<option value={input.model_id}>{input.model_id} — {t.unavailable}</option>}
            {models.map(item=><option key={modelId(item)} value={modelId(item)}>{item.display_name ?? modelId(item)}{(item.can_run ?? item.qualified) ? "" : ` — ${t.unavailable}`}</option>)}
          </select></Field>
          <Field label={t.observation}><select className={field} value={input.observation_mode} onChange={event=>patch({observation_mode:event.target.value as EvaluationRequest["observation_mode"]})}>
            <option value="history_replay">{t.history_replay}</option><option value="native_incremental">{t.native_incremental}</option>
          </select></Field>
          <Field label={t.memory}><select className={field} value={input.episode_memory} onChange={event=>patch({episode_memory:event.target.value as EvaluationRequest["episode_memory"]})}><option value="fresh">{t.fresh}</option><option value="carry">{t.carry}</option></select></Field>
          <Field label={t.reflection}><select className={field} value={input.reflection} onChange={event=>patch({reflection:event.target.value as EvaluationRequest["reflection"]})}><option value="off">{t.off}</option><option value="episode_note">{t.episode_note}</option></select></Field>
          <p className="coop-message-meta">{t.memoryHelp}</p>
          <Field label={t.compute}><select className={field} value={input.num_steps} disabled={!steps.length} onChange={event=>patch({num_steps:Number(event.target.value) as EvaluationRequest["num_steps"]})}>{(steps.length?steps:[8]).map(value=><option key={value} value={value}>{steps.length?value:t.noData}</option>)}</select></Field>
          <p className="coop-message-meta">{t.computeHelp}</p>
        </div>
        <div className="coop-settings-group">
          <span className="coop-setting">{t.cases}</span>
          <div className="evaluation-case-list" role="group" aria-label={t.cases}>{cases.map(item=><label key={item.id}>
            <input type="checkbox" checked={input.case_ids.includes(item.id)} onChange={event=>patch({case_ids:event.target.checked?[...input.case_ids,item.id]:input.case_ids.filter(id=>id!==item.id)})}/>
            {gameLabel(t,item.game)} · {item.id}<span className="coop-message-meta"> · {t.casesLimit}: {item.max_actions}</span>
          </label>)}</div>
          {number("repetitions",t.repetitions,1,10)}
          <Field label={t.opponent}><select className={field} value={input.opponent} onChange={event=>patch({opponent:event.target.value as EvaluationRequest["opponent"]})}><option value="optimal">{t.optimal}</option><option value="random">{t.random}</option><option value="remembering">{t.remembering}</option><option value="model">{t.modelOpponent}</option></select></Field>
          <p className="coop-message-meta">{t.soloHelp}</p>
          <label><input type="checkbox" checked={input.swap_sides} onChange={event=>patch({swap_sides:event.target.checked})}/> {t.swap}</label>
          <Field label={t.legal}><select className={field} value={input.legal_moves} onChange={event=>patch({legal_moves:event.target.value as EvaluationRequest["legal_moves"]})}><option value="listed">{t.listed}</option><option value="hidden">{t.hidden}</option></select></Field>
        </div>
        <div className="coop-settings-group">
          <Field label={t.responseMode}><select className={field} value={input.response_mode} onChange={event=>patch({response_mode:event.target.value as EvaluationRequest["response_mode"]})}><option value="mapped">{t.mapped}</option><option value="strict_json">{t.strict_json}</option></select></Field>
          <p className="coop-message-meta">{t.mappingHelp}</p>
          <Field label={t.decoding}><select className={field} value={input.decoding} onChange={event=>patch({decoding:event.target.value as EvaluationRequest["decoding"]})}><option value="greedy">{t.greedy}</option><option value="sampled">{t.sampled}</option></select></Field>
          {number("temperature",t.temperature,0,2,0.1,input.decoding==="greedy")}
          {number("top_p",t.topP,0.01,1,0.01,input.decoding==="greedy")}
          {number("seed",t.seed,0,2147483647)}
          {number("max_new_tokens",t.tokens,8,256)}
          {number("decision_timeout_s",t.timeout,1,90)}
          <p className="coop-message-meta">{t.decoderHelp}</p>
        </div>
      </fieldset>}
      <div className="evaluation-plan" aria-live="polite">
        <button className={button} disabled={!editable || !valid || lab.refreshing} onClick={()=>{void lab.check(input);}}>{t.check}</button>
        {checked&&<><div className="evaluation-counts"><strong>{t.plan}</strong><span>{t.planned}: {checked.planned_episodes}</span><span>{t.blocks}: {checked.planned_blocks}</span><span>{t.decisions}: {checked.planned_decisions}</span></div>
          {!!checked.reason_codes.length&&<ul className="evaluation-reasons">{checked.reason_codes.map(reason=><li key={reason}>{reasonText(t,language,reason)} · <code>{diagnosticCode(reason)}</code></li>)}</ul>}
          <details><summary>{t.actual}</summary><pre>{JSON.stringify(checked.configuration,null,2)}</pre></details>
        </>}
      </div>
      <div className="coop-history"><Field label={t.history}><select className={field+" evaluation-history"} disabled={lab.pending || lab.active} value={lab.selected?.id ?? ""} onChange={event=>{
        const selected = lab.evaluations.find(item=>item.id === event.target.value);
        const restored = selected ? savedEvaluationRequest(selected.config) : null;
        if (restored) setDraft(restored);
        lab.select(event.target.value);
      }}><option value="">{t.draft}</option>{lab.evaluations.map(item=><option key={item.id} value={item.id}>{item.id.slice(0,8)} · {evaluationLabel(t,item.status)}</option>)}</select></Field><span className="coop-message-meta">{t.version}: {lab.capabilities?.manifest_version ?? t.noData}</span>{lab.capabilities?.storage&&<span className="coop-message-meta">{t.stored}: {lab.capabilities.storage.series_used}/{lab.capabilities.storage.max_series} · {t.retention}: {lab.capabilities.storage.retention_days}</span>}</div>
      <div className="coop-panel evaluation-counts" aria-label={t.plan}>
        {(["planned","started","terminal","success","skipped"] as const).map(key=><span key={key}>{t[key]}: <strong data-counter={key}>{counts[key]}</strong></span>)}
      </div>
      {lab.selected ? <EvaluationReport snapshot={lab.selected} language={language}/> : <p className="coop-message-meta">{t.noSeries}</p>}
    </div>
  </section>;
}
