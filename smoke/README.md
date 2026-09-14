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
| S04 | bug-run (mixed roster) | `POST /runs {workflow: bug, humanConfirm: before:1, deliver: pr}` with claude (signed in), codex (401), copilot (quota), opencode (free tier), pi (absent): plan units are whole phases `triage, reproduce, fix, verify, deliver` (F-090); codex / copilot / pi benched AND NAMED in `unitDistributed.degradedReason`, no unit routed to them; a human gate before the deliver push; the repo-checks floor provisioned `node_modules` INTO the worktree and passed; the run branch landed on a LOCAL bare origin through the `gh` shim with the correction on it; `GET /runs/:id/diff` answers after completion; `GET /runs/:id/acceptance` writes nothing into the customer clone; **S-L1**: one armed `VERDICT: FAIL` from the evaluator seat parks the run at the `verdict_not_pass` escalation gate with deliver undispatched, approve retries and the seat answers PASS | F-090, F-7R2-006, F-7R3-001, F-E2E-030, F-E2E-029a, F-087, F-E2E-013, F-RC1-131 |
| S05 | bus-health | 8 quick launches back-to-back with `GET /projects/:id/activity` between them and an external `wicked-bus emit` after each (the F-E2E-021 trigger sequence) → 0 "database disk image is malformed" lines in the daemon log; when the bus DOES break, `/diagnostics.recentErrors` must carry it; on a clean loop a WAL-sidecar fault is injected and its visibility asserted | F-E2E-021 |
| S06 | campaign fan-out | `POST /testing/recon` over 2 corpus copies → 201, `campaignRegistered: true` (not the F-086 500), both siblings `awaiting_human` at intake on `GET /campaigns/:id`; then cancelled (no council convenes) | F-086 |
| S07 | interactive (opt-in) | the studio's doc-create path through crew's proxy answers honestly; the bridge is a cold `npx` fetch in v1, so this step is `--steps` opt-in — see TODO in the module | — |
| S08 | chat | on a daemon booted with `WICKED_CHAT_TURN_SECS=5`: a seat that cannot take a turn (codex) is refused BY NAME; `POST /chats {clis: [acp-smoke]}` warms the ACP-speaking seat shim (201; the daemon log says the seat was handed the skills snapshot); one turn → 202, `chatDelta` then `chatReply {ok: true}` on `/ws` with `usage`, the shim saw `session/prompt`, `GET /chats/:id.messages` holds both records; a 20 s turn is cut at the 5 s budget → `chatReply {ok: false}` naming the seat, the budget variable and the re-seat remedy, the seat released; the next send with `targets: [acp-smoke]` re-seats it (202 + an ok reply); `DELETE` → `chatClosed {reason: requested}`, `seats: []`, `messages: []` | F-2R2-009, F-RC1-110, F-RC1-112, F-RC1-113, F-RC1-116 |
| S09 | packaging | `wicked-crew --version` prints three `<name> <version>` lines equal to the installed tree (F-003); the installed tree: the host's `wicked-core-ts-<platform>` package is present at the core-ts version and satisfies crew's pin; `dist/studio/index.html` present; nothing the roster displays (`headless_invocation`, `login_invocation`, `binary`) points outside the temp root | six-package train, F-004 |
| S10 | teardown | SIGTERM → exit within 10 s; `wicked-crew status` against the stopped daemon exits ≠ 0 with one remedy line and no stack (F-RC1-044); `bus.db` passes `PRAGMA integrity_check`; the temp root is removed (unless `--keep`) | F-E2E-021b, F-RC1-044 |

Each step is its own module under `lib/steps/` so a failing step names the seam.

## Run it locally

```bash
# defaults: crew latest, core-ts as crew pins it, bus latest, garden latest tag; S01..S06,S08..S10
node smoke/bin/wicked-smoke.mjs

# a pinned set, keep the root, collect the report + daemon log + evidence
node smoke/bin/wicked-smoke.mjs --crew 0.7.33 --bus 2.3.4 --garden 12.35.0 \
  --keep --root /tmp/smoke-1 --report-dir ./smoke-out --assert-hermetic

# the PREVIOUS published set, explicitly pinned (the policy must read honestly there too)
node smoke/bin/wicked-smoke.mjs --crew 0.7.32 --core-ts 0.7.23 --step-timeout 900

# one seam
node smoke/bin/wicked-smoke.mjs --steps S03,S04
```

