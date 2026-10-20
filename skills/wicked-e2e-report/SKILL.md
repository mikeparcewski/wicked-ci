---
name: wicked-e2e-report
description: |
  Summarise an E2E certification run directory from the files the runner wrote: verdict counts by
  area, failures and errors first with links to their evidence (video, screenshots, trace,
  transcripts, result.json), and what blocks a pass (an incomplete oracle, a fixture fidelity, a
  missing adapter, an unmet dependency, a planned scenario). Uses `e2e report` and
  `e2e validate --report`; it never upgrades a verdict.

  Use when: "summarise the run", "what failed", "how did the smoke go", "show the results", "what
  blocks a pass", "e2e report".

  NOT for: deciding what to run (wicked-e2e-plan) or checking one capability's evidence in depth
  (wicked-e2e-evidence).
license: MIT
compatibility: any
metadata:
  role: worker
  phases: "*"
  archetypes: "*"
---

# wicked-e2e-report: summarise a run directory

## Runtime

Find the `e2e` CLI as the `wicked-e2e` skill's Runtime section says (`WICKED_CI_ROOT`, the
`wicked-ci-root` file next to this SKILL.md, or two directories above its real path), and run it
as `python3 <wicked-ci>/e2e/bin/e2e` from `<wicked-ci>`. If it is missing, stop and say so.

## Steps

1. Regenerate the reports and check the run:

   ```bash
   e2e report <run-dir>
   e2e validate --report <run-dir>
   ```

   `e2e report` rewrites `report.md`, `report.html` and `report.json` from the result files and
   embeds a validation result. `e2e validate --report` also runs `wicked-vault verify` when the
   vault CLI is on PATH.
2. Read `<run-dir>/report.json`: `counts`, `matrix` (area by verdict), `blockers`, `capabilities`
   (already ordered fail, error, partial, skipped, manual, pass) and `validation`.
3. Write the summary in this order:
   - **Validation first.** If `e2e validate --report` did not exit 0, say "this run is not
     certified" and list its failures before anything else (the `wicked-e2e-validate` skill
     explains them).
   - **Counts** by verdict, and the area-by-verdict table from `matrix`.
   - **Failures and errors** one by one: the id, the scenario and fidelity, the reason, and the
     evidence links from that capability's `evidence` (video, screenshots, trace, transcripts) plus
     its `result.json`. The paths are relative to the run directory.
   - **What blocks a pass**: the `blockers` table (each blocker with its count and example ids).
     Name the blocker kinds plainly: an incomplete oracle (untyped clauses), a fixture or
     integration fidelity, only direct reads, a check not observed or held only on a wildcard, a
     missing adapter (`adapter:none`), a missing checkout, an unmet dependency, a planned scenario,
     evidence the adapter cannot capture, a manual oracle.
   - **Passes**: the count, and the ids if there are few.
4. Point at `<run-dir>/report.html` for the videos and screenshots inline.

## Words to use

- `pass` only for a capability whose verdict is `pass` in `report.json`, in a run whose
  validation is OK.
- `partial` is "ran, not certified" and names what is missing. `skipped` is "did not run" and
  names why. `manual` is "needs a human; never a pass". `error` is "the run could not show it",
  not a product failure. `fail` is a scenario failure or a contradicted check: read the reason
  before calling it a product bug (a smoke step can fail on purpose, labelled in its reason).
- Never sum `partial` or `skipped` into a pass rate, and never say "all green" unless every
  verdict is `pass`.
