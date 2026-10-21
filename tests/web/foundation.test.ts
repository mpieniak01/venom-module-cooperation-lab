import assert from "node:assert/strict";
import test from "node:test";
import { messages, texts } from "../../web-next/lib/i18n";
import { healthState } from "../../web-next/lib/health";

test("translations have identical complete keys and unknown language falls back", () => {
  const expected = Object.keys(messages.en).sort();
  for (const language of ["pl", "en", "de"] as const) {
    assert.deepEqual(Object.keys(messages[language]).sort(), expected);
    assert.ok(Object.values(texts(language)).every((text) => text.length > 0));
  }
  assert.equal(texts("invalid"), messages.en);
});
test("discovery never invents a ready model from invalid or future responses", () => {
  for (const value of [null, false, 1, {}, { state: "ready", ready: true }, { state: "not_ready", ready: true }]) {
    assert.equal(healthState(value), "unavailable");
  }
  assert.equal(healthState({ state: "disabled" }), "disabled");
  assert.equal(healthState({ state: "not_ready", ready: false }), "not_ready");
});
