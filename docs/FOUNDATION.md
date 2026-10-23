# L1: optional module foundation

> Current host/CI qualification (2026-10-23): `e313319f2367599794be3231bda9d22df5a3daef`,
> ABI 1.0.0. Source of truth: [host-compatibility.json](../host-compatibility.json).
> The L1–L5 / 2026-10-21 acceptance and deployment SHAs below are historical;
> their measurements have not been rewritten. PR #19 contains the new recovery
> and repeatable-start acceptance.


This slice installs `venom-module-cooperation-lab` / `venom_module_cooperation_lab`
without GPU imports, downloads or generated runs. It is disabled by default.
The private repository stores source code only; SQLite, model weights and private
prompts must stay outside Git. The independent `/cooperation-lab` screen is a
truthful unavailable/not-ready workspace until C0 and L2–L4 are qualified.

## Host and activation

Original ABI baseline: `aa2d612434949f1149d27f64ff10e5dd05334e8e`; historically
qualified host/CI pin: `7401493f73db98dcdf2cb39503fca57eb2cbe421` after cleanup
follow-up. Historical GPU/matrix revisions remain unchanged. Module API **1.0.0**,
minimum runtime **1.6.0**, Python 3.12+, Node 24.22.0. See
[host-compatibility.json](../host-compatibility.json). These two version numbers
must not be conflated. CI checks this exact source SHA; updating it is a reviewed
compatibility change. This C0 host declares `FEATURE_COOPERATION_LAB: bool = False`
and `RUNTIME_ADMISSION_ENABLED: bool = False` in its Settings. Settings is the
single source of truth for backend flags, including values read from ENV_FILE.

Install the module into the existing host environment without installing a
second runtime: `HOST/.venv/bin/python -m pip install --no-deps --no-build-isolation .`.
The active instance is **not** registered by this slice. An explicit future
activation adds `manifest:modules/venom-module-cooperation-lab/module.json` to the
host's optional manifest configuration and enables both
`FEATURE_COOPERATION_LAB` and `NEXT_PUBLIC_FEATURE_COOPERATION_LAB`. The host owns
its manifest-generated route/menu. Flag OFF means no router, lifespan, data
creation or frontend polling. Missing/incompatible manifests are quarantined by
the host. Disable both flags and remove the manifest to roll back; retained data
is deliberately preserved.

L1 startup has no inference. It prepares only the namespaced schema. Host router
lifecycle boundaries isolate failures; SQLite lock wait is capped at one second.
No background storage task or automatic experiment starts. Health remains
`ready=false`; C0 disabled is `runtime_admission_disabled`, otherwise missing
qualification is explicit. GET never triggers model preparation.

## Storage contract

`LabStore.from_host(access_guard)` resolves `cooperation_lab` with host
`resolve_module_data_root` and enforces `ensure_module_mutation_allowed` before
creation, migration, recovery and every write. Access policy is mandatory;
there is no permissive default. The L1 internal store denies all run-data access.
The later runner supplies a trusted host policy and actor/owner. Browser/model
JSON never defines these identities. Discovery uses the host's localhost policy.
Deletion/export/read still require that policy; another owner receives 404.

Version 1 schema atomically contains runs, events, settings and qualifications.
A newer unknown schema fails closed. Explicit open marks prior nonterminal runs
`interrupted`, with no resume. One active database run is enforced by a partial
unique index; idempotency is scoped to owner and exact config. The runner in L3
adds transition rules; storage does not pretend to perform generation.

Limits are frozen in [CONTRACTS](CONTRACTS.md): 100 runs, 14 days, 512MiB across
`lab.sqlite3`, `-wal` and `-shm`, 2MiB retained payload/run, 64KiB/event, minimum
64MiB free. SQLite page/WAL overhead counts toward physical storage, while UTF-8
payload plus envelope reserve counts toward run size. Retention deletes terminal
runs only; it does not delete active runs to make a test pass. Reaching the run
quota returns an explicit error. All table names are hardcoded allowlisted.

An export reads bounded pages into at most a 4MiB JSON response and never creates
a persistent second copy. There is no automatic VACUUM: it needs a separate free
space budget. Disk-full/low-space errors are visible, never silent missing logs.
Private events belong to this namespace, not global host logs.

## Validation and scanners

`make check HOST=/home/ubuntu/venom` uses the host's existing Python/Node tools:
Ruff, mypy, pytest with >=90% coverage, TS, ESLint, Node tests and the real host
optional-module contract checker. CI checks out the pinned host into `host/`
and this module into `host/modules/venom-module-cooperation-lab`; it installs
only the host CI profile (no Torch/model download) and host frontend packages.
All fixture tests are labelled tests, never research model results.

The Sonar project `mpieniak01_venom-module-cooperation-lab` and CI credentials
were configured by the coordinator in organization `mpieniak01`; Snyk is pinned
to organization `fcc7b7c7-65c1-46dc-b715-c9de506a1942`. A real local Snyk scan of
requirements.txt examined 10 dependencies with zero vulnerable paths. This does
not by itself replace SCM/CI, Sonar or review. Those later gates and the real
browser/proxy acceptance are now recorded in [RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md),
including the passed reviewed PR #13 revision and the fresh final-commit CI
requirement before merge. This section describes the L1 slice, not the later
operator acceptance. No secrets are stored in source; missing secrets are never
reported as successful scans. The React workspace has meaningful DOM tests and LCOV.

Flagi backendu są odczytywane z host SETTINGS (Pydantic), także gdy plik .env nie jest eksportowany do os.environ. Limit busy_timeout SQLite ogranicza czekanie na blokadę; timeout async lifecycle nie przerywa synchronicznego I/O systemu plików.
