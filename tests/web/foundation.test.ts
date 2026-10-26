import assert from "node:assert/strict";
import test from "node:test";
import { diagnosticCode, messages, reasonLabel, scenarioLabel, texts } from "../../web-next/lib/i18n";
import { healthState } from "../../web-next/lib/health";
import { savedSettings } from "../../web-next/lib/workspace";

test("translations have identical complete keys and unknown language falls back", () => {
  const expected = Object.keys(messages.en).sort();
  for (const language of ["pl", "en", "de"] as const) {
    assert.deepEqual(Object.keys(messages[language]).sort(), expected);
    assert.ok(Object.values(texts(language)).every((text) => text.length > 0));
  }
  assert.equal(texts("invalid"), messages.en);
  assert.equal(texts("__proto__"), messages.en);
});
test("discovery never invents a ready model from invalid or future responses", () => {
  for (const value of [null, false, 1, {}, { state: "ready", ready: true }, { state: "not_ready", ready: true }]) {
    assert.equal(healthState(value), "unavailable");
  }
  assert.equal(healthState({ state: "disabled" }), "disabled");
  assert.equal(healthState({ state: "not_ready", ready: false }), "not_ready");
});


test("known readiness/error codes are translated in PL/EN/DE and future codes use a safe fallback", () => {
  const expected = {
    pl: ["Współdzielona kontrola zasobów jest wyłączona.", "Zasób modelu jest zajęty.", "Model nie ma aktualnej kwalifikacji hosta."],
    en: ["Shared runtime admission is disabled.", "The model resource is busy.", "The model has no current host qualification."],
    de: ["Die gemeinsame Ressourcenfreigabe ist deaktiviert.", "Die Modellressource ist belegt.", "Das Modell hat keine aktuelle Host-Qualifikation."],
  };
  for (const language of ["pl", "en", "de"] as const) {
    const t = texts(language);
    assert.deepEqual(["runtime_admission_disabled", "runtime_busy", "model_not_qualified"].map((code) => reasonLabel(t, code)), expected[language]);
    assert.equal(reasonLabel(t, "future_backend_code"), t.problemUnknown);
    assert.equal(reasonLabel(t, "/private/untrusted/path"), t.problemUnknown);
    assert.equal(reasonLabel(t, undefined), t.problemUnknown);
    assert.equal(reasonLabel(t, "__proto__"), t.problemUnknown);
    assert.equal(reasonLabel(t, "constructor"), t.problemUnknown);
  }
  assert.equal(diagnosticCode("future_backend_code"), "future_backend_code");
  assert.equal(diagnosticCode("/private/untrusted/path"), undefined);
});


test("saved form settings use immutable nested model/budgets and reject invalid values", () => {
  assert.deepEqual(savedSettings({model:{model_id:"rwkv7-g1d-0.4b"}}), {model:"rwkv7-g1d-0.4b"});
  assert.deepEqual(savedSettings({model:{model_id:"qwen3-4b-control"}, scenario_id:"correction", mode:"no_contact", seed:17, budgets:{max_turns:4,max_new_tokens:32}}),
    {model:"qwen3-4b-control",scenario:"correction",mode:"no_contact",seed:17,turns:4,tokens:32});
  assert.deepEqual(savedSettings({model:[],scenario_id:"unexpected",mode:"shell",seed:-1,budgets:{max_turns:9,max_new_tokens:0}}),{});
  assert.deepEqual(savedSettings({scenario_id:["split_facts"],mode:["dialog"]}),{});
  assert.deepEqual(savedSettings({model:{model_id:"/private/path"},seed:1.5,budgets:{max_turns:true,max_new_tokens:1025}}),{});
  assert.deepEqual(savedSettings({model:{model_id:".hidden"}}), {});
});


test("scenario labels are Polish while conversation language restores independently", () => {
  assert.deepEqual(["split_facts", "organization", "correction"].map(id => scenarioLabel(texts("pl"), id)),
    ["Rozdzielone informacje", "Wspólne obliczenie", "Sprawdzenie i poprawa propozycji"]);
  assert.equal(scenarioLabel(texts("en"), "split_facts"), "Split facts");
  assert.equal(scenarioLabel(texts("pl"), "future", "New task"), "New task");
  assert.equal(savedSettings({communication_language:"pl"}).communicationLanguage, "pl");
  assert.equal(savedSettings({communication_language:"en"}).communicationLanguage, "en");
  assert.equal(savedSettings({schema_version:1}).communicationLanguage, "en");
  assert.equal(savedSettings({communication_language:"fr"}).communicationLanguage, undefined);
});


test("tic-tac-toe labels and nine-move history remain scenario scoped",()=>{
 assert.equal(scenarioLabel(texts("pl"),"tic_tac_toe"),"Kółko i krzyżyk");
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",budgets:{max_turns:9}}).turns,9);
 assert.equal(savedSettings({scenario_id:"split_facts",budgets:{max_turns:9}}).turns,undefined);
});


test("competitive game variant restores with a distinct translated label",()=>{
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode:"game_competitive"}).mode,"game_competitive");
 assert.equal(texts("pl").gameCompetitive,"Gra, aby wygrać");
});


test("game series settings restore bounded count and explicit memory policy",()=>{
 const settings=savedSettings({scenario_id:"tic_tac_toe",game_count:4,remember_games:false});
 assert.equal(settings.gameCount,4);assert.equal(settings.rememberGames,false);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",game_count:99}).gameCount,1);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe"}).rememberGames,true);
});


test("live game modes restore from conversation history",()=>{
 for(const mode of ["game_strategic","game_reflection","game_assisted"]){
  assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode}).mode,mode);
 }
});


test("independent reflection budget restores explicit settings and historical 64-token limits",()=>{
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode:"game_reflection",reflection_max_new_tokens:192}).reflectionTokens,192);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode:"game_reflection"}).reflectionTokens,64);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",mode:"dialog"}).reflectionTokens,undefined);
});


test("restoring a historical Huginn game resets stale compute steps to the effective default",()=>{
 const previous={numSteps:64};
 const restored={...previous,...savedSettings({scenario_id:"tic_tac_toe",model:{model_id:"huginn-0125",architecture:"huginn_raven"}})};
 assert.equal(restored.numSteps,8);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",model:{model_id:"huginn-0125"},num_steps:32}).numSteps,32);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",model:{model_id:"huginn-0125"},num_steps:99}).numSteps,8);
 assert.equal(savedSettings({scenario_id:"tic_tac_toe",model:{model_id:"rwkv7-g1k-2.9b"}}).numSteps,undefined);
});
