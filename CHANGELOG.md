# Changelog

## Unreleased

### selftest — the :7721 rig's fixtures adopted; npm publish workflow (prepared; the first publish is the operator's)

- **Fixtures** (DESIGN §4) now live in `selftest/fixtures/`. The repos `hello-onboard`, `hello`, `tiny-math-untested`
  and `reqgraph-tm` are `git archive HEAD` exports of the rig lanes' checkouts. `mcp/echo-mcp.py` is the J6/MCP
  server, and `docs/` holds the Chat-journey documents. `fixtures/README.md` gives each one's provenance and use.
  `selfcheck` refuses a machine path in any fixture, and a mutation check confirmed it catches one. The PDFs carry
  no author metadata. Once wired into steps they replace the rig's GitHub fixture repos.

- `.github/workflows/selftest-release.yml` publishes `selftest/` to npm on a `selftest-v<X.Y.Z>` tag that equals
  `selftest/package.json`'s version. It runs the offline selfchecks, checks the tarball's contents, and uses tokenless
  OIDC trusted publishing with provenance. It runs in the protected `npm-release` environment (a required reviewer,
  `selftest-v*` tags only), which is also the npm trusted publisher's environment, and it refuses a tag whose commit
  is not on `main`. Only admins can create tags (`release-tags` ruleset).
- `selftest/package.json` is no longer `private`: it gains `files`, `repository`, `homepage` and `publishConfig`.
  The tarball (with the fixtures) is listed by `npm pack --dry-run` in CI.
- `selftest/RELEASING.md` covers a release, plus the one-time first publish and trusted-publisher setup on
  npmjs.com. npm registers a trusted publisher only on a package that already exists.
### e2e — studio journeys (U steps) sealed through `e2e run`

