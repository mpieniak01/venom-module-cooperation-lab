import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CooperationLabPage from "../../web-next/page";
import metadata from "../contracts/capabilities.json";
import type { LabEvent, Run } from "../../web-next/lib/protocol";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3300/cooperation-lab" });
for (const [name, value] of Object.entries({window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true})) {
  Object.defineProperty(globalThis, name, {value,configurable:true});
}
class Stream {
  static CLOSED = 2;
  static instances: Stream[] = [];
  readyState = 1;
  listeners = new Map<string, EventListener>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(readonly url: string) { Stream.instances.push(this); }
  addEventListener(kind: string, listener: EventListener) { this.listeners.set(kind, listener); }
  close() { this.closed = true; this.readyState = 2; }
  emit(event: LabEvent) { this.listeners.get(event.kind)?.({data:JSON.stringify(event)} as unknown as Event); }
}
Object.defineProperty(globalThis,"EventSource",{value:Stream,configurable:true});
const caps = { ...metadata, ready:true,state:"ready",models:metadata.models.map((model)=>({...model,qualified:true})) };
const aRun = (status = "running"): Run => ({id:"r1",status,created:1,last_seq:0,bytes:1,config:{model_id:"rwkv7-g1d-0.4b"}});
const response = (body: unknown, status=200) => ({ok:status<400,status,json:async()=>body}) as Response;
const settle = () => act(async () => { await new Promise((resolve)=>setImmediate(resolve)); });
const findButton = (root: Element, text: string) => [...root.querySelectorAll("button")].find((b)=>b.textContent===text)!;

