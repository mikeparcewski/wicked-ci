# e2e: the wicked platform certification suite

The platform's end-to-end certification suite: what has to be certified (the catalog), how each
item is checked (typed oracles), a validator that proves the list is complete (phase 1), and a
runner that executes the existing tests behind each capability, records evidence, seals it in
wicked-vault and writes a report (phase 2). The skills that drive it are phase 3.

The rule it encodes: **certify the user's exact path to its terminal state.** A launch is not done.
Creating something through the API is not creating it in the UI. A stub is not the real thing. A
capability's `user_path` is the path a user takes, and its oracle checks the state at the end of
it.

Next to it, `smoke/` (S01 to S10) stays what it is: a 5 to 8 minute artifact-level smoke of the
seams. The catalog points at smoke steps as scenarios where a step already exercises a capability,
and the runner drives those steps through the harness unchanged.

## Layout

| Path | What it is |
|---|---|
| `catalog/<area>.json` | The capabilities of one area, one record each (9 areas, 1410 capabilities). |
| `catalog/SCHEMA.json` | The JSON Schema (draft 2020-12) every area file must satisfy. |
| `surfaces/<repo>.json` | Each repo's user-facing surface elements and its test-file index, read from source at a pinned SHA. |
| `surfaces/pins.json` | The pinned SHA per repo, and the published `wicked-crew` version whose CLI is read. |
| `coverage-baseline.json` | The known unmapped surface elements (the coverage ratchet). |
| `profiles.json` | Saved selections: `smoke`, `daily`, `release` and `full`. |
| `bin/e2e` | The tool (Python 3, stdlib only). On Windows run `python e2e/bin/e2e ...`. |
| `lib/e2ecat/` | Its modules: schema subset validator, selection language, surface extractors, checks. |
| `lib/e2ecat/run.py` | `e2e run`: selection, plan, execution, judging, sealing (phase 2). |
| `lib/e2ecat/{deps,observe,verdict,evidence,report}.py` | Dependency checks, typed-check evaluation, THE verdict rule, evidence hashing and the vault seal, reports. |
| `lib/e2ecat/adapters/` | One adapter per kind of existing test: smoke steps, studio journeys, crew vitest, core cargo, direct reads. |
| `lib/e2ecat/pwhook/` | The Playwright evidence hook a studio journey runs under (video, trace, HAR, screenshots, DOM samples). |
| `lib/e2ecat/taps/` | The vitest setup file that records a crew test's HTTP exchanges. |
| `samples/` | A generated report from a real run (the report files only, no videos). |
| `tests/` | `python3 -m unittest discover -s e2e/tests -v` |

## A capability

```json
{
 "id": "crew-api.runs.launch.workflow",
 "title": "Launch a governed run on a named workflow against a registered repo",
 "surface": "api",
 "user_path": "POST /api/v1/runs {problem, workflow:'bug', repoRef}. ... Then let the run reach its terminal state.",
 "deps": ["daemon", "real-engine", "signed-in-seats", "registered-repo"],
 "cost": "L",
 "tags": ["crew-api", "runs", "launch", "smoke"],
 "required_evidence": ["api-transcript", "event-log"],
 "oracle": {"kind": "all", "of": [ ...typed checks... ], "complete": false, "untyped": ["..."]},
 "oracle_text": "the inventory's original wording",
 "covers": ["crew:route:POST /api/v1/runs", "crew:route:GET /api/v1/runs/:id"],
 "scenarios": [{"ref": "wicked-ci:smoke/lib/steps/S04-bug-run.mjs", "fidelity": "e2e-hermetic"}],
 "aliases": [], "related": [], "sources": ["wicked-crew:packages/crew/src/api/routes.ts:2416"],
 "notes": [], "origin": "inventory-2026-10-20"
}
```

- **`surface`**: `ui`, `api`, `cli`, `mcp`, `plugin` or `background`.
- **`cost`**: `S` is a fixture or hermetic check that takes seconds. `M` is one live seat turn. `L`
  is a governed run (councils), so run `L` items one at a time.
- **`tags`**: feature groups. They include the area, the id's second segment, and keyword groups
  such as `run-page`, `sign-in`, `plugins`, `editors`, `gates`, `launch`, `deliver`, `qe` and
  `governance`. `smoke` marks a capability a wicked-ci smoke step already exercises.
- **`covers`**: the surface keys (below) the capability's user path goes through.
- **`scenarios`**: existing tests that exercise it, each `{ref: "<repo>:<path>", name?, fidelity}`.
  Use `["planned"]` when no test exists yet. This phase writes no scenarios. It only maps to
  existing tests.
