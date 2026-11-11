# U08 — build an MCP server in Studio, consent to install, list it and call it

Draft for PRODUCT-WORKS J6. No profile registration. Recon is limited to the read-only crew and studio checkouts;
the engine and garden implementations are not reproduced here. References below use paths relative to this
checkout (`../wicked-crew`, `../wicked-studio`) and line numbers from the sources inspected for this draft.

## Workflow and steps

The catalog command is `/workflow-mcp-server`, option `mcp-server`
(`../wicked-crew/packages/crew/src/workflow-catalog/catalog-data-v2.ts:530`). Studio exposes the catalog command as
`composer-menu-item[data-cmd="/workflow-mcp-server"]`; each menu item also carries `data-card` and `data-option`
(`../wicked-studio/src/components/session/SlashMenu.tsx:144`). The launch body names `workflow` and the person's
`problem` (`../wicked-studio/src/board/launchModel.ts:252`).

Crew derives its served workflow from engine presets and catalog entries; a preset launch is composed by the
engine, not run from crew's display definition (`../wicked-crew/packages/crew/src/core/builtin-catalog.ts:2`,
`../wicked-crew/packages/crew/src/core/builtin-catalog.ts:11`). Crew's live-adapter mirror test asserts these IDs,
kinds, roles and pins (`../wicked-crew/packages/crew/tests/mcp-server-workflow-mirror.test.ts:47`):

| Step ID | Kind / role | Gate and work |
| --- | --- | --- |
| `scope` | recon / neutral | Conditional human confirmation; choose tools, auth, transport and target directory. |
| `source-discovery` | recon / neutral | Auto; inventory the source/tool surface, no code writes. |
| `design` | recon / neutral | Conditional human confirmation; tool schemas/annotations, auth, observability and rule checklist. |
| `build` | build / creator | Auto, code-writing, evidence-floor pin; scaffold TypeScript and build/probe it. |
| `test` | test / evaluator | Verified evidence and evidence-floor pin; human confirmation if verdict is not PASS. |
| `security-review` | review / evaluator | Depends on test, evidence-floor pin, conditional human confirmation. |
| `observability-review` | review / evaluator | Depends on test, evidence-floor pin, human confirmation if verdict is not PASS. |
| `install-plan` | build / neutral, Tool | Auto; dry run, depends on both reviews (or delivery in a delivering run). |
| `install` | build / neutral, Tool | `consent_before`, depends on install-plan; not a seat code-writing phase. |

Gate/evidence assertions: `../wicked-crew/packages/crew/tests/mcp-server-workflow-mirror.test.ts:62`.
Instructions and the two review gates: `../wicked-crew/packages/crew/tests/support/builtin-fixtures.ts:218` through
`:226`. That fixture still calls `test` neutral, while the live-adapter test explicitly asserts evaluator; this
draft follows the latter (`../wicked-crew/packages/crew/tests/mcp-server-workflow-mirror.test.ts:54`).

A delivering composition orders `scope → source-discovery → design → build → test → security-review /
observability-review → deliver → install-plan → install`; the reviews both depend on test. Crew tests assert the
exact ordered array and dependencies (`../wicked-crew/packages/crew/tests/mcp-server-workflow-mirror.test.ts:112`).
The production composition helper anchors deliver before install-plan, preserving install's dependency on its
plan (`../wicked-crew/packages/crew/src/core/deliver.ts:1898`, `:1920`). There can also be plan and assurance cards:
crew forwards a preset into the engine's floor-filled, gated plan
(`../wicked-crew/packages/crew/src/core/adapter.ts:2188`). U08 reuses U04's steering helper for those cards and stops
at the consent gate; it never treats a failed repository floor as an ordinary missing-judge judgment.

## Checks and worktree artifact

