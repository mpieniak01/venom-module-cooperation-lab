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
const caps={...metadata,ready:true,state:"ready",models:metadata.models.map((m)=>({...m,qualified:true,max_new_tokens:1024}))};
const run=(id:string,status:string):Run=>({id,status,created:1,last_seq:0,bytes:1,config:{model:{model_id:"rwkv7-g1d-0.4b"},scenario_id:"split_facts",mode:"dialog_encouraged",seed:0,budgets:{max_turns:8,max_new_tokens:128}}});
const response=(body:unknown,status=200)=>({ok:status<400,status,json:async()=>body})as Response;
const flush=()=>act(async()=>{await new Promise((r)=>setImmediate(r));});
const button=(box:Element,text:string)=>[...box.querySelectorAll("button")].find((b)=>b.textContent===text)!;
test("history cannot hide STOP; late cancel cannot replace a newly selected run",async()=>{
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
  await act(async()=>{history.value="archive";history.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});await flush();
  assert.equal(history.value,"archive");
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

test("operator prompt reaches the API once per key; retry retains draft, replies replay and STOP stays enabled", async()=>{
 const old=globalThis.fetch;localStorage.clear();Source.all=[];
 const current=run("operator-run","running");
 current.config={...current.config,scenario_id:"operator_conversation",mode:"operator_chat",communication_language:"pl"};
 const waiting:LabEvent={run_id:current.id,seq:1,kind:"operator",timestamp:1,payload:{waiting:true}};
 const calls:{key:string;content:string}[]=[];
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response(caps);
  if(path.endsWith("/messages")){
   calls.push({key:new Headers(init?.headers).get("Idempotency-Key")!,content:JSON.parse(String(init?.body)).content});
   if(calls.length===1)throw Error("temporary network error");
   Source.all.at(-1)!.emit({run_id:current.id,seq:2,kind:"message",timestamp:2,payload:{message_id:"op1",sender:"operator",recipient:"all",content:calls.at(-1)!.content,delivered_to:["A","B"]}});
   Source.all.at(-1)!.emit({run_id:current.id,seq:3,kind:"operator",timestamp:3,payload:{waiting:false}});
   return response({created:true},202);
  }
  if(path.endsWith("/events"))return response({events:[waiting],last_seq:1});
  if(path.endsWith("/runs/operator-run"))return response({run:current});
  return response({runs:[current]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  await act(async()=>Source.all.at(-1)?.onopen?.());
  assert.match(box.querySelector(".coop-run-state")!.textContent!,/Czeka na Twój wpis/);
  const area=box.querySelector("textarea")!;
  assert.ok(area);assert.equal(area.disabled,false);
  const set=Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype,"value")!.set!;
  await act(async()=>{set.call(area,"Moja wiadomość <script>test</script>");area.dispatchEvent(new dom.window.Event("input",{bubbles:true}));});
  assert.equal(button(box,"Wyślij do A i B").disabled,false);
  await act(async()=>button(box,"Wyślij do A i B").click());await flush();
  assert.match(area.value,/Moja wiadomość/);
  await act(async()=>button(box,"Wyślij do A i B").click());await flush();
  assert.equal(calls.length,2);assert.equal(calls[0].key,calls[1].key);
  assert.equal(area.value,"");assert.equal(button(box,"Wyślij do A i B").disabled,true);
  assert.equal(button(box,"Zatrzymaj").disabled,false);
  assert.match(box.querySelector(".coop-message-route")!.textContent!,/Operator → Wszyscy/);
  assert.equal(box.querySelector("script"),null);
  await act(async()=>{
   Source.all.at(-1)!.emit({run_id:current.id,seq:4,kind:"message",timestamp:4,payload:{sender:"A",recipient:"operator",content:"Odpowiedź A",delivered_to:["operator"]}});
   Source.all.at(-1)!.emit({run_id:current.id,seq:5,kind:"message",timestamp:5,payload:{sender:"B",recipient:"operator",content:"Odpowiedź B",delivered_to:["operator"]}});
   Source.all.at(-1)!.emit({run_id:current.id,seq:6,kind:"operator",timestamp:6,payload:{waiting:true}});
  });
  assert.match(box.textContent!,/Odpowiedź A/);assert.match(box.textContent!,/Odpowiedź B/);
  assert.match(box.textContent!,/Czat czeka na Twój wpis/);
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});


test("delete removes the selected terminal run with one click and blocks repeats while pending", async()=>{
 const old=globalThis.fetch;localStorage.clear();Source.all=[];
 const archive=run("archive","completed");
 localStorage.setItem("cooperation-lab.run","archive");
 let finish:((value:Response)=>void)|undefined;
 const deleted:string[]=[];
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(init?.method==="DELETE"){
   deleted.push(path);return new Promise<Response>(r=>{finish=r;});
  }
  if(path.endsWith("/capabilities"))return response(caps);
  if(path.endsWith("/events"))return response({events:[]});
  if(path.endsWith("/runs/archive"))return response({run:archive});
  return response({runs:[archive]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  await act(async()=>button(box,"Usuń próbę").click());
  assert.deepEqual(deleted,["/api/v1/cooperation-lab/runs/archive"]);
  assert.equal(button(box,"Potwierdź usunięcie"),undefined);
  assert.equal(button(box,"Usuń próbę").disabled,true);
  await act(async()=>button(box,"Usuń próbę").click());assert.equal(deleted.length,1);
  await act(async()=>finish?.(response(null,204)));await flush();
  assert.equal(button(box,"Usuń próbę"),undefined);
  assert.equal(box.querySelector(".coop-history-select")!.querySelectorAll("option").length,1);
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});


test("a completed ordinary run can start another with a restored 1024-token budget",async()=>{
 const old=globalThis.fetch;localStorage.clear();localStorage.setItem("cooperation-lab.run","complete");Source.all=[];
 let captured:Record<string,unknown>|undefined;
 const complete=run("complete","completed");complete.config.budgets={max_turns:8,max_new_tokens:1024};
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response(caps);
  if(init?.method==="POST"&&path.endsWith("/runs")){captured=JSON.parse(String(init.body));return response({run:run("next","queued"),created:true},202);}
  if(path.endsWith("/events"))return response({events:[]});
  if(path.endsWith("/runs/complete"))return response({run:complete});
  return response({runs:[complete]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  const tokenInput=[...box.querySelectorAll("input")].find(i=>i.parentElement?.textContent?.startsWith("Tokenów na turę"))!;
  assert.equal(tokenInput.value,"1024");assert.equal(tokenInput.max,"1024");
  await act(async()=>button(box,"Nowa próba").click());await flush();
  assert.equal(button(box,"Rozpocznij eksperyment").disabled,false);
  await act(async()=>button(box,"Rozpocznij eksperyment").click());await flush();
  assert.equal(captured?.max_new_tokens,1024);
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});


test("ordinary Start clamps to selected model only after clicking and submits once", async()=>{
 const old=globalThis.fetch;localStorage.clear();Source.all=[];
 const submissions:Record<string,unknown>[]=[];
 const complete=run("complete","completed");complete.config.budgets={max_turns:8,max_new_tokens:128};
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response({...caps,models:caps.models.map(m=>({...m,max_new_tokens:256}))});
  if(init?.method==="POST"&&path.endsWith("/runs")){
   submissions.push(JSON.parse(String(init.body)));
   const next=run("next","queued");next.config={...next.config,budgets:{max_turns:8,max_new_tokens:256},requested_max_new_tokens:16384};
   return response({run:next,created:true},202);
  }
  if(path.endsWith("/events"))return response({events:[]});
  if(path.endsWith("/runs/next")){const next=run("next","queued");next.config={...next.config,budgets:{max_turns:8,max_new_tokens:256},requested_max_new_tokens:16384};return response({run:next});}
  if(path.endsWith("/runs/complete"))return response({run:complete});
  return response({runs:[complete]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  const token=()=>[...box.querySelectorAll("input")].find(i=>i.parentElement?.textContent?.startsWith("Tokenów na turę"))!;
  await act(async()=>{token().value="16384";token().dispatchEvent(new dom.window.Event("input",{bubbles:true}));});
  assert.equal(token().value,"16384");assert.equal(submissions.length,0);
  const start=button(box,"Rozpocznij eksperyment");assert.equal(start.disabled,false);
  await act(async()=>{start.click();start.click();});await flush();
  assert.equal(submissions[0]?.max_new_tokens,16384,"API receives the original request for its audit/idempotency");
  await act(async()=>button(box,"Ustawienia eksperymentu").click());
  assert.equal(token().value,"256");assert.match(box.querySelector("output")?.textContent??"",/16384 → 256/);
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});


test("lost ordinary START acknowledgement retries original body/key and restores one accepted run",async()=>{
 const old=globalThis.fetch;localStorage.clear();Source.all=[];
 const attempts:{key:string;body:string}[]=[];
 const accepted=run("accepted","completed");accepted.config={...accepted.config,budgets:{max_turns:8,max_new_tokens:256},requested_max_new_tokens:4096};
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response({...caps,models:caps.models.map(m=>({...m,max_new_tokens:256}))});
  if(init?.method==="POST"&&path.endsWith("/runs")){
   attempts.push({key:new Headers(init.headers).get("Idempotency-Key")!,body:String(init.body)});
   if(attempts.length===1)throw Error("accepted by server but acknowledgement lost");
   return response({run:accepted,created:false},202);
  }
  if(path.endsWith("/events"))return response({events:[]});
  if(path.endsWith("/runs/accepted"))return response({run:accepted});
  return response({runs:[]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 const token=()=>[...box.querySelectorAll("input")].find(i=>i.parentElement?.textContent?.startsWith("Tokenów na turę"))!;
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await flush();
  await act(async()=>{token().value="4096";token().dispatchEvent(new dom.window.Event("input",{bubbles:true}));});
  await act(async()=>button(box,"Rozpocznij eksperyment").click());await flush();
  await act(async()=>button(box,"Ustawienia eksperymentu").click());
  assert.equal(token().value,"4096","unconfirmed START must keep the original request");
  await act(async()=>button(box,"Rozpocznij eksperyment").click());await flush();
  assert.equal(attempts.length,2);assert.deepEqual(attempts[1],attempts[0]);
  await act(async()=>button(box,"Ustawienia eksperymentu").click());
  assert.equal(token().value,"256");assert.equal(localStorage.getItem("cooperation-lab.run"),"accepted");
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});
