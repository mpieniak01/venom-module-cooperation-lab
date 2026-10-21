"use client";
import { useLayoutEffect, useRef } from "react";
import type { Json } from "./protocol";

// Static, module-owned styles: external module paths are not necessarily scanned
// by the host Tailwind JIT. Every selector stays inside this workspace.
export const workspaceStyles = `
.coop-workspace { box-sizing:border-box; display:flex; flex-direction:column; gap:12px; width:100%; max-width:1280px; margin:0 auto; padding:12px; height:calc(100dvh - var(--coop-top, 12rem) - 16px); min-height:0; overflow:hidden; color:#e2e8f0; }
.coop-workspace *, .coop-workspace *::before, .coop-workspace *::after { box-sizing:border-box; }
.coop-workspace .coop-header { display:flex; flex-shrink:0; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; }
.coop-workspace h1 { margin:0; font-size:20px; line-height:1.3; font-weight:600; }
.coop-workspace .coop-header p { margin:4px 0 0; font-size:12px; color:#94a3b8; }
.coop-workspace .coop-controls { min-width:0; margin:0; display:flex; flex-shrink:0; flex-wrap:wrap; align-items:center; gap:8px; border:1px solid #ffffff1a; border-radius:12px; padding:12px; background:#020617f2; z-index:10; }
.coop-workspace .coop-button { border:1px solid #ffffff33; border-radius:8px; padding:8px 12px; font-size:14px; line-height:20px; background:#0f172a; color:#e2e8f0; cursor:pointer; white-space:nowrap; }
.coop-workspace .coop-button:disabled { cursor:not-allowed; opacity:.45; }
.coop-workspace .coop-button:focus-visible, .coop-workspace .coop-field:focus-visible { outline:2px solid #2dd4bf; outline-offset:2px; }
.coop-workspace .coop-start { border-color:#34d399; background:#065f46; color:#ecfdf5; }
.coop-workspace .coop-stop, .coop-workspace .coop-danger { border-color:#fb7185; background:#9f1239; color:#fff1f2; }
.coop-workspace .coop-run-state { display:flex; flex-wrap:wrap; gap:4px 12px; margin-left:auto; font-size:12px; }
.coop-workspace .coop-notice { height:20px; flex-shrink:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; color:#fcd34d; }
.coop-workspace .coop-body { min-height:0; flex:1 1 0%; overflow-y:auto; overflow-x:hidden; scrollbar-gutter:stable; overscroll-behavior:contain; }
.coop-workspace .coop-settings { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; min-width:0; margin:0 0 12px; border:1px solid #ffffff1a; border-radius:12px; padding:12px; }
 .coop-workspace .coop-settings-group { display:flex; flex-direction:column; gap:8px; min-width:0; }
.coop-workspace .coop-settings-group h3 { margin:0 0 4px; font-size:13px; font-weight:600; color:#cbd5e1; }
.coop-workspace .coop-settings-hint { margin:0; font-size:12px; color:#67e8f9; }
.coop-workspace .coop-settings legend { padding:0 4px; font-size:14px; }
.coop-workspace .coop-setting { display:flex; flex-direction:column; gap:4px; min-width:0; font-size:12px; }
.coop-workspace .coop-field { min-width:0; max-width:100%; width:100%; border:1px solid #ffffff33; border-radius:8px; padding:8px; background:#020617; color:#e2e8f0; font:inherit; }
.coop-workspace .coop-field:disabled { color:#cbd5e1; opacity:.8; }
.coop-workspace .coop-history { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:12px; }
.coop-workspace .coop-history-picker { display:flex; min-width:0; align-items:center; gap:8px; font-size:12px; }
.coop-workspace .coop-history-select { max-width:18rem; width:auto; }
.coop-workspace .coop-confirmation { display:flex; flex-wrap:wrap; gap:8px; }
.coop-workspace .coop-main { display:grid; grid-template-columns:minmax(0,1fr); gap:12px; min-height:16rem; }
.coop-workspace .coop-column { display:flex; flex-direction:column; gap:12px; min-width:0; }
.coop-workspace .coop-participants { min-width:0; margin:0; padding:0; border:0; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.coop-workspace .coop-panel { min-width:0; border:1px solid #ffffff1a; border-radius:12px; padding:12px; }
.coop-workspace .coop-panel h2 { margin:0 0 8px; font-size:16px; font-weight:600; }
.coop-workspace .coop-messages { display:flex; flex-direction:column; gap:12px; list-style:none; margin:0; padding:4px; max-height:min(20rem, 50dvh); overflow-y:auto; overflow-x:hidden; scrollbar-gutter:stable; overscroll-behavior:contain; }
.coop-workspace .coop-messages:focus-visible { outline:2px solid #2dd4bf; outline-offset:2px; }
.coop-workspace .coop-message { flex:0 0 auto; min-width:0; border-radius:8px; background:#0f172a; padding:12px; }
.coop-workspace .coop-message p { white-space:pre-wrap; overflow-wrap:anywhere; }
.coop-workspace .coop-message { align-self:flex-start; max-width:94%; width:fit-content; border:1px solid #22d3ee44; border-left:3px solid #22d3ee; background:#082f493d; }
.coop-workspace .coop-message[data-sender="B"] { align-self:flex-end; border:1px solid #a78bfa55; border-right:3px solid #a78bfa; background:#2e10653d; }
.coop-workspace .coop-message-header { display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px; font-size:12px; color:#cbd5e1; }
.coop-workspace .coop-message-route { font-size:14px; color:#67e8f9; }
.coop-workspace .coop-message[data-sender="B"] .coop-message-route { color:#c4b5fd; }
.coop-workspace .coop-message time { font-variant-numeric:tabular-nums; color:#94a3b8; font-size:11px; }
.coop-workspace .coop-message .coop-message-content { margin:8px 0; font-size:14px; line-height:1.55; }
.coop-workspace .coop-message-meta { margin:4px 0 0; color:#94a3b8; font-size:11px; }
.coop-workspace .coop-composer { margin-top:12px; display:flex; flex-direction:column; gap:8px; }
.coop-workspace .coop-composer textarea { resize:vertical; min-height:4rem; max-height:10rem; }
.coop-workspace .coop-composer-actions { display:flex; flex-wrap:wrap; gap:8px; align-items:center; font-size:12px; }
.coop-workspace .coop-message[data-sender="operator"] { align-self:center; border:1px solid #34d39988; background:#064e3b55; }
.coop-workspace .coop-message[data-sender="operator"] .coop-message-route { color:#6ee7b7; }
.coop-workspace .coop-reply { display:block; margin-top:6px; font-size:12px; color:#a5b4fc; overflow-wrap:anywhere; }
.coop-workspace .coop-message:target { outline:2px solid #94a3b8; outline-offset:2px; }
.coop-workspace .coop-game-board { border-collapse:collapse; margin:8px 0; font-variant-numeric:tabular-nums; }
.coop-workspace .coop-game-board caption { text-align:left; font-size:12px; color:#94a3b8; margin-bottom:6px; }
.coop-workspace .coop-game-board td { width:42px; height:42px; border:1px solid #94a3b866; text-align:center; font-size:22px; font-weight:600; }
.coop-workspace .coop-game-board th { padding:4px 8px; font-size:12px; color:#94a3b8; }
.coop-workspace .coop-game-state { font-size:13px; margin:6px 0 0; }


.coop-workspace .coop-panel pre { max-height:20rem; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; font-size:12px; }
.coop-workspace .coop-usage { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:4px; margin-top:8px; font-size:12px; }
@media (min-width:1024px) {
  .coop-workspace[data-operator="true"] .coop-body { display:flex; flex-direction:column; }
  .coop-workspace[data-operator="true"] .coop-settings, .coop-workspace[data-operator="true"] .coop-history { flex-shrink:0; }
  .coop-workspace[data-operator="true"] .coop-main { flex:1; min-height:0; }
  .coop-workspace[data-operator="true"] .coop-column { min-height:0; }
  .coop-workspace[data-operator="true"] .coop-participants { grid-template-columns:repeat(3,minmax(0,1fr)); flex-shrink:0; }
  .coop-workspace[data-operator="true"] .coop-dialog { display:flex; flex-direction:column; flex:1; min-height:0; }
  .coop-workspace[data-operator="true"] .coop-dialog h2, .coop-workspace[data-operator="true"] .coop-composer { flex-shrink:0; }
  .coop-workspace[data-operator="true"] .coop-messages { flex:1; min-height:0; }
  .coop-workspace[data-operator="true"] aside { overflow-y:auto; }

  .coop-workspace .coop-settings { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .coop-workspace .coop-setting-wide { grid-column:span 2 / span 2; }
  .coop-workspace .coop-main { grid-template-columns:minmax(0,1fr) 18rem; }
}
@media (max-width:639px) {
  .coop-workspace .coop-settings { grid-template-columns:minmax(0,1fr); }
  .coop-workspace .coop-run-state { margin-left:0; width:100%; }
}
`;

