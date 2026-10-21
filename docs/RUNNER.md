# L3 runner and API v1

The host owns one detached experiment task and keeps strong references to every
actual CPU/subprocess operation. HTTP disconnect does not cancel inference or
release its lease. Two independent A/B histories share only immutable model
weights. The fair scheduler alternates A/B; single/self-correction use A only.
No-contact does not deliver partner messages. The encouragement variant lets
models propose a division of work without host-assigned roles.

## Qualification and identity

Only the trusted host's local administrative transport is accepted. Actor/owner
is `local_operator`, never browser/model JSON. Reads, export and delete retain the
same host access policy. Every mutation also uses core environment policy. Only
predefined model IDs are accepted, with no request-selected URL or filesystem
path. Checkpoint identity comes from the L2 model registry.

An enabled runtime admission controller and a matching qualification receipt are
required. SQLite qualifications must contain `qualified=true`, nonempty
`receipt_id`, and exact registry `model_id`, `architecture`, `provider`, `artifact`,
`revision`, `digest`, `tokenizer_hash`, `template_hash`, `runtime`, `quantization`.
Missing identity fields or a dependency overlay change require a new qualification;
discovery does not inspect or hash live files.
The CLI/qualification authority writes these trusted records; no web endpoint
accepts receipts. GET discovery never loads a model. RunConfig stores immutable
model/scenario versions, actual prompts, sampling/seed, budgets and a canonical
SHA256. The runtime load receipt records allowlisted real device/precision/load
metrics; unknown/private fields are discarded.

## Operator API

Prefix `/api/v1/cooperation-lab`:

- GET `/health`, `/capabilities`: actual readiness, model identities, frozen
  scenario metadata, modes and hard limits.
- POST `/runs`: JSON model_id, scenario_id, mode, optional sampling/seed and
  bounded max_turns/max_new_tokens. `Idempotency-Key` is mandatory; 202 returns
  `{run, created}` immediately, before model loading.
- GET `/runs?limit=20&after=<safe-id>` and `/runs/{id}`: bounded history/snapshot.
- POST `/runs/{id}/cancel`: idempotent, 202 `{run}`; cancelling is distinct from
  cancelled. No new turn starts after cancellation.
- GET `/runs/{id}/events?after=<seq>&limit=100`: persisted ordered journal.
- GET `/runs/{id}/events/stream?after=<seq>`: SSE, Last-Event-ID catch-up, id=seq,
  event=kind, data is the full REST event object. Ahead-of-history cursor gives
  409 `resync_required`; invalid cursor gives 400. No partial within-run pruning.
- GET `/runs/{id}/export`: bounded JSON attachment without a persistent copy.
- DELETE `/runs/{id}`: 204 for a terminal run; active runs cannot be removed.

Each event is `{run_id,seq,kind,payload,timestamp}`. Types are run/turn/message/
organization/usage/error/end. Message payload contains schema_version, identities,
message_id, in_reply_to, sequence, turn_id, timestamp, kind, content, delivered_to.
Sender is assigned by the runner. Plain text is a regular message, not an invented
organization proposal. A plain-text inferred reply has `reply_source=host_context`;
structured model replies use `model`. Invalid structured output, foreign reply IDs
and unknown recipients fail explicitly. Journal append precedes delivery to the
partner's isolated history. Complete is a model declaration, never ground truth.

[Shared capabilities fixture](../tests/contracts/capabilities.json) is serialized
actual backend metadata, checked by Python and consumed by frontend tests. Scenario
key is **scenario_id** and version is string **"1"**. It is a public contract
fixture with qualified=false, never evidence of real model qualification.

## Budgets and failure

At most 8 turns, 256 output tokens per turn, 2048 context tokens per participant,
16384 total input tokens, 2048 total output tokens and 18432 processing steps.
One 360-second monotonic deadline starts before preparation; loading and queueing
consume it. Before each turn the runner reserves its worst-case input/output.
Unknown usage stays null and is charged conservatively at the configured context
and output maxima. GenerationResult cannot override these limits. Adapters enforce
the actual tokenizer/context; the runner does not silently truncate histories.

Cancellation calls only its owned lease/adapter. The lifecycle waits for real
thread completion, closes owned resources inside C0 cleanup, and releases only
when the adapter verifies quiescence. An unconfirmed worker yields failed with
`runtime_quiescence_unconfirmed`, leaves runtime busy/quarantined, and cannot
launch another turn. A retained late-completion callback performs verified cleanup
when the same worker actually ends; there is no blind TTL release. Startup marks
old nonterminal runs interrupted without automatic resume.

Full-storage errors remain explicit. Terminal status can use the existing
reclamation reserve, so a full run cannot permanently prevent deletion. If a new
journal event cannot be written, snapshot exposes failure_code; the implementation
does not pretend that an unwritten event was persisted. No raw runtime exceptions,
private paths or prompts are logged in core.

## Validation boundary

L3 tests use bounded CPU fixtures and the real C0 ownership ledger, including an
actual blocking thread. They cover isolation/delivery, no-contact baselines,
idempotent parallel starts, cancel queued/preparing/generation, late completion,
malformed identities, conservative usage, storage failure, replay/SSE and host
access policy. They are not GPU qualification. Real host SSE proxy and actual
control/new-model sessions belong to the combined L4/L5 acceptance. No robot,
model download, host restart or live registration is performed by these tests.


## Lifecycle/late-close review hardening

The enabled module acquires C0 `module_startup_check` before opening/migrating or
recovering its own database. A real second API PID sharing the runtime namespace
is rejected before it can mark a live run interrupted. Module OFF has no storage
or admission IO; C0 OFF retains storage-only not-ready behavior. SQLite busy
wait is bounded, but synchronous filesystem work is not claimed to be a hard
async timeout.

Cleanup waits up to 10 seconds by default for the owned work/close phase. This
bounded grace accommodates actual process close/join under host load; the former
two-second grace could mark an otherwise successful run failed just before the
owned worker exited. It does not renew the 360-second inference deadline or admit
another turn after cancel/timeout. A phase exceeding the grace still fails closed
and retains ownership until verified late cleanup. Tests can inject shorter
cleanup timeouts; the production-grace regression advances asyncio's clock past
2.16 seconds without delaying the suite or terminating the real owned thread.

Cleanup retains exactly one `job.closing` task. A timeout preserves that real
worker and C0 ownership; another cleanup attempt waits on the same task rather
than spawning a second close. Once actual close/join confirms quiescence, the
owned completion callback performs idempotent final release and writes a durable
`run` event with unchanged terminal status, `quiescent=true`, `cleanup_late=true`.
The failed experiment never resumes. Failed close can be retried only after its
previous task has actually completed, without concurrent close workers.
