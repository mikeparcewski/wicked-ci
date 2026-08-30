---
id: ci-fixture
title: rules-conformance selftest fixture (valid corpus)
status: active
date: 2026-08-29
enforcement_class: policy
domain: ci-fixture
confidence: 1.0
---

# rules-conformance selftest fixture — valid corpus

A minimal, well-formed rules doc in the wicked-governance MarkdownAdapter convention. The
selftest workflow ingests THIS directory and asserts the recall report cites the two rule ids
below plus their wiki URIs (`<doc path>@<git blob sha>#<RULE-ID>`). Editing this file changes its
blob sha — the URIs in the report move with it by design (that is what makes them citable).

## Rules

- `POL-9001` (critical): The selftest's critical rule — must sort FIRST in the severity-ordered
  report (critical before warn).
- `PAT-9002` (warn): The selftest's warn-severity pattern rule — must sort AFTER the critical one.