- **`aliases`**: ids merged into this one as true duplicates. A selection by an alias still finds
  the capability.
- **`related`**: the same feature on a different user path, for example its API form next to its
  UI form. Those are different user paths, so both stay.

### Scenario fidelity

| fidelity | means |
|---|---|
| `e2e-live` | The real product: a real daemon, a built site or a real seat. |
| `e2e-hermetic` | Published artifacts with shimmed seats in a temp root (wicked-ci smoke). |
| `e2e-fixture` | The UI against a stub backend (studio's `uxfix` journeys). This is evidence, not certification. |
| `integration` | In-process routes or engine (crew `tests/`, core `tests/*.rs`, bus/vault CLI tests). |
| `unit` | One module. |

## Typed oracles

A capability's `oracle` is one typed check, an `all` of typed checks, or `manual`.

| kind | fields | holds when |
|---|---|---|
| `dom` | `selector`, `assert` (`visible`, `hidden`, `text-equals`, `text-matches`, `count`, `attr`), `value`, `attr`, `route` | the rendered page matches (Playwright locator semantics) |
| `api` | `method` (`GET` to `DELETE`, or `JSONRPC` for an MCP tool), `path`, `body`, `expect` (`status`, `json[]`, `error_code`), `capture` | the answer matches. `capture` binds `{name}` placeholders for later checks |
| `event` | `type`, `source` (`core-event`, `bus`, `ws`, `interactive`, `hook-log`, `transcript`, `network`), `where`, `count`, `within_s` | the event was observed on the path. `within_s` is a wait budget, not a performance assertion |
| `file` | `path`, `assert` (`exists`, `absent`, `sha256`, `json-path`, `matches`, `non-empty`), `json_path`, `value` | the file the path leaves behind matches |
| `exit` | `cmd`, `code` (an integer or `nonzero`), `stdout_matches`, `stderr_matches` | the command exits as stated |
| `npm` | `pkg`, `version`, `dist_tag` | the published version is the one stated |
| `gh` | `target` (`pr`, `run`, `release`), `repo`, `assert` | the GitHub object's state matches (read-only) |

- **`expect.json`** and `gh.assert` use one comparison shape: `{path, op, value}`. `op` is one of
  `eq`, `ne`, `exists`, `absent`, `in`, `matches`, `gt`, `gte`, `lt`, `lte`, `length` or
  `contains`. Paths use a JSONPath subset: `$.a.b`, `$.a[0]` and the filter `$.a[?(@.k=='v')].f`.
- **What the UI sent** is observed, not repeated. On a UI capability, a non-GET request is an
  `event` with `source: network` and `type: "POST /api/v1/runs"`, read from the browser's network
  transcript. `where` matches request-body fields (`body.workflow`), and `count: 0` asserts the
  request was never sent. An `api` check is a request the runner itself makes. On a UI path that
  is only ever a GET that reads the terminal state.
- **Requests are real routes.** Every request a check makes or observes on crew (`/api/v1`) or
  the bridge (`/api`, `/d/:doc`) must be a route in the pinned manifests, with a well-formed
  query. A bridge path written without its document mount resolves to `/d/{doc}` when only that
  form exists. On a document-engine capability, every relative path must be a bridge route.
- **Bodies and queries**: every non-GET check carries a body, either its own or
  `"{request_body}"` (the user path's own request body, bound by the scenario's setup). A query
  has no empty parameter. On a refusal path, a request whose clause states no refusal status
  gets no defaulted success status.
- **Placeholders** in `{braces}` come from a `capture` or from the runner's own bindings
  (`{port}`, `{runId}`, `{projectId}`, `{repoId}`, `{tag}`, and seeded values a scenario's setup
  names, such as `{stale_ord}`). A path's `:id` is named after its resource (`/runs/{runId}`).
- **`complete`** is computed recursively, by one function that catalog validation, the summary
  and the run-report guard all use. An oracle is complete only if it declares `complete: true`,
  lists no `untyped` clause, and every child of a composite (`all`, at any depth) is typed, with
  no `complete: false` and no `untyped` of its own. `validate` refuses a composite that declares
  `complete: true` over an incomplete, untyped or manual child.
- **What `complete` declares**: `true` means every clause of `oracle_text` is a typed check. `false` means the
  checks are necessary but not sufficient, and `untyped` lists the clauses that still need typing.
  A runner may report a partial oracle as `partial`, never as `pass`.
- **`manual`**: `{category, reason, precheck?}`. It is counted separately and is never a pass.
  - Most categories mean the oracle cannot be made deterministic as stated: `model-output` (the
    end state is model-written text), `human-gui` (a real provider login or a third-party GUI),
    `host-dependent`, `dead-path` (the engine no longer emits what the oracle reads),
    `stub-only` and `doc-drift`.
  - `untyped` is different. The oracle is deterministic in principle, but the inventory states it
    as prose (library calls, SQL, multi-step sequences) that could not be reduced yet. That is
    refinement debt.
  - `precheck` is a deterministic necessary condition the runner may still check.

## The evidence contract

- **`required_evidence`** lists what a run must keep for each capability. The values are `video`,
  `screenshot`, `trace`, `api-transcript`, `event-log`, `file-hash`, `ledger-entry`,
  `vault-entry` and `cli-transcript`.
- A **UI** capability always requires `video`, `screenshot` and `trace`.
- `cli-transcript` (stdout, stderr and the exit code) extends the original list of eight. Without
  it, the 337 CLI capabilities would have no evidence type of their own.

A run directory is what `e2e run` writes and what `e2e validate --report <run-dir>` checks:

```
<run-dir>/run.json                    {"version": 2, "run_id", "target", "profile"|"selection", "capabilities": [ids],
                                       "catalog_sha256", "plan", "vault": {"scope", "index"}, ...}
<run-dir>/<cap-id>/result.json        {"id", "verdict", "reason", "observed": [{"check", "value", "ok", "how"}],
                                       "evidence": {"<kind>": ["run-relative path", ...]},
                                       "scenario": {"ref", "name", "fidelity", "adapter", "status"}, "skip"?, ...}
<run-dir>/<cap-id>/evidence-manifest.json   {"id", "result_sha256", "files": {"<path>": "<sha256>"}}
<run-dir>/scenarios/<unit>/...        what each scenario run left (videos, traces, transcripts, logs)
<run-dir>/.wicked-vault/              the run's own vault; vault-index.json maps each capability to its entry
<run-dir>/report.{md,html,json}
```

The report fails when any of these holds:

- A selected capability has no `result.json`, or `run.json`'s capability list differs from what its
  selection resolves to (on the same catalog): a run cannot drop a capability and still validate.
- The verdict is missing, or is not one of `pass`, `fail`, `partial`, `manual`, `error` or
  `skipped`.
- A `skipped` capability does not name its unmet dependency in `skip.dep` (one of its own `deps`,
  or a runner requirement: `checkout:`, `adapter:`, `target:`, `evidence:`, `scenario:`). An
  `error` gives no reason.
- A `manual` oracle is reported as `pass`, or a partial oracle (`complete: false`, recursively) is
  reported as `pass`.
- A `pass` with any check whose `ok` is not `true`, a scenario that did not pass, a fidelity other
  than `e2e-live`/`e2e-hermetic`, a scenario that is not one of the capability's own, or only the
  runner's direct reads on a capability whose path is not itself a read (see the verdict rule).
- A contradicted check (`ok: false`) reported as anything but `fail`.
- `observed` does not hold one entry, with `value` and `ok`, for each typed check.
- A required evidence kind is missing, or one of its files is missing, empty or outside the run
  directory (`skipped` and `error` results carry none).
- The video is not a `.webm`, the screenshot is not a `.png`, or the trace is not a `.zip`.
- **Integrity**: a capability or the run has no vault entry; the vault payload does not hash to its
  entry; `result.json`, `run.json` or any evidence file differs from the hashes frozen in the vault;
  or `wicked-vault verify` (when the CLI is on PATH) does not pass. `--allow-unvaulted` skips the
  integrity check for a hand-written report; `--no-vault-cli` re-derives the hashes offline only.

A complete report exits 0, even when some verdicts are `fail`. The validator checks that the
evidence is complete and intact, and that no verdict claims more than the verdict rule allows. It
does not judge the product.

## Surface manifests

`e2e surfaces` reads each repo's checkout. It never runs a product binary. Each surface key is
`<prefix>:<kind>:<name>`.

| repo | prefix | kinds, and where they are read |
|---|---|---|
| wicked-studio | `studio` | `testid`, `testid-pattern`, `testid-computed` (from `testid-inventory.json`); `route` and `retired-route` (from `src/hooks/useRoute.ts`) |
| wicked-crew | `crew` | `route` (from `packages/crew/endpoint-manifest.json`); `ws`; `mcp` (the `wicked-crew mcp` tools and `ask`); `cli`, from the **published** tarball's compiled CLI (`npm pack wicked-crew@<pin>`, parsed, not executed) |
| wicked-estate | `estate` | `mcp` (from `all_tools()` and the memory, knowledge and proposal dispatch), `mcp-resource`, `cli` (from `cli_flags::COMMANDS` and the tool-bridge rows) |
| wicked-garden | `garden` | `skill`, `fork-skill` and `hook` (from `.claude-plugin/components.json` and `hooks/hooks.json`), `cli` (the `install.mjs` verbs), `pack` |
| wicked-core | `core` | `cli` (from `SUBCOMMAND_USAGE` and the dispatch arms of `src/bin/wicked-core.rs`) |
| wicked-interactive | `interactive` | `route`: the bridge root's `top.<verb>()` registrations, and each document service's `app.<verb>()` registrations under their `/d/:doc` mount; `cli` |
| wicked-bus, wicked-vault | `bus`, `vault` | `cli` (verbs and sub-verbs, and the `*-install` bins) |
| wicked-ledger | `ledger` | `export` (the public exports of `lib/index.mjs`; it has no CLI) |
| wicked-installer | `installer` | `cli`, `agent` (one per `src/install-<cli>.ts`), `product`, `bundle` |

- **Test index**: each manifest also lists the repo's test files. These are tracked, executable
  files (code, shell scripts, CI workflows) outside any `fixtures/` directory that sit under a
  test, e2e, spec, smoke or evidence directory or carry a test-style name, plus Rust files that
  contain `#[test]`. Markdown scenario write-ups and fixture data are not tests. `validate` checks
  every scenario reference against that list, offline.
- **Studio routes** are read block by block from `parse()`, including nested `second`/`third`
  branches and sub-page predicates resolved to their source lists. Extraction fails loudly if a
  known nested route (`/runs/new`, `/runs/:id/events`, `/testing/campaigns/:id`, `/rules/:id`)
  disappears.
- **Refreshing**: `e2e surfaces --clone main --write-pins` re-pins every repo to its current
  main. `e2e surfaces --clone pinned` reproduces the committed manifests byte for byte. CI checks
  that on every PR.

## The validator

`e2e validate` exits non-zero on any failure:

- **(a) Catalog.** Every area file is schema-valid, ids and aliases are unique, and `related`
  points at real ids. A UI capability requires video, screenshot and trace. Every `covers` key is
  a real surface element. Every scenario names a test file that exists at the pin. wicked-ci
  references are checked against this checkout, by the same executable-test rule.
  - Oracle semantics, including inside a manual `precheck`, cover what the schema subset cannot
    say: every comparison other than `exists`/`absent` carries a `value`; an `api` check expects
    something; an event `count` is not vacuous; `attr` names its attribute.
  - Every typed oracle states `complete`. A partial one lists `untyped`, and a complete one lists
    none. A UI oracle with no `dom` check cannot be complete.
- **(b) Surface coverage.** Every surface element is covered by at least one capability. Unmapped
  elements fail and are listed by repo.
  - With `--baseline coverage-baseline.json`, the known gaps are tolerated. Any new unmapped
    element fails, and so does any listed element that is now covered or gone. The list only
    shrinks.
  - `e2e baseline --write` regenerates the baseline, to drop entries.
- **(c) Scenarios.** Every capability has a scenario reference, or `planned`. `planned` is
  reported as uncovered. It is not a failure.
- **(d) Run report.** `--report <run-dir>`, as described in the evidence contract.
- **Profiles.** Every profile parses and selects at least one capability.

`--out DIR` writes `coverage.md` and `coverage.json`. They hold the per-area totals (with
scenario, planned, manual, untyped, typed complete or partial, best scenario fidelity) and the
per-repo unmapped counts by kind.

`e2e drift --against DIR` compares the pinned manifests with freshly extracted ones. It reports
added, removed and added-but-unmapped elements per repo, and never fails.

## Selection language and profiles

```
EXPR := TERM (WS TERM)*
TERM := [!] ( area:NAME | tag:NAME | id:GLOB | surface=NAME | cost<=S|M|L | oracle=KIND )
```

- Each NAME or GLOB may list alternatives separated by commas, for example
  `area:crew-api,foundation`.
- Terms with the same key are OR'd. Terms with different keys are AND'd. A `!` term excludes what
  it matches.
- `id:` uses fnmatch globs and also matches aliases.
- An empty expression, or `*`, selects everything.

```
e2e select 'area:studio-ui tag:run-page cost<=S'
e2e select --profile release
```

| profile | selection | count (2026-10-20 pins) |
|---|---|---:|
| `smoke` | `tag:smoke cost<=M !oracle=manual` | 33 |
| `daily` | `cost<=M !oracle=manual` | 834 |
| `release` | `cost<=L tag:launch,gates,deliver,qe,sign-in,install,plugins,smoke !oracle=manual` | 351 |
| `full` | everything (manual capabilities report `manual`) | 1410 |

## How the catalog was built

The catalog was normalised once from the 2026-10-20 inventory (1533 capabilities) and its
completeness critic. The normaliser stays out of the repo, because its inputs live outside it.
From now on the catalog files are the source.

- **Ids**: the inventory ids are kept.
- **Paths**: `sources` and scenario references are repo-qualified relative paths
  (`<repo>:<path>`). There are no machine paths.
- **Critic, missing capabilities**: 49 capabilities were added (`origin:
  "critic-2026-10-20"`). They include:
  - the acceptance conformance section;
  - the run-panel decisions ledger, diff viewer, deliver-lift, assumptions, data used, steering
    timeline and verdict diff;
  - the recon fan-out and author-tests launch panel;
  - the run mode and lead-agent pickers;
  - REST MCP servers;
  - the engine-authorised gate choices;
  - operator memory scope and rule reach;
  - memory expiry;
  - the DEFERRED verdict;
  - the product sites;
  - the wicked-ci reusable workflows;
  - five bus capabilities;
  - the estate cargo install;
  - three crew operator knobs;
  - the installed-browser recorder;
  - two studio details;
  - two engine guarantees.
- **Critic, duplicates**: 172 ids were merged into their survivor and recorded as `aliases`.
  - A cluster is merged only within one surface. The same feature on a different user path (API
    and UI) is kept, and the two are linked as `related`.
  - Glob-wide, parenthesised and `⊂`/`~` relations become `related`, not merges.
  - One critic pair, host and container sign-out, is two alternative branches (one run takes
    one), so it stays two capabilities linked as `related`.
- **Critic, proxy paths**:
  - Every studio capability is certified against a real crew daemon (a hermetic state home with
    shimmed seats) that serves its bundled studio. The uxfix fixture journeys remain as
    `e2e-fixture` scenarios.
  - Launch-only and stub-terminal capabilities now end at the run's terminal state
    (`run.session.status == completed` from `GET /api/v1/runs/{runId}`, plus one `sessionCompleted`).
  - UI-tagged engine capabilities whose path was the API start from their studio address.
  - Permissive disjunctions lost their failure branch.
  - Tautological oracles got seeded expected values.
  - CI-conclusion proxies became local re-derivations.
- **Critic, non-deterministic oracles**: these are `manual` with a reason, among them
  model-output content, real provider logins, third-party GUIs, host-dependent council
  detection, the ACP dead paths and the stub self-test. Machine-dependent timing thresholds were
  dropped from oracles and kept in `notes`.
- **Typed oracles**: they were extracted clause by clause from the inventory wording (testids,
  requests and statuses, JSON equalities, CoreEvent and bus event names, exit codes, files, npm
  versions).
  - When a clause names nothing typeable, the capability's own request, command, tool or terminal
    control is its necessary check, and the clause is listed in `untyped`.
  - A clause counts as typed only when it has one of the simple shapes a check captures whole: a
    bare status, `exit 0`, a testid that must be visible, or a request and its status. Every other
    clause (comparisons, counts, negations, request-body fields, prose) stays in `untyped`, even
    when it also produced a check. A negated, conditional (`when`, `if`, `or`) or arrowed
    (`X -> outcome`) clause yields no event check. A negated UI request becomes a `count: 0`
    network event.
  - **Exits**:
    - A clause's exit code binds to a command named in that clause, before the exit, outside any
      quoted message and not in a negated clause.
    - The path's own command comes from the user path only. Commands in the oracle text are
      checks or forbidden spawns.
    - The path's command binds only to an unconditional `exit 0`, and never on a rejection path
      (decided by the title).
    - Search commands (`grep`, `git grep`, `rg`) never bind, because their exit encodes a match.
    - Usage synopses become one invocation: `<name>` becomes `{name}`, and `[optional]` and
      `(a | b)` parts are dropped.
  - **Fallback**: when no clause yields a check, the capability's own request, tool, command or
    terminal control is the necessary check.
    - On a rejection path, a command expects the single non-zero code its unconditional clauses
      state. That holds only when the text names no exit 0 and the path has no other variants.
    - On any other path, it expects 0, unless the text or the path names non-zero exits for other
      conditions (code lists included). Then the capability stays untyped.
  - **UI capabilities** always carry the studio controls their user path names as `dom` checks,
    and the request the path sends as a `network` event. When the path names several requests,
    they are alternative branches, and none is required.
  - A bare status (`404`) binds to the path's request only when the clause starts with it, the
    clause is unconditional (no `for`, `when`, `if`, `once`, error condition or arrow), and the
    path names exactly one request. A clause naming several statuses or requests binds none.
  - A status binds only to a request it follows in its clause. An error status (4xx/5xx) is
    never extracted, because it needs its specific bad input, which prose does not give. Only
    hand-written checks that carry their body expect one. Empty query parameters (`?step=`) are
    dropped.
  - A choice list in a synopsis (`<agy|opencode|pi>`) becomes its first choice. A literal port of
    the operator's live daemons (7701, 7721) becomes `{port}`.
  - A success check on a verb the binary's surface manifest does not list is dropped (the prose
    named a script, not the CLI). `validate` refuses one too; a refusal check, with a non-zero
    exit, may run an unknown verb on purpose.
  - Shorthand never reaches a check. `[?q]` is dropped from paths. A path or request with `a|b`,
    `<x>` or `…` is left untyped. A glob selector `[a=b-*]` becomes `[a^="b-"]`, and a
    placeholder value is quoted (`[data-agent="{key}"]`).
  - `validate` refuses any shorthand left in a path, a network request, a selector or a command
    (`[optional]`, `a|b`, `<name>`, `…`; a shell pipe with spaces is fine), and any unquoted
    attribute value that is not a CSS identifier. An uppercase metavariable after a flag
    (`--db F`, `--manifest OUT.json`) becomes a placeholder named after the flag (`{db}`).
  - Response paths follow the wire. `GET /api/v1/runs/{runId}` answers `{run: {session, units}}`.
    A roster comparison must address `$.roster`. Other response paths come from the inventory's
    wording and are not yet checked against the response types; phase 2 binds them.
  - Hand-written oracles that omit a clause of their user path list it in `untyped` too.
  - 19 oracles are complete, 942 partial, 339 untyped and 110 manual.
