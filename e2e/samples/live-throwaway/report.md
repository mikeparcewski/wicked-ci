# e2e certification run 20261020T150410Z-0225

Target **live** (http://127.0.0.1:7811), selection `id:crew-api.health.get,crew-api.diagnostics.*,crew-api.roster.read,crew-api.skills.manifest,crew-api.chats.list,crew-api.campaigns.read,crew-api.standing-orders.read,studio-ui.shell.desk-loads,studio-ui.rail.order,crew-api.runs.list*,crew-api.projects.crud`. Started 2026-10-20T15:04:10+00:00, finished 2026-10-20T15:04:18+00:00.

A `pass` means every typed check was observed to hold, on something tied to this path, on a complete oracle at e2e-live or e2e-hermetic fidelity, on a path a scenario drove. `partial` lists what is missing. `skipped` names the unmet dependency. This report restates the results; `e2e validate --report` checks them.

## Summary

| verdict | capabilities |
|---|---:|
| fail | 2 |
| partial | 10 |
| skipped | 4 |
| pass | 1 |
| **total** | **17** |

## Coverage by area

| area | fail | partial | skipped | pass | total |
|---|---:|---:|---:|---:|---:|
| studio-ui | 0 | 2 | 0 | 0 | 2 |
| crew-api | 2 | 8 | 3 | 1 | 14 |
| foundation | 0 | 0 | 1 | 0 | 1 |

Evidence: hashed and recorded in wicked-vault scope `e2e-20261020T150410Z-0225`.

Validation (`e2e validate --report`, when this report was written): **OK**

## fail (2)

- **crew-api.roster.read** (api, S) via `direct` at e2e-live
  - checks: 0 held, 1 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - check 0 contradicted by what the run recorded
  - [api-transcript 1](crew-api.roster.read/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.roster.read/result.json)
- **crew-api.skills.manifest** (api, S) via `direct` at e2e-live
  - checks: 0 held, 1 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - check 0 contradicted by what the run recorded
  - [api-transcript 1](crew-api.skills.manifest/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.skills.manifest/result.json)

## partial (10)

- **crew-api.campaigns.read** (api, S) via `direct` at e2e-live
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: 200; campaign.nodes statuses match their runs' statuses; unknown -> 404
  - [api-transcript 1](crew-api.campaigns.read/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.campaigns.read/result.json)
- **crew-api.chats.list** (api, S) via `direct` at e2e-live
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: 200 contains chatId from open; after DELETE absent
  - [api-transcript 1](crew-api.chats.list/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.chats.list/result.json)
- **crew-api.diagnostics.governance** (api, S) via `direct` at e2e-live
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: diagnostics.governance.store non-null on a real boot; records is integer >= 0; when outbox has >=1 line, findings contains 'governance.deadletter'
  - [api-transcript 1](crew-api.diagnostics.governance/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.diagnostics.governance/result.json)
- **crew-api.diagnostics.recent-errors** (api, S) via `direct` at e2e-live
  - checks: 0 held, 0 contradicted, 1 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: after the seeded bus error the entry matches the daemon log line; daemon stdout has 0 'malformed' repeats; check 0 not observed; the runner only read the end state; no scenario drove the user's path
  - [api-transcript 1](crew-api.diagnostics.recent-errors/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.diagnostics.recent-errors/result.json)
- **crew-api.diagnostics.seat-governance** (api, S) via `direct` at e2e-live
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 2
  - the oracle is partial: seatGovernance.seats.length == roster length; each seat has governance_class in {acp_input_governance,os_sandbox,none}; roleFindings equals /health warnings of kind seat.work_default; diagnostics.seatGovernance.seats[].governance_mode.scoped_bound.mode in {admitted,os_sandbox,none}; any seat with mode 'none' yields health.warnings kind 'seats.ungoverned'; floor seats on a host with no sandbox launcher yield 'seats.os-floor-unarmable'. (Live 7721 read: claude admitted, codex/pi/copilot/opencode os_sandbox, hostBoundary sandbox-exec.)
  - [api-transcript 1](crew-api.diagnostics.seat-governance/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.diagnostics.seat-governance/result.json)
- **crew-api.diagnostics.skills** (api, S) via `direct` at e2e-live
  - checks: 0 held, 0 contradicted, 1 unsatisfied on the transcript, 0 not observed, of 1
  - check 0 not observed; the runner only read the end state; no scenario drove the user's path
  - [api-transcript 1](crew-api.diagnostics.skills/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.diagnostics.skills/result.json)
- **crew-api.health.get** (api, S) via `direct` at e2e-live
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: json.status=='ok'; json.version==packages/crew/package.json version; json.ping in {'ok','busy'}; json.capabilities.qeAcceptance in {'required','off'}; json.baseSkill.present is boolean
  - [api-transcript 1](crew-api.health.get/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.health.get/result.json)
- **crew-api.runs.list** (api, S) via `direct` at e2e-live
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: json.runs is array; every element has session.id and units[]; awaiting_human entries precede executing/terminal ones
  - [api-transcript 1](crew-api.runs.list/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.runs.list/result.json)
- **studio-ui.rail.order** (ui, S) via `direct` at e2e-live
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 1 not observed, of 3
  - the oracle is partial: DOM order of rail link texts equals the list in desk_rail_test ORDER; absence of links to /repos,/rules,/testing,/agents in rail; check 2 not observed; the runner only read the end state; no scenario drove the user's path
  - [api-transcript 1](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 2](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [screenshot 1](scenarios/direct/pw/visit/shots/001-visit.png) · [screenshot 2](scenarios/direct/pw/visit/shots/002-final-ctx1-page0.png) · [trace](scenarios/direct/pw/visit/trace/ctx-1.zip) · [video](scenarios/direct/pw/visit/video/page@2a91c9c5fde47a8f9fe1136867c40b9a.webm) · [result](studio-ui.rail.order/result.json)
- **studio-ui.shell.desk-loads** (ui, S) via `direct` at e2e-live
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 2
  - the oracle is partial: DOM: document.querySelector('[data-shell=desk]') present; [data-testid=desk] data-tab=='work'; rail boundingBox.width==236; 0 pageerror events; the runner only read the end state; no scenario drove the user's path
  - [api-transcript 1](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 2](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [screenshot 1](scenarios/direct/pw/visit/shots/001-visit.png) · [screenshot 2](scenarios/direct/pw/visit/shots/002-final-ctx1-page0.png) · [trace](scenarios/direct/pw/visit/trace/ctx-1.zip) · [video](scenarios/direct/pw/visit/video/page@2a91c9c5fde47a8f9fe1136867c40b9a.webm) · [result](studio-ui.shell.desk-loads/result.json)

## skipped (4)

- **crew-api.diagnostics.components** (api, S)
  - skipped: evidence:file-hash (direct cannot capture file-hash)
  - [result](crew-api.diagnostics.components/result.json)
- **crew-api.diagnostics.state-home** (api, S)
  - skipped: target:fixture (no e2e-live scenario (fidelities: integration); run --target fixture)
  - [result](crew-api.diagnostics.state-home/result.json)
- **crew-api.projects.crud** (api, S)
  - skipped: target:fixture (no e2e-live scenario (fidelities: e2e-hermetic, integration); run --target fixture)
  - [result](crew-api.projects.crud/result.json)
- **foundation.platform.vault.bin-posture** (api, M)
  - skipped: target:fixture (no e2e-live scenario (fidelities: integration); run --target fixture)
  - [result](foundation.platform.vault.bin-posture/result.json)

## pass (1)

- **crew-api.standing-orders.read** (api, S) via `direct` at e2e-live
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - [api-transcript 1](crew-api.standing-orders.read/api-transcript.json) · [api-transcript 2](scenarios/direct/pw/visit/api-transcript.json) · [api-transcript 3](scenarios/direct/api-transcript.json) · [event-log 1](scenarios/direct/pw/visit/network-events.json) · [event-log 2](scenarios/direct/event-log.json) · [result](crew-api.standing-orders.read/result.json)

