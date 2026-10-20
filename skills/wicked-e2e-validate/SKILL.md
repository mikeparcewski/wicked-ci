---
name: wicked-e2e-validate
description: |
  Run the E2E suite's validator and explain its failures in plain terms: catalog and coverage
  validation (is every surface element covered, which capabilities have no scenario, does every
  scenario name a real test) and run-report validation (is a run directory complete, intact and
  honest: missing evidence, a verdict that claims too much, a tampered file). Uses
  `e2e validate`; it never edits the catalog or a run to make it pass.

  Use when: "what's not covered", "coverage gaps", "which surface is unmapped", "validate the
  catalog", "is this run complete", "validate the run report", "why does validate fail".

  NOT for: summarising a run's verdicts (wicked-e2e-report) or opening one capability's evidence
  (wicked-e2e-evidence).
license: MIT
compatibility: any
metadata:
  role: worker
  phases: "*"
  archetypes: "*"
---

# wicked-e2e-validate: coverage and run-report validation

## Runtime

Find the `e2e` CLI as the `wicked-e2e` skill's Runtime section says (`WICKED_CI_ROOT`, the
`wicked-ci-root` file next to this SKILL.md, or two directories above its real path), and run it
as `python3 <wicked-ci>/e2e/bin/e2e` from `<wicked-ci>`. If it is missing, stop and say so.

## Coverage: "what's not covered"

```bash
e2e validate --baseline e2e/coverage-baseline.json --out <new-coverage-dir>
```

This is what CI runs. It prints one line (capabilities, with scenario, planned, manual, untyped,
unmapped elements, `OK` or `N FAILURES`) and writes `coverage.md` and `coverage.json`. Read
`coverage.json` and report:

- **Unmapped surface elements** (`unmapped`, by repo): user-facing elements (studio testids and
  routes, crew routes and CLI verbs, MCP tools, skills, hooks) that no capability covers. The
  baseline tolerates the known ones. Give the count per repo and kind, and a few keys.
- **Planned only** (`summary.total.planned`): capabilities with no test at all. They are
  uncovered, not failures.
- **Per area** (`summary`): with scenario, planned, manual, untyped, typed complete or partial,
  and the best scenario fidelity.

Without `--baseline` (`e2e validate`) every unmapped element fails: use that to see the full gap,
not as the CI gate. For drift against current mains, `e2e drift --against <fresh-manifests-dir>`
reports and never fails.

## Run report: "is this run complete"

```bash
e2e validate --report <run-dir> --baseline e2e/coverage-baseline.json
```

Exit 0 means the run directory is complete and intact and no verdict claims more than the verdict
rule allows. The same command also validates the catalog and coverage, so keep `--baseline`
(without it every known unmapped surface element fails too). Failure lines that start with
`report:` are about the run; the others are about the catalog at this checkout. It does not mean capabilities passed: read the verdicts with the `wicked-e2e-report`
skill. `--allow-unvaulted` and `--no-vault-cli` weaken the integrity check. Use them only when the
operator asks, and say so in the result.

## Explaining failures

Each failure is one line. Translate it, and name the capability or surface it is about.

| the line says | it means |
|---|---|
| `unmapped surface element (not in the baseline): <key>` | a new user-facing element no capability covers: add it to a capability's `covers`, or (only to drop entries) regenerate the baseline |
| `baseline entry is no longer unmapped, remove it: <key>` | the gap closed or the element is gone: the baseline only shrinks, so drop it with `e2e baseline --write` |
| `<id>: covers <key>, which no surface manifest lists` | the capability claims an element that does not exist at the pinned SHAs |
| `<id>: scenario <ref> is not a test file ...` | the scenario names a file that is not a test at the pin (renamed or removed) |
| `<id>: a UI capability must require video, screenshot and trace` | the catalog record under-asks for evidence |
| `<id>: oracle ... complete ...` | the oracle's `complete` flag disagrees with its clauses (it cannot be complete with untyped clauses or an incomplete child) |
| `report: <id>: no verdict (<id>/result.json missing)` | the run did not record that capability: the run is incomplete |
| `report: run.json: capabilities differ from the selection` | the run's list is not what its selection selects: a capability was dropped or added |
| `report: <id>: required evidence <kind> missing` / `... missing or empty` | the run kept no file (or an empty one) of a kind the capability requires |
| `report: <id>: ... must be .webm/.png/.zip` | the video, screenshot or trace has the wrong format |
| `report: <id>: the oracle is partial ...; report partial, not pass` | the result claims `pass` on an oracle that is not complete |
| `report: <id>: a manual oracle can never be pass` | a `manual` capability claims `pass` |
| `report: <id>: pass with a check that was not observed ...` / `... wildcard ...` / `... fidelity ...` / `... direct reads only ...` | the result claims more than the verdict rule allows |
| `report: <id>: a contradicted check (ok: false) must be fail` | a contradicted check was reported as something milder |
| `report: <id>: skip.dep ...` | a skip that names no dependency, or one that is not the capability's |
| `report: vault: <id>: evidence <path> changed after it was recorded` / `... is gone` / `result.json changed ...` | the file differs from the hash frozen in the vault: it was edited or deleted after the run |
| `report: vault: ... not recorded in wicked-vault` | the run was not sealed (no vault CLI, or `--no-vault`): its integrity cannot be checked |

Never fix a report failure by editing `result.json`, `run.json` or an evidence file: the vault
check exists to catch exactly that. A failing run is re-run into a new directory.
