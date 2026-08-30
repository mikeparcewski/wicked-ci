---
id: ci-fixture-violation
title: rules-conformance selftest fixture (a doc that violates the convention)
status: active
domain: ci-fixture
---

# rules-conformance selftest fixture — the violation

This doc opens with a frontmatter fence, so the MarkdownAdapter CLAIMS it — and its Rules section
below is deliberately malformed (`fatal` is not in the severity vocabulary
`info|warn|error|critical`). Ingest fails LOUD with this file's path and the reason; the
selftest asserts the seam reports that as a finding in the PR comment while the job stays green
(v1 never blocks).

## Rules

- `POL-9101` (fatal): This severity does not exist — the ingest must refuse the corpus.
