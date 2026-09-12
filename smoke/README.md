# wicked-smoke

A 5–8 minute **artifact-level** smoke for the wicked-* seams. It installs the PUBLISHED npm tarballs
(`wicked-crew` with its bundled studio, the prebuilt `wicked-core-ts` platform package crew pins,
`wicked-bus`) and the `wicked-garden` plugin tag into a hermetic temp root, boots the daemon with
shimmed seats (no model calls, no GitHub), and asserts the WIRE — HTTP JSON, engine events, the
filesystem — step by step. One line per step: `PASS` / `FAIL` / `EXPECTED-FAIL` with the seconds and
the evidence path; a JSON report; a GitHub step summary; non-zero exit on any `FAIL`.

No source builds, ever. What a customer's `npm i -g` composes is what runs here.

## Why — the classes only visible in composition

Every finding below was green in its repo's own CI when it shipped.

| Class | Findings | Only visible when |
|---|---|---|
| Cross-repo wire composition | F-086 (campaign seam missing `health.usable`), F-E2E-011 (crew `clis: []` × engine empty-eligible bail), F-082 (d.ts template backticks), api-types camelCase drift | the SEEDED workflows launch against the REAL engine addon with the REAL roster shape the daemon hands it |
| Shared process state | F-E2E-021 (two SQLite libraries on one WAL → ghost WAL), F-087 (`GET /runs/:id/diff` 500 on a half-reaped worktree), F-E2E-012 (branch + worktree debris in the customer's clone) | after N launches on a real filesystem + one external `wicked-bus emit` |
| Seat routing | F-7R2-006, F-7R3-001 (quota-dead seat routed), F-088 | a roster with mixed auth: signed-in, signed-out, quota-exhausted, not-installed |
| Governance posture | F-E2E-030 (deliver with no human gate), F-089 (workflow detect-only), F-090 (sentence-fragment units) | launching with the DEFAULT posture and inspecting plan units + gates |
| Packaging | stale studio bundle marker, six napi packages, F-078 lockfile stubs, F-004 headless plugin path | on the PUBLISHED tarball, not the source tree |
| Silent failure | health green while the bus is dead (F-E2E-021), publish warnings dropped (F-E2E-002), `recentErrors` empty | asserting `/diagnostics` after fault injection |

## The steps

| id | name | what it asserts | findings |
|---|---|---|---|
| S01 | boot | `wicked-crew serve --port <free> --db <tmp>/state/core.db` → `/health` + `/diagnostics` component versions equal the installed packages (crew, core-ts, studio bundle); the studio index is served same-origin and its dist marker equals `components.studioBundle`; `recentErrors` empty | packaging |
| S02 | skills | `diagnostics.skills.state == published`, portable count == total, `findings == []`; then the snapshot's recorded rules identity is rewritten to an OLDER version and the daemon restarted → accepted (`published`) with exactly ONE `skills.stale-rules` warning, `current.rules.stale == true`; the boot publish's warnings vs `findings` | F-083, F-E2E-002 |
| S03 | onboard | `POST /repos` (register + onboard the corpus) → the run completes past distribution with `clis: []`, `sessionStarted.cliCount == 0`, every unit a Tool executor (`wicked-estate` shim spawned with the bound `{repo_root}`/`{code_graph_db}`), no "no eligible seat" refusal; then the customer-visible debris (`wicked/<run-id>` branch, `wicked-worktrees/`) — asserted as the customer sees it, labelled | F-E2E-011, F-E2E-012 |
| S04 | bug-run (mixed roster) | `POST /runs {workflow: bug, humanConfirm: before:1, deliver: pr}` with claude (signed in), codex (401), copilot (quota), opencode (free tier), pi (absent): plan units are whole phases `triage, reproduce, fix, verify, deliver` (F-090); codex / copilot / pi benched AND NAMED in `unitDistributed.degradedReason`, no unit routed to them; a human gate before the deliver push; the repo-checks floor provisioned `node_modules` INTO the worktree and passed; the run branch landed on a LOCAL bare origin through the `gh` shim with the correction on it; `GET /runs/:id/diff` answers after completion; `GET /runs/:id/acceptance` writes nothing into the customer clone | F-090, F-7R2-006, F-7R3-001, F-E2E-030, F-E2E-029a, F-087, F-E2E-013 |
| S05 | bus-health | 8 quick launches back-to-back with `GET /projects/:id/activity` between them and an external `wicked-bus emit` after each (the F-E2E-021 trigger sequence) → 0 "database disk image is malformed" lines in the daemon log; when the bus DOES break, `/diagnostics.recentErrors` must carry it; on a clean loop a WAL-sidecar fault is injected and its visibility asserted | F-E2E-021 |
| S06 | campaign fan-out | `POST /testing/recon` over 2 corpus copies → 201, `campaignRegistered: true` (not the F-086 500), both siblings `awaiting_human` at intake on `GET /campaigns/:id`; then cancelled (no council convenes) | F-086 |
| S07 | interactive (opt-in) | the studio's doc-create path through crew's proxy answers honestly; the bridge is a cold `npx` fetch in v1, so this step is `--steps` opt-in — see TODO in the module | — |
| S08 | chat (opt-in) | `POST /chats` refuses a signed-out seat BY NAME, open/list/close answer; a real chat turn needs an ACP-speaking shim (v2) | F-2R2-009 |
| S09 | packaging | the installed tree: the host's `wicked-core-ts-<platform>` package is present at the core-ts version and satisfies crew's pin; `dist/studio/index.html` present; nothing the roster displays (`headless_invocation`, `login_invocation`, `binary`) points outside the temp root | six-package train, F-004 |
| S10 | teardown | SIGTERM → exit within 10 s; `bus.db` passes `PRAGMA integrity_check`; the temp root is removed (unless `--keep`) | F-E2E-021b |

Each step is its own module under `lib/steps/` so a failing step names the seam.

## Run it locally

```bash
# defaults: crew latest, core-ts as crew pins it, bus latest, garden latest tag; S01..S06,S09,S10
node smoke/bin/wicked-smoke.mjs

# a pinned set, keep the root, collect the report + daemon log + evidence
node smoke/bin/wicked-smoke.mjs --crew 0.7.32 --bus 2.3.4 --garden 12.34.0 \
  --keep --root /tmp/smoke-1 --report-dir ./smoke-out --assert-hermetic

# one seam
node smoke/bin/wicked-smoke.mjs --steps S03,S04
```

Host requirements: node ≥ 22, git, tar, `uv` (crew's skills seed runs `uv sync` for the garden
bundle and BLOCKS the publish without it — the harness exposes the host `uv` through a passthrough
wrapper, never the host PATH), and on Linux `bubblewrap` (the engine's checks sandbox; the workflow
installs it). `npm run check` inside `smoke/` parses every module and the step registry offline.

Options: `--crew --core-ts --bus --garden --steps --root --keep --report --report-dir --expect-fail
--expect-fail-steps --no-expect-fail --assert-hermetic --step-timeout --verbose` (`--help` for the
details). `--core-ts <v>` re-pins `wicked-core-ts` INSIDE the installed crew tree (what a customer's
`npm update` composes); `pinned` (default) takes whatever crew's range resolves.

## Hermetic by construction

Everything lives under ONE temp root (default `$RUNNER_TEMP` or the OS temp dir; `--root` to choose):
`HOME`, `CLAUDE_CONFIG_DIR`, `WICKED_HOME`, `WICKED_WORKER_HOME`, `WICKED_BUS_DATA_DIR`,
`WICKED_CREW_SYSTEM_SETTINGS`, `WICKED_WORKFLOWS_DIR`, `WICKED_INTERACTIVE_ROOT`, `TMPDIR`, the npm
prefix and cache, the git config. The PATH the daemon sees is: the shim dir, the temp npm prefix, the
node that runs the harness, and the SYSTEM directories only — never `~/.local/bin`, `~/.cargo/bin` or
a package manager's bin (so a real `claude`, `codex` or `pi` on the host is unreachable). Host tools the
product needs (`uv`, `python3`) reach the run through per-binary passthrough wrappers.
`--assert-hermetic` snapshots the mtimes under your real `$HOME` before the install and fails the run
if anything changed.

## What is stubbed (and what is not)

Real: the published crew daemon, the published core-ts engine addon (plan → distribute → councils →
gates → repo-checks floor → deliver script), the published bus, the published garden bundle (seeded and
published by the daemon's own skills store), git, the studio dist.

Shimmed (`smoke/shims/*.mjs`, launched through `sh`/`.cmd` wrappers that carry the absolute node path):

| binary | behaviour | why |
|---|---|---|
| `claude` | signed in; ballots vote option 1, judge turns `PASS … PASS`, the `fix` phase corrects `src/add.js`, read-only phases print prose | the one live seat; plain-text stdout rides the engine's passthrough adapter |
| `opencode` | free tier (no credential); same answers as claude | a second live seat so the evaluator can be identity-distinct from the creator |
| `codex` | credential file present, every turn exits 1 "Not logged in … 401" | the engine must learn `not_logged_in` from the ballot, not the probe |
| `copilot` | credential present, every turn exits 1 "exceeded your monthly quota" | the engine must bench `quota_exhausted` |
| `pi` | NOT on PATH | `not_installed` from the spawn error |
| `gh` | `pr create` prints a URL on a reserved host; `api user` prints an identity | the deliver phase opens its "PR" without GitHub |
| `wicked-estate` | records argv, exits 0 | onboarding's two tool phases run without an estate binary |
| `wicked-core` (CLI) | answers `gate-hook --protocol-version` with the protocol line; allows any hook call | the WRAPPED claude carrier probes it to arm input governance and fails the unit without it ("could not arm input governance: could not run `wicked-core gate-hook --protocol-version`", observed on 0.7.32) — the engine itself is the napi addon inside crew, never shimmed |

Every seat shim answers four prompt kinds, recognised from the prompt text the engine builds: a council
BALLOT (`RECOMMENDATION: 1 …`), an agent JUDGE (`PASS … PASS`), the FAILURE-TRIAGE judge
(`DECISION: ESCALATE`), and a WORKER turn (prose; the `fix` phase corrects `src/add.js`). Every
invocation is recorded in `<root>/shim-calls.ndjson` with its kind and cwd.

The shimmed seats are pinned through a council registry overlay the harness writes into the hermetic
`$HOME/.config/wicked-council/clis.toml` (the registry's documented wholesale-replace hatch): each
record names the ABSOLUTE shim path and carries no `[cli.acp]` block, so every turn runs on the wrapped
one-shot carrier. Two live observations on crew 0.7.32 make this necessary rather than cosmetic —
the daemon prepends its bundled ACP bridges' `node_modules/.bin` to PATH, and that directory carries a
REAL `codex` (`@openai/codex`, a dependency of `codex-acp`) that would win over any shim and call
OpenAI; and an ACP auth refusal on a worker turn is not retried on the wrapped carrier. `pi` is not
overlaid: its bare built-in name must fail to resolve.

Not shimmed in v1: the ACP transport (`claude-agent-acp`, `opencode acp`) — an ACP-speaking shim is
what lets S08 (chat) complete a turn; `wicked-interactive` (crew spawns it via `npx`, a network
fetch) — S07 is opt-in.

## The expected-fail labelling rule

A check may be tagged with the acceptance finding it detects. `lib/expect.mjs` holds the policy: for
the INSTALLED versions, which findings are KNOWN to still be present. A tagged check that fails is
reported `EXPECTED-FAIL (<finding>: <reason>)` — printed, in the report, never a red job, never
silently skipped. Rules today:

| finding | expected on | rule |
|---|---|---|
| F-E2E-021 | crew < 0.7.33 | the bus WAL loop after `GET /projects/:id/activity` + external emit, and its absence from `recentErrors` (S05) |
| F-E2E-030 | crew < 0.7.33 | no human gate before the deliver push under `humanConfirm: before:1` (S04) |
| F-E2E-002 | crew < 0.7.33 | publish warnings dropped from `/diagnostics.skills.findings` (S02) |
| F-E2E-012 | every version (by design) | tool-only onboarding keeps `wicked/<run-id>` + its worktree (S03) — retention, F-7R2-013 |
| F-7R2-006 / F-7R3-001 | core-ts ≤ 0.7.23 | **observed by this harness** (2026-09-12, 3 of 4 runs): codex fails every round-1 ballot `not_logged_in`, copilot `quota_exhausted` (both classified on `councilSeatFailed.reason`), the dispatcher's own bench answers round 2 with `benched`, and the distribution's ballot ledger benches neither — `degradedReason` names only the launcher-benched seat and `evaluator_distinct` seats the review units on the signed-out codex. The smoke reassigns the unit to a live seat at the escalation gate and continues, so the rest of S04 is still exercised; the routing checks stay EXPECTED-FAIL until core benches from every round. Worth a wicked-core issue. |

When a fix ships: flip the rule's version bound (or delete it). If the harness then still reports
EXPECTED-FAIL on the fixed version, the rule is wrong — not the product. `--no-expect-fail` runs strict;
`--expect-fail F-…` / `--expect-fail-steps S05` widen the policy for one run (a release train that
knowingly ships with a class open).

## Adding a step

1. Create `lib/steps/S11-<name>.mjs` exporting `id`, `name` and `async run(ctx, t)`.
2. Assert the WIRE: `t.check(name, ok, detail, { finding, evidence })`; write what you read with
   `t.evidence(name, obj)`; `t.info` for observations that are not verdicts.
3. Tag a check with the finding it detects; add a rule to `lib/expect.mjs` only if the current published
   version is known to exhibit it.
4. Register the id in `lib/args.mjs` (`ALL_STEPS`, and `DEFAULT_STEPS` unless it needs the network or
   more than ~60 s); `npm run check` verifies the registry.
5. Keep the whole default set ≤ 8 minutes on a GitHub runner (S04 is the budget's owner).

`ctx` gives you the layout (`ctx.L`), the hermetic `env`, the `daemon` (start/stop/restart/log
greps), `api()` (a JSON client on the daemon), `tree` + `versions` (the installed artifacts),
`shimCalls()` (every shim invocation with its prompt kind), and `state` (what earlier steps produced —
`corpus`, `origin`, `repoId`, `bugRunId`).

## Files

```
smoke/
  bin/wicked-smoke.mjs        CLI + orchestration (install → shims → steps → report → cleanup)
  lib/args.mjs                flags, step ranges
  lib/env.mjs                 layout + hermetic env/PATH
  lib/install.mjs             npm -g into the prefix; garden tag → marketplace-cache layout
  lib/shims.mjs               shim wrappers, host passthroughs, seat credential artifacts
  lib/daemon.mjs              serve / health-wait / SIGTERM timing / log greps
  lib/http.mjs lib/proc.mjs lib/runs.mjs lib/corpus.mjs lib/semver.mjs
  lib/expect.mjs              the expected-fail policy
  lib/report.mjs              checks → PASS/FAIL/EXPECTED-FAIL, JSON report, step summary
  lib/hermetic.mjs            $HOME mtime scan (--assert-hermetic)
  lib/steps/S01…S10           one module per seam
  shims/                      claude codex copilot opencode gh wicked-estate (+ _lib)
  fixtures/corpus/            the fixed repo (initialised into git at run time)
```