- **`covers`**: it was seeded two ways.
  - Explicit mention: a testid, route, command, tool, skill or hook named in the capability's
    text.
  - Source-file association: a UI capability that cites a studio component covers the testids
    that component declares.
  - At the 2026-10-20 pins, 2506 of 2749 studio elements are mapped. About 835 of them are named
    explicitly. The rest are mapped only by file association, which is a claim about which
    component the path drives, not about what it asserts. Phase 2 tightens it from the traces.

## Running: `e2e run`

```bash
python3 e2e/bin/e2e run --profile smoke --target fixture --out runs/smoke-1 --src ~/checkouts \
    --python ~/pw/bin/python --playwright-browsers ~/pw/browsers --build-slot "build-slot --"
python3 e2e/bin/e2e run --select 'area:studio-ui tag:run-page cost<=S' --target fixture --out runs/ui-1 --src DIR
python3 e2e/bin/e2e run --select 'surface=api cost<=S' --target live --studio http://127.0.0.1:7801 --out runs/live-1
python3 e2e/bin/e2e run ... --plan-only            # write plan.json, run nothing
python3 e2e/bin/e2e validate --report runs/smoke-1
python3 e2e/bin/e2e report runs/smoke-1            # regenerate report.md / .html / .json
```

`e2e run` exits 0 when the run is complete and its own report validates, whatever the verdicts
(read them from `report.json`), and 1 when it does not.

