# Changelog

## Unreleased

### smoke — S04 gets a distinct judge seat and asserts the fail-closed judge gate · F-A6-USAGE retired · F-E2E-002 re-bound (crew 0.8.5 release smoke)

crew 0.8.5's release smoke (run 37762305091) was red on both legs for three harness reasons; the
package was sound.

- **S04: a third live seat, `smoke-judge`.** From core-ts 0.7.40 (wicked-core#774 / #780) a unit's
  judge must be a seat distinct from the unit's seat AND its creator, and when the only such seats are
  benched the gate fails closed (`gateEscalated.condition: judge_unavailable`) instead of skipping
  the judge (0.7.39 skipped it and allowed). The smoke's two live seats (claude, opencode) left the
  `verify` unit (evaluator opencode, creator claude) no judge, so the bug run parked and was
  cancelled. `smoke-judge` is a custom registry key crew has no credential rule for (`auth:
  unknown`, council-eligible), answers like claude, and is written LAST in the overlay so the routing
  S04 asserts is unchanged; the live-seat rerun pool includes it.
- **S04: the fail-closed judge gate is asserted on its own.** On core-ts ≥ 0.7.40 a second short
  launch on the same mixed roster WITHOUT `smoke-judge` must park at a `judge_unavailable` gate that
  names the dead seats, with deliver never dispatched; the harness cancels it. Older engines are
  reported, not judged.
- **S04: gates are judged on the LATEST `gateEscalated` of the paused unit.** The handler matched the
  first verdict gate in the whole stream on every later pause of the same unit, so 0.8.5's
  `judge_unavailable` gate read as "a SECOND verdict gate".
- **F-A6-USAGE retired at crew 0.8.5** (crew #824 / #863: the ask relay sums the answer attempt's
  `cliUsage` into `chatReply.usage`; UNEXPECTED-PASS on both legs of run 37762305091).
- **F-E2E-002 bound moved to crew 0.8.6.** The `0.7.99` placeholder had expired, so the check read a
  hard FAIL on 0.8.x (13 `unresolved-ref` warnings logged by garden 12.44.0's mcp-scaffold TS
  templates, 0 findings). crew 0.8.6 reports a publish's warnings as `skills.publish-warning`
  findings and no longer ref-checks a skill's `assets/`. S02's stale-rules carry-over check leaves
  `skills.publish-warning` out (it belongs to the publish that found it; a restart does not re-scan).

### smoke — S08 follows the ask-path wire (crew 0.8.2) · F-A6-USAGE

- **S08 asserts the chat wire of the crew it installed — pool (< 0.8.2) or path (≥ 0.8.2).** crew
  0.8.2's release smoke (run 37426596418) failed S08 on both legs at the open: `POST /chats {clis:
  [acp-smoke]}` → 409 `seat 'acp-smoke' is not in the roster`. From crew 0.8.2 an ask is a team
  PATH (DES-ASK-TEAM-CHAT-001; DES-STUDIO-REBUILD-001 Amendment 6): `POST /chats` warms nothing and
  admits the default roster and the seats NAMED in `clis` by ONE rule, which refuses a
  council-disabled seat (the engine's roster does not list one), so the harness's ACP seat — written
  `enabled_for_council = false` so S04's mixed roster stays mixed — could no longer be spoken to.
  Harness lag, not a crew regression. On crew ≥ 0.8.2 S08 now:
  - re-writes the council overlay with the ACP seat `enabled_for_council = true` before its own
    restart (`writeCouncilOverlay(L, { acpSeatForCouncil: true })`; S08 is the last step that
    convenes a seat, S04's roster is untouched) and boots the daemon with its defaults — the pool
    knob `WICKED_CHAT_TURN_SECS` bounds no path step, but crew's turn index still derives a turn's
    staleness from it (wicked-crew#826), so a 5 s boot would un-stamp the 20 s step;
  - asserts the path wire: the open warms nothing (no ACP call, no `path` yet, `singleSeat`
    disclosed); the FIRST message launches the run — 202 `{seats, turnId, runId, stepId:
    "answer-1"}`, `GET /chats/:id.path` names it with `pa: acp-smoke`; ONE `chatReply{ok, run_id,
    ord, turn_id}` for the PA (one voice), the shim's own answer (no `[wicked-core]` refusal),
    reached over ACP (handshake + `session/prompt` after the first message), the run's events on
    the ACP carrier for the seat; the transcript's one `user` + one `seat` record; a slow step (the
    shim sleeps 20 s) → 202 `answer-2`, a send DURING it → 409 `turn_in_flight` naming the seat and
    the turn, the slow reply lands `ok: true` AFTER the sleep and STAMPED, the refused send left no
    record; a follow-up → 202 `answer-3` on the same run and the path's `stepId` moves; End →
    `chatClosed{reason: "closed"}`, `seats: []`, `messages: []`, the run `cancelled`.
  - keeps the pool wire's cases (5 s budget cut, eviction, re-seat by `targets`, `chatClosed
    {reason: "requested"}`) for crew < 0.8.2, unchanged.
- **`[cli.acp]` in the overlay now carries `acp_input_governance = true`.** The engine dispatches a
  path's `answer-N` step (`executes_code: false`) to a seat only when its ACP adapter is admitted to
  input governance; without it the unit is REFUSED ("not admitted to input governance") — and the
  ask relay surfaced that refusal text as a `chatReply{ok: true}` (run 2 of this change, kept in the
  lane's evidence).
- **F-A6-USAGE (wicked-crew#824), expected-fail on crew ≥ 0.8.2.** A path turn's `chatReply` carries
  no `usage` (the relay folds the unit's output; the unit frames carry none) — F-RC1-116's claim on
  the new wire. The pool wire keeps F-RC1-116. The bound is the placeholder; move it to the real fix
  version when it publishes.
- **The skills handing is disclosed, not asserted, on the path wire.** The engine hands a snapshot
  per seat LEVER (`SkillsSnapshot::delivery(cli)`); a synthetic seat it knows no lever for
  (acp-smoke) is handed none and emits no `skillsSnapshotHanded`, so the pool wire's F-RC1-113
  check has no path-wire equivalent in this harness — S08 reports the count as info.
- Verified locally against the published set: crew 0.8.2 / core-ts 0.7.38 / studio bundle 0.6.2 /
  garden 12.43.0 — S08 35 checks, 34 pass, 1 expected-fail (F-A6-USAGE).

### smoke — S08 counts the turn's own records, not every record (crew 0.7.48)

- **S08 no longer asserts "exactly 2 records" after a chat turn.** crew 0.7.48's release smoke (run
  37140085699) failed S08 on both legs with `3 record(s): user, seat, decisions`. crew 0.7.48 ships
  decision capture's studio-chat host (wicked-crew#773), which appends one derived `decisions` record
  per turn to the transcript, by design — a reader folds it onto the turn's `user` record, exactly as
  it folds `citations`. The check now asserts what F-RC1-112 is about: exactly ONE `user` record and
  exactly ONE `seat` reply from the seat, and nothing beside them but the derived kinds crew's wire
  contract names (`citations`, `decisions`, `system`). A second user or seat record, or a record of
  an unknown kind, still fails. On crew < 0.7.48 the transcript holds the same two records as before
  and the check passes unchanged.

### smoke — S04 asserts the teamed routing (wicked-core#590 S5) · F-SMOKE-004 / F-SMOKE-005

- **S04 tells the two routing eras apart and asserts the current one.** crew 0.7.45's release smoke
  (run 36946090323) failed S04 on both legs. core-ts 0.7.33 ships wicked-core#590 S5, which removed
  the per-phase ballots, and two of the three failing checks asserted that ballot behaviour. On core-ts
  ≥ 0.7.33 (or any `routingMethod: teamed` on the wire) each ballot check is replaced by the teamed
  contract's equivalent. No coverage is dropped:
  - "copilot benched and NAMED (ballot ledger)" → copilot benched in the run on its own refusal and
    named by `seatBenched` (`F-SMOKE-004`);
  - "no unit routed to a dead seat" → no unit routed to a launcher-benched seat (codex, pi; untagged),
    plus copilot handed exactly ONE unit turn, with later units re-seated (`F-SMOKE-004`);
  - "codex + copilot ballots were spawned" → copilot spawned (only its own refusal can tell) and codex
    never spawned (the probe benched it; untagged);
  - new: after the run, `GET /roster` reads copilot `council_eligible: false` with the engine's cause
    (`F-SMOKE-005`).

  The ballot-era checks are unchanged for core-ts < 0.7.33.
- **`F-SMOKE-004`** (core-ts 0.7.33; fixed in core-ts 0.7.34, wicked-core#689) and **`F-SMOKE-005`**
  (crew < 0.7.46) are labelled before the fixes publish. The 0.7.45 set reads EXPECTED-FAIL. The
  fixed set (crew 0.7.46 on core-ts 0.7.34) must PASS, and a stale label reads UNEXPECTED-PASS.
- **hermetic: `~/Library/Preferences/ContextStoreAgent.plist` is Apple runner noise.** The hosted macOS
  runner rewrote it during this PR's selftest (run 36952156549). It was the only non-allowlisted change,
  and every step read PASS or EXPECTED-FAIL. Allowlisted as a leaf, never the subtree, beside
  `Application Support/CrashReporter`.

### smoke — F-SMOKE-001 retired (wicked-core #460)

- **`F-SMOKE-001` is expected only on `core-ts < 0.7.27` on linux.** The Linux floor denial came from the
  validator jail's `--tmpfs` over the system temp dir, which hid a nested run worktree's gitdir
  (`<clone>/.git/worktrees/<name>`), so the pinned floor's `git status` died with "not a git
  repository" and denied work that was there. wicked-core #505 (C8 revised) removed the tmpfs and
  shipped in core-ts 0.7.27; wicked-core #460 adds the nested-worktree regression test on the ubuntu
  bwrap leg. The ubuntu S04 leg reached deliver on crew 0.7.40 / core-ts 0.7.30 (run 36067791652).

### smoke — the release-run gate actually gates (wicked-ci #30) · S08 labels flipped (wicked-ci #31)

- **`smoke.yml` resolves its own harness ref explicitly and fails fast when it cannot.** On a CROSS-REPO
  `workflow_call` GitHub leaves `github.job_workflow_sha` empty, so the checkout fell back to
  `github.sha` — the CALLER's commit — and crew's 0.7.35 release run tried to check out wicked-ci at
  crew's tag sha and died before S01 (release verdict crew 0.7.35 §Smoke gate). A new
  `Resolve the wicked-ci harness ref` step takes `inputs.wicked_ci_ref`, else `job_workflow_sha`, else
  `github.sha` ONLY for a same-repo call (dispatch / pull_request here), else a hard `::error` naming
  the remedy (`with: wicked_ci_ref: <the sha pinned in uses:>`). Callers in other repositories pass
  the ref (crew `release.yml` does from crew PR #599).
- **The `verdict` fold fails its job on `FAIL` / `UNEXPECTED-PASS`** (after writing `outputs.overall`),
  so a caller's `needs: smoke` turns red on a red set without reading the output itself.
- **Label rot flipped (UNEXPECTED-PASS on both legs of run 34865500000, crew 0.7.35 / core-ts 0.7.26):**
  `F-RC1-110`, `F-RC1-113` → expected only on `core-ts < 0.7.26`; `F-RC1-112`, `F-RC1-116` → expected
  only on `crew < 0.7.35`. `F-003` and `F-RC1-044` flipped as designed on the same run.

### smoke — S-L1: the evaluator-verdict gate (wicked-core #488 / #498; F-RC1-131 — FIX-IT-ALL L10 for L1)

- **Seat shims end an EVALUATOR turn with `VERDICT: PASS`.** From core-ts 0.7.26 the engine appends core
  #498's convention sentence to every evaluator unit's prompt, and from 0.7.27 an output whose last
  verdict line is not PASS is DENIED into an escalation gate — a shim that never said the line would
  park every review unit. `shims/_lib.mjs` detects the sentence (`isEvaluatorPrompt`) and appends the
  line after the turn's prose; recorded as `kind: verdict` in `shim-calls.ndjson`.
- **`WICKED_SMOKE_VERDICT_FAIL_ONCE`** (set by `hermeticEnv` to `<root>/verdict-fail-once`): while that
  token file exists the next evaluator turn consumes it (rename) and answers `VERDICT: FAIL` with a
  finding above the line.
- **S04 gains S-L1 (label `F-RC1-131`, `lt(coreTs, '0.7.27')`)**: the mixed run is launched with one
  failing verdict armed; the run must park at the evaluator-verdict gate — `gateEscalated.denialSource:
  evaluator_verdict`, or `condition: verdict_not_pass` only when the shim log shows the armed FAIL was
  answered (that condition also names the layer-2 judge's denial on older engines) — with 0
  `toolExecutorDispatched` for the deliver unit ahead of it;
  the harness approves ONCE (retry — the token is spent, the seat answers PASS) and the pipeline half
  continues unchanged. Below 0.7.27 the FAIL is recorded PASS and the run proceeds → EXPECTED-FAIL;
  UNEXPECTED-PASS = label rot. An untagged arm check proves exactly one FAIL was answered whenever the
  convention was seen; on < 0.7.26 (no sentence) it is an info line. The token is removed after the run.
- README: S04 row, the policy table row, the shim behaviour paragraph.

### smoke — S08 chat joins the default set on an ACP-speaking seat shim (DES-L5 S-CHAT-01 — FIX-IT-ALL L5-ci)

- **New shim `smoke/shims/acp-agent.mjs`**: an Agent Client Protocol agent over stdio (`initialize` →
  `session/new` → `session/prompt` answered with two `agent_message_chunk` deltas and a result carrying
  `usage`; `session/cancel` honoured; unknown requests refused with -32601). It sleeps before answering
  — `WICKED_SMOKE_ACP_SLEEP_MS` (env) or a per-prompt `smoke-acp-sleep-ms=<n>` token — so the chat turn
  budget is observable. Every JSON-RPC method is recorded in `shim-calls.ndjson`.
- **Sixth overlay seat `acp-smoke`** (`lib/shims.mjs`): a NEW registry key whose `[cli.acp]` names the
  shim (stdio transport) and which is `enabled_for_council = false` — S04's mixed-auth council roster is
  exactly what it was. It is the only seat the daemon's ACP path (`chat_ensure` → spawn → handshake →
  prompt) runs on in the smoke.
- **S08 promoted to the default step list** (`S01..S06,S08..S10`; S07 stays opt-in) with the S-CHAT-01
  assertions on a daemon restarted with `WICKED_CHAT_TURN_SECS=5` (`Daemon.start/restart({extraEnv})`):
  refusal by name (F-2R2-009, kept), open → 201 + the "handed skills gen" log line (F-RC1-113), one turn
  → 202 / `chatDelta` / `chatReply {ok:true}` on `/ws` with `usage` (F-RC1-116) / the shim's
  `session/prompt` record / `GET /chats/:id.messages` (F-RC1-112), a 20 s turn cut at the 5 s budget →
  `chatReply {ok:false}` naming the seat (untagged) and the budget variable + re-seat remedy
  (F-RC1-110), the seat released, the `targets` re-seat → 202 + an ok reply (untagged), `DELETE` →
  `chatClosed {reason: requested}`, `seats: []`, `messages: []` (F-RC1-112). New `lib/ws.mjs` collects
  `/ws` frames (node ≥ 22's WebSocket global; chat replies travel only there on the published daemon).
- **Four expected-fail labels** at the placeholder bound (`F-RC1-110`, `F-RC1-112`, `F-RC1-113`,
  `F-RC1-116` — open on every published set; their fixes are designed in DES-L5 for the wave-1 core-ts
  cut and the crew that pins it): move each to the REAL fix version the day it publishes, as
  F-7R2-006's did. The step's other checks are untagged and must pass on the published set.

### smoke — S10 `status` after SIGTERM, S09 `--version` (crew #551 / #493 — FIX-IT-ALL L10-7)

- **S10** runs `wicked-crew status --port <port>` against the daemon it has just SIGTERMed and asserts
  exit ≠ 0, ONE remedy line (`no daemon answering on 127.0.0.1:<port> — start it with \`wicked-crew
  serve\``) on stderr, empty stdout and no stack frame — the operator's "it worked before the reboot"
  moment (crew #551, F-RC1-044). **S09** runs `wicked-crew --version` and compares its three lines to
  the installed tree (crew `package.json`, the resolved `wicked-core-ts`, `dist/studio`'s marker), exit
  0, empty stderr (crew #493, F-003). Both are labelled to their fix version in `lib/expect.mjs`
  (`lt(crew, '0.7.35')`) BEFORE 0.7.35 publishes: a rehearsal on `latest` (0.7.34) reads EXPECTED-FAIL,
  the fixed set must PASS, and a stale label reads UNEXPECTED-PASS. First callers of `smoke.yml`: crew's
  `release.yml` gains `version` (npm view, ≤ 10 min) + `smoke` jobs after `release` (post-publish
  release-verify; D-L10-1 pre-`latest` gate owed).

### smoke — expected-fail policy follows the 2026-09-14 release train (crew 0.7.34 / core-ts 0.7.25)

- **F-7R2-006 / F-7R3-001 → fixed in core-ts 0.7.25** (wicked-core #473, bench-on-abstention). The
  placeholder bound `0.7.99` moved to the real fix version after smoke run 34798471429 (crew 0.7.34 /
  core-ts 0.7.25 / garden 12.36.0, ubuntu + macos) reported all three routing checks passing on both
  legs (`~ passed this time` only because the ids are FLAKY). The FLAKY flag stays for the sets the
  rule still covers (core-ts < 0.7.25); on ≥ 0.7.25 the checks are plain PASS / FAIL.
- **F-SMOKE-001 keeps its bound, gains its 0.7.25 shape.** With wicked-core #477 every denial PAUSES
  at an `escalation` gate instead of ending the run, and with #476 the creator floor runs before the
  pinned validator: on ubuntu-latest S04 now sees the floor's `install` exit 1 in the checks sandbox,
  the pinned-validator denial (same signature, new "the run left a change in its worktree" prefix) and
  a `floor_failed` / `pinned_validator` escalation gate. S04 records that gate as `floorEscalation`
  (cancelling as before — a retry would run the same shim into the same floor) and routes the checks
  it ends (`mixed run completed`, `no other failure escalation`, `pipeline run: no failure
  escalation`) into the F-SMOKE-001 cascade on Linux; `repo-checks floor ran` and `node_modules
  provisioned` left the cascade at core-ts ≥ 0.7.25 (they pass there — they were UNEXPECTED-PASS on
  the run). `repo checks passed` stays in it.
- **Hermetic scan: `~/Library/Preferences/pbs.plist` is Apple's pasteboard-server preference** — the
  one Apple leaf under Preferences without a `com.apple.` prefix; the macos-latest leg of the same run
  rewrote it as the ONLY change under `$HOME` and the scan read it as a leak. Classified as runner
  noise with the other named Apple leaves — as is `~/Library/Application Support/locationaccessstored`
  (Apple's location-access store), which the previous-set leg of this PR's own selftest surfaced the
  same way.

### smoke — wicked-smoke v1, the artifact-level smoke for the wicked-* seams (S01–S10)

- New reusable workflow `.github/workflows/smoke.yml` (`workflow_call` + `workflow_dispatch`) and
  harness `smoke/` (node ≥ 22, no dependencies). It installs the PUBLISHED artifacts — `wicked-crew`
  (bundled studio inside), the prebuilt `wicked-core-ts` platform package crew pins, `wicked-bus`,
  and the `wicked-garden` plugin tag laid out as the marketplace cache — into a hermetic temp root
  (`HOME`, `CLAUDE_CONFIG_DIR`, `WICKED_*`, npm prefix/cache all under it, `TMPDIR` too on macOS /
  Windows — on Linux `TMPDIR` stays the SYSTEM temp dir by design, because the engine's bwrap
  sandboxes `--tmpfs` the temp dir and a root-local TMPDIR masked the engine's own scratch; the PATH
  carries the shims, the temp prefix, node and the system dirs only), boots the daemon with shimmed seats
  (claude answers; codex exits 401; copilot exits quota; opencode answers on its free tier; pi is
  absent; `gh` and `wicked-estate` are stand-ins — no model calls, no GitHub), and asserts the wire:
  S01 boot/packaging versions + served studio marker, S02 skills publish (portable == total, no
  findings) + the F-083 stale-rules acceptance, S03 onboarding through the real engine with
  `clis: []` (F-E2E-011) + the customer-visible debris (F-E2E-012), S04 the default-posture `bug`
  run with the mixed roster (F-090 whole-phase units, F-7R2-006/F-7R3-001 benched seats NAMED,
  F-E2E-030 deliver gate, F-E2E-029a `node_modules` provisioned into the worktree, push to a local
  bare origin, F-087 diff after completion, F-E2E-013 acceptance read writes nothing), S05 bus
  health under the two-SQLite-libraries trigger (F-E2E-021, incl. visibility in `recentErrors`),
  S06 campaign fan-out (F-086), S09 the installed tree (platform package at the pinned version,
  studio dist, F-004 roster paths), S10 SIGTERM ≤ 10 s + `PRAGMA integrity_check` + cleanup.
  S07 (interactive) and S08 (chat) ship `--steps` opt-in with TODOs (cold `npx` bridge fetch; no
  ACP-speaking shim yet).
- Verdicts: one line per step `PASS` / `FAIL` / `EXPECTED-FAIL` / `UNEXPECTED-PASS` with seconds and
  evidence path; `EXPECTED-FAIL` is a check tagged with an acceptance finding the installed version
  is KNOWN to still exhibit (`smoke/lib/expect.mjs`, keyed to the REAL fix versions: F-E2E-021 on
  crew < 0.7.33 — fixed by crew #541/#542, S05 passes from 0.7.33, FLAKY below it (the race stayed
  clean on 1 of 13 loops); F-E2E-030 on core-ts < 0.7.24 —
  the deliver gate landed in the engine, and on crew ≥ 0.7.33 S04 asserts the
  `GET /health.capabilities.deliverGate` wire against the installed engine untagged; F-E2E-002,
  F-7R2-006 / F-7R3-001 (the F-SMOKE-002 residual) and F-SMOKE-003 open with no fix version yet —
  F-SMOKE-003 on every node and engine and declared FLAKY, both `delivered` and `stranded` having
  been observed on identical inputs; F-087 open on node ≥ 26 hosts and FLAKY too (500 on two runs,
  200 on the third); F-SMOKE-001 open on linux;
  F-E2E-012 by design) — named and reasoned, never a red
  job, never silently skipped; a tagged check that PASSES while its finding is still expected is
  `UNEXPECTED-PASS — retire the label` (step line, report `unexpectedPasses`, step summary; exit 3
  unless `--allow-unexpected-pass`). Gates are judged by `awaitingHuman.gateKind` (core-ts ≥ 0.7.24),
  never by prompt text; the deliver gate is approved so the push to the local bare origin is exercised.
  `--no-expect-fail` runs strict. JSON report + daemon log + shim call log + evidence upload as
  `wicked-smoke-<os>`; a step summary is written; exit non-zero on any FAIL.
- Inputs `crew_version`, `core_ts_version` (`pinned`), `bus_version`, `garden_ref`, `steps`,
  `os_matrix` (default `["ubuntu-latest","macos-latest"]`), `expect_fail_steps`,
  `expect_fail_findings`, `wicked_ci_ref` (empty = the commit the reusable workflow was called at,
  `github.job_workflow_sha`, so a caller's SHA pin pins the harness too), `artifact_suffix` (set it
  when one run calls the smoke twice: artifact names carry `-<suffix>` so the two invocations' verdict
  folds never merge each other's legs); output `overall` = the WORST leg across the matrix (folded by
  a `verdict` job from per-leg artifacts). `--assert-hermetic` (always on in the workflow) walks the
  wicked/CLI directories under the real `$HOME` fully (bounded) and fails the run if anything
  changed (`~/Library` is recorded to its grandchildren, watched where a third-party tool writes);
  three classes are reported as `noise`, not a leak: the macOS user media folders (a hosted macOS
  runner's own daemons write there — `photoanalysisd` under `~/Pictures`, a bare mtime move on
  `~/Movies`), Apple's own state under `~/Library` (`com.apple.*` preferences and caches, `Biome`,
  `Daemon Containers`, … — the runner churns them for the whole run), and a directory whose own mtime
  moved while none of its recorded direct children changed or whose changed descendants are all noise.
- Docs: README **smoke** section, `smoke/README.md` (what it catches, the step table, how to add a
  step, the expected-fail rule), `docs/smoke-consumer-recipes.md` (post-publish in `node-release`
  callers for crew/core/bus/garden/studio; per-PR against the others' `latest`).
- Self-test `.github/workflows/smoke-selftest.yml`: every PR touching `smoke/**` or the workflow runs
  the reusable `smoke.yml` from that ref on ubuntu + macos against the current published set, plus one
  macOS leg on the PREVIOUS published set (crew 0.7.32 / core-ts 0.7.23, `artifact_suffix: prev`) so
  the expected-fail policy is proven on both sets a customer can be running — the workflow_call seam
  proven before any consumer adopts it (the docs-lint / rules-conformance idiom).

## v1.2.0

Everything `v1` has floated onto since `v1.1.2`, now under a semver tag.
No breaking change: every new input defaults to the pre-1.2.0 behaviour.

### node-release — opt-in checks sandbox on Linux test runners (wicked-core#433)

- New input `arm_checks_sandbox` (boolean, default `false` — **opt-in**). When `true`,
  Linux test runners install `bubblewrap`, lift the ubuntu-24.04 AppArmor gate on
  unprivileged user namespaces (`kernel.apparmor_restrict_unprivileged_userns=0`,
  best-effort) and run a `bwrap … -- /bin/true` smoke before `install_cmd`; the smoke
  fails the step — not a test — when no boundary can be armed. Needed only by callers
  whose test suite drives a real deliver through `wicked-core-ts` ≥ 0.7.20: that engine
  re-runs a repository's checks INSIDE an OS write boundary before the deliver phase
  pushes and fails closed without one. wicked-crew's `deliver-e2e` suite is the first
  such caller — its `v0.7.29` release run went red on `no OS write boundary could be
  armed` while the same suite was green on PR CI, whose `ci.yml` arms exactly this
  (wicked-crew#527). The smoke is a proxy for the engine's own `bwrap` invocation, not
  the identical argv. Default `false` leaves every existing caller's test job unchanged;
  macOS / Windows runners are untouched either way.

### node-release — workspace publish dir + token-auth publish path (#7)

- New input `publish_working_dir` (string, default `.`): the directory `npm publish` runs
  from, in both the npm and the GitHub Packages publish jobs. Set it to the publishable
  package dir of a workspace whose root is private (e.g. `packages/crew`).
- New input `use_npm_token` (boolean, default `false`): publish with an `NPM_TOKEN` secret
  (`NODE_AUTH_TOKEN`) instead of tokenless OIDC trusted publishing — for brand-new package
  names that have no pre-registered trusted publisher. `--provenance` is still attached.
  The caller passes `secrets: inherit` and defines `NPM_TOKEN`. Default `false` keeps every
  existing caller on the OIDC path, byte-identical.

### node-release — `build_cmd` (compile before publish)

- New input `build_cmd` (string, default empty = no build): a command run at the repo root
  before publish (e.g. `npm install && npm run -w packages/crew build`) for packages whose
  `dist/` is gitignored rather than committed. Runs with full dev deps, in both publish
  jobs. The empty default leaves existing callers unchanged.

### rules-conformance — the CI conformance seam (AW-17, recall-report v1; #18)

- New reusable workflow `.github/workflows/rules-conformance.yml`: ingests the caller's
  governed rules corpus (`rules_dir`, default `governance/packs`) into a scratch store
  with `wicked-core rules ingest`, recalls it severity-ordered with
  `wicked-core rules recall --json`, and posts ONE sticky, advisory PR comment citing
  every applicable rule's id and wiki URI. It reports the applicable ruleset; it does
  NOT evaluate the diff and it NEVER blocks.
- Inputs `rules_dir`, `wicked_core_repo` (default `mikeparcewski/wicked-core`),
  `wicked_core_ref` (default `main`; resolved to a sha that keys the binary build cache),
  `comment` (default `true`). Outputs `status` (`reported` | `finding-ingest-failed` |
  `skipped-no-rules` | `skipped-no-toolchain` | `error-recall`), `rule_count`, `rule_ids`.
- **Honest fail-open**: a missing corpus or unavailable toolchain skips with a workflow
  notice; a corpus that fails to ingest is posted as a finding while the job stays
  green. Caller permissions: `contents: read`, `pull-requests: write`.
- Selftest `.github/workflows/rules-conformance-selftest.yml` runs the seam against
  `examples/fixtures/rules-conformance/{valid,violation}` on every wicked-ci PR and
  asserts the outputs; caller example in `examples/rules-conformance.yml`.

### docs-lint — the family docs lint (DT-21, recon-2026-08 docs-R25)

- New reusable workflow `.github/workflows/docs-lint.yml` and composite
  action `docs-lint/` (`docs-lint/docs_lint.py`, stdlib-only Python,
  cross-platform). Rules: **retired-name** (retired product names outside
  historical markers / exempt paths, per the DT-22 contract
  `docs/docs-lint-scope.md`; unclosed marker blocks are errors),
  **install-cmd** (parse-level, no-network smoke validation of documented
  npm / npx / `cargo install` / `claude plugin` commands against the static
  family registry `docs-lint/registry.json`), and opt-in **version-stamp**
  (doc stamps of the repo's own packages vs `package.json` / `Cargo.toml`).
- The recon-verified defects docs-R2 (cargo bin-on-PATH claim), docs-R4
  (nonexistent `claude plugins add`; one-step `/plugin install`; not-a-plugin
  install), docs-R17 (`npx` of a bin that is not an npm package), and
  docs-R23 (one-step plugin install in a retirement banner) are pinned as
  fixtures in `docs-lint/tests/` — each is provably caught pre-merge.
- New self-test workflow `.github/workflows/ci.yml`: unit tests on
  ubuntu/macos/windows + a self-lint of this repo's docs surface.
- **Repo-side enablement, pilot = this repo** (DT-22 top-up): `ci.yml`
  now also calls the reusable `docs-lint.yml` via `workflow_call`
  (`wicked_ci_ref` pinned to the building sha), exercising the exact seam
  consumer repos will use. The 68 unmarked retired-name mentions across
  wicked-garden / estate / vault / ledger / interactive / installer / core
  were annotated per `docs/docs-lint-scope.md` in each repo's
  `docs/dt22-topup` branch — the lint runs green on all seven, so consumer
  enablement can proceed once `v1` is retagged onto a commit that carries
  `docs-lint/`.

### Dependencies (Renovate)

- Action pins bumped in both reusable workflows: `actions/checkout` v6 → v7
  (`3d3c42e`), `actions/setup-node` v6 → v7 (`8207627`), `actions/setup-python`
  v6 → v7 (`5fda3b9`); `softprops/action-gh-release` stays on v3 at digest `efb3536`.

## v1.1.2

- `node-release.yml`: `publish-github-packages` now `needs: [test, publish-npm]` and is
  gated on `needs.publish-npm.result == 'success'`, so GitHub Packages never mirrors a
  version whose npm publish failed (closes the partial-release race; #3). No input change.

## v1.1.1

- Drop `vitest` from the "wicked shared deps" group. It was matched by both that
  rule and Renovate's built-in vitest-monorepo preset, producing duplicate PRs
  (wicked-bus #24 + #25). The built-in group now owns vitest. No workflow change.

## v1.1.0

Supply-chain hardening (no workflow behavior change vs v1.0.0).

- `default.json` preset now extends `helpers:pinGitHubActionDigests` and the
  `github-actions` group matches `pin`/`pinDigest` updates — Renovate
  digest-pins third-party actions across every consumer and keeps them bumped.
- Documented the **SHA-pin everything** posture: consumers pin the
  reusable-workflow ref to an immutable commit SHA (`@<sha> # v1.1.0`) and the
  Renovate preset to `#v1.1.0`, rather than the floating `@v1`. Renovate bumps
  both on each release.
- Added `renovate.json` so `wicked-ci` self-manages via its own preset.

## v1.0.0

First real release. The earlier draft was scaffolded but never tagged, so no
consumer ever pinned it — the action pins are baselined directly to what the
sibling repos already run in production (checkout@v6, setup-node@v6,
action-gh-release@v3, create-pull-request@v8) rather than the stale v4/v2/v7
the draft carried.

### Reusable workflows

- `node-ci.yml` — matrix test (ubuntu/macos/windows), inputs for
  working dir, install/test commands, node version, a configurable
  OS matrix, and optional Python setup.
- `node-release.yml` — npm publish (trusted publisher + provenance),
  GitHub Packages mirror publish, GitHub Release with auto-generated
  notes, and an optional catchup PR that bumps `package.json` on `main`
  to the released tag.

### New inputs (added so all four npm publishers — bus, brain, loom, vault — converge on one release workflow)

- **`os_matrix`** on `node-release.yml` (already on `node-ci.yml`):
  narrow the pre-publish test matrix, e.g. `["ubuntu-latest"]` for
  bash/python gates that don't run on Windows (wicked-vault, wicked-loom).
- **`setup_python` / `python_version`** on both workflows: set up Python
  before install/test for repos whose suites are pytest (wicked-loom) or
  bash that shells out to python (wicked-vault). Default `false` — npm-only
  callers are unaffected.

### Behavioural notes (vs the bespoke workflows)

- **Brain parity**: `pre_publish_install_dirs` runs in BOTH the npm and
  GH-Packages publish jobs. The previous brain workflow installed
  `server/` only in the npm job and `.` only in the GH-Packages job;
  the shared workflow installs whatever the caller lists in both, which
  is strictly safer with negligible extra runtime.
- **github-release `if:` cleanup**: dropped `always() &&` since the
  `needs:` already gates on success.
- **peter-evans/create-pull-request@v8** (bus/brain bespoke were already
  on v8; the draft template lagged at v7) — standardised on v8.
- **`fail-fast: false`** added to test matrices so a flake on one OS
  doesn't cancel the others.

### Cross-repo dependency coordination

- `default.json` — a Renovate preset the consumer repos extend
  (`"extends": ["github>mikeparcewski/wicked-ci"]`). Groups GitHub Action
  pin bumps into one PR per repo and pins shared npm deps
  (`better-sqlite3`, `vitest`, `@types/node`, `typescript`) to a common
  cadence so the family upgrades in lockstep instead of drifting.
