import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import CooperationLabPage from "../../web-next/page";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3300/cooperation-lab" });
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true });

test("actual workspace discovery, explicit refresh, unavailable and disabled states", async () => {
  const calls: string[] = [];
  let result: unknown = { state: "not_ready", ready: false };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push(String(url));
    assert.equal(init?.method, undefined);
    return { ok: true, json: async () => result } as Response;
  };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => { root.render(<CooperationLabPage />); });
    assert.match(container.textContent ?? "", /nie został jeszcze zakwalifikowany/);
    assert.equal(container.querySelectorAll("button")[1].disabled, true);
    assert.equal(calls.length, 1);
    result = { state: "disabled" };
    await act(async () => { container.querySelector("button")?.click(); });
    assert.match(container.textContent ?? "", /Moduł wyłączony/);
    globalThis.fetch = async () => ({ ok: false }) as Response;
    await act(async () => { container.querySelector("button")?.click(); });
    assert.match(container.textContent ?? "", /Połączenie niedostępne/);
    globalThis.fetch = async () => { throw new Error("network"); };
    await act(async () => { container.querySelector("button")?.click(); });
    assert.match(container.textContent ?? "", /Połączenie niedostępne/);
  } finally {
    await act(async () => { root.unmount(); });
    container.remove();
    globalThis.fetch = originalFetch;
  }
});

test("discovery timeout is visible and aborts only its own request", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const originalFetch = globalThis.fetch;
  let signal: AbortSignal | undefined;
  globalThis.fetch = async (_url, init) => {
    signal = init?.signal ?? undefined;
    return new Promise<Response>(() => {});
  };
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () => { root.render(<CooperationLabPage />); });
    assert.match(container.textContent ?? "", /Sprawdzanie gotowości/);
    await act(async () => { context.mock.timers.tick(5001); });
    assert.equal(signal?.aborted, true);
    assert.match(container.textContent ?? "", /Połączenie niedostępne/);
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
    context.mock.timers.reset();
  }
});