`--src DIR` holds the `wicked-studio`, `wicked-crew` and `wicked-core` checkouts (or name each with
`--checkout REPO=PATH`); this checkout is wicked-ci. `--python` is a Python with Playwright for the
studio journeys, `--build-slot` a command prefix that serialises heavy builds (cargo, vitest).

### Targets

- **`fixture`** runs what is hermetic: the wicked-ci smoke steps (published artifacts, shimmed
  seats, a temp root), the studio's fixture journeys (the built UI against the in-process uxfix
  stub), crew's vitest files and core's cargo tests (in-process), and the npm/gh reads.
- **`live`** certifies one running daemon, `--studio URL`: the runner's own direct reads, and with
  `--live-journeys` the studio's `e2e-live` journeys with `STUDIO_URL`/`CREW_ORIGIN` pointed at it
  (opt-in, because a live journey drives the daemon for real; some launch governed runs). It
  refuses the operator daemon ports (7701, 7721) unless `--allow-daemon-port`. The runner itself
  never sends a non-GET: what the UI sent is observed in the browser's HAR, never repeated.

### From selection to plan

1. The selection (or profile) picks the capabilities.
2. Each capability's scenarios are ranked by fidelity for the target (fixture: `e2e-hermetic`,
   `e2e-fixture`, `integration`, `unit`; live: `e2e-live`). On a tie, a scenario already planned
   for an earlier capability wins, so one run proves several capabilities: one smoke harness run
   carries every Sxx step the plan needs, one `run_journeys.py` call every journey, one vitest
   invocation per file, one cargo invocation per test target.
