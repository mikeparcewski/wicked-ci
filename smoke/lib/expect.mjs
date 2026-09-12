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
  // F-E2E-030: `deliver: pr` under the default `humanConfirm: before:1` posture pushes + opens the PR
  // with no human gate before the push. Present on 0.7.32.
  'F-E2E-030': ({ crew }) => (lt(crew, '0.7.33') ? `crew ${crew} < 0.7.33 — no human gate before the deliver push under the default posture` : null),
  // F-7R2-006 / F-7R3-001 — OBSERVED BY wicked-smoke on core-ts 0.7.23 + crew 0.7.32 (2026-09-12,
  // three of four runs): codex failed every round-1 ballot `not_logged_in` and copilot
  // `quota_exhausted` (both classified on `councilSeatFailed.reason`), the dispatcher's own bench
  // then answered round 2 with `benched`, and the distribution's ballot LEDGER benched neither —
  // `degradedReason` named only the launcher-benched seat and `evaluator_distinct` seated the review
  // units on the signed-out codex (the run escalated "triage judge failed: (cli `codex` exited 1)
  // Not logged in"). The ledger fires only when a seat fails a later (probation) round. No fixed
  // core-ts version known yet — remove these two rules when one ships.
  'F-7R2-006': ({ coreTs }) => (coreTs && !gte(coreTs, '0.7.24') ? `core-ts ${coreTs}: the ballot ledger does not bench a seat whose dead-class failure was on round 1 and whose round-2 outcome is the dispatcher's own bench — degradedReason omits it (observed by wicked-smoke)` : null),
  'F-7R3-001': ({ coreTs }) => (coreTs && !gte(coreTs, '0.7.24') ? `core-ts ${coreTs}: evaluator_distinct seats the review unit on a seat that failed every ballot (not benched by the ledger, see F-7R2-006) — the smoke reassigns it to a live seat and continues (observed by wicked-smoke)` : null),
};

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
