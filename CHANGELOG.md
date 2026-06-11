# Changelog

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