3. The first candidate that (a) has an adapter on this target, (b) can run on this host
   (checkout, toolchain), (c) can capture every required evidence kind, and (d) has every dep met
   is chosen. Otherwise the capability is `skipped` and `skip.dep` names the best candidate's
   unmet requirement. A skip is never a pass.

**Deps** (`deps.py`) are prose in the catalog. One rule table reduces each to a requirement class:

| class | how it is decided |
|---|---|
| `daemon`, `real-engine`, `signed-in-seats`, `registered-repo`, `projects-engine` | provided by the smoke harness (real daemon, shimmed seats); replaced by doubles in an integration test or the uxfix stub (which caps them below pass); on the live target probed read-only (`/health`, `/diagnostics` `components.coreTs`, `/roster` signed-in seats, `/repos`, `/projects`) |
| `container`, `network`, `gh-auth`, tools (`node>=N`, `python>=3.N`, `cargo`, `git`, `ffmpeg`, ...), product binaries, platform | probed on the host (`docker info`, a DNS lookup, `gh auth status`, PATH, versions); "or stub" deps are met by the test's stub |
| `credential` (a provider account, an API key, the keychain) | never met: the runner reads no credential |
| a catalog id | a prerequisite the scenario's own setup performs (recorded) |
| anything else ("open chat", "snapshot") | scenario setup state, recorded as unchecked |

