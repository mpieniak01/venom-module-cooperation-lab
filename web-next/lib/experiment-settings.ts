import type { SavedSettings } from "./workspace";
const controls=["single","self_correction","no_contact","dialog","dialog_encouraged"];
export function scenarioPolicy(scenario:string) {
  switch(scenario){
    case "tic_tac_toe":return {modes:["dialog","game_competitive"],defaultMode:"dialog",turns:9,min:1,max:9,step:1,entry:"automatic"};
    case "peer_review":return {modes:["operator_review"],defaultMode:"operator_review",turns:6,min:3,max:6,step:3,entry:"operator"};
    case "operator_conversation":return {modes:["operator_chat","operator_relay"],defaultMode:"operator_chat",turns:8,min:2,max:8,step:2,entry:"operator"};
    case "split_facts":case "organization":case "correction":return {modes:controls,defaultMode:"dialog_encouraged",turns:8,min:1,max:8,step:1,entry:"automatic"};
    default:return null;
  }
}
export function selectScenario<T extends SavedSettings>(form:T,scenario:string):T {
  const policy=scenarioPolicy(scenario);if(!policy)return form;
  return {...form,scenario,mode:policy.modes.includes(form.mode)?form.mode:policy.defaultMode,turns:policy.turns};
}
export function selectMode<T extends SavedSettings>(form:T,mode:string):T {
  return scenarioPolicy(form.scenario)?.modes.includes(mode)?{...form,mode}:form;
}
