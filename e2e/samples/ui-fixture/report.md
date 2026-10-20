# e2e certification run 20261020T150258Z-1ed4

Target **fixture**, selection `id:studio-ui.rail.*,studio-ui.shell.desk-loads area:studio-ui`. Started 2026-10-20T15:02:58+00:00, finished 2026-10-20T15:03:58+00:00.

A `pass` means every typed check was observed to hold, on something tied to this path, on a complete oracle at e2e-live or e2e-hermetic fidelity, on a path a scenario drove. `partial` lists what is missing. `skipped` names the unmet dependency. This report restates the results; `e2e validate --report` checks them.

## Summary

| verdict | capabilities |
|---|---:|
| partial | 7 |
| skipped | 1 |
| **total** | **8** |

## Coverage by area

| area | partial | skipped | total |
|---|---:|---:|---:|
| studio-ui | 7 | 1 | 8 |

Evidence: hashed and recorded in wicked-vault scope `e2e-20261020T150258Z-1ed4`.

Validation (`e2e validate --report`, when this report was written): **OK**

## partial (7)

- **studio-ui.rail.action-row** (ui, S) via `wicked-studio:e2e/desk_search_test.py` `1` at e2e-fixture
  - checks: 1 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 1
  - the oracle is partial: each route: all 4 testids visible inside [data-testid=desk-rail-actions]; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_search/api-transcript.json) · [event-log](scenarios/wicked-studio-journeys/pw/desk_search/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_search/shots/001-desk-search-header-desk.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_search/shots/002-desk-search-header-project.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_search/shots/003-desk-search-header-run.png) · [screenshot 4](scenarios/wicked-studio-journeys/pw/desk_search/shots/004-desk-search-header-general.png) · [screenshot 5](scenarios/wicked-studio-journeys/pw/desk_search/shots/005-desk-search-all.png) · [screenshot 6](scenarios/wicked-studio-journeys/pw/desk_search/shots/006-desk-search-rules.png) · [trace 1](scenarios/wicked-studio-journeys/pw/desk_search/trace/ctx-1.zip) · [trace 2](scenarios/wicked-studio-journeys/pw/desk_search/trace/ctx-2.zip) · [video 1](scenarios/wicked-studio-journeys/pw/desk_search/video/page@ad2786deb135a4538a6b095f12634aeb.webm) · [video 2](scenarios/wicked-studio-journeys/pw/desk_search/video/page@b99178b9724c2ad039a642c4ae879e9e.webm) · [result](studio-ui.rail.action-row/result.json)
- **studio-ui.rail.badge-count** (ui, S) via `wicked-studio:e2e/desk_home_test.py` `ONE COUNT` at e2e-fixture
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 1 not observed, of 3
  - the oracle is partial: int([data-testid=desk-rail-badge].innerText) == count of decision+failure rows in [data-testid=desk-inbox-list]; equals number in watchtower-sentence; check 2 not observed; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_home/api-transcript.json) · [event-log](scenarios/wicked-studio-journeys/pw/desk_home/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_home/shots/001-desk-home.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_home/shots/002-desk-home-away.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_home/shots/003-final-ctx1-page0.png) · [trace](scenarios/wicked-studio-journeys/pw/desk_home/trace/ctx-1.zip) · [video](scenarios/wicked-studio-journeys/pw/desk_home/video/page@d90474f58b34f0883cbff0153fbb98c7.webm) · [result](studio-ui.rail.badge-count/result.json)
- **studio-ui.rail.health-heart** (ui, S) via `wicked-studio:e2e/desk_rail_test.py` at e2e-fixture
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 2
  - the oracle is partial: [data-testid=rail-health-state] text; after click location.pathname=='/health' and [data-testid=health-page] visible; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_rail/api-transcript.json) · [event-log](scenarios/wicked-studio-journeys/pw/desk_rail/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_rail/shots/001-desk-rail.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_rail/shots/002-desk-rail-new-project.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_rail/shots/003-desk-rail-general.png) · [screenshot 4](scenarios/wicked-studio-journeys/pw/desk_rail/shots/004-rail-polish-rail-1440x700-light.png) · [screenshot 5](scenarios/wicked-studio-journeys/pw/desk_rail/shots/005-rail-polish-rail-1440x700-dark.png) · [screenshot 6](scenarios/wicked-studio-journeys/pw/desk_rail/shots/006-rail-polish-rail-390x844-light.png) · [trace](scenarios/wicked-studio-journeys/pw/desk_rail/trace/ctx-1.zip) · [video](scenarios/wicked-studio-journeys/pw/desk_rail/video/page@175edecb584cb3cf95669b055b47a8c2.webm) · [result](studio-ui.rail.health-heart/result.json)
- **studio-ui.rail.order** (ui, S) via `wicked-studio:e2e/desk_rail_test.py` `ORDER` at e2e-fixture
  - checks: 3 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 3
  - the oracle is partial: DOM order of rail link texts equals the list in desk_rail_test ORDER; absence of links to /repos,/rules,/testing,/agents in rail; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_rail/api-transcript.json) · [event-log](scenarios/wicked-studio-journeys/pw/desk_rail/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_rail/shots/001-desk-rail.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_rail/shots/002-desk-rail-new-project.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_rail/shots/003-desk-rail-general.png) · [screenshot 4](scenarios/wicked-studio-journeys/pw/desk_rail/shots/004-rail-polish-rail-1440x700-light.png) · [screenshot 5](scenarios/wicked-studio-journeys/pw/desk_rail/shots/005-rail-polish-rail-1440x700-dark.png) · [screenshot 6](scenarios/wicked-studio-journeys/pw/desk_rail/shots/006-rail-polish-rail-390x844-light.png) · [trace](scenarios/wicked-studio-journeys/pw/desk_rail/trace/ctx-1.zip) · [video](scenarios/wicked-studio-journeys/pw/desk_rail/video/page@175edecb584cb3cf95669b055b47a8c2.webm) · [result](studio-ui.rail.order/result.json)
