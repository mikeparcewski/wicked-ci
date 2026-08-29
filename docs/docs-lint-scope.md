# Docs-lint scope — retired-name rule (DT-22 → DT-21)

**Status:** convention definition, committed ahead of the lint (DT-21, per
recon-2026-08 docs-R25). The 2026-08 marker pass (DT-22) annotated every
legitimate historical mention across the live repos against exactly this
definition, so the lint starts green on first enable.

**Retired names:** `wicked-testing` (retired 2026-08, Phase 6),
`wicked-brain` (retired 2026-08, Phase 5-S7), `wicked-signals`
(archived 2026-07). A retired name in a live doc is a defect **unless** it is
marker-annotated (§2) or exempt (§3, §4).

## 1. What the lint matches

Content only — filenames are never matched (e.g.
`examples/wicked-testing.release.yml` is a legal filename; its *content*
carries a marker). One regex, applied per line:

```
(^|[^.\w-])wicked-(testing|brain|signals)(?!://)\b
```

Deliberate exclusions built into the pattern (these are **live contracts**,
not narrative, and need no marker):

- **Dot-path store roots** — `.wicked-testing/` (legacy QE evidence root,
  still dual-read by wicked-ledger) and `~/.wicked-brain` (frozen archive,
  never write). The leading `.` fails the lookbehind class.
- **`wicked-brain://` URIs** — source attribution on chunks migrated into
  wicked-estate. The `://` lookahead excludes them.

## 2. Marker convention

A mention is legitimate-historical when its line, block, or file is marked.
Markers are matched as **substrings of a line** (so they work inside existing
block comments, table rows, headings, and code fences).

| Form | Markdown / HTML / Astro template | JS / TS / TSX | CSS | Python / shell / YAML / TOML |
|---|---|---|---|---|
| **Line** (same line as the mention) | `<!-- historical -->` | `// historical` | `/* historical */` | `# historical` |
| **Block open** (marker alone on its line) | `<!-- historical -->` | `// historical` | `/* historical */` | `# historical` |
| **Block close** | `<!-- /historical -->` | `// /historical` | `/* /historical */` | `# /historical` |
| **Whole file** (within the first 15 lines) | `<!-- historical-doc -->` | `// historical-doc` | `/* historical-doc */` | `# historical-doc` |

- An optional reason is allowed after the token: `<!-- historical: v1 sample,
  namespace kept at retirement -->`.
- **Line vs block:** a marker sharing its line with other content exempts
  that line only; a marker alone on its line (ignoring leading comment
  syntax/whitespace) toggles a block until the matching close marker.
- **Whole-file** is for dated point-in-time records that remain useful as
  written (superseded ADRs, dated plans/specs, v1 reference docs). Prefer
  line/block markers in living documents so new drift is still caught.
- Precedent: `wicked-bus/reqs/SPEC.md` (DT-16) and
  `wicked-vault/docs/CONTRACTS.md` already use the `<!-- historical -->`
  block form; this doc standardizes it.

## 3. Path scope — what the lint scans

Per live repo, relative to the repo root:

**Scanned (docs surface):**
- `README.md` and every root-level `*.md` (`CLAUDE.md`, `AGENTS.md`,
  `ARCHITECTURE.md`, `USERS_GUIDE.md`, `CONTRIBUTING.md`, …)
- `packages/*/README.md` — published npm READMEs (the highest-drift surface)
- `docs/**/*.md`
- `reqs/**/*.md`
- `skills/**/*.md`
- `.claude/**/*.md`
- `site/src/**` (site source: `.astro`, `.ts`, `.tsx`, `.js`, `.css`, `.md`)
- `examples/**` (teaching configs, e.g. this repo's release workflows)

**Exempt by path (never scanned):**
- `archived/**` — any path containing an `archived/` segment; likewise the
  lint only runs on live repos, so archived repos (wicked-testing,
  wicked-brain, wicked-signals, wicked-understanding, …) and the retirement
  banners DT-5 keeps in them are out of scope by construction
- `**/CHANGELOG.md` — release history is a record; annotating past entries
  would falsify them
- `**/*MIGRATION*` — migration docs exist to name what they migrated from
- `.product/**` — dated requirements/design/review artifacts (point-in-time
  records)
- `.wicked-testing/**`, `.wicked-qe/**`, `.wicked-vault/**` — evidence/data
  stores (fixtures included, wherever they appear in the tree)
- `scenarios/**` — QE scenario fixtures (test data, not narrative)
- code and test trees: `src/**`, `lib/**`, `bin/**`, `scripts/**`,
  `hooks/**`, `tests/**`, `test/**`, `e2e/**`, `packages/*/src/**`,
  `packages/*/tests/**` — this is a **docs** lint; `site/src/**` is the one
  deliberate exception (site copy is user-facing narrative)
- generated/vendored: `node_modules/**`, `dist/**`, `build/**`, `target/**`,
  lockfiles
- dot-configs (`.gitignore`, `.npmignore`, editor/CI config)

## 4. Declared-exempt content (outside any repo the lint runs in)

- The family workspace root `CLAUDE.md` (the `wicked/` checkout root, not a
  git repo) keeps retired products as **table rows marked 📦 retired** — that
  table is the canonical record of what retired and where it went; exempt.

## 5. Review rule for new marks

A marker asserts "this mention is deliberately historical." Adding one to
*new* text describing a retired product as live is a review reject — fix the
text instead. The marker pass never deletes content: annotate what is
legitimately historical, fix what is wrong.
