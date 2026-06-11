# wicked-ci

Shared GitHub Actions reusable workflows for the wicked-* family of npm
packages (wicked-testing, wicked-bus, wicked-brain, and future siblings).

Two workflows live here:

- `.github/workflows/node-ci.yml` — matrix test on ubuntu/macos/windows
- `.github/workflows/node-release.yml` — publish to npm + GitHub Packages,
  cut a GitHub Release, and (optionally) open a catchup PR that bumps
  `package.json` on `main` to the released tag.

Consumers call them via `uses:`. Versions are pinned by tag — `@v1` for
the latest non-breaking line.

## Versioning policy

- Tags follow semver: `v1.0.0`, `v1.1.0`, `v2.0.0`, …
- Floating major tags `v1`, `v2`, … always point to the latest patch in
  that line. Consumers pin to the float (`@v1`) to inherit fixes and
  non-breaking inputs.
- Breaking changes (renamed inputs, removed jobs) bump the major and
  require consumers to update their `@vN` pin.
- A bad shared change can break every consumer at once. Test in a
  feature branch (`@my-test-branch`) on one repo before re-pointing the
  major tag.

## node-ci.yml — inputs

All optional; defaults match the existing wicked-bus / wicked-testing
shape (test from repo root, `npm install` + `npm test`).

| input              | default                                              | notes |
|--------------------|------------------------------------------------------|-------|
| `test_working_dir` | `.`                                                  | for nested packages, e.g. `server` |
| `install_cmd`      | `npm install`                                        | |
| `test_cmd`         | `npm test`                                           | |
| `node_version`     | `lts/*`                                              | |
| `os_matrix`        | `["ubuntu-latest","macos-latest","windows-latest"]`  | JSON array string |

## node-release.yml — inputs

| input                       | required | default                | notes |
|-----------------------------|----------|------------------------|-------|
| `package_name`              | yes      |                        | unscoped, e.g. `wicked-bus` |
| `scope`                     |          | `@mikeparcewski`       | used to rename for GH Packages publish |
| `version_dirs`              |          | `.`                    | newline-separated; bump multiple `package.json` files (e.g. `.\nserver`) |
| `pre_publish_install_dirs`  |          | (empty)                | newline-separated; runs `npm install --omit=dev` before publish in each dir — needed when a nested package's deps are required by the tarball or by a `prepublishOnly` hook |
| `test_working_dir`          |          | `.`                    | |
| `install_cmd`               |          | `npm install`          | |
| `test_cmd`                  |          | `npm test`             | |
| `node_version`              |          | `lts/*`                | |
| `enable_sync_pr`            |          | `false`                | open a `release-sync/<tag>` PR that bumps `package.json` on `main` |
| `enable_github_packages`    |          | `true`                 | mirror publish to GitHub Packages |

## Required permissions on the caller

Reusable workflows can only narrow the caller's `GITHUB_TOKEN`
permissions, never widen them. Callers must declare:

```yaml
permissions:
  contents: write       # github-release, sync-pr commit
  packages: write       # GitHub Packages publish
  id-token: write       # npm trusted-publisher provenance
  pull-requests: write  # sync-pr (only when enable_sync_pr: true)
```

`secrets: inherit` on the calling job passes `GITHUB_TOKEN` (and any
trusted-publisher OIDC config) through to the reusable workflow.

## Caller examples

### Simple — root package, no sync PR (wicked-testing)

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ['v*']
permissions:
  contents: write
  packages: write
  id-token: write
jobs:
  release:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-release.yml@v1
    with:
      package_name: wicked-testing
    secrets: inherit
```

### Root package + catchup PR (wicked-bus)

```yaml
jobs:
  release:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-release.yml@v1
    with:
      package_name: wicked-bus
      enable_sync_pr: true
    secrets: inherit
```

### Nested package — root + server (wicked-brain)

```yaml
jobs:
  release:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-release.yml@v1
    with:
      package_name: wicked-brain
      test_working_dir: server
      version_dirs: |
        .
        server
      pre_publish_install_dirs: |
        .
        server
      enable_sync_pr: true
    secrets: inherit
```

### CI

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  ci:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-ci.yml@v1
```

For wicked-brain (tests live in `server/`):

```yaml
jobs:
  ci:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-ci.yml@v1
    with:
      test_working_dir: server
```

Repo-specific extra jobs (e.g. wicked-brain's `wiki` job, wicked-testing's
`evals` job) stay in the caller as separate jobs alongside `uses:` —
don't try to fold those into the shared workflow.

### Non-node test suites — bash / python (wicked-vault, wicked-loom)

Some siblings publish to npm but test with bash or pytest. Use `test_cmd`,
`os_matrix`, and `setup_python` rather than forking the workflow.

wicked-vault — bash proofs, no Windows:

```yaml
jobs:
  release:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-release.yml@v1
    with:
      package_name: wicked-vault
      os_matrix: '["ubuntu-latest"]'
      test_cmd: 'bash test/cli-baseline.sh && bash test/attestation.sh && bash test/bus-integration.sh'
      enable_sync_pr: true
    secrets: inherit
```

wicked-loom — pytest gate before an npm publish:

```yaml
jobs:
  release:
    uses: mikeparcewski/wicked-ci/.github/workflows/node-release.yml@v1
    with:
      package_name: wicked-loom
      os_matrix: '["ubuntu-latest"]'
      setup_python: true
      install_cmd: 'python -m pip install --upgrade pip pytest'
      test_cmd: 'PYTHONPATH=python python -m pytest -q'
      enable_sync_pr: true
    secrets: inherit
```

A repo whose CI matrix is over *python versions* (loom's 3.9–3.12, the
understanding suite's 3.10–3.12) is genuinely repo-specific — keep that
`ci.yml` bespoke, the same way brain's `wiki` job stays in the caller.

## Cross-repo dependency upgrades — Renovate

`default.json` is a Renovate preset every consumer extends:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>mikeparcewski/wicked-ci"]
}
```

It groups all GitHub Action pin bumps into one PR per repo (auto-merged on
minor/patch) and pins the shared npm deps (`better-sqlite3`, `vitest`,
`@types/node`, `typescript`, `react`/`react-dom`) to a common cadence.
Renovate opens PRs per repo, not one PR across repos — but a single preset
means every sibling bumps the same way at the same time, which is what stops
the action-pin drift this repo was created to fix from coming back.

## Cutover

For each npm consumer (wicked-bus, wicked-brain, wicked-testing, wicked-vault,
wicked-loom):

1. Replace `release.yml` (and `ci.yml` where it fits) with the caller stubs
   above; keep repo-specific jobs (wiki / evals / windows-smoke /
   python-version matrix) as siblings.
2. Open a no-op tag (`v0.0.0-test`) on a throwaway branch first, or
   point `@v1` at a branch SHA temporarily, to verify before
   tagging a real release.
3. Once green, push the next real tag — publish should be identical to
   the prior bespoke workflow.

> **Note:** `v1.0.0` baselines the action pins to what the repos already run
> (checkout@v6 / setup-node@v6 / gh-release@v3 / create-pull-request@v8). Push
> this repo and tag `v1` (and the floating `v1`) before re-pointing any
> consumer at `@v1`.

## Future siblings

Add a 15-line caller. No copy-paste of publish jobs.
