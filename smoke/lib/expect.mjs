// The EXPECTED-FAIL policy: which acceptance findings the installed versions are KNOWN to still
// exhibit. A check tagged with such a finding that fails is reported EXPECTED-FAIL (not FAIL) and the
// reason is printed — the harness says which finding, and why it is expected on this version. Flip
// or remove a rule when the fix ships; `--no-expect-fail` runs strict; `--expect-fail F-…` adds one.
//
// Keyed to the REAL fix versions (verified against the published CHANGELOGs, 2026-09-14):
//   crew 0.7.34 (npm latest; pins core-ts ^0.7.25, bus ^2.3.4, studio ^0.5.9) — state-home preflight
//   409 (#555), BASE skill warn-first (#557), distinctnessFallback + NoEligibleSeat 409 (#558);
//   crew 0.7.33 — F-E2E-021 root cause (#541) + visibility (#542), the `deliverGate` wire (#543).
//   core-ts 0.7.25 — the ballot LEDGER fix (wicked-core #473, bench-on-abstention: a dead-class ballot
//   corroborated by the dispatcher's abstention benches the seat) closes F-7R2-006 / F-7R3-001; every
//   denial now PAUSES at an `escalation` gate (#477) and the creator owes the repo-checks floor (#476)
//   — which changes the SHAPE of F-SMOKE-001 on Linux (see its rule), not its presence.
//   core-ts 0.7.24 — the ENGINE deliver gate (F-E2E-030), floor provisioning (F-E2E-029a),
//   `awaitingHuman.gateKind`.
import { gte, lt } from './semver.mjs';

/** A deliberately unreachable version bound: "expected on every version published so far". */
export const NOT_FIXED_YET = '0.7.99';

/**
 * Built-in rules, evaluated against the INSTALLED versions.
 * Each returns a reason string (expected on this version) or null (must pass).
 */
