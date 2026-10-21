"use client";

import { useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { healthState, type HealthState } from "./lib/health";
import { texts } from "./lib/i18n";

export default function CooperationLabPage() {
  const { language } = useLanguage();
  const t = texts(language);
  const [state, setState] = useState<HealthState>("loading");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let mounted = true;
    const timeout = setTimeout(() => { if (mounted) setState("unavailable"); abort.abort(); }, 5000);
    fetch("/api/v1/cooperation-lab/health", { signal: abort.signal, cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : null)
      .then((value: unknown) => setState(healthState(value)))
      .catch(() => { if (!abort.signal.aborted) setState("unavailable"); })
      .finally(() => clearTimeout(timeout));
    return () => { mounted = false; clearTimeout(timeout); abort.abort(); };
  }, [revision]);
  const label = state === "not_ready" ? t.notReady : state === "disabled" ? t.disabled : state === "loading" ? t.loading : t.unavailable;
  return <section aria-labelledby="cooperation-lab-title" className="space-y-4 p-4">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h1 id="cooperation-lab-title" className="text-2xl font-semibold">{t.title}</h1>
      <button type="button" className="rounded border px-3 py-2" onClick={() => setRevision((value) => value + 1)}>{t.refresh}</button>
    </header>
    <p>{t.description}</p>
    <p role="status">{label}</p>
    <button type="button" disabled className="rounded border px-3 py-2 disabled:opacity-50">{t.start}</button>
    <p>{t.noRuns}</p>
    <details><summary>{t.limits}</summary><dl>
      <dt>{t.runs}</dt><dd>100</dd><dt>{t.retention}</dt><dd>14</dd><dt>{t.disk}</dt><dd>512</dd>
    </dl></details>
  </section>;
}
