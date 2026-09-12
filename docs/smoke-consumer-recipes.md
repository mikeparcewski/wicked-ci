# wicked-smoke — consumer recipes

The smoke (`.github/workflows/smoke.yml`, harness under `smoke/`) tests the **published** wicked-*
artifacts as a customer's `npm i -g` composes them — not any repo's source tree. It exists because the
acceptance program kept finding seams that were green in every repo's own CI and broke only in
composition: the seeded workflows launched against the real engine addon with the roster shape the
daemon actually hands it, shared SQLite state on a real filesystem, seat routing with a mixed-auth
roster, the default governance posture, the packaging of the tarball itself. Every wicked-* repo
should call it twice: **post-publish** (smoke what was just published, against the others' `latest`)
and **per-PR** (does my change still compose with what is published?).

Pin the ref per the README's pinning policy (a SHA with a `# v1.x.y` comment); `@v1` below is the
readable form.

## Inputs at a glance

| input | default | what it does |
|---|---|---|
| `crew_version` | `latest` | wicked-crew npm version to install (bundled studio rides inside) |
| `core_ts_version` | `pinned` | `pinned` = whatever the installed crew's `wicked-core-ts` range resolves; an explicit version re-pins it inside crew's tree |
| `bus_version` | `latest` | wicked-bus npm version |
| `garden_ref` | `latest` | wicked-garden git tag (`12.34.0`), laid out as the marketplace cache |
| `steps` | default set | `S01..S06,S09,S10`; `S07` (interactive) and `S08` (chat) are opt-in in v1 |
| `os_matrix` | `["ubuntu-latest","macos-latest"]` | Windows is not in the default matrix (the repo-checks floor has no OS write boundary there and fails closed) |
| `expect_fail_steps` | `` | step ids whose failures are ALL expected on this version set |
| `expect_fail_findings` | `` | finding ids added to the built-in expected-fail policy |
| `wicked_ci_ref` | `v1` | where the harness is taken from |

Output `overall`: `PASS`, `PASS (with expected failures)` or `FAIL`. The job fails only on a FAIL
(an EXPECTED-FAIL step never fails the job — it is printed and reported as such).

## wicked-crew — post-publish, in the release workflow

Smoke the version that was just published, against the others' `latest`. `node-release` runs on a
tag push; the smoke job needs the version the tag names.

```yaml
# .github/workflows/release.yml (crew)
jobs:
  release:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-release.yml@v1
    with:
      package_name: wicked-crew
      publish_working_dir: packages/crew
      build_cmd: npm install && npm run -w packages/crew build:with-studio
      arm_checks_sandbox: true
    secrets: inherit
  version:
    runs-on: ubuntu-latest
    outputs:
      v: ${{ steps.v.outputs.v }}
    steps:
      - id: v
        run: echo "v=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"
  smoke:
    needs: [release, version]
    uses: mikeparcewski/wicked-ci/.github/workflows/smoke.yml@v1
    with:
      crew_version: ${{ needs.version.outputs.v }}
```

npm propagation: the publish is visible to `npm install` within a minute on the public registry; if
the smoke's install step reports `No matching version`, re-run the job (the harness fails loud, it
never falls back to an older version).

## wicked-core — post-publish of core-ts (the six napi packages)

The core-ts release publishes `wicked-core-ts` plus five platform packages. The smoke installs the
**published crew** and re-pins core-ts inside it to the version just released, which exercises the
exact composition a crew user gets after a `npm update`:

```yaml
  smoke:
    needs: [publish-napi]
    uses: mikeparcewski/wicked-ci/.github/workflows/smoke.yml@v1
    with:
      core_ts_version: ${{ needs.publish-napi.outputs.version }}   # e.g. 0.7.23
```

S09 asserts the host's platform package resolves at that exact version (the six-package train is in
step), S03/S04/S06 drive the seeded workflows through the new addon.

## wicked-bus — post-publish

```yaml
  smoke:
    needs: [release]
    uses: mikeparcewski/wicked-ci/.github/workflows/smoke.yml@v1
    with:
      bus_version: ${{ needs.version.outputs.v }}
      steps: 'S01,S03,S05,S10'          # boot, an onboarding, the bus-health loop, teardown integrity
```

The daemon consumes its OWN pinned wicked-bus (a dependency inside the crew tree); the top-level
`wicked-bus@<v>` is what the external emitter (`wicked-bus emit` — the process wicked-estate spawns)
runs as. That is the two-library-instances-on-one-WAL composition S05 targets (F-E2E-021).

## wicked-garden — post-publish (a tag)

```yaml
  smoke:
    uses: mikeparcewski/wicked-ci/.github/workflows/smoke.yml@v1
    with:
      garden_ref: ${{ github.ref_name }}      # the tag, e.g. v12.34.0
      steps: 'S01,S02,S10'                     # the skills publish + stale-rules half
```

S02 asserts the daemon publishes the bundle with **no findings** and every skill portable, then that a
generation published under older portability rules is accepted with exactly one `skills.stale-rules`
warning (F-083).

## wicked-studio — post-publish

Studio ships inside crew's tarball; a studio release alone changes nothing a customer installs until
crew republishes with the bumped devDependency. Run the smoke on the **crew** release (S01 asserts
`components.studioBundle` equals the served dist marker) and, on a studio release, run it against
`latest` to record what the shipped bundle currently is:

```yaml
  smoke:
    uses: mikeparcewski/wicked-ci/.github/workflows/smoke.yml@v1
    with:
      steps: 'S01,S09,S10'
```

## Per-PR — "does my change still compose with what is published?"

A PR cannot smoke its own unpublished artifact (no source builds by design), so the per-PR call is a
**canary against the published set**: it proves the seams the PR is about to ship into are healthy at
`latest`, and it catches the other repos' drift before a release train starts. Cheap on every PR:

```yaml
# .github/workflows/ci.yml (any wicked-* repo)
jobs:
  smoke-latest:
    uses: mikeparcewski/wicked-ci/.github/workflows/smoke.yml@v1
    with:
      os_matrix: '["ubuntu-latest"]'
      steps: 'S01,S02,S03,S09,S10'
```

For a PR that changes an engine seam (crew's adapter, core-ts bindings), add `S04,S06`.

## Expected failures — the labelling rule

The harness carries a small policy (`smoke/lib/expect.mjs`): a check tagged with an acceptance finding
that the installed version is KNOWN to still exhibit is reported **EXPECTED-FAIL** with the finding id
and the reason, never silently skipped and never a red job. On crew `< 0.7.33` that is S05
(F-E2E-021: the bus WAL loop + its invisibility in `/diagnostics.recentErrors`), the deliver-gate
check in S04 (F-E2E-030), the publish-warnings check in S02 (F-E2E-002), and the branch/worktree
debris check in S03 (F-E2E-012, retention by design). When a fix ships, flip the rule; if the
harness then still reports EXPECTED-FAIL on the fixed version, that is a bug in the rule, not the
product. `--no-expect-fail` (harness) runs strict.

## Running it locally

```bash
node smoke/bin/wicked-smoke.mjs --crew 0.7.32 --bus 2.3.4 --garden 12.34.0 --keep --report-dir ./smoke-out
```

Requirements on the host: node ≥ 22, git, tar, `uv` (crew's skills seed), and on Linux `bubblewrap`
(the engine's checks sandbox). Everything the run writes lands under `--root` (default: the OS temp
dir); `--assert-hermetic` fails the run if anything under your real `$HOME` changed.
