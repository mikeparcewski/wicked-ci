---
name: wicked-e2e-plan
description: |
  Show what an E2E certification selection or profile would run, before anything runs: the
  capabilities, the scenarios and units, what they need (signed-in seats, a container runtime,
  registered repos, checkouts, tools), the cost tier, an estimated time range with its basis, and
  which capabilities can only end partial, manual or skipped. Uses `e2e run --plan-only`, which
  runs nothing.

  Use when: "what would run", "plan the release run", "how long would the daily take", "what does
  certifying plugins need", "dry run the smoke", "e2e plan".

  NOT for: running the selection (wicked-e2e-run) or reading a finished run (wicked-e2e-report).
license: MIT
compatibility: any
metadata:
  role: worker
  phases: "*"
  archetypes: "*"
---

# wicked-e2e-plan: what a selection would run

## Runtime

Find the `e2e` CLI as the `wicked-e2e` skill's Runtime section says (`WICKED_CI_ROOT`, the
`wicked-ci-root` file next to this SKILL.md, or two directories above its real path), and run it
as `python3 <wicked-ci>/e2e/bin/e2e` from `<wicked-ci>`. If it is missing, stop and say so.

## Input

A selection expression or a profile, a target (`fixture` by default, or `live` with the
`--studio URL` the operator gave), and where the checkouts are, if any. With no selection yet,
resolve the request first, the way the `wicked-e2e` skill says: the request written to a scratch
file with a file writer, then `e2e resolve --request-file <scratch-file>`.

## Steps

1. Write the plan into a new, empty scratch directory (the runner refuses a non-empty one):

   ```bash
   e2e run --select '<expr>' --target fixture --out <new-plan-dir> --plan-only
   e2e run --profile <name> --target fixture --out <new-plan-dir> --plan-only --src <checkouts-dir>
   ```

   Pass `--src` (or `--checkout REPO=PATH`) when the operator has wicked-studio, wicked-crew or
   wicked-core checkouts: without them, every scenario in those repos is skipped as
   `checkout:<repo>`. On the live target the plan probes the daemon with read-only GETs only.
2. Read the summary it prints (the same data is under `summary` in `<new-plan-dir>/plan.json`).
3. Tell the operator, in this order:
   - **Selected / will run / skipped**: the three counts, the cost mix (`S` seconds, `M` one live
     seat turn, `L` a governed run) and the areas.
   - **Units**: each unit the plan runs (one smoke harness run, one journeys call, one vitest
     file, one cargo target, one batch of direct reads) with its scenario count.
   - **Needs**: each requirement class with how it is met. `provided` means the scenario brings
     it (the smoke harness's real daemon and shimmed seats, a test's doubles). Shimmed seats prove
     the wire, not a real sign-in. `met` means a host or live probe found it. For seat sign-in,
     container and registered-repo needs, add the area notes from the `wicked-e2e` skill's
     `refs/<area>.md`.
   - **Estimate**: the printed low-to-high range and its basis per unit (`measured` on the
     sample runs or `assumed`). Say it is an estimate. Host load and cold cargo builds move it.
   - **Best possible verdicts**: how many can `pass` at best, and why the others cannot (a
     partial oracle, a fixture or integration fidelity, only direct reads, a manual oracle). A
     capability with ceiling `pass` still passes only if every check is observed to hold.
   - **Skipped before running**, grouped by the unmet requirement (`skip.dep`), with what would
     unblock each: a checkout (`--src`), the live target, a container runtime, a scenario that does
     not exist yet (`scenario:planned`), or an adapter that does not exist yet (`adapter:none`).
   - **Ask before running**: when the summary prints it, repeat its reasons. A run of this
     selection needs the operator's explicit yes.
4. Do not start the run from here. Running is the `wicked-e2e-run` skill, after the operator
   agrees.
