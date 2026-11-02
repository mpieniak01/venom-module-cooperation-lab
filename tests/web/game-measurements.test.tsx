import assert from "node:assert/strict";
import test from "node:test";
import {renderToStaticMarkup} from "react-dom/server";
import {JSDOM} from "jsdom";
import {GameMeasurements,measuredRatio} from "../../web-next/lib/game-measurements";
import {GameReflections} from "../../web-next/lib/game-board";
import {savedSettings} from "../../web-next/lib/workspace";
import {messages} from "../../web-next/lib/i18n";
import type {Json,LabEvent} from "../../web-next/lib/protocol";

const measurement:Json={version:"live-tactical-measurement-v1",totals:{proposals:5,legal_moves:4,optimal_moves:2,win_opportunities:2,wins_taken:1,block_opportunities:0,blocks_taken:0,rule_opportunities:2,rule_followed:0,first_empty_choices:3,invalid_format:1,illegal_moves:0,unavoidable_threats:1,repeated_tactical_errors:1},
 games:[{number:1,status:"completed",legal_moves:4,proposals:4,optimal_moves:2},{number:2,status:"failed",legal_moves:0,proposals:1}],
 rules:{A:{win_now:{with_reminder:{opportunities:2,followed:0},without_reminder:{opportunities:1,followed:1}}}},
 transfer:{A:{source_equivalent:{opportunities:1,followed:0},new_position:{opportunities:1,followed:1}}},failure_category:"format"};
const render=(value:Json|undefined,language="pl")=>new JSDOM(renderToStaticMarkup(<GameMeasurements measurement={value} language={language}/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;

test("zero opportunities, unknown fields and invalid counts are unassessed",()=>{
 for(const [a,b] of [[0,0],[undefined,1],[1,undefined],[-1,2],[2,1],[1.5,2],[true,2]] as const)assert.equal(measuredRatio(a,b,"missing"),"missing");
 assert.equal(measuredRatio(0,4,"missing"),"0/4 (0%)");
 assert.equal(measuredRatio(1,4,"missing"),"1/4 (25%)");
 for(const value of [undefined,null,[],{version:"other"}])assert.match(render(value).body.textContent??"",/brak danych nie oznacza zera/);
});

test("measurements expose denominators, partial games, recurrence and real rule application",()=>{
 const doc=render(measurement),text=doc.body.textContent??"";
 assert.match(text,/Legalne \/ propozycje4\/5 \(80%\)/);
 assert.match(text,/Bloki \/ możliwe blokiNie oceniono/);
 assert.match(text,/Zastosowania \/ okazje0\/2 \(0%\)/);
 assert.match(text,/Powtórzone błędy w równoważnej pozycji1/);
 assert.match(text,/Zatrzymano: format odpowiedzi/);
 assert.equal(doc.querySelectorAll('[aria-label="Partia 1"]').length,1);
 assert.match(text,/Z przypomnieniem0\/2/);
 assert.match(text,/Reguła na innej pozycji niż przykład1\/1/);
 for(const [code,label] of [["illegal_move","nielegalny ruch"],["infrastructure","infrastruktura"],["cancelled","żądanie"]])assert.match(render({...measurement as object,failure_category:code}).querySelector('[role="status"]')?.textContent??"",new RegExp(label));
 assert.equal(render({version:"live-tactical-measurement-v1"}).querySelector('[role="status"]'),null);
});

test("new measurement labels have locale parity and grounded memory restores explicitly",()=>{
 for(const lang of ["pl","en","de"] as const){
  assert.deepEqual(Object.keys(messages[lang]).sort(),Object.keys(messages.en).sort());
  assert.match(render(measurement,lang).body.textContent??"",/4\/5/);
 }
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode:"game_reflection",reflection_context:"grounded_example"}).reflectionContext,"grounded_example");
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode:"game_reflection"}).reflectionContext,"rule_only");
 const note:LabEvent={run_id:"fixture",seq:1,kind:"reflection",timestamp:1,payload:{game_number:1,player:"A",accepted:true,note_source:"model_selected_host_catalog_rule",content:"rule",validation:{orientations_checked:8}}};
 const doc=new JSDOM(renderToStaticMarkup(<GameReflections events={[note]} language="pl"/>),{url:"http://localhost:3300/cooperation-lab"}).window.document;
 assert.match(doc.body.textContent??"",/Poprawna reguła wskazana; zapisano do pamięci/);
 assert.match(doc.body.textContent??"",/stosowanie jej przez model nie zostało potwierdzone/);
});
