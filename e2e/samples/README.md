# Sample run reports

Reports that `e2e run` wrote on a workstation, committed so the format can be read without running
anything. Only the report files are here: the videos, traces, screenshots, transcripts, result
files and the run's vault stayed in the run directory, so the evidence links in these reports do
not resolve from this directory.

| directory | command | what it shows |
|---|---|---|
| `smoke-fixture/` | `e2e run --profile smoke --target fixture --src DIR ...` | the 33 smoke-profile capabilities (partial 28, fail 2, error 2, skipped 1): the wicked-ci smoke steps S01-S09 run through the harness (e2e-hermetic), one crew vitest file, one gh read. The fails are S03's labelled F-E2E-012 (its capabilities fail with the step); the errors are S01/S02, which record no event log their capabilities require; the one UI capability is skipped (its only runnable scenario records no browser). No pass: of the 33, only one oracle is complete, and its scenario's reads were made in a state it seeds on purpose. (In three earlier runs S06 failed too, `POST /testing/recon` answering 202 `launching` where the step expects 201: timing-dependent.) |
| `ui-fixture/` | `e2e run --select 'id:studio-ui.rail.*,studio-ui.shell.desk-loads area:studio-ui' --target fixture ...` | 8 capabilities (partial 7, skipped 1): five studio fixture journeys run through `run_journeys.py` with the Playwright hook (video, trace, HAR and screenshots per capability); fixture fidelity is evidence, never a pass |
| `live-throwaway/` | `e2e run --select '...' --target live --studio http://127.0.0.1:<free port>` | 17 capabilities (pass 1, fail 2, partial 10, skipped 4) against a throwaway `wicked-crew serve` 0.15.5 (its own state home, no seat CLIs and no `uv` on its PATH): direct read-only GETs, a /ws subscription and one read-only studio visit. The pass is `crew-api.standing-orders.read` (a complete oracle on a read-only path); the fails are real for that daemon (`GET /skills` answers 503 without a published skills snapshot; no signed-in claude on its roster). Its request log showed only GETs |

Each report embeds the `e2e validate --report` result for its run at the time it was written.
