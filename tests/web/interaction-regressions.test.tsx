import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CooperationLabPage from "../../web-next/page";
import metadata from "../contracts/capabilities.json";
import type { Run, LabEvent } from "../../web-next/lib/protocol";
const dom=new JSDOM("<!doctype html><body></body>",{url:"http://localhost:3300/cooperation-lab"});
for(const [name,value]of Object.entries({window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true}))Object.defineProperty(globalThis,name,{value,configurable:true});
class Source{
 static CLOSED=2;static all:Source[]=[];readyState=1;onopen:(()=>void)|null=null;onerror:(()=>void)|null=null;
 listeners=new Map<string,EventListener>();
 constructor(readonly url:string){Source.all.push(this);}
 addEventListener(k:string,l:EventListener){this.listeners.set(k,l);}
 close(){this.readyState=2;}
 emit(e:LabEvent){this.listeners.get(e.kind)?.({data:JSON.stringify(e)}as unknown as Event);}
}
Object.defineProperty(globalThis,"EventSource",{value:Source,configurable:true});
const caps={...metadata,ready:true,state:"ready",models:metadata.models.map((m)=>({...m,qualified:true}))};
const run=(id:string,status:string):Run=>({id,status,created:1,last_seq:0,bytes:1,config:{model:{model_id:"rwkv7-g1d-0.4b"},scenario_id:"split_facts",mode:"dialog_encouraged",seed:0,budgets:{max_turns:8,max_new_tokens:128}}});
const response=(body:unknown,status=200)=>({ok:status<400,status,json:async()=>body})as Response;
const flush=()=>act(async()=>{await new Promise((r)=>setImmediate(r));});
const button=(box:Element,text:string)=>[...box.querySelectorAll("button")].find((b)=>b.textContent===text)!;
test("history cannot hide STOP; late cancel cannot replace a newly selected run; deletion confirms a single ID",async()=>{
 const old=globalThis.fetch;localStorage.clear();Source.all=[];
 let cancelResolve:((value:Response)=>void)|undefined;
 const active=run("active","running"),archive=run("archive","completed");
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response(caps);
  if(path.endsWith("/cancel"))return new Promise<Response>((r)=>{cancelResolve=r;});
  if(path.endsWith("/events"))return response({events:[]});
  if(path.endsWith("/runs/active"))return response({run:active});
  if(path.endsWith("/runs/archive"))return response({run:archive});
  assert.ok(!init?.method||init.method==="GET");return response({runs:[active,archive]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  const history=[...box.querySelectorAll("select")].find((s)=>s.parentElement?.textContent?.startsWith("Historia prób"))!;
  assert.equal(history.disabled,true);assert.equal(button(box,"Zatrzymaj").disabled,false);
  await act(async()=>button(box,"Zatrzymaj").click());
  await act(async()=>Source.all[0].emit({run_id:"active",seq:1,kind:"end",payload:{status:"completed"},timestamp:1}));
  await act(async()=>button(box,"Usuń próbę").click());assert.ok(button(box,"Potwierdź usunięcie"));
  await act(async()=>{history.value="archive";history.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});await flush();
  assert.equal(history.value,"archive");assert.equal(button(box,"Potwierdź usunięcie"),undefined);
  await act(async()=>cancelResolve?.(response({run:run("active","cancelling")},202)));await flush();
  assert.equal(history.value,"archive");
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});
test("STOP during an unacknowledged start queues cancellation of the returned ID",async()=>{
 const old=globalThis.fetch;localStorage.clear();localStorage.setItem("cooperation-lab.run","old");Source.all=[];
 let acknowledge:((value:Response)=>void)|undefined;let current:Run|null=run("old","completed");const cancelled:string[]=[];
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response(caps);
  if(init?.method==="POST"&&path.endsWith("/runs"))return new Promise<Response>((r)=>{acknowledge=r;});
  if(path.endsWith("/cancel")){cancelled.push(path);current=run("pending","cancelling");return response({run:current},202);}
  if(path.endsWith("/events"))return response({events:[]});
  if(path.endsWith("/runs/pending")||path.endsWith("/runs/old"))return response({run:current});
  return response({runs:current?[current]:[]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  await act(async()=>button(box,"Rozpocznij eksperyment").click());
  assert.equal(button(box,"Zatrzymaj").disabled,false);
  await act(async()=>button(box,"Zatrzymaj").click());await flush();
  assert.match(box.textContent??"",/Zatrzymywanie obliczeń/);
  current=run("pending","created");
  await act(async()=>acknowledge?.(response({run:current,created:true},202)));await flush();
  assert.deepEqual(cancelled,["/api/v1/cooperation-lab/runs/pending/cancel"]);
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});

test("a terminal journal event newer than the run snapshot completes catch-up without opening SSE", async () => {
 const old = globalThis.fetch;
 localStorage.clear(); Source.all = [];
 localStorage.setItem("cooperation-lab.run", "finished");
 const snapshot = run("finished", "running");
 const end: LabEvent = {run_id:"finished",seq:2,kind:"end",payload:{status:"completed"},timestamp:2};
 globalThis.fetch = async (url, init) => {
  assert.ok(!init?.method || init.method === "GET");
  const path = new URL(String(url), "http://localhost").pathname;
  if (path.endsWith("/capabilities")) return response(caps);
  if (path.endsWith("/events")) return response({events:[end],last_seq:2});
  if (path.endsWith("/runs/finished")) return response({run:snapshot});
  return response({runs:[snapshot]});
 };
 const box = document.createElement("div"); document.body.append(box);
 const root = createRoot(box);
 try {
  await act(async () => root.render(<CooperationLabPage/>)); await flush();
  assert.equal(Source.all.length, 0);
  assert.equal(button(box,"Zatrzymaj").disabled, true);
  assert.equal(button(box,"Rozpocznij eksperyment").disabled, false);
 } finally {
  await act(async () => root.unmount()); box.remove(); globalThis.fetch = old; localStorage.clear();
 }
});
