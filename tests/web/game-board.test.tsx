import assert from "node:assert/strict";
import test from "node:test";
import {renderToStaticMarkup} from "react-dom/server";
import {JSDOM} from "jsdom";
import {GameBoard,GameSeriesResults,GameReflections} from "../../web-next/lib/game-board";
import type {LabEvent} from "../../web-next/lib/protocol";
const render=(event?:LabEvent,ended=false)=>new JSDOM(renderToStaticMarkup(<GameBoard event={event} ended={ended} language="pl"/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
const event:LabEvent={run_id:"game",seq:4,kind:"game",timestamp:1,payload:{board:["X","X","X","O","O","","","",""],winner:"A",finished:true,draw:false,next_player:null}};
test("game board shows nine labelled squares and only referee-confirmed outcomes",()=>{
 const empty=render();assert.equal(empty.querySelectorAll("tbody td").length,9);
 assert.match(empty.body.textContent??"",/Następny ruch: A/);
 const win=render(event);assert.equal(win.querySelector('[aria-label="A3"]')?.textContent,"X");
 assert.match(win.body.textContent??"",/Wygrywa: A \(X\)/);
 const draw=render({...event,payload:{...event.payload,winner:null,draw:true}});
 assert.match(draw.body.textContent??"",/Remis/);
 const incomplete=render(undefined,true);assert.match(incomplete.body.textContent??"",/Partia nierozstrzygnięta/);
 const unknown=render({...event,payload:{board:["X"],winner:"A",finished:true}});
 assert.match(unknown.body.textContent??"",/Stan planszy nieznany/);assert.equal(unknown.querySelector("table"),null);
});


test("series board shows actual progress and per-game results",()=>{
 const seriesEvent={...event,payload:{...event.payload,series:{number:2,total:3,remember_games:true,results:[{number:1,winner:null,draw:true,moves:["A:A1"]},{number:2,winner:"A",draw:false,moves:["A:B2"]}]}}};
 const doc=new JSDOM(renderToStaticMarkup(<><GameBoard event={seriesEvent} ended={false} language="pl"/><GameSeriesResults event={seriesEvent} events={[]} language="pl"/></>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.match(doc.body.textContent??"",/Partia 2 \/ 3/);
 const results=doc.querySelector('[aria-label="Wyniki serii"]')!;
 assert.deepEqual([...results.querySelectorAll(".coop-game-balance tbody td")].map(n=>n.textContent),["1","0","1"]);
 assert.deepEqual([...results.querySelectorAll(".coop-game-results-table thead th")].map(n=>n.textContent),["Partia","Wynik","Ruchy"]);
 assert.deepEqual([...results.querySelectorAll(".coop-game-results-table tbody tr")].map(n=>[...n.children].map(c=>c.textContent)),[["1","Remis","1"],["2","A (X)","1"]]);
 assert.equal(results.querySelector("details"),null);
 assert.equal(results.querySelector(".coop-messages"),null);
 assert.equal(doc.querySelector('[aria-label="Kółko i krzyżyk"] [aria-label="Wyniki serii"]'),null);
});


test("rejected reflections are labelled and raw output is separate from accepted memory",()=>{
 const notes:LabEvent[]=[
  {run_id:"game",seq:1,kind:"reflection",timestamp:1,payload:{player:"A",game_number:1,accepted:false,reason_code:"instruction_echo",content:"",raw_content:"copied instruction"}},
  {run_id:"game",seq:2,kind:"reflection",timestamp:2,payload:{player:"B",game_number:1,accepted:true,reason_code:"accepted",content:"Take an immediate winning move before trying to block."}},
 ];
 const doc=new JSDOM(renderToStaticMarkup(<GameReflections events={notes} language="pl"/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.match(doc.querySelector('[role="status"]')?.textContent??"",/Nie zapisano do pamięci: Model skopiował instrukcję/);
 assert.equal(doc.querySelector("pre")?.textContent,"copied instruction");
 assert.match(doc.body.textContent??"",/Zapisano do pamięci/);
 assert.match(doc.body.textContent??"",/Take an immediate winning move/);
});


test("evidence checks, historical format-only notes and skipped notes have different labels",()=>{
 const notes:LabEvent[]=[
  {run_id:"game",seq:1,kind:"reflection",timestamp:1,payload:{player:"A",game_number:1,accepted:false,skipped:true,reason_code:"no_supported_mistake",content:""}},
  {run_id:"game",seq:2,kind:"reflection",timestamp:2,payload:{player:"B",game_number:1,accepted:true,content:"Block an immediate threat.",note_source:"model_selected_host_catalog_rule",raw_content:"block_win",validation:{orientations_checked:8}}},
  {run_id:"game",seq:3,kind:"reflection",timestamp:3,payload:{player:"A",game_number:2,accepted:true,content:"An old unverified rule."}},
 ];
 const doc=new JSDOM(renderToStaticMarkup(<GameReflections events={notes} language="pl"/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 const text=doc.body.textContent??"";
 assert.match(text,/Pominięte notatki: Brak własnego błędu/);
 assert.match(text,/Reguła potwierdzona na błędzie i 8 orientacjach/);
 assert.match(text,/Historyczna kontrola formatu/);
 assert.equal(doc.querySelector("pre")?.textContent,"block_win");
 assert.match(text,/Model wybrał regułę z podanych możliwości/);
});