The build instructions request `--lang typescript`, a committed `mcp-server.config.json`, conformance smoke and a
contract test per tool under `npm test`, plus `typecheck`, `lint`, `test`, SPDX headers and opt-in OTLP exports
(`../wicked-crew/packages/crew/tests/support/builtin-fixtures.ts:221`). The test instructions say the verify floor
runs repository typecheck/lint/test and ask the reviewer to check initialize, tools/list, tools/call, missing-secret
startup and httpStream 401 paths (`../wicked-crew/packages/crew/tests/support/builtin-fixtures.ts:222`). Crew's
repo-check reporting fixture records `npm run typecheck`, `npm run lint`, `npm run test` with exit codes
(`../wicked-crew/packages/crew/tests/deliver-text.test.ts:90`). **The exact engine floor command construction and
garden's conformance runner are not present in these references; these instructions/report fixtures do not prove
the full runtime acceptance algorithm.**

Crew's installed-server fixture provides `package.json` with `main: dist/server.js`, build/typecheck/lint/test/start
scripts, and shipped dist/tools/config files
(`../wicked-crew/packages/crew/tests/fixtures/mcp/unit-convert/package.json:12`). Its credential-free config has
`key`, `version`, `transport: stdio`, `auth.scheme: none`, `rateLimitPerMin`
(`../wicked-crew/packages/crew/tests/fixtures/mcp/unit-convert/mcp-server.config.json:1`); its hand-written tools
manifest is `{"tools":[]}` (`../wicked-crew/packages/crew/tests/fixtures/mcp/unit-convert/tools.json:1`). The installed
layout is `<root>/mcp-servers/<key>/current/{dist,package.json,package-lock.json,tools.json,mcp-server.config.json}`;
crew's test installs dependencies there and starts `node .../dist/server.js`
(`../wicked-crew/packages/crew/tests/mcp-installed-server.test.ts:109`). That existing fixture uses a network-tagged
dependency install; U08's substitute must avoid those dependencies
(`../wicked-crew/packages/crew/tests/mcp-installed-server.test.ts:53`, `:150`).

The U08 shim writes this proposed, dependency-free substitute **only in the creator's `build` turn**, under
`selftest-u08-mcp/` in the seat's current run worktree:

| File | Purpose in this draft |
| --- | --- |
| `src/server.ts` | TypeScript's JavaScript subset; newline-delimited JSON-RPC stdio server with one `echo({text})` tool. |
| `dist/server.js` | Runnable entry point, identical to the subset source; build script regenerates it. |
| `build.mjs` | Node syntax check and local copy, no compiler/dependency download. |
| `package.json`, `package-lock.json` | Key/name `selftest-u08-mcp`, module package, zero dependencies, scripts above, main `dist/server.js`. |
| `mcp-server.config.json`, `tools.json` | Credential-free stdio config and empty generated-tool manifest; echo is hand-written. |
| `test/contract.test.mjs` | Starts a bounded child over pipes, exercises initialize/list/call, validates echo output and invalid-input/unknown-method errors. |
| `test/run.mjs` | Bounded Node test runner; disables the compile cache like the existing corpus runner. |

This wire implementation follows crew's own dependency-free newline JSON-RPC fixture
(`../wicked-crew/packages/crew/tests/fixtures/mcp/inspect-server.mjs:1`, `:21`). Crew's real registry probe connects,
initializes and pages through tools/list using the SDK, then disconnects
(`../wicked-crew/packages/crew/src/mcp/probe.ts:1`, `:18`). Thus stdout contains protocol only; notifications have no
response; initialize echoes the proposed protocol version; tools/list includes the schema and four annotations;
tools/call validates its argument and returns MCP text content. Empty resources/prompts lists support the inspector's
initial list calls (`../wicked-studio/e2e/editor-fixtures/mcp-inspector.html:204`).

U08's proposed scope has no auth, upstream, HTTP or telemetry export. Its `typecheck` and `lint` scripts perform
syntax checks only; they are **not semantic TypeScript or ESLint checks**. The stub does not claim to implement the
workflow's production FastMCP/zod/telemetry stack, nor claim that its prose ran garden's probe. Compatibility with
the real conformance/install runner remains an explicit unverified assumption. A stricter floor must fail this
draft; the journey supplies no override for it.

The MCP turns use their own truthful stack-check record, and the shim's existing record judge accepts either whole
known record sentence, continuing to reject incomplete sentences. The build also repairs the known corpus `add()` defect and appends the server test to the root's existing test
command. Existing corpus assertions remain active. Root build/typecheck/lint scripts dispatch to the nested package,
preserving any existing commands. The intent explicitly requests this repair. Repeated build turns are byte-stable
and say `NO CHANGE NEEDED`; read-only turns never manufacture a build, install, registry entry or call.

