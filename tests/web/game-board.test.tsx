import assert from "node:assert/strict";
import test from "node:test";
import {renderToStaticMarkup} from "react-dom/server";
import {JSDOM} from "jsdom";
import {GameBoard} from "../../web-next/lib/game-board";
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
