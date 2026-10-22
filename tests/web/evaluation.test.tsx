import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { EvaluationWorkspace } from "../../web-next/lib/evaluation";
import { evaluationDefaults, isEvaluationCapabilities, isEvaluationPreflight, isEvaluationSnapshot, savedEvaluationRequest, validEvaluationRequest, type EvaluationSnapshot } from "../../web-next/lib/evaluation-protocol";
import { evaluationTexts } from "../../web-next/lib/evaluation-i18n";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {url:"http://localhost:3300/cooperation-lab"});
for (const [name,value] of Object.entries({window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true})) Object.defineProperty(globalThis,name,{value,configurable:true});
const response = (body:unknown,status=200) => ({ok:status<400,status,json:async()=>body}) as Response;
const settle = () => act(async()=>{await new Promise(resolve=>setImmediate(resolve));});
const caps = {ready:true, cases:[{id:"ttt-start",game:"tic_tac_toe",max_actions:9},{id:"memory-1",game:"memory",max_actions:64}], games:["tic_tac_toe","memory"], manifest_version:"suite-v1", limits:{series:100}, models:[{model_id:"huginn-0125",display_name:"Huginn",can_run:true,observation_modes:["history_replay"],compute_steps:[8,16,32,64]}]};
const preflight = {supported:true, reason_codes:[], planned_episodes:4, planned_blocks:2, planned_decisions:36, configuration:{protocol:"game-eval-v2"}, items:[]};
function saved(status="running"):EvaluationSnapshot {return {id:"series-1",status,config:{model_id:"huginn-0125",observation_mode:"history_replay",episode_memory:"fresh",num_steps:32},updated:1,progress:{planned:4,started:3,terminal:2,success:1,skipped:1},episodes:[],summary:{}};}
const findButton = (box:Element,text:string) => [...box.querySelectorAll("button")].find(item=>item.textContent===text)!;
const select = (box:Element,label:string) => [...box.querySelectorAll("select")].find(item=>item.parentElement?.textContent?.startsWith(label))!;
async function choose(box:Element,label:string,value:string) {await act(async()=>{const node=select(box,label);node.value=value;node.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});}
async function number(box:Element,label:string,value:string) {await act(async()=>{const node=[...box.querySelectorAll("input[type=number]")].find(item=>item.parentElement?.textContent?.startsWith(label)) as HTMLInputElement;node.value=value;node.dispatchEvent(new dom.window.Event("input",{bubbles:true}));});}
async function setup(fetcher:typeof fetch,language="pl") {
  const old=globalThis.fetch;globalThis.fetch=fetcher;
  const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
  await act(async()=>root.render(<EvaluationWorkspace language={language}/>));await settle();
  return {box,close:async()=>{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;}};
}