### Adapters

| adapter | runs | fidelity | evidence |
|---|---|---|---|
| `wicked-ci-smoke` | `smoke/lib/steps/Sxx-*.mjs` through `smoke/bin/wicked-smoke.mjs --steps ...`, unchanged; `WICKED_SMOKE_TAP_DIR` turns on `smoke/lib/tap.mjs` | e2e-hermetic | per step: the API transcript, the event log (/ws frames, events read back from `GET /runs/:id/events`, the hermetic `bus.db`), the CLI transcript, the harness's evidence dir (hashed) |
| `wicked-studio-journeys` | `e2e/<name>_test.py` through the studio's `e2e/run_journeys.py`, unchanged, with `pwhook/` on PYTHONPATH | e2e-fixture (fixture) / e2e-live (live) | per context: `.webm` video, Playwright `trace.zip`, HAR of every `/api/` exchange, every screenshot plus a final one per page, the fixture's own request log, DOM samples of the capability's `dom` checks |
| `wicked-crew-vitest` | `packages/crew/tests/*.test.ts` (one file, `-t name` when the scenario names one) under crew's own config plus `taps/vitest-tap.mjs` | integration | the vitest JSON report and log; the API transcript of every Fastify `inject()` and `/api/` `fetch` |
| `wicked-core-cargo` | `cargo test --test <t>` / `--lib` (per crate), filtered by test name, inside `--build-slot` | integration / unit | the test output |
| `direct` | the runner's own reads: GET on the live daemon, npm and gh reads, `<bin> --version`/`--help` on the live host, one read-only visit of the studio root | e2e-live | the API and CLI transcripts of the reads; the visit's video, trace and screenshot |