const RULES = {
  // F-RC1-044 (crew #551): with no daemon answering, `wicked-crew status` printed the whole
  // `TypeError: fetch failed … ECONNREFUSED` stack through main().catch, and a non-2xx body as JSON
  // with exit 0. FIXED in crew 0.7.35 (`daemonFetch`: one remedy line, exit 1) — S10 asserts it
  // against the daemon it has just stopped. Labelled to the fix version BEFORE 0.7.35 publishes
  // (FIX-IT-ALL L10-7), so the rehearsal on 0.7.34 reads EXPECTED-FAIL and the fixed set must PASS.
  'F-RC1-044': ({ crew }) => (crew && lt(crew, '0.7.35') ? `crew ${crew} < 0.7.35 — \`wicked-crew status\` with the daemon down prints a fetch-failed stack trace instead of one remedy line (fixed in crew 0.7.35)` : null),
  // F-003 (crew #493): `wicked-crew --version` answered "Unknown command". FIXED in crew 0.7.35 (three
  // lines for THIS install: crew, wicked-core-ts, bundled studio) — S09 compares them to the tree.
  'F-003': ({ crew }) => (crew && lt(crew, '0.7.35') ? `crew ${crew} < 0.7.35 — \`wicked-crew --version\` answers "Unknown command" (fixed in crew 0.7.35)` : null),
  // F-E2E-021: two SQLite libraries on one WAL bus db (node:sqlite read in projects/activity) → the
  // daemon's six subscribers die "database disk image is malformed"; recentErrors stays empty.
  // FIXED in crew 0.7.33 (#541 one library per db file per process; #542 connection-fatal bus errors
  // reach /diagnostics.recentErrors) — S05 must PASS from 0.7.33 on. On < 0.7.33 the race is
  // TIMING-DEPENDENT in the product: it fired on 12 of 13 loops observed (locally and on every hosted
  // runner) and stayed clean once (selftest 34748757134, previous-set leg) — FLAKY, so a clean loop on
  // 0.7.32 is disclosed, never a verdict; the retire bound is the fix version, not that run.
  'F-E2E-021': ({ crew }) => (lt(crew, '0.7.33') ? `crew ${crew} < 0.7.33 — bus WAL loop after GET /projects/:id/activity + external emit, silent in /diagnostics.recentErrors (fixed in 0.7.33: crew#541 + #542)` : null),
  // F-E2E-012: a tool-only run (onboarding) keeps `wicked/<run-id>` + a full worktree in the
  // customer's clone. STILL PRESENT on 0.7.33 and documented as retention BY DESIGN (F-7R2-013);
  // the harness asserts the customer-visible behaviour and labels it — remove this rule when the
  // product stops minting a branch/worktree for tool-only workflows.
  'F-E2E-012': () => 'tool-only onboarding keeps its wicked/<run-id> branch + worktree (retention by design, F-7R2-013) — flip when the product changes',
  // F-E2E-002: a publish that lands with warnings shows `skills.findings: []` in /diagnostics — the
  // warnings live only in the daemon log. Open on every crew published so far (the 0.7.33 CHANGELOG
  // carries no fix; an earlier bound of 0.7.33 here was a guess and would have flipped this check to a
  // hard FAIL the day 0.7.33 landed) — replace the placeholder bound with the real fix version.
  'F-E2E-002': ({ crew }) => (crew && !gte(crew, NOT_FIXED_YET) ? `crew ${crew}: publish warnings are dropped from /diagnostics.skills.findings (open — no fix version yet)` : null),
  // F-E2E-030: `deliver: pr` under the default `humanConfirm: before:1` posture pushed + opened the PR
  // with no human gate before the push. The gate landed in the ENGINE — core-ts 0.7.24 (`should_pause`
  // pauses before a Tool unit whose phase id is `deliver`, whatever the run-level human_confirm says),
  // so the rule is keyed to the installed addon, not to crew. crew 0.7.33 adds the WIRE around it
  // (`deliverGate` on POST /runs, `GET /health.capabilities.deliverGate`) — S04 asserts that wire
  // separately and untagged whenever crew ≥ 0.7.33 is installed.
  'F-E2E-030': ({ coreTs }) => (coreTs && lt(coreTs, '0.7.24') ? `core-ts ${coreTs} < 0.7.24 — no human gate before the deliver push under the default posture (fixed in the engine at 0.7.24; crew 0.7.33 adds the deliverGate wire)` : null),
  // F-7R2-006 / F-7R3-001 — the F-SMOKE-002 residual, OBSERVED BY wicked-smoke on core-ts 0.7.23 AND
  // 0.7.24 (crew 0.7.32 and 0.7.33): codex failed every round-1 ballot `not_logged_in` and copilot
  // `quota_exhausted` (both classified on `councilSeatFailed.reason`), the dispatcher's own bench then
  // answered round 2 with `benched`, and the distribution's ballot LEDGER benched neither —
  // `degradedReason` named only the launcher-benched seat and `evaluator_distinct` seated the review
  // units on the signed-out codex. FIXED in core-ts 0.7.25 — wicked-core #473 (S5 bench-on-abstention:
  // a dead-class ballot corroborated by the dispatcher's own abstention benches the seat for the run;
  // the evaluator≠creator fallback is disclosed as `unitDistributed.distinctnessFallback`). Observed
  // by wicked-smoke run 34798471429 (crew 0.7.34 / core-ts 0.7.25, ubuntu AND macos): codex and copilot
  // benched and NAMED in degradedReason, no unit routed to a dead seat — all three checks passed on
  // both legs, so the placeholder bound moved to the real fix version the same day.
  'F-7R2-006': ({ coreTs }) => (coreTs && lt(coreTs, '0.7.25') ? `core-ts ${coreTs} < 0.7.25 — the ballot ledger does not bench a seat whose dead-class failure was on round 1 and whose round-2 outcome is the dispatcher's own bench — degradedReason omits it (F-SMOKE-002 residual; fixed in core-ts 0.7.25, wicked-core#473)` : null),
  'F-7R3-001': ({ coreTs }) => (coreTs && lt(coreTs, '0.7.25') ? `core-ts ${coreTs} < 0.7.25 — evaluator_distinct seats the review unit / judge on a seat that failed every ballot (not benched by the ledger, see F-7R2-006 / F-SMOKE-002) — the smoke reassigns to a live seat and continues (fixed in core-ts 0.7.25, wicked-core#473)` : null),
  // F-SMOKE-003 — OBSERVED BY wicked-smoke (2026-09-12): `session.delivery` reads `stranded` for a run
  // whose branch IS on the local origin and whose PR WAS opened through the gh shim. crew derives
  // `delivered` from a `run.delivered` trail entry it records by grepping the deliver transcript for
  // the PR URL (`delivery-index.ts prUrlFrom`); the transcript carries one `deliver: EXCLUDED
  // (scratch-dir): …` line per file the checks floor left under the worktree scratch — npm logs and
  // node's on-disk compile cache (node ≥ 22 writes one; node 24 and 26 both observed) — and whether the
  // URL survives whatever caps the transcript on its way to the index varies with that count. The CI
  // evidence of 2026-09-12 22:11Z (run 34722047107) shows BOTH readings on node 24 with byte-identical
  // transcript heads: core-ts 0.7.24 read `delivered`, core-ts 0.7.23 read `stranded`; the run before
  // read the reverse. Hence: keyed to crew only (no fix version yet), on every node and every engine,
  // and declared FLAKY — a `delivered` reading is disclosed, never a verdict. The harness classifies
  // delivery from the bare origin first and labels the product's disagreeing wire value with this id.
  'F-SMOKE-003': ({ crew }) => (crew && !gte(crew, NOT_FIXED_YET) ? `crew ${crew}: session.delivery reads 'stranded' while the branch is on the origin and the PR was opened — the wire disagrees with the artifact (deliver-transcript URL behind a variable number of EXCLUDED lines; open — no fix version yet; both readings observed on identical inputs)` : null),
  // F-087 — `GET /runs/:id/diff` is not robust to what the worktree holds. Acceptance: a half-reaped
  // worktree → 500. OBSERVED BY wicked-smoke (2026-09-12, node 26 hosts): on a COMPLETED run the
  // route shells `git diff --no-index -- /dev/null <untracked>` per untracked file and answers 500
  // ("Command failed: git diff … tmp/wicked-checks/tmp/node-compile-cache/…") on the checks' compile
  // cache under the worktree scratch. Every node 24 runner (CI, 2026-09-12) answered 200 with the same
  // cache present, so the trigger is keyed to the host node major as well — and on node 26 itself the
  // route answered 500 on two runs (the independent review's) and 200 on the third (wicked-smoke run
  // (a), 2026-09-13, crew 0.7.32), so the finding is FLAKY: a 200 is disclosed, never a verdict.
  // No crew fix version yet.
  'F-087': ({ crew, nodeMajor }) => (crew && !gte(crew, NOT_FIXED_YET) && (nodeMajor ?? 0) >= 26 ? `crew ${crew} on node ${nodeMajor}: GET /runs/:id/diff answers 500 on a completed run whose worktree scratch holds the checks' node compile cache (git diff --no-index fails per untracked file) — open, no fix version yet` : null),
  // F-SMOKE-001 — Linux only: the fix unit's floors fail inside the engine's `bwrap` sandbox although
  // the judge PASSED and the worker's `src/add.js` write succeeded. core-ts 0.7.23 / 0.7.24: the pinned
  // evidence floor (`git status --porcelain | grep -q . || git log …`, run inside the validator sandbox)
  // denies "no coverage report was produced … the script denied before writing one" and the run ENDS.
  // core-ts 0.7.25 (wicked-smoke run 34798471429, ubuntu-latest, crew 0.7.34): the creator floor (#476)
  // runs first and its `install` check exits 1 inside the checks sandbox (`repoChecksEvaluated.outcome:
  // 'failed'`), the pinned validator then denies with the same signature prefixed "the run left a change
  // in its worktree (done is re-derived from the diff, never asserted)", and #477 PARKS the run at an
  // `escalation` gate (`gateEscalated.condition: 'floor_failed'`, source `pinned_validator`) that S04
  // cancels. Deterministic on ubuntu-latest (every selftest run, three root layouts, core-ts 0.7.23,
  // 0.7.24 and 0.7.25), absent on macOS with byte-identical inputs; confirmed by the independent review
  // as a core-ts finding. The pipeline half cannot proceed past `fix` there; its checks are tagged with
  // this finding ONLY when the fix unit's denial carries that signature (S04 `floorDenied` /
  // `floorEscalation`). No fix version yet.
  'F-SMOKE-001': ({ coreTs, platform }) => (platform === 'linux' && coreTs && !gte(coreTs, NOT_FIXED_YET) ? `core-ts ${coreTs} on linux: the fix unit's floors fail inside the bwrap sandbox — the pinned evidence floor denies ("no coverage report was produced … the script denied before writing one"; on ≥ 0.7.25 prefixed "the run left a change in its worktree", after the creator floor's install exited 1, and the denial pauses at an escalation gate the smoke cancels) — open, no fix version yet` : null),
};