test("evaluation never auto-starts, requires exact preflight and sends selected memory, compute and decoder settings once",async()=>{
  const calls:{path:string;init?:RequestInit}[]=[];
  const {box,close}=await setup(async(url,init)=>{
    const path=String(url);calls.push({path,init});
    if(path.endsWith("/capabilities"))return response(caps);
    if(path.endsWith("/preflight"))return response(preflight);
    if(init?.method==="POST"&&path.endsWith("/evaluations"))return response({evaluation:saved(),created:true},202);
    return response({evaluations:[]});
  });
  try {
    assert.equal(calls.filter(call=>call.init?.method==="POST").length,0);
    const start=findButton(box,"Rozpocznij serię");assert.equal(start.disabled,true);
    await choose(box,"Przekazywanie obserwacji","native_incremental");
    await choose(box,"Pamięć między partiami","carry");await choose(box,"Notatka po partii","episode_note");
    await choose(box,"Kroki Huginn","32");await choose(box,"Dekodowanie","sampled");
    await choose(box,"Lista legalnych akcji","hidden");await choose(box,"Przeciwnik / referencja","random");
    await number(box,"Temperatura","0.7");await number(box,"Powtórzenia","2");
    await act(async()=>findButton(box,"Sprawdź konfigurację").click());await settle();
    const checked=JSON.parse(String(calls.find(call=>call.path.endsWith("/preflight"))?.init?.body));
    assert.equal(checked.observation_mode,"native_incremental");assert.equal(checked.episode_memory,"carry");assert.equal(checked.reflection,"episode_note");
    assert.equal(checked.num_steps,32);assert.equal(checked.decoding,"sampled");assert.equal(checked.temperature,0.7);assert.equal(checked.repetitions,2);assert.equal(checked.legal_moves,"hidden");assert.equal(checked.opponent,"random");
    assert.match(box.textContent??"",/Zaplanowane: 4/);assert.match(box.textContent??"",/Bloki: 2/);assert.equal(start.disabled,false);
    await number(box,"Seed","18");assert.equal(start.disabled,true,"changing the form invalidates preflight");
    await act(async()=>findButton(box,"Sprawdź konfigurację").click());await settle();
    await act(async()=>{start.click();start.click();});await settle();
    const starts=calls.filter(call=>call.path.endsWith("/evaluations")&&call.init?.method==="POST");assert.equal(starts.length,1);
    assert.ok((starts[0].init?.headers as Record<string,string>)["Idempotency-Key"]);
    assert.equal(JSON.parse(String(starts[0].init?.body)).seed,18);
    assert.equal(findButton(box,"Zatrzymaj serię").disabled,false);assert.equal(start.disabled,true);
    assert.equal(box.querySelector('[data-counter="started"]')?.textContent,"3");
    assert.ok([...box.querySelectorAll("a")].some(item=>item.href.endsWith("/evaluations/series-1/export?format=jsonl")));
  } finally {await close();}
});

test("unsupported configuration displays reason and cannot start; malformed server data is not accepted",async()=>{
  let malformed=false;const posts:string[]=[];
  const {box,close}=await setup(async(url,init)=>{
    if(init?.method==="POST")posts.push(String(url));
    if(String(url).endsWith("/capabilities"))return response(caps);
    if(String(url).endsWith("/preflight"))return response(malformed?{supported:true}:{...preflight,supported:false,reason_codes:["native_unsupported"]});
    return response({evaluations:[]});
  });
  try {
    await choose(box,"Przekazywanie obserwacji","native_incremental");
    await act(async()=>findButton(box,"Sprawdź konfigurację").click());await settle();
    assert.match(box.textContent??"",/Model nie obsługuje natywnego stanu/);assert.match(box.textContent??"",/native_unsupported/);
    assert.equal(findButton(box,"Rozpocznij serię").disabled,true);assert.equal(posts.length,1);
    malformed=true;await act(async()=>findButton(box,"Sprawdź konfigurację").click());await settle();
    assert.match(box.textContent??"",/invalid_response/);assert.equal(findButton(box,"Rozpocznij serię").disabled,true);
  }finally{await close();}
});

test("history keeps errors, null costs and all counters visible while rendering model text safely",async()=>{
  const snapshot:EvaluationSnapshot={...saved("failed"),summary:{by_game:[{game:"memory",episodes:4,successes:1,model_errors:2,infrastructure_errors:0,median_decision_s:null,p95_decision_s:null,input_tokens:null,output_tokens:0,peak_vram_bytes:null}],errors:{illegal_action:2}},episodes:[{case_id:"memory-1",episode:1,block_id:"block",attempt:2,status:"illegal_action",reason_code:"illegal_action",result:null,decisions:[{player:"A",observation:{revealed:[1]},response:"<script>alert('unsafe')</script>",action:{cards:[1,1]},valid:false,error:"illegal_action",seconds:null}]}]};
  const {box,close}=await setup(async(url)=>String(url).endsWith("/capabilities")?response(caps):response({evaluations:[snapshot]}));
  try {
    await choose(box,"Historia serii","series-1");
    assert.deepEqual([...box.querySelectorAll("[data-counter]")].map(node=>node.textContent),["4","3","2","1","1"]);
    assert.match(box.textContent??"",/Niedozwolona akcja/);assert.match(box.textContent??"",/Brak danych/);
    assert.match(box.textContent??"",/<script>alert\('unsafe'\)<\/script>/);assert.equal(box.querySelector("script"),null);
    assert.match(box.querySelector('section[aria-label="Wyniki według gry"]')?.textContent??"",/Błędy modelu/);
    assert.equal(box.querySelector('section[aria-label="Wyniki według gry"] tbody td')?.textContent,"4");
    assert.equal(box.querySelector('section[aria-label="Wyniki według gry"] tbody td:nth-of-type(8)')?.textContent,"Brak danych");
  }finally{await close();}
});

