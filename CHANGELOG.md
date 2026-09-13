# Changelog

## Unreleased

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
  crew < 0.7.33 — fixed by crew #541/#542, S05 passes from 0.7.33; F-E2E-030 on core-ts < 0.7.24 —
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
