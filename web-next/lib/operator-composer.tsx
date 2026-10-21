"use client";
import { useState } from "react";
import { texts } from "./i18n";

export function OperatorComposer({runId,active,waiting,sending,language,relay,review=false,onSend}:{
  runId:string|null; active:boolean; waiting:boolean; sending:boolean; language:string; relay:boolean; review?:boolean;
  onSend:(content:string)=>Promise<boolean>;
}) {
  const t=texts(language);
  const [draft,setDraft]=useState({runId,text:""});
  if(draft.runId!==runId) setDraft({runId,text:""});
  const ready=active&&waiting&&!sending;
  return <form className="coop-composer" onSubmit={async event=>{
    event.preventDefault(); if(!ready||!draft.text.trim())return;
    const sent=draft.text;
    if(await onSend(sent))setDraft(before=>before.runId===runId&&before.text===sent?{runId,text:""}:before);
  }}>
    <label className="coop-setting">{relay?t.operatorRelayPrompt:t.operatorPrompt}
      <textarea className="coop-field" rows={3} maxLength={2000} value={draft.text}
        disabled={!active||sending} onInput={event=>setDraft({runId,text:event.currentTarget.value})}/>
    </label>
    <div className="coop-composer-actions">
      <button type="submit" className="coop-button coop-start" disabled={!ready||!draft.text.trim()}>{relay?t.operatorRelaySend:review?t.reviewSend:t.operatorSend}</button>
      <span role="status">{active?(waiting?t.operatorWaiting:t.operatorResponding):t.operatorInactive}</span>
    </div>
    {relay&&<p className="coop-message-meta">{t.operatorRelayHint}</p>}
    <p className="coop-message-meta">{review?t.reviewLimit:t.operatorLimit}</p>
  </form>;
}