- **studio-ui.rail.sessions-open** (ui, S) via `wicked-studio:e2e/desk_session_test.py` `GROUPED BY CHAT` at e2e-fixture
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 2
  - the oracle is partial: location.pathname=='/s/chat-pay'; count([data-testid=session-run])==2; r-solo is its own rail-session 'run:r-solo'; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_session/api-transcript.json) · [event-log](scenarios/wicked-studio-journeys/pw/desk_session/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_session/shots/001-desk-session.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_session/shots/002-desk-session-closed.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_session/shots/003-final-ctx1-page0.png) · [trace](scenarios/wicked-studio-journeys/pw/desk_session/trace/ctx-1.zip) · [video](scenarios/wicked-studio-journeys/pw/desk_session/video/page@fb3d5eef230bc7c8c860edf5df2a34b6.webm) · [result](studio-ui.rail.sessions-open/result.json)
- **studio-ui.rail.site-name** (ui, S) via `wicked-studio:e2e/desk_settings_honest_test.py` `#512` at e2e-fixture
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 2
  - the oracle is partial: [data-testid=desk-rail-brand] innerText matches saved name; PUT /api/v1/settings body carries the name; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_settings_honest/api-transcript.json) · [event-log 1](studio-ui.rail.site-name/event-log.json) · [event-log 2](scenarios/wicked-studio-journeys/pw/desk_settings_honest/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_settings_honest/shots/001-desk-settings-honest-site-name.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_settings_honest/shots/002-final-ctx1-page0.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_settings_honest/shots/003-desk-settings-honest-notif-blocked.png) · [screenshot 4](scenarios/wicked-studio-journeys/pw/desk_settings_honest/shots/004-final-ctx2-page0.png) · [screenshot 5](scenarios/wicked-studio-journeys/pw/desk_settings_honest/shots/005-desk-settings-honest-notif-dismissed.png) · [screenshot 6](scenarios/wicked-studio-journeys/pw/desk_settings_honest/shots/006-final-ctx3-page0.png) · [trace 1](scenarios/wicked-studio-journeys/pw/desk_settings_honest/trace/ctx-1.zip) · [trace 2](scenarios/wicked-studio-journeys/pw/desk_settings_honest/trace/ctx-2.zip) · [trace 3](scenarios/wicked-studio-journeys/pw/desk_settings_honest/trace/ctx-3.zip) · [trace 4](scenarios/wicked-studio-journeys/pw/desk_settings_honest/trace/ctx-4.zip) · [trace 5](scenarios/wicked-studio-journeys/pw/desk_settings_honest/trace/ctx-5.zip) · [video 1](scenarios/wicked-studio-journeys/pw/desk_settings_honest/video/page@2f159a07a62acd1c0c470e9c5a345767.webm) · [video 2](scenarios/wicked-studio-journeys/pw/desk_settings_honest/video/page@50c54c749520d5107810da1e4dc34a52.webm) · [video 3](scenarios/wicked-studio-journeys/pw/desk_settings_honest/video/page@56dd5e69d33c69d932dd69820bc8dff7.webm) · [video 4](scenarios/wicked-studio-journeys/pw/desk_settings_honest/video/page@7f17f3788fce58fbd68b2f5837fee3e3.webm) · [video 5](scenarios/wicked-studio-journeys/pw/desk_settings_honest/video/page@f3a351bca8031fa6398a9fdb9a458620.webm) · [result](studio-ui.rail.site-name/result.json)
- **studio-ui.shell.desk-loads** (ui, S) via `wicked-studio:e2e/desk_home_test.py` `SHELL` at e2e-fixture
  - checks: 2 held, 0 contradicted, 0 unsatisfied on the transcript, 0 not observed, of 2
  - the oracle is partial: DOM: document.querySelector('[data-shell=desk]') present; [data-testid=desk] data-tab=='work'; rail boundingBox.width==236; 0 pageerror events; fidelity e2e-fixture is not certification (needs e2e-live or e2e-hermetic)
  - [api-transcript](scenarios/wicked-studio-journeys/pw/desk_home/api-transcript.json) · [event-log](scenarios/wicked-studio-journeys/pw/desk_home/network-events.json) · [screenshot 1](scenarios/wicked-studio-journeys/pw/desk_home/shots/001-desk-home.png) · [screenshot 2](scenarios/wicked-studio-journeys/pw/desk_home/shots/002-desk-home-away.png) · [screenshot 3](scenarios/wicked-studio-journeys/pw/desk_home/shots/003-final-ctx1-page0.png) · [trace](scenarios/wicked-studio-journeys/pw/desk_home/trace/ctx-1.zip) · [video](scenarios/wicked-studio-journeys/pw/desk_home/video/page@d90474f58b34f0883cbff0153fbb98c7.webm) · [result](studio-ui.shell.desk-loads/result.json)

## skipped (1)

- **studio-ui.rail.group-fold** (ui, S)
  - skipped: adapter:none (no adapter runs its scenarios (wicked-studio unit) on the fixture target)
  - [result](studio-ui.rail.group-fold/result.json)