## Install consent

`install-plan` runs `bash -c` with the admitted `${WICKED_GARDEN_ROOT}/scripts/wicked-garden run
scripts/mcp/install.py --from-run --dry-run --json`; `install` runs the same script with
`--from-run --target "$WICKED_CONSENT_CHOICE" --json`. Neither uses PATH discovery or npx
(`../wicked-crew/packages/crew/tests/mcp-server-workflow-mirror.test.ts:77`). The plan resolves write targets and
install runs on the daemon host as daemon user, stages under `~/.wicked/mcp-servers/<key>/current`, registers with
crew, writes worker CLI configs and probes tools/list
(`../wicked-crew/packages/crew/tests/support/builtin-fixtures.ts:225`, `:226`).

The engine pauses **before** install with `gateKind: consent` and `consent_before`; standing orders cannot approve
that gate (`../wicked-crew/packages/crew/tests/mcp-server-workflow-mirror.test.ts:70`, `:101`). Plan choices are
`consent:worker` (default), `consent:operator` and reject; the second also writes the person's CLI configs
(`../wicked-crew/packages/crew/tests/support/builtin-fixtures.ts:209`). Studio reads the matching awaitingHuman
frame's writeTargets/choiceLabels and maps `consent:worker` to `{approve:true, action:"consent:worker"}`
(`../wicked-studio/src/board/gateRowModel.ts:121`, `:156`). The card marks the default without preselecting it
(`../wicked-studio/src/components/session/GateRow.tsx:932`).

Card selectors: `session-gate-row`; `session-gate-choice[data-choice-key="consent:worker"]`;
`session-gate-send` / `session-gate-confirm`; `session-gate-more-about`; the nested
`session-gate-consent-writes[data-choice-key="consent:worker"]`; `session-gate-consent-write[data-own="false"]`.
Sources: `../wicked-studio/src/components/session/GateRow.tsx:929`, `:976`, `:998`. The UI submits
`POST /api/v1/runs/<rid>/gate` with that decision **after the undo window**
(`../wicked-studio/src/api/client.ts:306`). Crew admits the `consent:<id>` action with approve true
(`../wicked-crew/packages/crew/src/api/routes.ts:1014`, `:1106`).

U08 opens the file list and checks that worker targets exist and are all program-owned, checks that this server is
absent before consent, selects the worker choice, presses the card's control and waits for that exact successful
browser POST. It then requires completion and the installed registry path. The harness step may cancel a leftover
run in finally; cancellation is cleanup evidence only. It always removes scenario.json, including cleanup failures.

## Listing and the person's call

Studio routes `/mcp` to its MCP surface (`../wicked-studio/src/App.tsx:750`, `:775`); the API path helper uses `/mcp`
and optional `?server=` (`../wicked-studio/src/api/mcp.ts:38`). Rows have
`mcp-server-row[data-server="selftest-u08-mcp"]`, `mcp-server-toggle`, `mcp-server-health`, `mcp-server-auth` and
`mcp-server-tools` (`../wicked-studio/src/components/McpToolsPage.tsx:250`). Expanding shows
`mcp-tool-row[data-subject="mcp:selftest-u08-mcp/echo"]` and class/status/enable controls
(`../wicked-studio/src/components/McpToolsPage.tsx:190`, `:302`). U08 checks the actual row and its health, and uses a
GET to corroborate that its command args point into the installed `current/dist/server.js` copy.

Click `mcp-server-inspect` on that row to reach `/mcp/inspect?server=selftest-u08-mcp`
(`../wicked-studio/src/components/McpToolsPage.tsx:274`). The host's `mcp-inspect-server` select is preselected from
the route; Connect sends `{target:{server:"selftest-u08-mcp"}}` without command-entry consent
(`../wicked-studio/src/api/mcpInspect.ts:26`, `../wicked-studio/src/components/editors/McpInspectPage.tsx:398`).
`mcp-inspect-connect` starts the session, `mcp-inspect-state[data-state="ready"]` shows readiness, and
`mcp-inspect-calls` shows calls (`../wicked-studio/src/components/editors/McpInspectPage.tsx:576`, `:595`, `:616`).

