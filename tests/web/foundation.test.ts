import assert from "node:assert/strict";
import test from "node:test";
import { diagnosticCode, messages, reasonLabel, texts } from "../../web-next/lib/i18n";
import { healthState } from "../../web-next/lib/health";

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
