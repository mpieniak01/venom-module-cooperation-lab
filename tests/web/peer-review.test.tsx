import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { Conversation } from "../../web-next/lib/chat";
import { OperatorComposer } from "../../web-next/lib/operator-composer";
import { savedSettings } from "../../web-next/lib/workspace";
import type { LabEvent } from "../../web-next/lib/protocol";

test("review replay labels the actual phases, routes and causal reply links",()=>{
 const events:LabEvent[]=[
  {run_id:"review",seq:1,kind:"message",timestamp:1,payload:{message_id:"draft",sender:"A",recipient:"B",phase:"draft",content:"Błędna propozycja",delivered_to:["B"]}},
  {run_id:"review",seq:2,kind:"message",timestamp:2,payload:{message_id:"review",sender:"B",recipient:"A",phase:"critique",content:"Konkretna uwaga",in_reply_to:"draft",delivered_to:["A"]}},
  {run_id:"review",seq:3,kind:"message",timestamp:3,payload:{message_id:"revision",sender:"A",recipient:"operator",phase:"revision",content:"Poprawiony wynik",in_reply_to:"review",delivered_to:["operator"]}},
 ];
 const doc=new JSDOM(renderToStaticMarkup(<Conversation language="pl" events={events}/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 const messages=[...doc.querySelectorAll(".coop-message")];
 assert.equal(messages.length,3);
 assert.match(messages[0].textContent!,/Propozycja/);assert.match(messages[1].textContent!,/Recenzja/);assert.match(messages[2].textContent!,/Poprawa/);
 assert.equal(messages[2].querySelector(".coop-message-route")?.textContent,"A → Operator");
 assert.equal(messages[2].querySelector("a")?.getAttribute("href"),"#coop-message-2");
 const form=new JSDOM(renderToStaticMarkup(<OperatorComposer runId="review" active waiting sending={false} relay={false} review language="pl" onSend={async()=>true}/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.match(form.body.textContent!,/Wyślij zadanie/);assert.match(form.body.textContent!,/3 etapy/);
 assert.equal(savedSettings({scenario_id:"peer_review",mode:"operator_review",budgets:{max_turns:6}}).turns,6);
 assert.equal(savedSettings({scenario_id:"peer_review",mode:"operator_review",budgets:{max_turns:8}}).turns,undefined);
});
