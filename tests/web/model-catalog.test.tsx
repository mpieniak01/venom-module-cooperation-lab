import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CooperationLabPage from "../../web-next/page";
import metadata from "../contracts/capabilities.json";
import type {LabEvent,Run} from "../../web-next/lib/protocol";
import {engineId,modelState} from "../../web-next/lib/model-selection";
import {texts} from "../../web-next/lib/i18n";
const dom=new JSDOM("<!doctype html><body></body>",{url:"http://localhost:3300/cooperation-lab"});
for(const [name,value]of Object.entries({window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true}))Object.defineProperty(globalThis,name,{value,configurable:true});
const response=(body:unknown)=>({ok:true,status:200,json:async()=>body})as Response;
const flush=()=>act(async()=>{await new Promise(r=>setImmediate(r));});
const select=(box:Element,label:string)=>[...box.querySelectorAll("select")].find(s=>s.parentElement?.textContent?.startsWith(label))!;
const button=(box:Element,label:string)=>[...box.querySelectorAll("button")].find(b=>b.textContent===label)!;
test("engine filters models, unsupported stays disabled, selection is read only and explicit check uses qualified route",async()=>{
 const old=globalThis.fetch;localStorage.clear();
 const requests:{path:string;method:string;body?:string}[]=[];
 const caps={...metadata,ready:true,state:"ready",engines:[{engine_id:"local_component",name:"RWKV"},{engine_id:"ollama",name:"Ollama"},{engine_id:"multi_runtime",name:"multi_runtime"}],models:[
  {...metadata.models[0],qualified:true},
  {model_id:"ollama-small",engine_id:"ollama",display_name:"small:1b",qualified:false,can_qualify:true},
  {model_id:"unsupported",engine_id:"multi_runtime",display_name:"Gemma",qualified:false,availability_reason:"adapter_not_supported"},
 ]};
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;requests.push({path,method:init?.method??"GET",body:init?.body as string|undefined});
  if(path.endsWith("/capabilities"))return response(caps);
  if(path.endsWith("/qualifications"))throw new Error("test response interrupted");
  return response({runs:[]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  const engine=select(box,"Silnik");
  await act(async()=>{engine.value="ollama";engine.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  assert.equal(select(box,"Model").options.length,1);assert.match(select(box,"Model").textContent??"",/small:1b/);
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,true);assert.ok(button(box,"Sprawdź model (opcjonalnie)"));
  assert.ok(requests.every(r=>r.method==="GET"));
  await act(async()=>{engine.value="multi_runtime";engine.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  assert.match(select(box,"Model").textContent??"",/Brak adaptera/);assert.equal(button(box,"Sprawdź model (opcjonalnie)"),undefined);
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,true);
  await act(async()=>{engine.value="ollama";engine.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  await act(async()=>button(box,"Sprawdź model (opcjonalnie)").click());await flush();
  const mutations=requests.filter(r=>r.method==="POST");assert.equal(mutations.length,1);
  assert.equal(mutations[0].path,"/api/v1/cooperation-lab/qualifications");assert.deepEqual(JSON.parse(mutations[0].body!),{model_id:"ollama-small"});
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});
test("model statuses and fallback engines are explicit",()=>{
 const t=texts("pl");assert.equal(engineId({provider:"ollama"}),"ollama");
 assert.equal(engineId({}),"local_component");assert.equal(modelState({qualified:true},t),t.modelReady);
 assert.equal(modelState({},t),t.modelOffline);assert.equal(modelState({can_qualify:true},t),t.modelPending);
});

class RecoveryStream {
 static CLOSED=2;static all:RecoveryStream[]=[];readyState=1;
 onopen:(()=>void)|null=null;onerror:(()=>void)|null=null;listeners=new Map<string,EventListener>();
 constructor(readonly url:string){RecoveryStream.all.push(this);}
 addEventListener(k:string,l:EventListener){this.listeners.set(k,l);}
 close(){this.readyState=2;}
 emit(e:LabEvent){this.listeners.get(e.kind)?.({data:JSON.stringify(e)}as unknown as Event);}
}
test("failed experiment recovers through New run, refresh, direct START and STOP without mandatory qualification",async()=>{
 const oldFetch=globalThis.fetch,oldSource=globalThis.EventSource;localStorage.clear();RecoveryStream.all=[];
 Object.defineProperty(globalThis,"EventSource",{value:RecoveryStream,configurable:true});
 const good={...metadata.models[1],model_id:"ollama-direct",engine_id:"ollama",display_name:"installed:1b",qualified:false,can_run:true,can_qualify:true};
 const caps={...metadata,ready:true,state:"ready",models:[good,{model_id:"unsupported",engine_id:"multi_runtime",qualified:false,can_run:false,availability_reason:"adapter_not_supported"}]};
 let current:Run={id:"failed",status:"failed",created:1,last_seq:2,bytes:1,config:{model:{model_id:good.model_id},scenario_id:"correction",mode:"no_contact",budgets:{max_turns:2,max_new_tokens:32}}};
 const oldRun=current;localStorage.setItem("cooperation-lab.run",current.id);
 const keys:string[]=[];let cancels=0;let replayCount=0;
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response(caps);
  if(path.endsWith("/qualifications"))throw Error("Unexpected mandatory qualification");
  if(init?.method==="POST"&&path.endsWith("/runs")){
   keys.push((init.headers as Record<string,string>)["Idempotency-Key"]);
   assert.equal(JSON.parse(String(init.body)).model_id,good.model_id);
   current={...oldRun,id:"next"+keys.length,status:"queued",last_seq:0};return response({run:current});
  }
  if(path.endsWith("/cancel")){cancels++;current={...current,status:"cancelled",last_seq:1};return response({run:current});}
  if(path.endsWith("/events")){
   replayCount++;
   return response({events:path.includes("/failed/")?[{run_id:"failed",seq:1,kind:"error",timestamp:1,payload:{code:"malformed_model_output"}},{run_id:"failed",seq:2,kind:"end",timestamp:1,payload:{status:"failed"}}]:[]});
  }
  if(path.includes("/runs/"))return response({run:path.endsWith("/failed")?oldRun:current});
  return response({runs:[oldRun,...(current.id!==oldRun.id?[current]:[])]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  assert.match(box.textContent??"",/nieprawidłowy format/);
  const scenario=select(box,"Scenariusz");
  await act(async()=>{scenario.value="tic_tac_toe";scenario.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  assert.equal(box.querySelector(".coop-game-board"),null,"draft cannot relabel an archived experiment");
  const engine=select(box,"Silnik");
  await act(async()=>{engine.value="multi_runtime";engine.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,true);
  await act(async()=>button(box,"Nowa próba").click());await flush();
  assert.equal(select(box,"Historia prób").value,"");
  assert.equal(select(box,"Silnik").value,"ollama");
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,false);
  await act(async()=>button(box,"Odśwież").click());await flush();
  assert.equal(select(box,"Historia prób").value,"");assert.equal(button(box,"Rozpocznij eksperyment").disabled,false);
  await act(async()=>button(box,"Rozpocznij eksperyment").click());await flush();
  assert.equal(keys.length,1);assert.equal(button(box,"Zatrzymaj").disabled,false);
  current={...current,status:"completed",last_seq:1};
  await act(async()=>RecoveryStream.all.at(-1)!.emit({run_id:current.id,seq:1,kind:"end",timestamp:1,payload:{status:"completed"}}));await flush();
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,false);
  await act(async()=>button(box,"Rozpocznij eksperyment").click());await flush();
  assert.equal(keys.length,2);assert.notEqual(keys[0],keys[1]);
  const before=replayCount;await act(async()=>button(box,"Odśwież").click());await flush();assert.ok(replayCount>before);
  await act(async()=>button(box,"Zatrzymaj").click());await flush();
  assert.equal(cancels,1);assert.equal(button(box,"Zatrzymaj").disabled,true);
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=oldFetch;Object.defineProperty(globalThis,"EventSource",{value:oldSource,configurable:true});localStorage.clear();}
});
