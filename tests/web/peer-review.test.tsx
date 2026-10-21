import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { Conversation } from "../../web-next/lib/chat";
import { OperatorComposer } from "../../web-next/lib/operator-composer";
import { scenarioPolicy, selectScenario, selectMode } from "../../web-next/lib/experiment-settings";
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


test("scenario controls allowed variants, turn budgets and startup; variant never changes scenario",()=>{
 const draft={model:"rwkv7-g1d-0.4b",scenario:"split_facts",mode:"dialog_encouraged",turns:8,tokens:128,seed:0,communicationLanguage:"pl" as const};
 const review=selectScenario(draft,"peer_review");
 assert.equal(review.mode,"operator_review");assert.equal(review.turns,6);
 assert.deepEqual(scenarioPolicy(review.scenario)?.modes,["operator_review"]);
 assert.equal(selectMode(review,"operator_relay"),review);
 const game=selectScenario(review,"tic_tac_toe");
 assert.equal(game.mode,"dialog");assert.equal(game.turns,9);assert.equal(scenarioPolicy(game.scenario)?.entry,"automatic");
 const chat=selectScenario(game,"operator_conversation");
 assert.equal(chat.mode,"operator_chat");assert.equal(chat.turns,8);assert.equal(scenarioPolicy(chat.scenario)?.entry,"operator");
 const relay=selectMode(chat,"operator_relay");assert.equal(relay.scenario,chat.scenario);assert.equal(relay.mode,"operator_relay");
 const task=selectScenario(relay,"split_facts");assert.equal(task.mode,"dialog_encouraged");assert.equal(task.turns,8);
 assert.equal(scenarioPolicy("unknown"),null);assert.equal(selectScenario(task,"unknown"),task);
 assert.equal(scenarioPolicy("organization")?.modes.length,5);assert.equal(scenarioPolicy("correction")?.step,1);
});
