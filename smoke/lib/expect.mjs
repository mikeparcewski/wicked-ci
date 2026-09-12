// The EXPECTED-FAIL policy: which acceptance findings the installed versions are KNOWN to still
// exhibit. A check tagged with such a finding that fails is reported EXPECTED-FAIL (not FAIL) and the
// reason is printed — the harness says which finding, and why it is expected on this version. Flip
// or remove a rule when the fix ships; `--no-expect-fail` runs strict; `--expect-fail F-…` adds one.
import { gte, lt } from './semver.mjs';

/**
 * Built-in rules, evaluated against the INSTALLED versions.
 * Each returns a reason string (expected on this version) or null (must pass).
 */
const RULES = {
  // F-E2E-021: two SQLite libraries on one WAL bus db (node:sqlite read in projects/activity) → the
  // daemon's six subscribers die "database disk image is malformed"; recentErrors stays empty.
  'F-E2E-021': ({ crew }) => (lt(crew, '0.7.33') ? `crew ${crew} < 0.7.33 — bus WAL loop after GET /projects/:id/activity + external emit, silent in /diagnostics.recentErrors` : null),
  // F-E2E-012: a tool-only run (onboarding) keeps `wicked/<run-id>` + a full worktree in the
  // customer's clone. STILL PRESENT on 0.7.32 and documented as retention BY DESIGN (F-7R2-013);
  // the harness asserts the customer-visible behaviour and labels it — remove this rule when the
  // product stops minting a branch/worktree for tool-only workflows.
  'F-E2E-012': () => 'tool-only onboarding keeps its wicked/<run-id> branch + worktree (retention by design, F-7R2-013) — flip when the product changes',
  // F-E2E-002: a publish that lands with warnings shows `skills.findings: []` in /diagnostics — the
  // warnings live only in the daemon log. Open on 0.7.32 (no fixed version known yet).
  'F-E2E-002': ({ crew }) => (lt(crew, '0.7.33') ? `crew ${crew}: publish warnings are dropped from /diagnostics.skills.findings` : null),
  // F-E2E-030: `deliver: pr` under the default `humanConfirm: before:1` posture pushed + opened the PR
  // with no human gate before the push. The gate landed in the ENGINE — core-ts 0.7.24 (`should_pause`
  // pauses before a Tool unit whose phase id is `deliver`, whatever the run-level human_confirm says),
  // so the rule is keyed to the installed addon, not to crew.
  'F-E2E-030': ({ coreTs }) => (coreTs && lt(coreTs, '0.7.24') ? `core-ts ${coreTs} < 0.7.24 — no human gate before the deliver push under the default posture` : null),
  // F-7R2-006 / F-7R3-001 — OBSERVED BY wicked-smoke on core-ts 0.7.23 AND 0.7.24 + crew 0.7.32
  // (2026-09-12): codex failed every round-1 ballot `not_logged_in` and copilot `quota_exhausted`
  // (both classified on `councilSeatFailed.reason`), the dispatcher's own bench then answered round 2
  // with `benched`, and the distribution's ballot LEDGER benched neither — `degradedReason` named only
  // the launcher-benched seat and `evaluator_distinct` seated the review units on the signed-out codex
  // (the run escalated "triage judge failed: (cli `codex` exited 1) Not logged in"). The ledger fires
  // only when a seat fails a later (probation) round. NO FIXED VERSION EXISTS YET (0.7.24 ships the
  // deliver gate and floor provisioning only): the bound below is a deliberately unreachable
  // placeholder — replace it with the real fix version when core ships one, and the UNEXPECTED-PASS
  // surfacing in report.mjs will say so the moment the product starts passing.
  'F-7R2-006': ({ coreTs }) => (coreTs && !gte(coreTs, NOT_FIXED_YET) ? `core-ts ${coreTs}: the ballot ledger does not bench a seat whose dead-class failure was on round 1 and whose round-2 outcome is the dispatcher's own bench — degradedReason omits it (open — no fix version yet; observed by wicked-smoke on 0.7.23 and 0.7.24)` : null),
  'F-7R3-001': ({ coreTs }) => (coreTs && !gte(coreTs, NOT_FIXED_YET) ? `core-ts ${coreTs}: evaluator_distinct seats the review unit / judge on a seat that failed every ballot (not benched by the ledger, see F-7R2-006) — the smoke reassigns to a live seat and continues (open — no fix version yet)` : null),
  // F-SMOKE-003 — OBSERVED BY wicked-smoke (2026-09-12, node ≥ 24 hosts): the deliver phase's unit
  // output is capped, and hundreds of `EXCLUDED (scratch-dir): …node-compile-cache/…` lines push the
  // PR URL past the cap, so `delivery-index` reads `stranded` for a run whose branch IS on the origin
  // and whose PR WAS opened. The harness classifies delivery from the bare origin first and labels the
  // product's disagreeing wire value with this finding. No crew fix version yet.
  // Both F-SMOKE-003 and F-087 are TRIGGERED by node's on-disk compile cache landing in the checks'
  // scratch under the worktree — node ≥ 26 on the host that runs the checks (the runner's node, the
  // one the harness itself runs on). On node 24 runners neither reproduces (CI macOS 2026-09-12), so
  // the rules are keyed to the host node major as well as the product version.
  // F-SMOKE-003 has TWO triggers observed: node ≥ 26 on any engine (the compile-cache EXCLUDED lines
  // push the URL past the cap), and core-ts ≥ 0.7.24 on any node (CI macOS node 24 + 0.7.24 read
  // `stranded` with the branch on the origin and the PR opened; the same runner on 0.7.23 read
  // `delivered`) — the engine's 0.7.24 deliver-phase changes altered what crew's delivery-index sees.
  'F-SMOKE-003': ({ crew, coreTs, nodeMajor }) => (crew && !gte(crew, NOT_FIXED_YET) && ((nodeMajor ?? 0) >= 26 || (coreTs && gte(coreTs, '0.7.24'))) ? `crew ${crew} (core-ts ${coreTs}, node ${nodeMajor}): session.delivery reads 'stranded' while the branch is on the origin and the PR was opened — the wire disagrees with the artifact (open — no fix version yet)` : null),
  // F-087 — `GET /runs/:id/diff` is not robust to what the worktree holds. Acceptance: a half-reaped
  // worktree → 500. OBSERVED BY wicked-smoke (2026-09-12, node 26 hosts): on a COMPLETED run the
  // route shells `git diff --no-index -- /dev/null <untracked>` per untracked file and answers 500
  // ("Command failed: git diff … tmp/wicked-checks/tmp/node-compile-cache/…") on the checks' compile
  // cache under the worktree scratch. No crew fix version yet.
  'F-087': ({ crew, nodeMajor }) => (crew && !gte(crew, NOT_FIXED_YET) && (nodeMajor ?? 0) >= 26 ? `crew ${crew} on node ${nodeMajor}: GET /runs/:id/diff answers 500 on a completed run whose worktree scratch holds the checks' node compile cache (git diff --no-index fails per untracked file) — open, no fix version yet` : null),
  // F-SMOKE-001 — Linux only: the pinned evidence floor (`git status --porcelain | grep -q . || git
  // log …`, run inside the engine's `bwrap --ro-bind / / … --bind <worktree>` validator sandbox)
  // denies the `fix` unit "no coverage report was produced … the script denied before writing one"
  // although the judge PASSED and the worker's `src/add.js` write succeeded. Deterministic on
  // ubuntu-latest (every selftest run, three root layouts, core-ts 0.7.23 and 0.7.24), absent on macOS
  // with byte-identical inputs; confirmed by the independent review as a core-ts finding. The
  // pipeline half cannot proceed past `fix` there; its checks are tagged with this finding ONLY when
  // the fix unit's denial carries that signature. No fix version yet.
  'F-SMOKE-001': ({ coreTs, platform }) => (platform === 'linux' && coreTs && !gte(coreTs, NOT_FIXED_YET) ? `core-ts ${coreTs} on linux: the pinned evidence floor denies the fix unit inside the bwrap validator sandbox ("no coverage report was produced … the script denied before writing one") — open, no fix version yet` : null),
};

/** A deliberately unreachable version bound: "expected on every version published so far". */
export const NOT_FIXED_YET = '0.7.99';

/**
 * Findings whose expected failure is TIMING-DEPENDENT in the product itself: the class fails
 * deterministically on an unloaded runner (every CI leg, the independent review) but has been seen to
 * pass under heavy host load — for F-7R2-006 / F-7R3-001 the ballot ledger DOES bench a dead seat
 * when its later (probation) ballot rounds also fail, which a slow host makes likely. An unexpected
 * PASS on a flaky finding is still printed and recorded (`unexpectedPasses[].flaky: true`) but does
 * not fail the run: it is disclosure of a flake, not a stale label. Retire the flag with the label.
 */
const FLAKY = new Set(['F-7R2-006', 'F-7R3-001']);

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