/**
 * Findings whose expected failure is TIMING-DEPENDENT in the product itself: the class fails
 * deterministically on an unloaded runner (every CI leg, the independent review) but has been seen to
 * pass under heavy host load — for F-7R2-006 / F-7R3-001 the ballot ledger DOES bench a dead seat
 * when its later (probation) ballot rounds also fail, which a slow host makes likely; for F-SMOKE-003
 * the PR URL sometimes survives the transcript cap (both readings on identical inputs, see the rule);
 * for F-087 the diff route answered 500 on two node-26 runs and 200 on the third; for F-E2E-021 the
 * WAL race stayed clean on 1 of 13 loops on crew 0.7.32.
 * An unexpected PASS on a flaky finding is still printed and recorded (`unexpectedPasses[].flaky:
 * true`) but does not fail the run: it is disclosure of a flake, not a stale label. Retire the flag
 * with the label. The flag matters only while the finding's rule is ACTIVE for the installed
 * versions: F-7R2-006 / F-7R3-001 stay listed for the sets their rule still covers (core-ts <
 * 0.7.25, where the ledger flake is real); on core-ts ≥ 0.7.25 the rule is off and the checks are
 * plain PASS / FAIL.
 */
const FLAKY = new Set(['F-7R2-006', 'F-7R3-001', 'F-SMOKE-003', 'F-087', 'F-E2E-021']);

export class ExpectPolicy {
  constructor(versions, { extra = [], disabled = false } = {}) {
    this.versions = versions;
    this.disabled = disabled;
    this.extra = new Set(extra);
  }

  /** The reason a failing check tagged `finding` is expected — or null when it must pass. */
  reasonFor(finding) {
    if (this.disabled) return null;
    if (this.extra.has(finding)) return `listed in --expect-fail`;
    const rule = RULES[finding];
    return rule ? rule(this.versions) : null;
  }

  /** Whether an unexpected pass on `finding` is a known timing flake rather than a stale label. */
  isFlaky(finding) {
    return !this.disabled && FLAKY.has(finding);
  }

  /** For the report: every active rule. */
  active() {
    const out = {};
    if (this.disabled) return out;
    for (const [f, rule] of Object.entries(RULES)) {
      const r = rule(this.versions);
      if (r) out[f] = r;
    }
    for (const f of this.extra) out[f] = 'listed in --expect-fail';
    return out;
  }
}
