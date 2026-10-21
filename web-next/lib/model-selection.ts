import type { Model } from "./protocol";
export function engineId(model:Model):string { return model.engine_id??model.provider??"local_component"; }
export function modelState(model:Model,t:{modelReady:string;modelPending:string;modelUnsupported:string;modelOffline:string}):string {
  if(model.availability_reason==="adapter_not_supported")return t.modelUnsupported;
  if(model.qualified)return t.modelReady;
  return model.can_qualify?t.modelPending:t.modelOffline;
}
