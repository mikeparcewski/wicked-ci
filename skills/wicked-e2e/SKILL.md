---
name: wicked-e2e
description: |
  Router for the wicked platform E2E certification suite (wicked-ci's `e2e` CLI over the
  1410-capability catalog). Turns a plain request into an action and a catalog selection with the
  deterministic `e2e resolve` helper, shows what would run with `e2e run --plan-only`, asks before
  anything costly or live, then routes to plan, run, validate, report or evidence.

  Use when: "test the run page", "certify plugins", "run the smoke", "everything about sign-in",
  "what's not covered", "re-run what failed", "e2e", "certify the platform", "which capabilities
  cover X", "is X certified".

  NOT for: writing new scenarios or tests, judging a product by reading its code, or running the
  wicked-ci smoke harness on its own (that is `smoke/`).
license: MIT
compatibility: any
metadata:
  role: router
  phases: "*"
  archetypes: "*"
---

# wicked-e2e: the certification suite router

The catalog under `e2e/catalog/` lists what the platform must do, each capability with a user
path, a typed oracle and the evidence a run must keep. The `e2e` CLI selects capabilities, runs
the existing tests behind them, seals the evidence and reports. This skill only chooses what to
ask the CLI. It never decides a verdict.

## Runtime

The CLI is `e2e/bin/e2e` in a wicked-ci checkout, run as `python3 <wicked-ci>/e2e/bin/e2e ...`
(`python` on Windows). Find `<wicked-ci>`, taking the first that holds `e2e/bin/e2e`:

1. the `WICKED_CI_ROOT` environment variable;
2. the path written in the file `wicked-ci-root` next to this SKILL.md (`skills/install.sh --copy`
   writes it);
3. two directories above this SKILL.md's real path (a symlinked install).

If none holds it, or Python 3 is missing, stop and say so. In this skill and the ones it routes
to, `e2e <subcommand>` means that command. Run commands from `<wicked-ci>` so the relative paths
in them (`e2e/coverage-baseline.json`) resolve.

## The rules that never bend

- **A verdict exists only in the CLI's files.** Say a capability passed only when its `verdict`
  in the run's `report.json` (or `<cap-id>/result.json`) is `pass` and
  `e2e validate --report <run-dir> --baseline e2e/coverage-baseline.json` exited 0.
  `partial`, `skipped`, `manual` and `error` are not passes, and "nothing failed" is not "it
  passed". `e2e run` exiting 0 means the run is complete, not that anything passed.
- **Ask before anything costly or live.** When `e2e resolve` or the plan prints
  `ask before running`, show the plan and get an explicit yes before `e2e run`. That covers any
  selected capability at cost `M` (a live seat turn) or `L` (a governed run), and every live
  target.
- **Live needs a URL the operator gave you.** Never guess a daemon URL. Never pass
  `--allow-daemon-port`, and never target port 7701 or 7721 (the operator's daemons). Never add
  `--live-journeys` without asking: those journeys drive the daemon for real.
- **Never invent output.** Quote the counts and lines the CLI printed. If a command failed, report
  its exit code and stderr.

## Step 1: resolve the request

```bash
e2e resolve "<the request, verbatim>" [--run-dir RUN_DIR] [--json]
```

It prints the action, how each word was read (area, tag, id, profile or ignored), the selection,
how many capabilities it selects by cost and area, the target, what is still needed, whether to
ask before running, and the next commands. It exits 0 only when `status` is `resolved`.

- `needs-input`: ask the operator for what `needs:` names (a run directory for re-run, report or
  evidence; a `--studio URL` for live), then resolve again with it.
- `no-match`: say which words matched nothing. Offer the closest areas or tags from
  `refs/<area>.md`, or a selection the operator writes (`e2e select 'tag:<x>'` lists what it
  picks). Never widen to everything on your own.
- `refused`: the request targets an operator daemon. Say so and offer a throwaway daemon.
- Read the `explain` lines back to the operator in one sentence ("'run page' is the tag run-page,
  15 capabilities in studio-ui") so a misreading is caught before anything runs. Name any word
  "read as a filler word" that is also a catalog tag: the selection may be wider than meant.

## Step 2: route

| action | go to |
|---|---|
| `run`, `rerun` | show the plan first (`wicked-e2e-plan`), ask when it says so, then `wicked-e2e-run` |
| `plan` | `wicked-e2e-plan` |
| `validate-coverage`, `validate-report` | `wicked-e2e-validate` |
| `report` | `wicked-e2e-report` |
| `evidence` | `wicked-e2e-evidence` |

**Hand-off**: open the skill the table names and carry out its steps with the resolved
selection (or profile), target and run directory as its input. On Claude Code this is the Skill
tool; on any other seat open the named skill from your catalog and carry it out inline, then
continue here.

## Areas

One short reference per catalog area: its setup quirks and dependencies, plus a block generated
from the catalog (counts, tags, id groups, dependency classes, who can run it). Read the area's
reference before planning a run in it.

- [studio-ui](refs/studio-ui.md): built studio, Playwright, fixture journeys vs a live daemon.
- [crew-api](refs/crew-api.md): the smoke harness, crew vitest, read-only live GETs.
- [core-engine](refs/core-engine.md): cargo in a build slot, container runtime, governed runs.
- [estate](refs/estate.md): estate binaries, indexed graphs, mostly no adapter yet.
- [garden](refs/garden.md): the plugin install prerequisite, python and node.
- [plugins-and-installs](refs/plugins-and-installs.md): crew's consent gate, sandboxed homes.
- [interactive-and-docs](refs/interactive-and-docs.md): the crew-proxied bridge, ffmpeg, sites.
- [foundation](refs/foundation.md): temp bus roots, the run's own vault, gh reads.
- [seats-and-clis](refs/seats-and-clis.md): sign-in prerequisites per CLI, floors, credentials.

## Selections and profiles

The selection language (`e2e/README.md`): `area:`, `tag:`, `id:` (globs, aliases too), `surface=`,
`cost<=S|M|L`, `oracle=`, `!` to exclude. Terms with the same key are OR'd, different keys AND'd.
Profiles: `smoke` (cheap seams), `daily` (no governed run), `release` (release-blocking journeys,
governed runs included), `full` (everything; manual ones report `manual`).