- **U04/U05/U06 read a single-rule card.** When one rule is left unchecked, studio names it ("The rule POL-2101 needs
  your call", "Confirm or skip POL-2101") instead of counting. Core main reached that state on 2026-11-11, and U04
  stopped at an "unknown" card on the Tier 2 main set. The journeys now accept both wordings.
- The `wicked-ci-smoke` adapter claims `selftest/lib/steps/Uxx-*.mjs`. It runs the harness with the runner's
  Python and the e2e Playwright hook, and the journey's driver loads that hook explicitly (it runs `python -I`).
  The hook writes the browser's `/api/` HAR, the catalog's DOM samples and copies of the screenshots under
  `<tap>/pw/<step>/driver/`. The driver keeps its own trace and video.
- These become the step's browser HTTP observations and `network` events, its DOM samples, and its screenshot,
  video and trace evidence. They are sealed in the run's wicked-vault like every other scenario.
- Steps that read the onboarded corpus (S04–S06, S11, S12, U04–U07) get S03 first. Before, a plan that selected
  one of them alone was refused by the harness.
- Four studio-ui capabilities gain a `wicked-ci` U scenario (`e2e-hermetic`). The pairs are `agents.table`/U02,
  `session.deliver-card`/U04, `gate.plain-words`/U05 and `steer.import`/U06. U01 (the Nerve Center) and U03 (the
  Assist composer) have no matching capability yet. A HAR that does not parse leaves the `network` stream incomplete.
  U steps are probed with the journey's own `python -I`. A local
  `e2e run --select id:studio-ui.steer.import` ran U06. It observed five of the six typed checks from the browser
  (the HAR event, the DOM samples, the rules-list API) and sealed them in the vault, and `validate --report` read
  OK. The verdict was partial: the oracle is partial, and "retired absent" is not on U06's path.

### selftest — U06 steering cited, U07 stalled run (EXPECTED-FAIL F-CREW-1501)

- **U06 (J7).** The person imports a one-rule markdown doc on the Steering page (More → Import rules…) and sees the
  rule listed in force. A `/bug` run's rule-check card, opened as a person would, then lists the rule, and the
  run's gate carries it. It is in `pr` (about 2.5 min) and `release`.
  - Hermetic limit: the engine accepts no judge for the rule check here, so the rules read "unchecked" (the
    thin-roster card).
  - A plan cites only `plan.compose` testing rules.
- **U07 (J8).** Scenario `fix: stall` makes the fix turn sit silent and idle. With `workerStallMinutes: 1` and
  escalation and the silent-turn rung off, `GET /system` and the Nerve Center's Runs row must say stalled. It is in
  `release`.
  - It is EXPECTED-FAIL `F-CREW-1501` (wicked-crew#1501): core's 15 s `toolActivity` working heartbeat is a relay
    frame, and crew's watchdog restamps its silence clock on every frame. Reproduced: 150 s silent against a 60 s
    threshold, and the run read "working: last event 1 s ago".
  - The step cancels its run and restores the knobs after.
- **Journey checks can name a finding** (`finding: "F-…"`), so the expected-fail policy decides them as it does for
  API checks. The driver writes the journey's state (the run it launched) into `result.json` for its step's cleanup.
  The shim call log records the rule ids a rule check named (`ruleIds`).
- **U07's oracle (review):**
  - Only the heartbeat's own signature, the run still executing in its silent turn and read as "working", carries
    `F-CREW-1501`. A missing run or row, a finished run or any other state is an ordinary failure.
  - One 4 min budget runs from the shim's marker for both surfaces. The marker names this run's worktree, so a stale
    one is refused.
  - Cleanup is checked: the run is cancelled and reaches a terminal state, and the knobs are restored from
    `GET /settings`'s `settings`.
- **Review r2 on #71:**
  - U07 is SKIPPED before any setup when there is no browser.
  - Cleanup cancels the launched run by its id even when the runs list fails.
  - An observation counts only inside the deadline.
  - The row's visible `nc-run-liveness` label must agree with its data.
  - A pass carries the finding too, so a fixed crew reads UNEXPECTED-PASS until the label is retired.
  - U06's step cancels its parked run, checked.
- **U06's oracle (review):** the receipt must read "1 of 1 entry imported" for the rule. The wire check reads the
  current gate's structured rule rows, and the UI check reads that gate row's own rule list.

### selftest — pull-request CI (`selftest.yml`) and Tier 2 packs

- **`.github/workflows/selftest.yml`**, the reusable workflow a product repo calls on its pull requests. It packs the
  repo under test from the caller's tree at `github.sha` (the PR merge commit) and crew, studio and garden from
  their `main` (the engine stays crew's published pin unless core is under test: Tier 2), then runs `--profile pr`
  on ubuntu. It is **advisory** by default: the job stays green and the suite's real
  verdict goes to a warning annotation, the job summary and the `overall` output, until the flake rate is measured.
  wicked-ci's own CI calls it on the `main` set (Tier 1, and Tier 2 with core under test), not advisory.
- **Tier 2: `pack --core-src`.** It napi-builds `crates/wicked-core-ts` from a wicked-core checkout and packs it
  with the host's binary inside, stamped `+st.<sha7>`, with no platform optionalDependencies and no scripts. The set
  names it as `coreTs`. `--cargo-target` keeps the cargo build cacheable.
- **The Playwright browser is installed without apt first** (smoke.yml and selftest.yml). The runner image carries
  Chrome's libraries. The system packages are installed only if the browser cannot launch, with three tries and a
  15 min bound. Apt DNS failures on the runner failed every studio-journey leg of this PR twice. The set also records the engine crate's
  version and its gate protocol from that tree, and the `wicked-core` CLI shim answers with them. The first Tier 2
  run on core main failed every governed unit with "this engine speaks 3, the CLI speaks 1", because the shim always
  said protocol 1. On a Tier 2 set, S09 checks the binding inside the installed engine and its stamped version,
  in place of the release-train checks. A `--core-ts` given after `--set` drops the set's engine facts.

### selftest — governed journeys through studio (U04, U05), S12, scenario data, teardown sweep

- **U04 (J4).** A bug fix is launched from New job, steered on its cards and delivered, all in studio:
  - The person turns QE acceptance off in Settings first. The stub seats keep no QE ledger, and the run labels the
    skip as the operator's; it never reads as passed.
  - The plan gate is approved in the thread. Each decision is waited on until the UI's own POST goes out, because a
    card sends only after its 10 s undo window.
  - The hermetic roster has one signed-in work CLI, so every "no independent judge" card and every "N rules need
    your call" card gets the person's own labelled judgment.
  - The deliver card is confirmed. Passes when the run is completed, the run page shows the delivery, and the branch
    on the bare origin returns the sum. In the `pr` profile.
- **U05 (J5).** Scenario `fix: break` makes the stub's fix add a wrong test, `add keeps zero as the identity`. The
  run must stop at a card that names it and offers a way forward, and deliver nothing. In
  `release`.
- **S12 (wicked-core#1373).** A second hermetic daemon (its own state, port, bus and worker home) registers the
  same fixture clone and restarts. The first daemon's worktrees must survive. EXPECTED-FAIL (`F-CORE-1373`) until
  the owner-scoped reaper ships; locally it removed 5 of 5. In `release`.
- **Scenario data.** `<root>/scenario.json`, written by a step and removed after, drives the stub seats.
- **Seat shims:**
  - read the unit's step id (`then: <step> — …`), so a studio job's read-only `pa-scope` never writes;
  - accept the PA's team step reviews (`STEP <id>: ACCEPT`);
  - the chat seat answers governed work steps once S08 has made it work-eligible.
- **Teardown sweep.** After the daemon stops, any process still naming the run root is stopped and listed in the
  report (`leftoverProcesses`). The harness's own ancestors are excluded. A document bridge once outlived its daemon.
- **Journey evidence.** Each journey now also records a video and a trace beside its screenshots. (Sealing U steps
  through `e2e run` needs the browser's HTTP and DOM observations exported first: next.)

### selftest — studio journeys (U01-U03) and `wicked-selftest serve`

- **Studio journeys.** The U steps drive the daemon's own studio in Chromium (Python Playwright), against the same
  hermetic daemon as the API steps:
  - U01 opens studio. The Desk and the Nerve Center render; the rail tile's tone equals the page's; the service the
    hermetic daemon lacks (wicked-estate) reads down, and the page is not called all good.
  - U02 checks that every stub seat on Helpers reads as it is: signed in is Ready, signed out is Not ready with a way
    forward.
  - U03 asks in chat. The answer sits under its question and names its helper, and the UI's own requests opened the
    chat and sent it.
- **The driver** (`journeys/driver.py`) aborts every off-origin request and records page and console errors, responses
  of 400 or more, and the non-GETs the UI sent. It takes terminal-state screenshots at 1440x700 and 390x844 in both
  themes into the step's evidence. A journey with no checks is an ERROR. With no `--python` (or
  `WICKED_SELFTEST_PYTHON`), the U steps are SKIPPED with the reason and named on the verdict line, never passed.
- **Profiles.** `pr` and `release` now include U01-U03. `smoke` (the release smoke's default) is unchanged.
  `smoke.yml` takes a `profile` input and installs Python Playwright + Chromium when it carries U steps.
  smoke-selftest adds a `pr`-profile leg on ubuntu.
- **`wicked-selftest serve`.** It boots the hermetic daemon (S01 S02 S03, or `--steps`) and holds it open, with stub
  seats and the fixture repo, until Ctrl-C, SIGTERM or `<root>/stop`. This is how the operator sees a branch live
  before it is packaged, with nothing outside the root.
- **Seat shims.** A chat answer step (`answer-N — <words> |||`) is answered as a chat seat would, about the fixture, citing
  its file, instead of acknowledging a "fix phase" guessed from the chat scope's text.
- **Ranges.** Step ranges stay within one family: `S01..S11` never picks up a U step, and `U01..U03` works.

### selftest — the smoke harness grows into the product self-test (`wicked-selftest`)

- **Why.** When a change lands in wicked-crew, wicked-studio, wicked-core or wicked-garden, nothing proves the
  product still works before merge. The floors run unit tests, and the smoke installs only what is already
  published. The :7721 test rig that filled the gap by hand is retired. The operator approved one consistent
  self-test: humans, pull-request CI, a governed run's floor and the release smoke run one versioned suite, and they
  differ only in the set they install and the profile they select.
- **Moved.** `smoke/` is now `selftest/`, with its history. The package is `wicked-selftest` 0.2.0 with two bins:
  `wicked-selftest run|pack`, and `wicked-smoke`, kept as an exact alias of `wicked-selftest run`. With no new flag,
  a run is what the smoke always ran: the published set and the same steps, checks and report. `smoke.yml`,
  `smoke-selftest.yml`, `e2e-catalog.yml`, the e2e catalog's scenario references, the e2e smoke adapter and the docs
  follow the move, and the e2e test index counts `selftest/` as a test directory. Callers that pin a wicked-ci SHA
  are unaffected.
- **Sets.** `--crew`, `--bus` and `--core-ts` take a local `.tgz` file as well as an npm version. A source directory
  is refused, because npm would run its `prepare` script and link the checkout into the install. `--garden` takes a
  local `.tgz` or directory as well as a tag: a git checkout is exported with `git archive HEAD`. `--set <file.json>`
  names them together, with paths resolved against the file's directory. Anything that could silently test something
  else is refused: an unknown key, a missing pack, an empty or whitespace value (npm reads `wicked-crew@ ` as latest),
  or a tarball whose `package.json` names another package. A pack path may hold spaces; a version or tag may not. The installed version is then checked against the pack's.
  A garden manifest's version must be a single-component semver before anything under the plugin cache is replaced, so
  a `../` version can't reach outside the root. A linked
  `.claude-plugin/plugin.json` is refused before it is read.
- **Pack (Tier 1).** `wicked-selftest pack --crew-src --studio-src --garden-src --out` builds packs the way the dev
  copy does: garden exported, studio built with its dist stamped, crew built with that studio dist bundled. It writes
  `set.json`. Every build runs in a `git archive <recorded sha>` export under `--out`. The checkouts are only read: git
  runs with `--no-optional-locks` and command-scoped `core.fsmonitor=false`, and garden's tarball is gzipped in
  process, not by a git archive filter. An interrupted pack can't leave a checkout stamped or half-built, and a checkout
  that moves mid-pack can't change what was recorded. `--out` must not exist yet, because creating it is the claim, and
  `set.json` is published atomically. The build runs with a constructed environment:
  HOME, npm cache/config and temp under `--out`; no system or global git config; no inherited `GIT_*` routing; argument
  arrays, never a shell. A checkout with uncommitted or untracked changes is refused unless `--allow-dirty`, which
  records that they were left out. crew and studio versions are stamped `+st.<sha7>`. Building runs the checkouts' own
  code, so it is for trusted trees or a sandbox. `run` never builds.
- **Reserved ports.** The harness never binds 7701, 7702, 7703 or 7721.
- **Profiles.** `--profile smoke` is the default and today's set. `pr` is S01 S02 S03 S04 S08 S10, for a pull request
  and a governed run's floor. `release` is every step except the opt-in S07. A profile only selects steps, and
  `--steps` and `--profile` are exclusive. The report records the profile.
- `npm run check` covers profiles, the set-file refusals, the garden version guard, reserved ports, and `pack` on
  disposable fixture checkouts (untouched checkouts, the stamp, the bundled studio, HEAD-only exports, dirty refusal).
  The smoke workflow runs both checks.

### smoke — the seat shims answer the engine's rule check; S02 reads crew's home-scrubbed paths

- crew 0.18.0's release smoke (run 42512851279) failed S02, S04 and S11 on ubuntu and macOS. The package was
  sound; the harness was behind two product changes.
- **S04 + S11 (rule check).** core-ts 0.15.32 (wicked-core#1317) judges every steering rule in force at review
  and delivery: a judge seat answers one `RULE <id>: KEPT|BROKEN|N/A — <cite>` line per rule inside a
  `BEGIN VERDICTS <nonce>` … `END VERDICTS <nonce>` block. The shims took those prompts for worker turns and
  answered prose, so every rule read "unchecked", the verify gate held ("8 steering rule(s) need you:
  MCPS-1006 unchecked …") and both runs were cancelled before delivery. S04's "opencode never spawned for
  governed work" check also counted those 32 judge calls as worker turns.
- The shims now recognise a rule-check prompt (kind `rules`, recorded as such) and answer the call's block
  the way the engine's own stub runner does (`stub_rule_verdicts`). On the change each rule is N/A, naming the
  changed files the prompt lists; at delivery (no file list) and for a process rule (reported only) it is N/A
  with the reason. POL-2101's record clause has no N/A: the judge looks in each step record for the whole
  `Stack check:` sentence every `_lib.mjs` worker turn now ends with, and answers KEPT quoting it, or BROKEN
  naming each record without it (a TODO, a denial or a cut line is not the sentence). No bar moved: an answer
  outside the block, a KEPT without its evidence, or a record with no stack check still holds the gate.
- **S02 (home-scrubbed paths).** crew 0.18.0 (crew#1439) scrubs home paths out of `/health`, `/diagnostics`,
  `/system` and `/roster`, so the published snapshot's path read `~/wicked-smoke-root/state/skills/...`. "Points
  inside the temp root" and `existsSync` then failed while generation 1 sat on disk (the daemon log shows it
  seeded and published from the Claude plugin cache, garden 12.66.1). crew#1439's new garden-discovery order
  played no part. The scrub is lossy (any user's home reads `~`), so S02 maps a scrubbed path back only onto
  the path `GET /skills` attests unscrubbed (the current generation and its skills root), and only when that
  path scrubs to exactly what was shown. "Inside the temp root" is now judged by path components after
  normalising, so a `..` escape fails. An older crew's absolute path is unchanged.
- `npm run check` covers it: each rule-check kind is answered and counted (a simplified mirror of the engine's
  parse and its per-subject bars), a record with no stack check, or only part of one, is BROKEN, every
  answering shim dispatches the kind, and the S02 mapping accepts only an attested path and refuses another
  user's home, a traversal and an escape from the root. These checks fail on the previous shims and S02.

### e2e — garden.site.chrome checks the new header (wicked-web#57)

- The shared header's Experiments menu is gone (wicked-web bc5ca29): the flask is a plain link to
  wickedlabs.ai, and a product site's lockup is the path "Wicked Agile / labs / wicked-garden". The
  capability's oracle asserted the old menu (`.dropdown-plane` count 4). It now checks the topbar's Breadcrumb
  nav holds 3 links and the flask's Wicked Labs link points at `https://wickedlabs.ai/`. The theme clause
  stays untyped, so the oracle stays `complete: false`.
- The theme clause names the key the chrome writes, `wa-theme-v3` (wicked-web Topbar), not `wa-theme`.
- Nothing runs this oracle against the garden site today. No adapter claims `wicked-garden:site/tests/...`,
  and `validate` checks only that the scenario file exists at the pinned garden SHA. A live run's direct
  read visits only the studio root, which has neither header, so its result is the same before and after.
  The change turns no job red, before or after the garden site moves to the new header.

### smoke — S04 runs phased on a power-mode crew; S11 proves the power-mode bug run

- crew 0.16.11 made power mode the default for a repository launch, and crew 0.16.12's release smoke (run
  41428295027) failed S04 on both OSes: the launch sent no `power` field, so the run was a power run. Its plan
  was `pa-scope, architecture, fix, verify, review, security_review, deliver`, not the preset phases S04
  asserts. The seat shims did not know the orchestrator turn protocol: they never ended a turn with
  `HANDOFF:`, so the build ran all 12 turns. After a hand-off send-back the shim answered "nothing to change"
  without the engine's `no change needed` declaration, so the build unit was rejected ("the build step changed
  nothing in the worktree").
- S04 now sends `power: false` when `GET /health.capabilities.powerMode` is true (an older crew never sees the
  field), so its phased assertions stand unchanged.
- New step **S11 bug-run (power mode)**, run right after S04 (S10's teardown stays last; `ALL_STEPS` is the
  run order). It launches the same issue with `power: true` on the live seats and proves:
  - the power run;
  - an orchestrator hand-off before the turn cap;
  - a one-round passing hand-off;
  - completion with no escalation and the human deliver gate;
  - delivery of `a + b` to the local origin, with the PR opened by the `gh` shim.
  A crew without `capabilities.powerMode` is noted and not judged.
- The seat shims answer the orchestrator protocol (wicked-core `src/power.rs`), only on orchestrator prompts
  (`[power mode] You are the ORCHESTRATOR` / `[power mode] Turn N of at most M`). The first turn applies the
  corpus fix and ends `HANDOFF:`. A turn over a tree that already holds the fix declares `NO CHANGE NEEDED:`
  and hands off. Phased prompts are answered exactly as before.
- `--steps` ranges are numeric (`S01..S11` selects every step 1 to 11) and run in `ALL_STEPS` order. A
  positional slice of the run order would have silently dropped S05-S10.
- S11 fails, never passes vacuously, on any of these:
  - a broken or malformed `/health` (not a JSON object), or a launch answer without a `runId`;
  - an orchestrator that is not the creator unit's seat, turns on another seat, out of order or after a
    session restart, or a last turn that did not hand off;
  - a hand-off row without step, unit or round, a second round, or a missing `rescore` or `checks` on the build
    unit;
  - a hand-off that does not run every evaluator phase the DECLARED plan requires (`power.plan.handoff`:
    tests → verify, a distinct-seat or design review → review, security → security_review). Each phase must be
    recorded under its own step (`qe`, `review`, `security`) by the unit's assigned seat, and that seat must not
    be the orchestrator's (evaluator ≠ creator);
  - a build floor whose LAST `repoChecksEvaluated` on the build unit did not pass with a passing test check;
  - a `gateEscalated` anywhere in the run's event history, even one the poll missed between views;
  - an evaluator-verdict gate (nothing is armed for S11, so the shared helper's S04 retry is off:
    `launchAndFollow(…, { retryArmedVerdict: false })`);
  - a deliver gate that is not the wire kind, or whose pause does not name the run's branch, or sees it
    already on the origin or a PR already opened;
  - a `gh pr create` that is not `--head <run_branch>` from the run's own worktree.
- `selfcheck.mjs` checks:
  - the step registry as a set, plus the run order (S11 after S04, S10 last), and the numeric ranges;
  - the orchestrator protocol (fix + `HANDOFF:`, `NO CHANGE NEEDED:` + `HANDOFF:` on a fixed tree, and a
    phased prompt unchanged);
  - S11's judgements (exported pure functions) against the recorded good run and each adversarial wire above;
  - S11 against a 500 or array `/health` and a 201 launch without a `runId`.
  It fails without the shim change. The two `launchAndFollow` options (the verdict retry opt-out and the
  deliver-pause hook) run inside its gate-polling loop. They are exercised by the live smoke, not by
  `selfcheck.mjs`.

### smoke — S02 reads the skills verdict after crew's background publish lands

- crew 0.16.2 (crew#1146) listens before the skills snapshot is verified: the boot ladder publishes in the
  background and `/diagnostics` reports skills `publishing` (with a transient base-skill finding) for about
  2-13 s after ready. S02 read `/diagnostics` once, right after `/health`, so crew 0.16.2's release smoke
  (run 40277224745) failed S02 on both OSes with `state publishing` while every other step passed. S02 now
  polls `/diagnostics` while the state is `publishing` (500 ms, up to 120 s) before each of its three reads
  (boot, after the stale-rules restart, after a restore) and notes the wait. An older crew is never
  `publishing`, so its first answer is used at once. The assertions are unchanged. The wait is bounded as a
  whole (each request is raced against what is left, at least 1 s, and also by the step's deadline), and it
  honours the step's abort signal, so a timed-out S02 throws instead of going on to rewrite the skills root and
  restart the daemon under the next step. `selfcheck.mjs` covers an older crew, a refused state, publishing
  then published, a stuck publish, a hung request, and an abort before and during the wait.

### e2e — phase 3: the wicked-e2e skills, `e2e resolve`, `e2e evidence`, plan summaries and pass blockers

- **`skills/`**: six portable skills over the `e2e` CLI: `wicked-e2e` (router), `wicked-e2e-plan`,
  `wicked-e2e-run`, `wicked-e2e-validate`, `wicked-e2e-report` and `wicked-e2e-evidence`, plus
  `wicked-e2e/refs/<area>.md` per catalog area (hand-written setup quirks and a block generated
  from the catalog by `skills/tools/gen_refs.py`). `skills/install.sh DEST` (or `--codex`) installs
  them by symlink or `--copy`.
- **`e2e resolve "<request>"`**: a deterministic request-to-selection reader for the router (areas
  and aliases, tags, ids, id segments, profiles, literal terms; refuses 7701/7721; flags cost M/L
  and live selections as ask-first; "re-run what failed" from a run directory).
- **`e2e run --plan-only`** prints and writes a plan summary: needs, skips by dependency, the best
  verdict each capability can reach, a time estimate with its basis, `ask_before_running`.
- **`e2e report`** gains "What blocks a pass". **`e2e evidence <run-dir> <cap-id>`** lists one
  capability's evidence with per-file integrity against the vault.
- CI: skill lint (frontmatter, real subcommands and flags from `e2e --help`, portability, honesty
  guards), the install script and 54 router evals on ubuntu, macOS and Windows; the refs check.

### e2e — phase 1 of the platform certification suite: catalog, typed oracles, surface manifests, coverage validator

The certification rule is "the user's exact path to its terminal state". A launch is not done,
creating something through the API is not creating it in the UI, and a stub is not the real thing.
`e2e/` now holds what has to be certified and proves that list is complete. It runs nothing
against a product. The runner, the evidence capture and the skills are phases 2 and 3.

- **`e2e/catalog/<area>.json`**: 1410 capabilities in 9 areas, normalised from the 2026-10-20
  inventory (1533) and its completeness critic. The critic folds:
  - 49 capabilities added;
  - 172 true duplicates merged and kept as `aliases` (merged only within one surface; the UI and
    API forms of a feature stay separate as `related`);
  - proxy paths converted to the real user path: studio against a real crew daemon serving its
    bundled studio, and launches that end at the run's terminal state;
  - permissive and tautological oracles tightened.
- **`e2e/catalog/SCHEMA.json`**: the record schema.
  - Each capability carries a **typed oracle**: `dom`, `api`, `event`, `file`, `exit`, `npm` or
    `gh`, an `all` of those, or `manual` with a category and reason. Manual is counted
    separately and is never a pass.
  - Each capability also carries `required_evidence`. A UI capability always requires `video`,
    `screenshot` and `trace`.
- **`e2e/surfaces/`**: user-facing surface elements and a test-file index per repo, read from
  source at pinned SHAs.
  - The repos are studio, crew, estate, garden, core, interactive, bus, vault, ledger and
    installer.
  - The crew CLI comes from the published tarball's compiled text, read without executing it.
  - The manifests reproduce byte for byte from `pins.json`.
- **`e2e/bin/e2e validate`** (Python 3, stdlib only):
  - schema and id checks;
  - every surface element covered (unmapped elements fail by repo, with a ratchet baseline that
    only shrinks);
  - every scenario reference a real test file at the pin;
  - oracle semantics: comparisons carry values, nothing is vacuous, every typed oracle states
    `complete`, completeness is computed recursively over composites (one function for the
    catalog, the summary and the run-report guard), and a UI oracle with no dom check is never
    complete;
  - `--report <run-dir>`, which checks a phase 2 run for verdicts, observed values and non-empty
    evidence (UI needs a `.webm`; symlinks may not leave the run dir).
- **`e2e select`**: the selection language (`area:`, `tag:`, `id:` glob, `surface=`, `cost<=`,
  `oracle=`, `!`), and `e2e/profiles.json` (`smoke`, `daily`, `release`, `full`).
- **`.github/workflows/e2e-catalog.yml`**:
  - On PRs: unit tests on 3 OSes, manifest reproduction from the pins, and `e2e validate
    --baseline`.
  - Daily: a drift report against current mains. It never fails and opens nothing.

### smoke — the chat seat declares `seat_eligible_for_work` (crew 0.15.2)

The crew 0.15.2 release smoke (run 39233376132) failed S04 on ubuntu and macOS. crew#916 made crew
read a seat's two roles separately: `enabled_for_council` (may vote) and `seat_eligible_for_work` (may
be seated for work, default true). The overlay wrote the chat seat `chat-smoke` with
`enabled_for_council = false` and no work flag, so on 0.15.2 it became work-eligible. The engine
then re-seated reproduce / verify / review / security_review onto it as the distinct evaluator. Its
shim prints no `VERDICT:` line, so verify rejected and the run was cancelled.

- The chat seat (`chat-smoke` on C5, `acp-smoke` before) is written `seat_eligible_for_work = false`
  beside `enabled_for_council = false`, so through S01–S07 it neither votes nor takes a unit.
- S08's re-write sets both flags `true`: a chat's `answer-N` step is a unit, and a council-enabled
  seat with work off is reviewer-only.
- No other record changes. Engines before the split ignore the key (optional, default true).

### smoke — S05 no longer truncates the live bus WAL (wicked-crew#1050)

The crew 0.13.0 and 0.13.1 release smokes (runs 38856860493 and 38886447659) failed S10 on ubuntu:
`bus.db` failed `PRAGMA integrity_check` (`btreeInitPage() returns error code 11`). The cause was the
harness. After a clean S05 loop, the WB-014 "visibility" probe ran `truncateSync('bus.db-wal', 0)`
under the live daemon, which destroys every frame not yet checkpointed. A connection that still has
those pages cached can keep appending past the zero-filled hole. Its last close can then checkpoint
the zeros into `bus.db`, because a checkpoint reads frames through the WAL index and does not
re-verify checksums. The results by leg:

- On ubuntu, crew 0.11.0 through 0.12.4 logged `SQLITE_IOERR_SHORT_READ` (522) after the truncation,
  and S10 passed.
- On ubuntu, crew 0.13.0 and 0.13.1 logged nothing, and S10 failed.
- The macOS legs logged 522 and passed.
- Every leg recorded `daemonErrorLines: []`, so the probe never exercised visibility.
- With the probe removed, crew 0.13.1 passes S10 on ubuntu (this PR's smoke-selftest).

The changes:

- **S05 injects no WAL fault.** The after-loop `recentErrors` checks and the F-E2E-021 loop are
  unchanged. The injection-specific visibility check is gone.
- **The selfcheck runs in the reusable smoke workflow before the smoke**, and it carries a guard.
  The guard fails on a direct fs mutation call (truncate, unlink, rm, write, append, rename, copy,
  `createWriteStream`) whose arguments name a `-wal`/`-shm` path, in any smoke module, with comments
  stripped. It is a textual heuristic: an alias or a precomputed path variable gets past it.
- **The selfcheck also demonstrates the failure** where `node:sqlite` is available. It truncates a
  live WAL under a writer with warm pages, then requires either a refused write or a corrupt
  `integrity_check`, never a silent `ok`. A control run with no truncation must read `ok`.

### smoke — C5 crews (>= 0.13.0): the host seat floor and a headless chat seat (crew 0.13.0 release smoke)

crew 0.13.0 (wicked-crew#1018, core-ts 0.12.0 / wicked-core#950) runs governed seats in containers by
default, removes ACP from the seats, and refuses a governed run on a host with no container runtime.
The release smoke (crew run 38856860493) read that as S04 and S08 failures on macOS (no container
runtime: every unit refused `no_container_runtime`) and on ubuntu (Docker present: seats refused
`agent_signed_out` / "container seats require an isolated config home"). The old wire is kept for
older crews; the previous-set leg (crew 0.7.32) is unchanged.

- **Every daemon start on a C5 crew sets `WICKED_SEAT_FLOOR=host`** (`lib/env.mjs` `seatFloorEnv`,
  `Daemon` `baseEnv`): the labelled interim host floor the operator's own daemon runs, where each
  unit runs its CLI's headless mode on the wrapped carrier. Older crews get no floor variable.
- **S08 on a C5 crew speaks to a headless chat seat, `chat-smoke`** (`shims/chat-agent.mjs`). On the
  host floor the engine runs a governed unit only on a launch that keeps a per-call check (a binary
  whose file stem is `claude`, or a bounded codex; wicked-core `host_floor_keeps_a_check`), so the
  seat's launcher is `<root>/bin/chat-seat/claude`: the claude carrier arms the gate hook through the
  `wicked-core` shim and reads the shim's stream-json output (deltas and `usage`). The ACP
  assertions (handshake, `session/prompt`, `acpSessionStarted`) run only for crews < 0.13.0; on C5
  the step asserts the shim's headless worker turn (`-p` + the gate hook's `--settings`, stream-json),
  and the run's `unitDistributed` to the seat, `governanceContextArmed`, `unitOutputDelta` and
  `unitOutputCaptured{governed: true, stepStatus: ok}`. The overlay writes `chat-smoke` instead of
  `acp-smoke` on a C5 crew, council-disabled until S08 like before.
- **S04 on the C5 host floor (crew >= 0.13.1, core-ts >= 0.12.1).** core-ts 0.12.1 (wicked-core#976)
  benches every seat the host floor refuses for governed work UP FRONT (`governed_only`, reason
  `needs_container_floor`, source `launcher`); those seats still judge, triage and vote. In the
  smoke's roster that left claude as the only governed seat (codex is benched for worktree-bound
  runs), so the bug run's review units had no evaluator distinct from the creator and the engine
  refused the plan at the scope step, by design and named on the wire (NoEligibleSeat,
  wicked-core#747; crew 0.13.1 run 38861691576: all three S04 launches `failed` after `pa-scope`).
  Harness lag, fixed: on a C5 crew `smoke-judge` launches through `<root>/bin/judge-seat/claude`, so
  it is the second governed seat (the distinct evaluator) and opencode is the distinct judge. The
  pre-C5 copilot contract (one unit turn, benched on its own quota refusal, `seatBenched`, carried
  to the roster: F-SMOKE-004/005) cannot happen there; it is replaced by: copilot and opencode named
  in `degradedReason` with the host-floor reason, every governed unit seated on claude or
  `smoke-judge`, no worker turn on copilot / opencode, codex never spawned. F-SMOKE-005 is judged
  only when a judge-turn quota refusal benched copilot in the run. The no-judge launch drops opencode
  (the judge) instead of `smoke-judge` (now the evaluator). crew 0.13.0 (core-ts 0.12.0, no up-front
  bench) keeps the old assertions.

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
- **S04 (ballot era, core-ts < 0.7.25): a pipeline run whose only escalations were dead-seat units
  reassigned to a live seat carries the F-7R3-001 tag.** With the third live seat the 0.7.23 mixed
  run completes through those reassignments and is itself the pipeline run (it used to fall back to
  the live-seat rerun), so "pipeline run: no failure escalation" now reads EXPECTED-FAIL there.
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