**Prerequisite:** the call form is supplied by an enabled editor claiming `mcp-server`, not this host page. With no
editor, `mcp-inspect-no-plugin` asks the person to create one; without its `mcp.session` grant, Connect is disabled
(`../wicked-studio/src/components/editors/McpInspectPage.tsx:93`, `:178`, `:479`, `:581`). U08 assumes an already
consented inspector with Studio's existing e2e plugin controls: `plugin-card` / `editor-frame`, `[data-item="echo"]`,
`input[data-arg="text"]`, `plugin-call`, `plugin-result[data-error="0"]`
(`../wicked-studio/e2e/desk_mcp_inspect_test.py:85`, `:140`). These are fixture-plugin selectors, **not a guaranteed
contract of every production inspector**.

The person's click on echo's Call must return the unique supplied text in that plugin result and show
`tools/call echo` on the host call line. U08 observes the session-start receipt, then requires the exact same
session's successful UI `POST /api/v1/mcp-inspect/sessions/<sid>/rpc` with
`{method:"tools/call",params:{name:"echo",arguments:{text:...}}}`. Bridge start/rpc/delete paths and bodies:
`../wicked-studio/src/api/mcpInspect.ts:61`, `:66`, `:79`. The plugin renders the returned server result, not its input
preview (`../wicked-studio/e2e/editor-fixtures/mcp-inspector.html:293`). Finally the person clicks
`mcp-inspect-disconnect`, and U08 requires that session's DELETE; the host also deletes owned sessions on leaving
(`../wicked-studio/src/components/editors/McpInspectPage.tsx:309`, `:328`, `:607`). This proves human inspector
callability; it does not prove governed worker first-use policy approval or broker-token calls. Those are a separate
path, illustrated by `POST /mcp/call {token,subject,args}` in crew's J6 test
(`../wicked-crew/packages/crew/tests/mcp-installed-server.test.ts:168`).

## Hermetic limits, verification and open questions

No daemon, browser, install, network, commit or push was run while drafting. The later journey is intended to use
the existing isolated harness; it creates no registry entry by script and adds no inspector fixture or grants.
Missing inspector/editor/grant is a failed check, never a passing substitute call. There is no dependency download
in the generated server. Actual garden installation, consent rendering and the full journey remain unexecuted.

Local validation covers JS parsing, Python AST parsing, artifact generation in a temporary corpus, read-only phase
behavior, byte-identical build retry, the preserved corpus tests, the server's real stdio contract test, both known
stack-check sentences and rejection of an incomplete record. The
existing `selftest/lib/selfcheck.mjs:19` demands every step be registered; its full registry check is expected to
reject this intentionally unregistered draft until the reviewer wires U08 into args. Running it confirmed that
specific `step registry mismatch` failure at line 22. No args/profile file changed.

Open questions / assumptions not verified from the permitted source:

1. Does the selected runtime engine retain the step IDs/gates crew's live-adapter test asserts, and does the
   admitted garden installer discover this nested package and accept its lock/build/output layout? Exact garden
   conformance/floor implementation is outside these two references. In particular: does it permit a dependency-free
   TypeScript subset, syntax-only typecheck/lint, auth:none/stdio-only failure-path exclusions and no telemetry stack?
2. Which consented inspector editor will the hermetic root contain, and does it expose the existing e2e plugin's
   controls? The inspected harness does not provision one. Without that prerequisite, the terminal UI call cannot
   complete in this draft; installing an editor would be an additional product journey/setup decision.
3. Does the released harness bundle match the checked-out launch and consent wire, and keep all installer/worker
   homes under the run root? Source supports the intended POSTs, but this draft did not run the product or exercise
   its chosen artifact versions. U04's Settings/plan/missing-judge/rule-card behavior is reused without live proof.
4. Are a human inspector call and a retained installed copy the desired J6 terminal contract? This draft requires a
   fresh server key, leaves its install within the disposable root, cancels unfinished matching runs (list limit
   100, matching U06/U07), and does not test worker broker approval, operator-CLI install, credentials or a hosted
   server. Those omissions and the simplified stack require reviewer agreement before profile registration.
