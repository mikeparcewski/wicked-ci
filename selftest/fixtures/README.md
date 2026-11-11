# Fixtures

Everything a step or a journey works on. Each is **data**: a step copies a fixture into its run root (or `git init`s
it there with a fixed author and dates, as `lib/corpus.mjs` does for `corpus/`), and nothing runs from this directory.

| Path | What | Used by | From |
|---|---|---|---|
| `corpus/` | the add.js bug repo (`add()` returns `a - b`); its tests fail on the base | S03, S04, S11, U03–U07 | wicked-smoke |
| `repos/hello-onboard/` | a two-file repo for "Add a repository" | (onboarding journeys) | the :7721 rig, lane e2e-1104 |
| `repos/hello/` | `greet(name)` with a test | (onboarding, MCP inspect) | the :7721 rig, lane e2e-1105 (`hello-1105`) |
| `repos/tiny-math-untested/` | `clamp()` is wrong and untested, so the suite passes on the bug (DES-RULE-CHECK-001) | (J4/J5 rule-check journeys) | the :7721 rig, lane apps-k5-chat |
| `repos/reqgraph-tm/` | tiny-math for the requirements graph | (reqgraph journeys) | lane reqgraph-validate |
| `mcp/echo-mcp.py` | a minimal stdio MCP server (`echo`, `note_add`) | (U08: `/workflow-mcp-server` install, MCP inspect) | the :7721 rig, lane e2e-1105 |
| `docs/` | Chat-journey documents (an RFP, a company profile and financials, facts; `.txt` and `.pdf`) | (chat-with-documents journeys) | the :7721 rig, lane e2e-1105 (`cj/`) |

The repos are `git archive HEAD` exports of the rig's fixture checkouts (tracked files only; no `.git`, no rig
worktrees). `echo-mcp.py`'s `note_add` writes beside the script: copy it into the run root before starting it. The
PDFs carry no author metadata (checked); `selfcheck` refuses a home path in any fixture.
