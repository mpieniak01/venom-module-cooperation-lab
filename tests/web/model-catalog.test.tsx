import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CooperationLabPage from "../../web-next/page";
import metadata from "../contracts/capabilities.json";
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
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,true);assert.ok(button(box,"Sprawdź model"));
  assert.ok(requests.every(r=>r.method==="GET"));
  await act(async()=>{engine.value="multi_runtime";engine.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  assert.match(select(box,"Model").textContent??"",/Brak adaptera/);assert.equal(button(box,"Sprawdź model"),undefined);
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,true);
  await act(async()=>{engine.value="ollama";engine.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  await act(async()=>button(box,"Sprawdź model").click());await flush();
  const mutations=requests.filter(r=>r.method==="POST");assert.equal(mutations.length,1);
  assert.equal(mutations[0].path,"/api/v1/cooperation-lab/qualifications");assert.deepEqual(JSON.parse(mutations[0].body!),{model_id:"ollama-small"});
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});
test("model statuses and fallback engines are explicit",()=>{
 const t=texts("pl");assert.equal(engineId({provider:"ollama"}),"ollama");
 assert.equal(engineId({}),"local_component");assert.equal(modelState({qualified:true},t),t.modelReady);
 assert.equal(modelState({},t),t.modelOffline);assert.equal(modelState({can_qualify:true},t),t.modelPending);
});