test("STOP and resume mutate only the selected series and keep the same control group",async()=>{
  let snapshot=saved();const posts:string[]=[];
  const {box,close}=await setup(async(url,init)=>{
    const path=String(url);
    if(path.endsWith("/capabilities"))return response(caps);
    if(init?.method==="POST") {posts.push(path);snapshot={...snapshot,status:path.endsWith("/cancel")?"cancelled":"running"};return response({evaluation:snapshot});}
    return response({evaluations:[snapshot]});
  });
  try {
    await choose(box,"Historia serii","series-1");
    const stop=findButton(box,"Zatrzymaj serię"),controls=stop.parentElement;
    assert.equal(stop.disabled,false);
    await act(async()=>stop.click());await settle();assert.equal(stop.disabled,true);
    const resume=findButton(box,"Wznów serię");assert.equal(resume.disabled,false);
    await act(async()=>resume.click());await settle();assert.equal(stop.disabled,false);assert.equal(stop.parentElement,controls);
    assert.deepEqual(posts,["/api/v1/cooperation-lab/evaluations/series-1/cancel","/api/v1/cooperation-lab/evaluations/series-1/resume"]);
  }finally{await close();}
});

test("evaluation contracts reject bad input and translation rows cover PL EN DE",()=>{
  const input={...evaluationDefaults(),model_id:"rwkv",case_ids:["ttt"]};
  assert.equal(validEvaluationRequest(input),true);assert.equal(validEvaluationRequest({...input,max_new_tokens:1}),false);assert.equal(validEvaluationRequest({...input,case_ids:[]}),false);
  assert.equal(isEvaluationCapabilities(caps),true);assert.equal(isEvaluationCapabilities({...caps,cases:[{id:"../../etc",game:"nim",max_actions:4}]}),false);
  assert.equal(isEvaluationPreflight(preflight),true);assert.equal(isEvaluationPreflight({...preflight,planned_episodes:-1}),false);
  assert.equal(isEvaluationSnapshot(saved()),true);assert.equal(isEvaluationSnapshot({...saved(),id:"../unsafe"}),false);
  assert.deepEqual(Object.keys(evaluationTexts("pl")),Object.keys(evaluationTexts("en")));assert.deepEqual(Object.keys(evaluationTexts("de")),Object.keys(evaluationTexts("en")));
  assert.equal(evaluationTexts("de").start,"Serie starten");assert.equal(evaluationTexts("en").start,"Start series");
});

test("busy runtime blocks START even after a supported preflight and refresh stays read-only",async()=>{
  const calls:{path:string;method:string}[]=[];
  const {box,close}=await setup(async(url,init)=>{
    const path=String(url);calls.push({path,method:init?.method??"GET"});
    if(path.endsWith("/capabilities"))return response({...caps,ready:false,reason_code:"runtime_busy"});
    if(path.endsWith("/preflight"))return response(preflight);
    return response({evaluations:[]});
  });
  try {
    await act(async()=>findButton(box,"Sprawdź konfigurację").click());await settle();
    assert.equal(findButton(box,"Rozpocznij serię").disabled,true);assert.match(box.textContent??"",/Zasób modelu jest zajęty/);
    await act(async()=>findButton(box,"Odśwież").click());await settle();
    assert.equal(calls.filter(call=>call.method==="POST").length,1);assert.ok(calls.filter(call=>call.method==="POST").every(call=>call.path.endsWith("/preflight")));
  }finally{await close();}
});