export function useWorkspaceViewport() {
  const ref = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    let previous = -1;
    const measure = () => {
      const top = Math.max(0, node.getBoundingClientRect().top);
      if (Math.abs(top - previous) > .5) {
        previous = top;
        node.style.setProperty("--coop-top", top + "px");
      }
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    if (node.parentElement) observer?.observe(node.parentElement);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  return ref;
}

export type SavedSettings = { model:string; scenario:string; mode:string; turns:number; tokens:number; seed:number; communicationLanguage:"pl" | "en" };
function record(value: Json | undefined): Record<string, Json> {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
export function savedSettings(config: Record<string, Json>): Partial<SavedSettings> {
  const result: Partial<SavedSettings> = {};
  const model = record(config.model).model_id ?? config.model_id;
  if (typeof model === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(model)) result.model = model;
  if (typeof config.scenario_id === "string" && ["peer_review", "operator_conversation", "split_facts", "organization", "correction", "tic_tac_toe"].includes(config.scenario_id)) result.scenario = config.scenario_id;
  if (typeof config.mode === "string" && ["single", "self_correction", "no_contact", "dialog", "dialog_encouraged", "operator_chat", "operator_relay", "operator_review"].includes(config.mode)) result.mode = config.mode;
  if (config.communication_language === "pl" || config.communication_language === "en") result.communicationLanguage = config.communication_language;
  else if (config.schema_version === 1 || Array.isArray(config.prompts)) result.communicationLanguage = "en";
  const budgets = record(config.budgets);
  const pairs = [["turns", budgets.max_turns, config.mode === "operator_review" ? 3 : 1, config.mode === "operator_review" ? 6 : config.scenario_id === "tic_tac_toe" ? 9 : 8], ["tokens", budgets.max_new_tokens, 1, 256], ["seed", config.seed, 0, 2147483647]] as const;
  for (const [name, value, minimum, maximum] of pairs) {
    if (typeof value === "number" && Number.isInteger(value) && value >= minimum && value <= maximum) result[name] = value;
  }
  return result;
}
