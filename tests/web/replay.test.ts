import assert from "node:assert/strict";
import test from "node:test";
import { readReplay, replayedRun } from "../../web-next/lib/replay";
import type { LabEvent, Run } from "../../web-next/lib/protocol";

const event = (seq:number, kind:string, status:LabEvent["payload"]["status"]):LabEvent => ({run_id:"r1",seq,kind,timestamp:seq,payload:{status}});
const snapshot:Run = {id:"r1",status:"running",created:1,last_seq:0,bytes:1,config:{}};

test("replay uses the latest typed status and never stringifies an object status", () => {
  const replayed = replayedRun(snapshot,[event(1,"end","completed"),event(2,"run",{unexpected:"running"})],2);
  assert.equal(replayed.status,"completed");
  assert.equal(replayed.last_seq,2);
  assert.equal(snapshot.status,"running");
  assert.equal(replayedRun(snapshot,[event(1,"message","cancelled")],1).status,"running");
});

test("catch-up is bounded to four GET pages and stops applying results after disposal", async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  const abort = new AbortController();
  globalThis.fetch = async (_url, init) => {
    assert.ok(!init?.method || init.method === "GET");
    const first = calls++ * 100 + 1;
    return {ok:true,status:200,json:async()=>({events:Array.from({length:100},(_,index)=>event(first+index,"run","running"))})} as Response;
  };
  try {
    const result = await readReplay("r1",abort.signal,()=>true);
    assert.equal(calls,4);
    assert.equal(result?.cursor,400);
    assert.equal(result?.events.length,256);
    assert.equal(await readReplay("r1",abort.signal,()=>false),null);
    assert.equal(calls,5);
  } finally { globalThis.fetch=previous; }
});
