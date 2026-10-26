import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { Conversation, recordedTime } from "../../web-next/lib/chat";
import type { LabEvent } from "../../web-next/lib/protocol";

const first:LabEvent = {run_id:"r1",seq:5,kind:"message",timestamp:1792580400.123,
  payload:{message_id:"a1",sender:"A",recipient:"B",kind:"ask",content:"Co wiesz?",delivered_to:["B"]}};
const second:LabEvent = {...first,seq:8,timestamp:1792580401.456,
  payload:{message_id:"b1",sender:"B",recipient:"A",kind:"message",content:"<img src=x onerror=alert(1)>",in_reply_to:"a1",delivered_to:["A"]}};

test("chat keeps sender, recipient, exact persisted time and reply reference without unsafe HTML", () => {
 const box=new JSDOM(renderToStaticMarkup(<Conversation events={[first,second]} language="pl"/>), {url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.equal(box.querySelectorAll(".coop-message").length,2);
 assert.equal(box.querySelector('[data-sender="B"] .coop-message-route')?.textContent,"B → A");
 assert.equal(box.querySelector('a.coop-reply')?.getAttribute("href"),"#coop-message-5");
 assert.equal(box.querySelector("time")?.getAttribute("datetime"),"2026-10-21T11:00:00.123Z");
 assert.match(box.querySelector("time")?.textContent??"",/[,.]123/);
 assert.match(box.body.textContent??"",/Przekazano do B/);
 assert.match(box.body.textContent??"",/Pytanie/);
 assert.equal(box.querySelector("img"),null);
 assert.match(box.body.textContent??"",/<img src=x onerror=alert/);
});

test("chat never invents delivery or timestamps and translates message labels", () => {
 const event={...first,timestamp:NaN,payload:{sender:"A",recipient:"all",kind:"complete",content:"Done",in_reply_to:"missing",delivered_to:[]}};
 const box=new JSDOM(renderToStaticMarkup(<Conversation events={[event]} language="en"/>), {url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.match(box.body.textContent??"",/A → Everyone/);
 assert.match(box.body.textContent??"",/Not forwarded in this condition/);
 assert.match(box.body.textContent??"",/Time unknown/);
 assert.match(box.body.textContent??"",/Reply to an earlier message/);
 assert.match(box.body.textContent??"",/Completion claim/);
 assert.equal(box.querySelector("time"),null);
 assert.equal(recordedTime(Infinity,"pl"),null);
 const unknown=new JSDOM(renderToStaticMarkup(<Conversation events={[{...first,payload:{content:"Hi"}}]} language="en"/>), {url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.match(unknown.body.textContent??"",/Delivery unconfirmed/);
});


test("chat labels actual use of an applicable private rule without inventing it for old moves",()=>{
 const events:LabEvent[]=[first,{...second,payload:{...second.payload,rule_application:{rule_id:"win_now",applicable:true,followed:false}}},{...second,seq:9,payload:{...second.payload,rule_application:{rule_id:"block_win",applicable:true,followed:true}}}];
 const doc=new JSDOM(renderToStaticMarkup(<Conversation events={events} language="pl"/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.equal(doc.querySelectorAll("[data-rule-use]").length,2);
 assert.equal(doc.querySelector('[data-rule-use="ignored"]')?.textContent,"Reguła zignorowana: win_now");
 assert.equal(doc.querySelector('[data-rule-use="followed"]')?.textContent,"Reguła zastosowana: block_win");
});