test("active polling updates the selected report and stops after completion without a second start",async()=>{
  let reads=0;const posts:string[]=[];
  const {box,close}=await setup(async(url,init)=>{
    const path=String(url);if(init?.method==="POST")posts.push(path);
    if(path.endsWith("/capabilities"))return response(caps);
    if(path.endsWith("/evaluations/series-1")){reads++;return response({evaluation:{...saved("completed"),progress:{planned:4,started:4,terminal:4,success:2,skipped:0}}});}
    return response({evaluations:[saved()]});
  });
  try {
    await choose(box,"Historia serii","series-1");
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,2100));});
    assert.equal(reads,1);assert.equal(box.querySelector('[data-counter="terminal"]')?.textContent,"4");assert.equal(findButton(box,"Zatrzymaj serię").disabled,true);assert.equal(posts.length,0);
    await act(async()=>findButton(box,"Odśwież").click());await settle();assert.equal(reads,2);
  }finally{await close();}
});

test("terminal poll reads readiness afterward so earlier busy state cannot strand START",async()=>{
  let terminalDelivered=false;
  const order:string[]=[];
  const {box,close}=await setup(async(url)=>{
    const path=String(url);
    if(path.endsWith("/evaluations/series-1")){order.push("terminal");terminalDelivered=true;return response({evaluation:{...saved("completed"),can_resume:false}});}
    if(path.endsWith("/capabilities")){order.push("capabilities");return response({...caps,ready:terminalDelivered,reason_code:terminalDelivered?"ready":"runtime_busy"});}
    return response({evaluations:[saved()]});
  });
  try{
    await choose(box,"Historia serii","series-1");
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,2100));});
    assert.deepEqual(order.slice(-2),["terminal","capabilities"]);
    assert.equal(findButton(box,"Zatrzymaj serię").disabled,true);
    assert.equal(findButton(box,"Wznów serię").disabled,true);
    assert.doesNotMatch(box.querySelector("output")?.textContent??"",/Zasób modelu jest zajęty/);
  }finally{await close();}
});

test("backend can_resume allows a completed partial series and denies unrecoverable failures",async()=>{
  const rows=[{...saved("completed"),can_resume:true},{...saved("failed"),id:"series-2",can_resume:false}];
  const {box,close}=await setup(async(url,init)=>{
    if(String(url).endsWith("/capabilities"))return response(caps);
    if(init?.method==="POST")return response({evaluation:{...rows[0],status:"running",can_resume:false}});
    return response({evaluations:rows});
  });
  try{
    await choose(box,"Historia serii","series-1");assert.equal(findButton(box,"Wznów serię").disabled,false);
    await choose(box,"Historia serii","series-2");assert.equal(findButton(box,"Wznów serię").disabled,true);
    await choose(box,"Historia serii","series-1");
    await act(async()=>findButton(box,"Wznów serię").click());await settle();
    assert.equal(findButton(box,"Zatrzymaj serię").disabled,false);
  }finally{await close();}
});

