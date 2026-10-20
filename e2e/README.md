# e2e: the wicked platform certification catalog

This is phase 1 of the platform's end-to-end certification suite: what has to be certified, how
each item is checked, and a validator that proves the list is complete. The runner and the
evidence capture (phase 2) and the skills (phase 3) build on it. This phase runs nothing against a
product. It reads the source of each repo and the catalog.

The rule it encodes: **certify the user's exact path to its terminal state.** A launch is not done.
Creating something through the API is not creating it in the UI. A stub is not the real thing. A
capability's `user_path` is the path a user takes, and its oracle checks the state at the end of
it.

Next to it, `smoke/` (S01 to S10) stays what it is: a 5 to 8 minute artifact-level smoke of the
seams. The catalog points at smoke steps as scenarios where a step already exercises a capability.

## Layout

| Path | What it is |
|---|---|
| `catalog/<area>.json` | The capabilities of one area, one record each (9 areas, 1411 capabilities). |
| `catalog/SCHEMA.json` | The JSON Schema (draft 2020-12) every area file must satisfy. |
| `surfaces/<repo>.json` | Each repo's user-facing surface elements and its test-file index, read from source at a pinned SHA. |
| `surfaces/pins.json` | The pinned SHA per repo, and the published `wicked-crew` version whose CLI is read. |
| `coverage-baseline.json` | The known unmapped surface elements (the coverage ratchet). |
| `profiles.json` | Saved selections: `smoke`, `daily`, `release` and `full`. |
| `bin/e2e` | The tool (Python 3, stdlib only). On Windows run `python e2e/bin/e2e ...`. |
| `lib/e2ecat/` | Its modules: schema subset validator, selection language, surface extractors, checks. |
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
  form exists. A non-GET check carries `body: "{request_body}"`: the user path's own request
  body, which the scenario's setup binds.
- **Placeholders** in `{braces}` come from a `capture` or from the runner's own bindings
  (`{port}`, `{runId}`, `{projectId}`, `{repoId}`, `{tag}`, and seeded values a scenario's setup
  names, such as `{stale_ord}`). A path's `:id` is named after its resource (`/runs/{runId}`).
- **`complete`**: `true` means every clause of `oracle_text` is a typed check. `false` means the
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

A run directory (phase 2's output) is checked by `e2e validate --report <run-dir>`:

```
<run-dir>/run.json                 {"version": 1, "capabilities": [ids]}   (or "selection": EXPR, or "profile": NAME)
<run-dir>/results/<id>.json        {"id", "verdict", "observed": [{"value", "ok"}, ...], "evidence": {"<kind>": ["relative/path", ...]}}
```

The report fails when any of these holds:

- A selected capability has no results file.
- The verdict is missing, or is not one of `pass`, `fail`, `partial`, `manual`, `error` or
  `skipped`.
- A selected capability is `skipped`. Deselect it instead.
- A `manual` oracle is reported as `pass`, or a partial oracle (`complete: false`) is reported as
  `pass`.
- `observed` does not hold one entry, with `value` and `ok`, for each typed check.
- A required evidence kind is missing, or one of its files is missing, empty or outside the run
  directory.
- The video is not a `.webm`, the screenshot is not a `.png`, or the trace is not a `.zip`.

A complete report exits 0, even when some verdicts are `fail`. The validator checks that the
evidence is complete. It does not judge the results.

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
| `daily` | `cost<=M !oracle=manual` | 847 |
| `release` | `cost<=L tag:launch,gates,deliver,qe,sign-in,install,plugins,smoke !oracle=manual` | 356 |
| `full` | everything (manual capabilities report `manual`) | 1411 |

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
- **Critic, duplicates**: 171 ids were merged into their survivor and recorded as `aliases`.
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
    attribute value that is not a CSS identifier.
  - Response paths follow the wire. `GET /api/v1/runs/{runId}` answers `{run: {session, units}}`.
    A roster comparison must address `$.roster`. Other response paths come from the inventory's
    wording and are not yet checked against the response types; phase 2 binds them.
  - Hand-written oracles that omit a clause of their user path list it in `untyped` too.
  - 19 oracles are complete, 956 partial, 326 untyped and 110 manual.
- **`covers`**: it was seeded two ways.
  - Explicit mention: a testid, route, command, tool, skill or hook named in the capability's
    text.
  - Source-file association: a UI capability that cites a studio component covers the testids
    that component declares.
  - At the 2026-10-20 pins, 2506 of 2749 studio elements are mapped. About 835 of them are named
    explicitly. The rest are mapped only by file association, which is a claim about which
    component the path drives, not about what it asserts. Phase 2 tightens it from the traces.

## Commands

```bash
python3 e2e/bin/e2e validate --baseline e2e/coverage-baseline.json --out e2e-out   # what CI runs
python3 e2e/bin/e2e validate                                                        # strict: every unmapped element fails
python3 e2e/bin/e2e validate --report <run-dir>                                     # phase 2 run completeness
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

The runner, the evidence capture and the skills (phases 2 and 3). No scenario is written here.
Capabilities map to existing tests, or are `planned`.