A lower-fidelity test cannot record an event log or a product CLI transcript natively. When it
did not, its test report stands in for `api-transcript`, `event-log` or `cli-transcript`, and the
result says so (`evidence_substitutes`). Such a result is never a `pass` (its fidelity caps it).
When a scenario could not capture a required kind at all, the capability is `error` ("required
evidence not captured"), never a verdict on the product.

### Observing the oracle

Each typed check is evaluated on what the proving scenario recorded (`observe.py`), and its
OBSERVED value is kept in `result.json`:

- `ok: true` the check held on a recorded exchange, event, invocation, file or DOM sample (or on a
  read-only direct read).
- `ok: false` a definitive contradiction: the runner's own read of the end state answers otherwise
  (a direct GET, npm or gh read, a direct `--version` run), a complete event stream (the browser's
  HAR) lacks the event or holds a forbidden one, or a file the scenario left behind holds another
  value.
- `ok: null` not observed: nothing matched (no such request, invocation or event, a partial
  stream, a DOM check never seen to hold at a sample point), or the matching exchanges were
  unsatisfied (`how: "transcript: unsatisfied"`). A scenario's request is not necessarily made in
  the state the oracle describes: a poll before the run settled, a step that seeds a warning on
  purpose. The report counts unsatisfied checks separately. Neither is ever a pass.
- A hold is marked `wildcard` when nothing ties what held to this path: a request matched through
  an unbound `{placeholder}` (some run completed, not necessarily this path's), an event in a
  stream window other runs share, a gh check on a repo's latest workflow run. It is recorded as
  held, and it never counts toward a pass.
- The runner's own direct read decides (`ok: false` on a mismatch) only when the capability's
  user path is itself that read. On any other path it read a daemon nobody drove down the path,
  so a mismatch is `direct: unsatisfied`.

### The verdict rule

`verdict.py` is the one rule the runner derives with and `validate --report` re-checks with:

| verdict | when |
|---|---|
| `error` | the scenario could not run, or could not capture required evidence |
| `fail` | the scenario failed, or a check was contradicted |
| `manual` | the oracle is manual |
| `pass` | every check observed to hold on something tied to this path (no `wildcard` hold), the oracle complete (recursively), fidelity `e2e-live` or `e2e-hermetic`, and a scenario drove the path. The runner's direct reads alone pass only a capability whose user path is itself nothing but such reads (`GET`, `npm view`, a gh read) and whose every check is one |
| `partial` | it ran and none of the above: the result lists what is missing |
| `skipped` | it did not run; `skip.dep` names why |

### Evidence integrity

After judging, the runner hashes every evidence file of each capability into
`<cap-id>/evidence-manifest.json` (with the hash of its `result.json`) and records the manifest in
the run's own wicked-vault (`wicked-vault record --artifact`, scope `e2e-<run-id>`, phase
`certify`, the claim is the capability id), the CLI garden's `prove` uses. `run.json` is recorded
the same way. The vault freezes a copy of each manifest, and `validate --report` re-derives every
hash against the frozen copy. So deleting a video, editing a transcript, or flipping a verdict after
the run is detected. As wicked-vault documents, unkeyed hashes catch mutation, not a determined
writer who rewrites the vault too. Set `E2E_VAULT` to use a vault CLI that is not on PATH
(`E2E_VAULT='npx -y wicked-vault'`).

### Reports

`report.json` (for CI and a future studio view), `report.md` and `report.html`: the result of
`e2e validate --report` on the run as the report was written (so a report never reads cleaner than
its run), the summary counts, a coverage matrix by area and verdict, and every capability (fail, error, partial, skipped,
manual, then pass) with its scenario, fidelity, checks held, the reason, and links to its video,
screenshots, trace, transcripts and `result.json`. Paths are run-relative and the home directory is
redacted. `e2e report <run-dir>` regenerates them. `samples/` holds the report of a real smoke run.

## Commands

```bash
python3 e2e/bin/e2e validate --baseline e2e/coverage-baseline.json --out e2e-out   # what CI runs
python3 e2e/bin/e2e validate                                                        # strict: every unmapped element fails
python3 e2e/bin/e2e run --profile smoke --target fixture --out RUN_DIR --src DIR      # run the selection
python3 e2e/bin/e2e validate --report <run-dir>                                     # run completeness + integrity
python3 e2e/bin/e2e report <run-dir>                                                # regenerate the reports
python3 e2e/bin/e2e select --profile daily
python3 e2e/bin/e2e surfaces --clone pinned --out /tmp/pinned-check                 # reproduce the manifests
python3 e2e/bin/e2e surfaces --clone main --crew-npm latest --write-pins            # re-pin to current mains
python3 e2e/bin/e2e drift --against /tmp/main-surfaces
python3 e2e/bin/e2e baseline --write
python3 -m unittest discover -s e2e/tests -v
```

## CI

`.github/workflows/e2e-catalog.yml` runs two kinds of job.

- **On PRs and pushes to main that touch `e2e/`, `smoke/` (smoke steps are scenarios) or a workflow**:
  - the unit tests on ubuntu, macOS and Windows;
  - a check that the manifests reproduce from their pinned SHAs;
  - `e2e validate --baseline`;
  - the coverage summary, written to the step summary and kept as an artifact.
- **Daily, or by hand**: it re-extracts the surfaces from every repo's current main and the
  latest published crew, then writes the drift report and a validate run against current mains.
  This job only reports. It never fails, and it opens nothing.

## Not in this phase

- The skills that drive the runner (phase 3).
- New scenarios: the runner maps to existing tests only. Capabilities with only `planned` (and
  those whose scenarios have no adapter yet: studio and garden unit tests, estate, interactive,
  bus, vault and installer suites) report `skipped`.
- Event-log capture for cargo tests (the engine's durable logs live in the tests' temp dirs).