test("terminal series deletes with one click and updates capacity without confirmation",async()=>{
  const oldConfirm=globalThis.confirm;
  Object.defineProperty(globalThis,"confirm",{value:()=>{throw Error("confirmation is forbidden");},configurable:true});
  let removed=false;const deletes:string[]=[];
  const {box,close}=await setup(async(url,init)=>{
    const path=String(url);
    if(init?.method==="DELETE"){deletes.push(path);removed=true;return response({deleted:true});}
    if(path.endsWith("/capabilities"))return response({...caps,storage:{series_used:removed?0:1,max_series:100,retention_days:14}});
    return response({evaluations:removed?[]:[{...saved("completed"),can_resume:false}]});
  });
  try{
    await choose(box,"Historia serii","series-1");assert.match(box.textContent??"",/Zapisane serie: 1\/100/);
    assert.equal(findButton(box,"Usuń serię").disabled,false);
    await act(async()=>{findButton(box,"Usuń serię").click();findButton(box,"Usuń serię").click();});await settle();
    assert.deepEqual(deletes,["/api/v1/cooperation-lab/evaluations/series-1"]);
    assert.equal(select(box,"Historia serii").value,"");assert.equal(findButton(box,"Usuń serię").disabled,true);
    assert.match(box.textContent??"",/Zapisane serie: 0\/100/);assert.equal(box.querySelector('[data-counter="planned"]')?.textContent,"0");
  }finally{await close();Object.defineProperty(globalThis,"confirm",{value:oldConfirm,configurable:true});}
});

test("selecting active Huginn history restores its exact settings and polling never overwrites later edits",async()=>{
  const request={...evaluationDefaults(),model_id:"huginn-0125",case_ids:["ttt-start","memory-1","nim-last","sokoban-push"],repetitions:3,num_steps:32 as const,episode_memory:"carry" as const,reflection:"episode_note" as const,max_new_tokens:96,seed:9,decision_timeout_s:60};
  const historic={...saved(),config:{request},can_resume:false};
  const historyCaps={...caps,models:[{model_id:"rwkv7-g1k-2.9b",display_name:"RWKV",can_run:true,compute_steps:[]},...caps.models],cases:[...caps.cases,{id:"nim-last",game:"nim",max_actions:1},{id:"sokoban-push",game:"sokoban",max_actions:16}]};
  const {box,close}=await setup(async(url)=>{
    const path=String(url);
    if(path.endsWith("/capabilities"))return response(historyCaps);
    if(path.endsWith("/evaluations/series-1"))return response({evaluation:{...historic,status:"completed"}});
    return response({evaluations:[historic]});
  });
  try{
    assert.equal(select(box,"Model").value,"rwkv7-g1k-2.9b");
    await choose(box,"Historia serii","series-1");
    assert.equal(select(box,"Model").value,"huginn-0125");assert.equal(select(box,"Kroki Huginn").value,"32");
    assert.equal(select(box,"Pamięć między partiami").value,"carry");assert.equal(select(box,"Notatka po partii").value,"episode_note");
    assert.equal(box.querySelector<HTMLFieldSetElement>("fieldset.coop-settings")?.disabled,true);
    assert.equal(box.querySelectorAll('.evaluation-case-list input:checked').length,4);
    const tokens=()=>[...box.querySelectorAll<HTMLInputElement>('input[type="number"]')].find(node=>node.parentElement?.textContent?.startsWith("Tokenów na decyzję"))!;
    assert.equal(tokens().value,"96");
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,2100));});
    assert.equal(box.querySelector<HTMLFieldSetElement>("fieldset.coop-settings")?.disabled,false);
    await number(box,"Tokenów na decyzję","128");
    await act(async()=>findButton(box,"Odśwież").click());await settle();
    assert.equal(tokens().value,"128","snapshot refresh must not overwrite the operator's terminal draft");
    assert.equal(select(box,"Model").value,"huginn-0125");
  }finally{await close();}
});

test("saved evaluation settings whitelist the public form and reject malformed history",()=>{
  const request={...evaluationDefaults(),model_id:"huginn-0125",case_ids:["ttt-start"]};
  assert.deepEqual(savedEvaluationRequest({request:{...request,unexpected:"discarded"},other:"ignored"}),request);
  assert.deepEqual(savedEvaluationRequest({...request,snapshot_restore:false}),request);
  assert.equal(savedEvaluationRequest({request:{...request,num_steps:7}}),null);
  assert.equal(savedEvaluationRequest({request:{...request,case_ids:"bad"}}),null);
  assert.equal(savedEvaluationRequest({request:{...request,episode_memory:"unrecognized"}}),null);
});