Host requirements: node ≥ 22, git, tar, `uv` (crew's skills seed runs `uv sync` for the garden
bundle and BLOCKS the publish without it — the harness exposes the host `uv` through a passthrough
wrapper, never the host PATH), and on Linux `bubblewrap` (the engine's checks sandbox; the workflow
installs it). `npm run check` inside `smoke/` parses every module and the step registry offline.

Options: `--crew --core-ts --bus --garden --steps --root --reuse-root --keep --report --report-dir
--expect-fail --expect-fail-steps --no-expect-fail --allow-unexpected-pass --assert-hermetic
--step-timeout --verbose` (`--help` for the details). `--core-ts <v>` re-pins `wicked-core-ts`
INSIDE the installed crew tree (what a customer's `npm update` composes); `pinned` (default) takes
whatever crew's range resolves — S09's "crew's pin resolves to the installed" check is the intended
signal when a caller pins outside that range. The report is `<root>/report.json`, copied to
`--report-dir`, or to `./wicked-smoke-report.json` when the root is removed without one.
`--step-timeout` raises the built-in ceilings (S01 300 s — also the daemon's boot wait, S04 540 s,
S05 420 s); a step that hits its ceiling is ABORTED (its wait loops stop), reported `ERROR`, and the
run continues. A COLD first boot publishes the garden bundle (`uv sync` of its pyproject): 5 s on a
hosted runner, 11 minutes on a loaded workstation (load ≈ 30) — raise `--step-timeout` there.

## Hermetic by construction

Everything lives under ONE temp root (default `$RUNNER_TEMP` or the OS temp dir; `--root` to choose;
a non-empty root is refused unless `--reuse-root`): `HOME`, `CLAUDE_CONFIG_DIR`, `WICKED_HOME`,
`WICKED_WORKER_HOME`, `WICKED_BUS_DATA_DIR`, `WICKED_CREW_SYSTEM_SETTINGS`, `WICKED_WORKFLOWS_DIR`,
`WICKED_INTERACTIVE_ROOT`, the npm prefix and cache, the git config — and `TMPDIR` on macOS and
Windows. **On Linux `TMPDIR` is the SYSTEM temp dir by design**: the engine's validator and checks
sandboxes are `bwrap … --tmpfs <std::env::temp_dir()>` with the run dir re-bound inside, and a TMPDIR
under the run root masked the engine's own scratch there (the pinned evidence floor answered "no
coverage report was produced" on ubuntu while macOS passed); Linux therefore runs the configuration
wicked-crew's own deliver e2e uses — what the engine writes under `/tmp` is ephemeral runner state,
and `--assert-hermetic` does not cover `/tmp` there. The PATH the daemon sees is: the shim dir, the temp npm prefix, the
node that runs the harness, and the SYSTEM directories only — never `~/.local/bin`, `~/.cargo/bin` or
a package manager's bin (so a real `claude`, `codex` or `pi` on the host is unreachable). Host tools the
product needs (`uv`, `python3`) reach the run through per-binary passthrough wrappers.
`--assert-hermetic` snapshots the mtimes/sizes under your real `$HOME` before the install (a FULL
bounded walk under the directories the wicked family and the CLIs write — `.claude .config .wicked*
.npm .codex .copilot .pi .local .cargo …` — so an in-place edit of `~/.config/wicked-council/clis.toml`
or a new file four levels down in a plugin cache is caught; `~/Library` is recorded to its
grandchildren; every other top-level directory by its own mtime; entries are visited sorted so the
per-root entry budget cuts at the same place in both snapshots) and
fails the run if anything changed; a `--root` placed under `$HOME` is excluded from the scan. Three
classes are reported as `noise` (printed, kept in the JSON `hermetic.noise`, verdict unchanged) and
are NOT leaks: anything under the macOS user media folders `Movies Music Pictures Public` — a hosted
macOS runner's own daemons write there during a run (`photoanalysisd` under `~/Pictures/Photos
Library.photoslibrary/…`, selftest run 34744141719; a bare mtime move on `~/Movies`, run 34722047107),
nothing wicked does; Apple's own state under `~/Library` — the scan watches only the subtrees a
third-party tool writes to (`Application Support`, `Caches`, `Preferences`, `Logs`, `LaunchAgents`,
`Python`, `pnpm`, `Developer`, `Containers`, …) and inside them treats `com.apple.*`,
`group.com.apple.*`, UUID-named and a few named Apple leaves as noise (a hosted macOS runner churns
`Preferences/com.apple.*.plist`, `Caches/com.apple.*`, `Biome`, `Daemon Containers` for the whole
run — selftest 34746373419), so `~/Library/Caches/ms-playwright (new)` or
`~/Library/Application Support/<tool>` is still `changed`; and a directory whose own mtime moved while
none of its recorded direct children changed, or whose changed descendants are all noise (a
directory's mtime moves only when a direct child is added, removed or renamed — a child created and
removed during the run, or Apple's; the runner does that to `~/Library` itself, run 34745299650). A
leak leaves a file, and a recorded file that is new, removed or modified is still `changed`; a bare
mtime move on a directory whose children were NOT recorded (deeper than the record, or past the
entry budget) stays a real change. On a shared
workstation the scan reports OTHER processes' writes
too (a live daemon's WAL files, another session's tool caches) — it is designed for a dedicated
runner, where it is always on.

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
| `acp-agent` (seat key `acp-smoke`) | speaks ACP over stdio: `initialize` → `session/new` → `session/prompt` answered with two `agent_message_chunk` deltas and a result carrying `usage`; sleeps `WICKED_SMOKE_ACP_SLEEP_MS` (env) or a per-prompt `smoke-acp-sleep-ms=<n>` token first; every JSON-RPC method recorded | the chat carrier (S08): a chat warms its seats over ACP, and until a seat spoke it a turn could not complete in the smoke — the F-RC1-110/111/112 class landed live. Council-disabled in the overlay so S04's roster is unchanged |
| `gh` | `pr create` prints a URL on a reserved host; `api user` prints an identity | the deliver phase opens its "PR" without GitHub |
| `wicked-estate` | records argv, exits 0 | onboarding's two tool phases run without an estate binary |
| `wicked-core` (CLI) | answers `gate-hook --protocol-version` with the protocol line; allows any hook call | the WRAPPED claude carrier probes it to arm input governance and fails the unit without it ("could not arm input governance: could not run `wicked-core gate-hook --protocol-version`", observed on 0.7.32) — the engine itself is the napi addon inside crew, never shimmed |

Every seat shim answers four prompt kinds, recognised from the prompt text the engine builds: a council
BALLOT (`RECOMMENDATION: 1 …`), an agent JUDGE (`PASS … PASS`), the FAILURE-TRIAGE judge
(`DECISION: ESCALATE`), and a WORKER turn (prose; the `fix` phase corrects `src/add.js`). Every
invocation is recorded in `<root>/shim-calls.ndjson` with its kind and cwd.
An EVALUATOR turn — a worker prompt carrying core #498's convention sentence (`||| VERDICT (evaluator
unit): make the LAST line of your output exactly VERDICT: PASS or VERDICT: FAIL …`, core-ts ≥ 0.7.26) —
ends with `VERDICT: PASS` (recorded as `kind: verdict`); while the token file named by
`WICKED_SMOKE_VERDICT_FAIL_ONCE` exists, the first such turn consumes it (a rename) and ends
`VERDICT: FAIL` with a finding above the line — how S04 proves the evaluator-verdict gate (F-RC1-131).

The shimmed seats are pinned through a council registry overlay the harness writes into the hermetic
`$HOME/.config/wicked-council/clis.toml` (the registry's documented wholesale-replace hatch): each
record names the ABSOLUTE shim path and — for the five v1 seats — carries no `[cli.acp]` block, so every
unit turn runs on the wrapped one-shot carrier; the sixth record, `acp-smoke`, is the exception: a NEW key
(the merged registry appends it) whose `[cli.acp]` names the ACP-speaking shim and which is
`enabled_for_council = false`. Two live observations on crew 0.7.32 make this necessary rather than cosmetic —
the daemon prepends its bundled ACP bridges' `node_modules/.bin` to PATH, and that directory carries a
REAL `codex` (`@openai/codex`, a dependency of `codex-acp`) that would win over any shim and call
OpenAI; and an ACP auth refusal on a worker turn is not retried on the wrapped carrier. `pi` is not
overlaid: its bare built-in name must fail to resolve.

The ACP transport is shimmed for ONE seat only (`acp-agent`, above): the real bridges
(`claude-agent-acp`, `opencode acp`, `codex-acp`) are never spawned — the five v1 seats have no
`[cli.acp]`. Not shimmed: `wicked-interactive` (crew spawns it via `npx`, a network fetch) — S07 is
opt-in.

## The expected-fail labelling rule

A check may be tagged with the acceptance finding it detects. `lib/expect.mjs` holds the policy: for
the INSTALLED versions, which findings are KNOWN to still be present. A tagged check that fails is
reported `EXPECTED-FAIL (<finding>: <reason>)` — printed, in the report, never a red job, never
silently skipped. A tagged check that PASSES while its finding is still expected to fail is reported
**`UNEXPECTED-PASS — retire the label`** (step line, JSON `unexpectedPasses`, step summary) and fails
the run with exit 3 unless `--allow-unexpected-pass`: the product changed (or the label was wrong) and
the policy must move the same day. One exception, declared per finding (`FLAKY` in `lib/expect.mjs`):
a class whose failure is timing-dependent in the product — F-7R2-006 / F-7R3-001 fail on every unloaded
runner but the ledger DOES bench a dead seat when its later ballot rounds also fail, which a slow host
makes likely; F-SMOKE-003's PR URL sometimes survives the transcript cap; F-087's diff route answered
200 on one node-26 run in three; F-E2E-021's WAL race stayed clean on 1 of 13 loops on crew 0.7.32 —
reports an unexpected pass
as `~ passed this time … timing-dependent` (printed, in `unexpectedPasses` with `flaky: true`) without
changing the verdict. Rules today, keyed to the REAL fix versions (npm latest 2026-09-14: crew 0.7.34
pinning core-ts ^0.7.25 / bus ^2.3.4 / studio ^0.5.9; a bound of `0.7.99` means "no fix version
exists yet"):

| finding | expected on | rule |
|---|---|---|
| F-RC1-044 | crew < 0.7.35 | `wicked-crew status` with the daemon down prints the `TypeError: fetch failed` stack (and a non-2xx body as JSON, exit 0) instead of one remedy line + exit 1 (S10, after SIGTERM) — FIXED in crew 0.7.35 (`daemonFetch`); labelled ahead of the publish (FIX-IT-ALL L10-7) so the fixed set must PASS |
| F-003 | crew < 0.7.35 | `wicked-crew --version` answers "Unknown command" instead of the three `<name> <version>` lines of THIS install (S09, compared to the installed tree) — FIXED in crew 0.7.35 |
| F-RC1-131 | core-ts < 0.7.27 | an EVALUATOR unit whose output ends `VERDICT: FAIL` (or has no verdict line) is recorded PASS and the run proceeds to deliver (wicked-core #488, the false-pass class). S04 arms ONE failing verdict through the `WICKED_SMOKE_VERDICT_FAIL_ONCE` token the seat shim consumes and asserts the gate (`gateEscalated.denialSource: evaluator_verdict`; `condition: verdict_not_pass` counts only when the shim log shows the armed FAIL was answered — that condition also names the layer-2 judge's denial on older engines) + 0 `toolExecutorDispatched` for deliver ahead of it — FIXED in core-ts 0.7.27 (FIX-IT-ALL L1 PR-1A); labelled ahead of the publish, so the fixed set must PASS and a stale label reads UNEXPECTED-PASS |
| F-RC1-113 | core-ts < 0.7.26 — FIXED on the 0.7.35 set (wicked-smoke run 34865500000; wicked-ci #31) | a chat seat is warmed with `SkillsDelivery::None` (wicked-core #487 / crew #563): no "handed skills gen" line in the daemon log, no `WICKED_GARDEN_ROOT` on the seat, so the garden skills are unreachable from a chat (S08) |
| F-RC1-110 | core-ts < 0.7.26 — FIXED on the 0.7.35 set (wicked-smoke run 34865500000; wicked-ci #31) | a chat turn cut at `WICKED_CHAT_TURN_SECS` reads `seat '<cli>' turn ended TimedOut: …` — the budget variable and the re-seat remedy are unnamed (crew #562); the cut itself, the seat being named and released, and the `targets` re-seat are asserted UNTAGGED (S08) |
| F-RC1-112 | crew < 0.7.35 — FIXED on the 0.7.35 set (wicked-smoke run 34865500000; wicked-ci #31) | `GET /chats/:id` carries no `messages`: the transcript exists only in the tab that asked (crew #503 = F-085) (S08, after a turn and after close) |
| F-RC1-116 | crew < 0.7.35 — FIXED on the 0.7.35 set (wicked-smoke run 34865500000; wicked-ci #31) | `chatReply` carries no `usage` although the shim reports it on the prompt result — chat turns are unmetered on the wire (wicked-core #412, chat half) (S08) |
| F-E2E-021 | crew < 0.7.33 (FLAKY) | the bus WAL loop after `GET /projects/:id/activity` + external emit, and its absence from `recentErrors` (S05) — FIXED in crew 0.7.33 (#541 one SQLite library per db file per process, #542 connection-fatal bus errors reach `recentErrors`): S05 PASSES there and is EXPECTED-FAIL on 0.7.32, where the malformed loop is observed on 12 of 13 runs (a clean loop is a disclosed flaky pass, not a verdict) |
| F-E2E-030 | core-ts < 0.7.24 | no human gate before the deliver push under `humanConfirm: before:1` (S04) — the gate landed in the ENGINE (core-ts 0.7.24 `should_pause` before a `deliver` Tool unit), so the rule is keyed to the addon. crew 0.7.33 adds the WIRE around it (`deliverGate` on `POST /runs`, `GET /health.capabilities.deliverGate`, `session.auto_deliver`) — S04 asserts that wire untagged whenever crew ≥ 0.7.33 is installed: the capability must equal (core-ts ≥ 0.7.24) |
| F-E2E-002 | crew < 0.7.99 (open — no fix yet) | publish warnings dropped from `/diagnostics.skills.findings` (S02) — the 0.7.33 CHANGELOG carries no fix; an earlier bound of 0.7.33 was a guess |
| F-E2E-012 | every version (by design) | tool-only onboarding keeps `wicked/<run-id>` + its worktree (S03) — retention, F-7R2-013 |
| F-7R2-006 / F-7R3-001 | core-ts < 0.7.25 (FIXED in core-ts 0.7.25 — wicked-core #473 bench-on-abstention; FLAKY while the rule is active) | **observed by this harness on 0.7.23 AND 0.7.24 (crew 0.7.32 and 0.7.33)**: codex failed every round-1 ballot `not_logged_in`, copilot `quota_exhausted` (both classified on `councilSeatFailed.reason`), the dispatcher's own bench answered round 2 with `benched`, and the distribution's ballot ledger benched neither — `degradedReason` named only the launcher-benched seat and `evaluator_distinct` / the judge rotation seated units and judges on the dead codex/copilot. **On core-ts 0.7.25 (crew 0.7.34, run 34798471429) codex and copilot were benched and NAMED and no unit was routed to a dead seat on ubuntu AND macos** — the placeholder bound moved to the real fix version the same day; the smoke still reassigns to a live seat at the escalation gate on the older sets. |
| F-SMOKE-003 | crew < 0.7.99, every node and engine (open — no fix yet; FLAKY) | **observed by this harness**: `session.delivery` reads `stranded` for a run whose branch IS on the origin and whose PR WAS opened. crew derives `delivered` from a `run.delivered` trail entry it records by grepping the deliver transcript for the PR URL (`delivery-index.ts prUrlFrom`); the transcript carries one `deliver: EXCLUDED (scratch-dir): …` line per file the checks floor left under the worktree scratch (npm logs, node's on-disk compile cache — node 24 and 26 both write one) and whether the URL survives the cap varies with that count: selftest run 34722047107 read `delivered` on core-ts 0.7.24 and `stranded` on 0.7.23 on node 24 with byte-identical transcript heads, the run before the reverse. S04 judges delivery from the bare origin (`git ls-remote`) + the `gh` shim call first and labels the product's disagreeing wire value with this finding; a `delivered` reading is disclosed as a flaky pass, not a verdict. |
| F-087 | crew < 0.7.99 AND host node ≥ 26 (open) | `GET /runs/:id/diff` answers 500 on a COMPLETED run whose worktree scratch holds the checks' compile cache (`git diff --no-index` fails per untracked file) — the F-087 "not robust to what the worktree holds" class, observed by this harness on node 26 hosts; every node 24 runner answered 200 with the same cache present. |
| F-SMOKE-001 | core-ts < 0.7.99 on linux (open) | the fix unit's floors fail inside the engine's `bwrap` sandbox although the judge PASSED and the worker's write succeeded — deterministic on ubuntu-latest (three root layouts; core-ts 0.7.23, 0.7.24 and 0.7.25), absent on macOS; confirmed by the independent review as a core-ts finding. Shape on 0.7.23/0.7.24: the pinned evidence floor denies "no coverage report was produced … the script denied before writing one" and the run ends. Shape on 0.7.25 (run 34798471429): the creator floor (#476) runs first and its `install` exits 1 in the checks sandbox, the pinned validator denies with the same signature prefixed "the run left a change in its worktree", and #477 parks the run at an `escalation` gate (`floor_failed` / `pinned_validator`) that S04 cancels — recorded as `floorEscalation`. The pipeline checks downstream of `fix` carry this tag ONLY when the fix unit's denial has that signature (a cascade of one finding, not five regressions); "the floor ran" / "install attempted" left the cascade at 0.7.25. |

When a fix ships: flip the rule's version bound (or delete it). If the harness then still reports
EXPECTED-FAIL on the fixed version, the rule is wrong — not the product; if it reports UNEXPECTED-PASS,
the fix landed before the rule moved. `--no-expect-fail` runs strict; `--expect-fail F-…` /
`--expect-fail-steps S05` widen the policy for one run (a release train that knowingly ships with a
class open).

### Gates are judged by kind, never by prompt text

core-ts ≥ 0.7.24 says WHY a run paused on the wire — `awaitingHuman.gateKind` (`run_level` | `def` |
`deliver` | `terminal` | `escalation` | `failure` | `triage`) — and S04 keys every decision on it:
intake/def → approve, deliver → approve (the push goes to the local bare origin through the `gh` shim,
which is what exercises the deliver seam), escalation/failure/triage naming a dead seat → reassign to
a live seat, any other wire escalation → cancel. On an engine without `gateKind` the fallback derives a
kind from the cursor phase and the prompt's OPENING words, records that it guessed, and never cancels
from a guess (a guessed escalation is approved once and re-judged).

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
`shimCalls()` (every shim invocation with its prompt kind — the ACP seat adds one record per JSON-RPC
method), `lib/ws.mjs`'s `openFrames(daemon.origin)` for the `/ws` stream, and `state` (what earlier steps produced —
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
  lib/ws.mjs                  /ws frame collector (chat replies travel only on /ws)
  lib/expect.mjs              the expected-fail policy
  lib/report.mjs              checks → PASS/FAIL/EXPECTED-FAIL, JSON report, step summary
  lib/hermetic.mjs            $HOME mtime scan (--assert-hermetic)
  lib/steps/S01…S10           one module per seam
  shims/                      claude codex copilot opencode acp-agent gh wicked-estate wicked-core (+ _lib)
  fixtures/corpus/            the fixed repo (initialised into git at run time)
```