test("workspace has no automatic generation, double start uses one request, SSE deduplicates and STOP keeps a stable control group", async()=>{
  const oldFetch=globalThis.fetch;
  const calls: {url:string;init?:RequestInit}[]=[];
  localStorage.clear(); Stream.instances=[];
  let current: Run | null=null;
  globalThis.fetch=async(url,init)=>{
    const path=new URL(String(url),"http://localhost:3300").pathname;
    calls.push({url:String(url),init});
    if(path.endsWith("/capabilities")) return response(caps);
    if(init?.method==="POST" && path.endsWith("/runs")) { current=aRun("created"); return response({run:current,created:true},202); }
    if(init?.method==="POST" && path.endsWith("/cancel")) { current=aRun("cancelling"); return response({run:current},202); }
    if(path.endsWith("/events")) return response({events:[],last_seq:0,resync:false});
    if(path.endsWith("/runs/r1")) return response({run:current});
    return response({runs:current?[current]:[]});
  };
  const box=document.createElement("div"); document.body.append(box);
  const root=createRoot(box);
  try {
    await act(async()=>root.render(<CooperationLabPage/>)); await settle();
    assert.equal(calls.filter((c)=>c.init?.method==="POST").length,0);
    const languageSelect=[...box.querySelectorAll("select")].find(s=>s.parentElement?.textContent?.startsWith("Język rozmowy modeli"))!;
    assert.equal(languageSelect.value,"pl");
    assert.match(box.textContent??"",/Rozdzielone informacje/);
    await act(async()=>{languageSelect.value="en";languageSelect.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
    const start=findButton(box,"Rozpocznij eksperyment"); assert.equal(start.disabled,false);
    await act(async()=>{start.click();start.click();}); await settle();
    const posts=calls.filter((c)=>c.init?.method==="POST" && c.url.endsWith("/runs"));
    assert.equal(posts.length,1); assert.ok((posts[0].init?.headers as Record<string,string>)["Idempotency-Key"]);
    assert.equal(JSON.parse(String(posts[0].init?.body)).communication_language,"en");
    assert.equal(Stream.instances.length,1);
    const stream=Stream.instances[0]; assert.match(stream.url,/after=0/);
    const first:LabEvent={run_id:"r1",seq:1,kind:"message",timestamp:1,payload:{sender:"A",recipient:"B",kind:"proposal",content:"I can collect facts."}};
    const second:LabEvent={...first,seq:2,payload:{sender:"B",recipient:"A",kind:"message",content:"I received your proposal."}};
    await act(async()=>{stream.onopen?.();stream.emit(first);stream.emit(first);stream.emit(second);});
    assert.equal(box.querySelectorAll("ol li").length,2);
    assert.match(box.textContent??"",/I received your proposal/);
    const stop=findButton(box,"Zatrzymaj"); const controls=stop.parentElement;
    await act(async()=>stop.click());
    assert.equal(calls.filter((c)=>c.url.endsWith("/cancel")).length,1);
    assert.equal(stop.parentElement,controls); assert.match(box.textContent??"",/Zatrzymywanie obliczeń/);
    await act(async()=>stream.emit({run_id:"r1",seq:3,kind:"end",timestamp:2,payload:{status:"cancelled"}}));
    await act(async()=>stream.emit({run_id:"r1",seq:1,kind:"run",timestamp:1,payload:{status:"running"}}));
    assert.equal(stream.closed,true); assert.equal(stop.disabled,true);
    assert.equal(findButton(box,"Rozpocznij eksperyment").disabled,false);
  } finally { await act(async()=>root.unmount());box.remove();globalThis.fetch=oldFetch; }
});

test("reloaded selected run replays persisted events; disconnect never cancels computation",async()=>{
  const oldFetch=globalThis.fetch;const calls:string[]=[];Stream.instances=[];
  localStorage.setItem("cooperation-lab.run","r1");
  const event:LabEvent={run_id:"r1",seq:1,kind:"message",timestamp:1,payload:{sender:"A",recipient:"B",content:"Saved message",kind:"message"}};
  globalThis.fetch=async(url,init)=>{
    calls.push((init?.method??"GET")+" "+String(url));
    if(String(url).endsWith("/capabilities"))return response(caps);
    if(String(url).includes("/events"))return response({events:[event],last_seq:1});
    if(String(url).endsWith("/runs/r1"))return response({run:aRun()});
    return response({runs:[aRun()]});
  };
  const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
  try {
    await act(async()=>root.render(<CooperationLabPage/>));await settle();
    assert.match(box.textContent??"",/Saved message/);assert.match(Stream.instances[0].url,/after=1/);
    await act(async()=>{const stream=Stream.instances[0];stream.onerror?.();stream.onerror?.();stream.onerror?.();});
    assert.match(box.textContent??"",/Połączenie przerwane/);
    assert.equal(findButton(box,"Zatrzymaj").disabled,false);
    assert.ok(calls.every((c)=>c.startsWith("GET ")));
    await act(async()=>findButton(box,"Odśwież").click());await settle();
    assert.match(box.textContent??"",/Połączenie przerwane/);
    assert.equal(Stream.instances.length,1);
    await act(async()=>findButton(box,"Połącz ponownie").click());await settle();
    assert.equal(Stream.instances.length,2);assert.equal(box.querySelectorAll("ol li").length,1);
  }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=oldFetch;localStorage.clear();}
});

test("failed discovery and invalid server data remain visible without starting a model",async()=>{
  const oldFetch=globalThis.fetch;localStorage.clear();
  globalThis.fetch=async()=>response({unexpected:"shape"});
  const box=document.createElement("div");const root=createRoot(box);
  try{
    await act(async()=>root.render(<CooperationLabPage/>));await settle();
    assert.equal(box.querySelector('output.coop-notice')?.textContent?.trim(), "Otrzymano nieprawidłowe dane z laboratorium.");
    assert.equal(box.querySelector("details code")?.textContent, "invalid_response");
    assert.equal(findButton(box,"Rozpocznij eksperyment").disabled,true);
    globalThis.fetch=async()=>{throw new Error("network");};
    await act(async()=>findButton(box,"Odśwież").click());await settle();
    assert.equal(box.querySelector('output.coop-notice')?.textContent?.trim(), "Brak połączenia z laboratorium.");
    assert.equal(box.querySelector("details code")?.textContent, "connection_unavailable");
  }finally{await act(async()=>root.unmount());globalThis.fetch=oldFetch;}
});


test("readiness reasons and unknown errors share one fixed notice slot and preserve stable diagnostic codes", async () => {
  const oldFetch = globalThis.fetch;
  localStorage.clear();
  let reason = "runtime_admission_disabled";
  globalThis.fetch = async (url, init) => {
    assert.ok(!init?.method || init.method === "GET");
    return String(url).endsWith("/capabilities")
      ? response({...caps, ready:false, state:"not_ready", reason_code:reason})
      : response({runs:[]});
  };
  const box = document.createElement("div"); document.body.append(box);
  const root = createRoot(box);
  try {
    await act(async () => root.render(<CooperationLabPage/>)); await settle();
    const notice = box.querySelector('output.coop-notice')!;
    const controls = findButton(box, "Zatrzymaj").parentElement;
    assert.match(notice.className, /h-5/);
    assert.equal(notice.textContent?.trim(), "Współdzielona kontrola zasobów jest wyłączona.");
    assert.equal(box.querySelector("details code")?.textContent, reason);
    assert.equal(findButton(box, "Rozpocznij eksperyment").disabled, true);
    for (const [next, translated] of [
      ["module_disabled", "Laboratorium jest wyłączone."],
      ["future_backend_code", "Nie udało się wykonać operacji."],
    ]) {
      reason = next;
      await act(async () => findButton(box, "Odśwież").click()); await settle();
      assert.equal(box.querySelector('output.coop-notice'), notice);
      assert.equal(notice.textContent?.trim(), translated);
      assert.equal(box.querySelector("details code")?.textContent, next);
      assert.equal(findButton(box, "Zatrzymaj").parentElement, controls);
    }
  } finally {
    await act(async () => root.unmount()); box.remove(); globalThis.fetch = oldFetch; localStorage.clear();
  }
});


test("selected Qwen history shows its actual immutable settings and module styles work without host Tailwind", async () => {
  const oldFetch = globalThis.fetch;
  localStorage.clear(); Stream.instances = [];
  localStorage.setItem("cooperation-lab.run", "qwen-history");
  const selected: Run = {id:"qwen-history", status:"running", created:1,last_seq:0,bytes:1,
    config:{model:{model_id:"qwen3-4b-control"},scenario_id:"correction",mode:"no_contact",seed:17,budgets:{max_turns:4,max_new_tokens:32}}};
  globalThis.fetch = async (url, init) => {
    assert.ok(!init?.method || init.method === "GET");
    const path = new URL(String(url),"http://localhost:3300").pathname;
    if (path.endsWith("/capabilities")) return response(caps);
    if (path.endsWith("/events")) return response({events:[]});
    if (path.endsWith("/runs/qwen-history")) return response({run:selected});
    return response({runs:[selected]});
  };
  const box = document.createElement("div"); document.body.append(box); const root = createRoot(box);
  try {
    await act(async () => root.render(<CooperationLabPage/>)); await settle();
    const settings = box.querySelector<HTMLFieldSetElement>("fieldset.coop-settings")!;
    assert.equal(settings.disabled,true);
    assert.deepEqual([...settings.querySelectorAll("select")].map((select) => select.value),["qwen3-4b-control","correction","no_contact","en"]);
    assert.deepEqual([...settings.querySelectorAll("input")].map((input) => input.value),["4","32","17"]);
    const view = box.querySelector<HTMLElement>(".coop-workspace")!;
    const body = box.querySelector<HTMLElement>(".coop-body")!;
    assert.equal(dom.window.getComputedStyle(view).display,"flex");
    assert.equal(dom.window.getComputedStyle(view).overflow,"hidden");
    assert.equal(dom.window.getComputedStyle(body).overflowY,"auto");
    assert.equal(dom.window.getComputedStyle(findButton(box,"Rozpocznij eksperyment")).backgroundColor,"rgb(6, 95, 70)");
    assert.equal(dom.window.getComputedStyle(findButton(box,"Zatrzymaj")).backgroundColor,"rgb(159, 18, 57)");
    assert.equal(view.style.getPropertyValue("--coop-top"),"0px");
  } finally {
    await act(async () => root.unmount()); box.remove(); globalThis.fetch=oldFetch; localStorage.clear();
  }
});


test("switching Qwen history to RWKV replaces the model with its dotted immutable ID", async () => {
  const oldFetch = globalThis.fetch;
  localStorage.clear(); Stream.instances = [];
  localStorage.setItem("cooperation-lab.run", "qwen-history");
  const saved = (id:string, model:string, turns:number, tokens:number, seed:number):Run => ({id,status:"completed",created:1,last_seq:0,bytes:1,
    config:{model:{model_id:model},scenario_id:"split_facts",mode:"dialog",seed,budgets:{max_turns:turns,max_new_tokens:tokens}}});
  const qwen = saved("qwen-history","qwen3-4b-control",4,32,17);
  const rwkv = saved("rwkv-history","rwkv7-g1d-0.4b",2,16,3);
  globalThis.fetch = async (url, init) => {
    assert.ok(!init?.method || init.method === "GET");
    const path = new URL(String(url),"http://localhost:3300").pathname;
    if (path.endsWith("/capabilities")) return response(caps);
    if (path.endsWith("/events")) return response({events:[]});
    if (path.endsWith("/runs/qwen-history")) return response({run:qwen});
    if (path.endsWith("/runs/rwkv-history")) return response({run:rwkv});
    return response({runs:[qwen,rwkv]});
  };
  const box = document.createElement("div"); document.body.append(box); const root = createRoot(box);
  try {
    await act(async () => root.render(<CooperationLabPage/>)); await settle();
    const settings = box.querySelector<HTMLFieldSetElement>("fieldset.coop-settings")!;
    const model = settings.querySelector("select")!;
    assert.equal(model.value,"qwen3-4b-control");
    const history = [...box.querySelectorAll("select")].find((select) => select.parentElement?.textContent?.startsWith("Historia prób"))!;
    assert.equal(history.disabled,false);
    await act(async () => {history.value="rwkv-history"; history.dispatchEvent(new dom.window.Event("change",{bubbles:true}));}); await settle();
    assert.equal(history.value,"rwkv-history");
    assert.equal(model.value,"rwkv7-g1d-0.4b");
    assert.deepEqual([...settings.querySelectorAll("input")].map((input) => input.value),["2","16","3"]);
  } finally {
    await act(async () => root.unmount()); box.remove(); globalThis.fetch=oldFetch; localStorage.clear();
  }
});


test("tic-tac-toe selects dialog and nine moves and live game events update the board",async()=>{
 const old=globalThis.fetch;localStorage.clear();Stream.instances=[];
 const game:Run={...aRun(),config:{model_id:"rwkv7-g1d-0.4b",scenario_id:"tic_tac_toe",mode:"dialog",communication_language:"pl",budgets:{max_turns:9,max_new_tokens:128}}};
 let posted:Record<string,unknown>|null=null;
 globalThis.fetch=async(url,init)=>{
  const path=new URL(String(url),"http://localhost").pathname;
  if(path.endsWith("/capabilities"))return response(caps);
  if(init?.method==="POST"&&path.endsWith("/runs")){posted=JSON.parse(String(init.body));return response({run:game,created:true},202);}
  if(path.endsWith("/events"))return response({events:[],last_seq:0});
  if(path.endsWith("/runs/r1"))return response({run:game});
  return response({runs:[]});
 };
 const box=document.createElement("div");document.body.append(box);const root=createRoot(box);
 try{
  await act(async()=>root.render(<CooperationLabPage/>));await settle();
  const selector=[...box.querySelectorAll("select")].find(s=>s.parentElement?.textContent?.startsWith("Scenariusz"))!;
  await act(async()=>{selector.value="tic_tac_toe";selector.dispatchEvent(new dom.window.Event("change",{bubbles:true}));});
  const mode=[...box.querySelectorAll("select")].find(s=>s.parentElement?.textContent?.startsWith("Wariant"))!;
  assert.equal(mode.value,"dialog");assert.equal(mode.options.length,1);assert.equal(mode.options[0].textContent,"Gra naprzemienna");
  const turns=box.querySelector<HTMLInputElement>('input[type="number"]')!;
  assert.equal(turns.value,"9");assert.equal(turns.max,"9");assert.equal(posted,null);
  assert.equal(box.querySelectorAll(".coop-game-board tbody td").length,9);
  await act(async()=>findButton(box,"Rozpocznij eksperyment").click());await settle();
  assert.equal((posted as unknown as Record<string,unknown>).scenario_id,"tic_tac_toe");
  assert.equal((posted as unknown as Record<string,unknown>).max_turns,9);
  assert.ok(Stream.instances[0].listeners.has("game"));
  await act(async()=>Stream.instances[0].emit({run_id:"r1",seq:1,kind:"game",timestamp:1,payload:{board:["X","X","X","O","O","","","",""],winner:"A",finished:true,draw:false,next_player:null}}));
  assert.match(box.querySelector(".coop-game-state")?.textContent??"",/Wygrywa: A/);
  assert.equal(box.querySelector('[aria-label="A1"]')?.textContent,"X");
 }finally{await act(async()=>root.unmount());box.remove();globalThis.fetch=old;localStorage.clear();}
});
