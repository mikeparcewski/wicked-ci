---
name: wicked-e2e-run
description: |
  Execute an E2E certification selection or profile with `e2e run` against the fixture target or
  an explicitly named live daemon, then validate the run directory with `e2e validate --report`
  and hand the result to wicked-e2e-report. Refuses the operator's daemon ports, asks before any
  costly (cost M or L) or live run, and never reports a verdict the run directory does not hold.

  Use when: "run it", "certify it now", "run the smoke profile", "run the selection against my
  throwaway daemon", "re-run what failed", "e2e run".

  NOT for: deciding what to run (wicked-e2e / wicked-e2e-plan) or explaining results
  (wicked-e2e-report).
license: MIT
compatibility: any
metadata:
  role: worker
  phases: "*"
  archetypes: "*"
---

# wicked-e2e-run: execute, validate, hand off

## Runtime

Find the `e2e` CLI as the `wicked-e2e` skill's Runtime section says (`WICKED_CI_ROOT`, the
`wicked-ci-root` file next to this SKILL.md, or two directories above its real path), and run it
as `python3 <wicked-ci>/e2e/bin/e2e` from `<wicked-ci>`. If it is missing, stop and say so.

## Before running: the gate

1. You have a plan for exactly this selection, target and checkouts (the `wicked-e2e-plan`
   skill). If not, make one first.
2. If the plan (or `e2e resolve`) printed `ask before running`, show its reasons and the estimate
   and wait for the operator's explicit yes. A yes for a different selection or target does not
   count.
3. If the selection came from a free-text request (not an exact selection, profile or capability
   id the operator wrote), the operator has confirmed the resolved selection, even when nothing in
   it costs more than `S`.
4. **Live target**: only with a `--studio URL` the operator gave. Never ports 7701 or 7721, never
   `--allow-daemon-port`. Add `--live-journeys` only when the operator asked for live journeys by
   name, because they drive the daemon for real and some launch governed runs.
5. Cost `L` items are governed runs. Run one such selection at a time, never two runs in
   parallel.

## Run

Use a new, empty run directory. The runner refuses a non-empty one, so a run never mixes with an
earlier run's files.

```bash
e2e run --select '<expr>' --target fixture --out <new-run-dir> --src <checkouts-dir>
e2e run --profile smoke --target fixture --out <new-run-dir> --src <checkouts-dir> --python <python-with-playwright> --playwright-browsers <browsers-dir> --build-slot "<prefix> --"
e2e run --select '<expr>' --target live --studio <url-the-operator-gave> --out <new-run-dir>
```

- **Re-run what failed**: resolve it from the earlier run, then run its selection into a NEW
  directory: `e2e resolve --request-file <scratch-file> --run-dir <earlier-run-dir>` (the
  file holds "re-run what failed", written with a file writer) prints an `id:` list
  of the fail and error capabilities and the earlier run's target.
- **Long runs**: the plan's estimate can exceed one shell call. Follow your harness's rules for
  long commands, check progress in `<new-run-dir>/runner.log` in short calls, and do not report
  anything until `<new-run-dir>/report.json` exists.

## After running

1. Note the exit code. 0 means the run is complete and its own report validated, whatever the
   verdicts. 1 means it did not validate. 2 means it refused to start (read stderr).
2. Validate it yourself:

   ```bash
   e2e validate --report <new-run-dir> --baseline e2e/coverage-baseline.json
   ```

   Exit 0 is required before anyone treats a verdict in this run as real. Keep `--baseline`:
   without it the validator also fails on every known unmapped surface element. A non-zero exit
   lists failures, and any of them means the run is not certified: say so, and hand the lines to
   the `wicked-e2e-validate` skill to explain. `report:` lines are about the run; the others are
   about the catalog the run was judged by, which can make a recorded verdict wrong too.
3. **Hand-off**: open the `wicked-e2e-report` skill and summarise `<new-run-dir>` with it. On
   Claude Code this is the Skill tool; on any other seat open the named skill from your catalog
   and carry it out inline, then continue here.

Report the run directory, the exit codes of `e2e run` and `e2e validate --report`, and the verdict
counts from `report.json`, never your own reading of the logs.
