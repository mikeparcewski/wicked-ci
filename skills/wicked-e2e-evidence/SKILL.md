---
name: wicked-e2e-evidence
description: |
  Explain and open the evidence behind an E2E certification verdict: what each capability must
  keep (video, screenshot and trace for UI; API, event and CLI transcripts; file hashes; vault
  entries), where it lives in a run directory, and whether it is intact. Uses
  `e2e evidence <run-dir> <cap-id>` to list one capability's files with their hash status against
  the run's wicked-vault, and explains how tampering is detected.

  Use when: "show me the video", "open the evidence for X", "where is the trace", "was this
  evidence tampered with", "how is evidence verified", "e2e evidence".

  NOT for: the run's overall verdicts (wicked-e2e-report) or a whole-run integrity check
  (wicked-e2e-validate, `e2e validate --report`).
license: MIT
compatibility: any
metadata:
  role: worker
  phases: "*"
  archetypes: "*"
---

# wicked-e2e-evidence: open and verify a capability's evidence

## Runtime

Find the `e2e` CLI as the `wicked-e2e` skill's Runtime section says (`WICKED_CI_ROOT`, the
`wicked-ci-root` file next to this SKILL.md, or two directories above its real path), and run it
as `python3 <wicked-ci>/e2e/bin/e2e` from `<wicked-ci>`. If it is missing, stop and say so.

## Open one capability's evidence

```bash
e2e evidence <run-dir> <cap-id>
e2e evidence <run-dir> <cap-id> --json
```

It prints the verdict and scenario, then every evidence file by kind with its status and absolute
path, then `result.json`, the vault entry and `integrity: INTACT` or `NOT INTACT` (exit 0 or 1).

| status | means |
|---|---|
| `ok` | the file hashes to what the vault froze when the run was sealed |
| `changed` | the file was edited after the run |
| `gone` | the file was deleted |
| `not-recorded` | the result lists a file the frozen manifest does not |
| `unverified` | the run was never sealed, so nothing can be checked |

Give the operator the paths to open: the `.webm` video and `.png` screenshots play and show in any
browser or viewer, and the trace `.zip` opens with `npx playwright show-trace <trace.zip>`. The
JSON transcripts are plain text. `<run-dir>/report.html` embeds the videos and screenshots per
capability. If the status is not `ok`, say the evidence cannot be trusted and do not describe it as
proof.

## What a run keeps

- `required_evidence` on each capability lists the kinds: `video`, `screenshot`, `trace`,
  `api-transcript`, `event-log`, `file-hash`, `ledger-entry`, `vault-entry`, `cli-transcript`. A UI
  capability always requires video, screenshot and trace.
- Studio journeys record per browser context a `.webm` video, a Playwright `trace.zip`, a HAR of
  every `/api/` exchange (the network events a UI check observes), screenshots, and DOM samples.
- The smoke harness records per step the API transcript, the event log (`/ws` frames, events read
  back, the hermetic bus) and the CLI transcript. Crew vitest records its JSON report and every
  `inject()`/`fetch` exchange. Cargo records its test output.
- A lower-fidelity test's report may stand in for a transcript it could not record. The result
  lists it under `evidence_substitutes`, and such a result can never pass.
- A required kind the adapter could not capture makes the capability `error`, never a verdict.

## How tampering is detected

1. After judging, the runner hashes `result.json` and every evidence file of each capability into
   `<cap-id>/evidence-manifest.json`.
2. It records each manifest, and `run.json`, with `wicked-vault record --artifact` in the run's
   own vault (`<run-dir>/.wicked-vault`, scope `e2e-<run-id>`). The vault keeps a frozen copy and
   binds it into a hashed entry.
3. `e2e validate --report` and `e2e evidence` re-hash every file against that frozen copy, so a
   deleted video, an edited transcript or a verdict flipped after the run is caught.
   `e2e validate --report` also runs `wicked-vault verify` on every entry when the CLI is on PATH.
4. Limits, to state when asked: the hashes are unkeyed, so they catch mutation, not a writer who
   also rewrites `.wicked-vault/`. An unsealed run (no vault CLI, or `--no-vault`) cannot be
   verified at all, and `e2e validate --report` refuses it.
