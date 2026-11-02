// S11 power-mode bug run — the seeded `bug` workflow launched in POWER MODE, the way crew >= 0.16.11
// runs a repository launch by default (DES-POWER-MODE; wicked-core src/power.rs).
//
// WHY it exists (crew 0.16.12 release smoke, run 41428295027): the default launch became a power run in
// crew 0.16.11, and S04 kept asserting the PHASED bug run (the preset phases, the plan approval, one
// unit per phase). S04 now opts out with `power: false`; this step proves the power path end to end on
// the same corpus and issue:
//   - the launch is a power run (`session.power.on`);
//   - the build unit runs as ONE orchestrator session whose turns end at `CHECKPOINT:` / `HANDOFF:`
//     (the seat shims answer the orchestrator protocol: shims/_lib.mjs `orchestratorTurn` applies the
//     corpus correction and hands off in the same turn), so it hands off before the turn cap;
//   - the hand-off (the composed plan's evaluator steps and the build's floor) passes with no send-back;
//   - the human DELIVER gate still pauses the run before the push, and the run delivers: the run branch
//     on the local bare origin carries `a + b` and the `gh` shim opened the PR.
// It runs right after S04 (the same daemon, roster and corpus; S10's teardown stays last) and needs S03.
import { realpathSync } from 'node:fs';
import { ISSUE_TEXT, branches } from '../corpus.mjs';
import { gitTry } from '../proc.mjs';
import { eventsOfType, phaseOf } from '../runs.mjs';
import { JUDGE_SEAT_KEY } from '../shims.mjs';
import { launchAndFollow, worktreeEvidence } from './S04-bug-run.mjs';

export const id = 'S11';
export const name = 'bug-run (power mode)';

/** wicked-core power.rs MAX_TURNS_DEFAULT: the build attempt's turn cap (the last turn is told to hand off). */
const MAX_TURNS = 12;
/** Hand-off step statuses that are not a failure (crew-api-types HandoffStep.status). */
const HANDOFF_OK = new Set(['passed', 'skipped']);

/**
 * Did the build run as ONE orchestrator session that HANDED OFF? The creator unit's seat is the
 * orchestrator, every turn ran on it, turns are numbered 1..n with no session restart, and the last turn's
 * outcome is a hand-off, before the cap. Missing evidence is a "no" (codex on #61).
 */
export function orchestratorHandedOff(power, units) {
  const orch = power?.orchestrator ?? null;
  const turnLog = Array.isArray(power?.turnLog) ? power.turnLog : null;
  const lastTurn = turnLog?.at(-1) ?? null;
  const buildUnit = typeof orch?.ord === 'number' ? (units ?? []).find((u) => u.ord === orch.ord) ?? null : null;
  // ONE session on ONE seat: the creator unit's seat, every turn on it, turns numbered 1..n, no restart.
  const ok = typeof orch?.cli === 'string' && orch.cli !== '' && buildUnit?.role === 'creator' && buildUnit.assigned_cli === orch.cli
    && orch.sessionRestarts === 0
    && typeof orch.turns === 'number' && orch.turns >= 1 && orch.turns < MAX_TURNS
    && turnLog !== null && turnLog.length === orch.turns && turnLog.every((tl, i) => tl?.turn === i + 1 && tl?.cli === orch.cli)
    && lastTurn?.outcome === 'handoff';
  return { ok, orch, buildUnit, lastTurn };
}

/**
 * Did the hand-off run every step of the composed plan and pass in ONE round? Every row names its step,
 * unit and round; all are round 1; the build's own floor (`checks`) ran on the build unit; every
 * evaluator unit has a row; each (unit, step)'s LAST record (the log keeps `running`, then the result)
 * passed or was skipped. A row without identity, or a missing step, is a "no" (codex on #61).
 */
export function handoffPassed(power, units, buildUnit) {
  const handoff = power?.handoff ?? null;
  const rows = Array.isArray(handoff?.steps) ? handoff.steps : [];
  const rowsValid = rows.length > 0 && rows.every((r) => typeof r?.step === 'string' && r.step !== '' && typeof r.round === 'number' && typeof r.ord === 'number' && typeof r.status === 'string');
  const finalOf = new Map();
  for (const r of rows) finalOf.set(`${r?.ord}/${r?.step}`, r?.status);
  const evaluatorOrds = (units ?? []).filter((u) => u.role === 'evaluator').map((u) => u.ord);
  // The build's own steps (the re-score and its floor) on the build unit, and an EVALUATOR step (not a
  // build step under another ordinal) for every evaluator unit of the composed plan.
  const BUILD_STEPS = ['rescore', 'checks'];
  const missing = [
    ...BUILD_STEPS.filter((st) => !(buildUnit && rows.some((r) => r?.ord === buildUnit.ord && r?.step === st))).map((st) => `${st} on the build unit`),
    ...evaluatorOrds.filter((o) => !rows.some((r) => r?.ord === o && typeof r?.step === 'string' && !BUILD_STEPS.includes(r.step))).map((o) => `an evaluator step for unit ${o}`),
  ];
  const ok = rowsValid && handoff?.round === 1 && rows.every((r) => r.round === 1) && evaluatorOrds.length > 0 && missing.length === 0
    && [...finalOf.values()].every((v) => HANDOFF_OK.has(v));
  return { ok, round: handoff?.round ?? null, finalOf, missing, rowsValid };
}

/** A /health answer the step may interpret: 200 and a JSON object (an array or null is not one). */
export function healthUsable(health) {
  return health?.status === 200 && health.json !== null && typeof health.json === 'object' && !Array.isArray(health.json);
}

/**
 * Was the run paused at its deliver gate BEFORE any push or PR? The pause must name the run branch (the
 * same one the run finally delivers), the branch must be absent from the origin then, and no PR may have
 * been created. Missing identity is a "no" (codex on #61).
 */
export function deliverPauseClean(atDeliver, finalRunBranch) {
  return atDeliver !== null && typeof atDeliver?.runBranch === 'string' && atDeliver.runBranch !== '' && atDeliver.runBranch === finalRunBranch
    && atDeliver.onOrigin === false && atDeliver.prCreates === 0;
}

/** The build unit's OWN floor passed: its `repoChecksEvaluated` (same ord) passed, with a passing test check. */
export function creatorFloorPassed(events, buildUnit) {
  if (!buildUnit) return false;
  return (events ?? []).some((e) => e?.type === 'repoChecksEvaluated' && e.ord === buildUnit.ord && e.passed === true && e.outcome === 'passed'
    && Array.isArray(e.checks) && e.checks.some((c) => c?.name === 'test' && c.outcome === 'passed'));
}

/** Is there a `gh pr create --head <runBranch>` call made from the run's own worktree? (codex on #61) */
export function prForRun(ghCalls, runBranch, workdir, real = (p) => p) {
  if (typeof runBranch !== 'string' || runBranch === '' || typeof workdir !== 'string') return false;
  const wd = real(workdir);
  const headOf = (argv) => { const i = argv.indexOf('--head'); return i >= 0 ? argv[i + 1] ?? null : null; };
  return (ghCalls ?? []).some((c) => Array.isArray(c?.argv) && c.argv[0] === 'pr' && c.argv[1] === 'create' && headOf(c.argv) === runBranch && real(c.cwd) === wd);
}

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const env = ctx.env;
  if (!ctx.state.corpus) throw new Error('S11 needs S03 (the corpus + origin) — run --steps S03,S11');
  const corpus = ctx.state.corpus;
  const origin = ctx.state.origin;

  const health = await api.get('/health');
  const caps = health.json?.capabilities ?? null;
  t.evidence('health-capabilities', { crew: ctx.versions.crew, coreTs: ctx.versions.coreTs, status: health.status, capabilities: caps });
  // A broken /health is a failure, never "an older crew": only a valid answer may skip the step.
  const healthOk = healthUsable(health);
  t.check('GET /health 200 with a JSON body', healthOk, `status ${health.status} ${String(health.text ?? '').slice(0, 200)}`);
  if (!healthOk) return;
  if (caps?.powerMode !== true) {
    t.info('power mode', `crew ${ctx.versions.crew} does not advertise capabilities.powerMode; there is no power run to prove (S04 covers the phased run)`);
    return;
  }

  // The live seats only, as S04's pipeline arm: claude, opencode and the third live seat. (S04 leaves
  // copilot benched on quota and codex / pi signed out; routing over dead seats is S04's to prove.)
  const roster = await api.get('/roster');
  const seats = roster.json?.roster ?? [];
  const live = seats.filter((s) => s.key === 'claude' || s.key === 'opencode' || s.key === JUDGE_SEAT_KEY);
  t.evidence('roster-before-launch', roster.json);
  t.check(`the live seats are listed (claude, opencode, ${JUDGE_SEAT_KEY})`, live.length === 3, live.map((s) => s.key).join(',') || 'none');

  const body = { problem: ISSUE_TEXT, workflow: 'bug', deliver: 'pr', repoRef: ctx.state.repoId ?? 'corpus', power: true, clisJson: JSON.stringify(live) };
  // Same labelled QE skip as S04: the hermetic corpus has no QE ledger; this step proves the power
  // build, the hand-off and delivery, not QE acceptance.
  if (caps?.qeAcceptanceOverride === true) body.skipQeAcceptance = { reason: 'wicked-smoke S11: the hermetic corpus has no QE ledger; this step proves the power build and delivery, not QE acceptance' };

  const shimOffset = ctx.shimCalls().length;
  const prCreateCalls = (from) => ctx.shimCalls().slice(from).filter((c) => c.shim === 'gh' && c.argv[0] === 'pr' && c.argv[1] === 'create');
  // What had happened when the run paused at its deliver gate (wire kind only): nothing may be pushed
  // or opened yet. Recorded before the harness approves the gate.
  let atDeliver = null;
  const beforeDeliverApprove = async (v, rec) => {
    if (rec.kindSource !== 'wire' || atDeliver !== null) return;
    const branch = v?.session?.run_branch ?? null;
    atDeliver = { runBranch: branch, onOrigin: typeof branch === 'string' && branch !== '' ? branches(origin, env, 'wicked/').includes(branch) : null, prCreates: prCreateCalls(shimOffset).length };
  };
  // Nothing is armed for this run: an evaluator-verdict gate is a failure here, never a retry.
  const pipe = await launchAndFollow(ctx, api, t, 'power', body, { retryArmedVerdict: false, beforeDeliverApprove });
  t.check('the power launch answered a runId', pipe !== null && typeof pipe.runId === 'string' && pipe.runId !== '', pipe ? `runId ${pipe.runId}` : 'no runId in the launch answer');
  if (!pipe) return;
  const view = pipe.view;
  const session = view?.session ?? null;
  const power = session?.power ?? null;
  const evRun = '<evidence>/S11/power-run.json';
  t.evidence('power-state', power);

  t.check('power run reached a terminal state within the budget', !pipe.timedOut && view !== null, `status ${session?.status} after ${pipe.gates.length} gate(s)${pipe.aborted ? ' (aborted at the step ceiling)' : ''}`, { evidence: evRun });
  t.check('the launch is a power run (session.power.on)', power?.on === true, `power: ${JSON.stringify(power ? { available: power.available, on: power.on, refusedReason: power.refusedReason } : null)}`, { evidence: evRun });

  const { ok: handedOff, orch, buildUnit, lastTurn } = orchestratorHandedOff(power, pipe.units);
  t.check(`the build ran as one orchestrator session that handed off before the turn cap (${MAX_TURNS})`, handedOff, `orchestrator: ${JSON.stringify(orch)}; build unit: ${buildUnit ? `${buildUnit.ord}/${buildUnit.role}` : 'none'}; last turn: ${JSON.stringify(lastTurn)}`, { evidence: evRun });

  const ho = handoffPassed(power, pipe.units, buildUnit);
  t.check('the hand-off ran every step of the composed plan and passed in one round (no send-back)', ho.ok, `round ${ho.round}; ${[...ho.finalOf].map(([k, v]) => `${k}=${v}`).join(', ') || 'no steps'}${ho.missing.length ? `; missing: ${ho.missing.join(', ')}` : ''}${ho.rowsValid ? '' : '; a row lacks step/ord/round/status'}`, { evidence: evRun });

  const completed = session?.status === 'completed';
  t.check('power run completed', completed, `status ${session?.status}; ${pipe.denials.join(' | ').slice(0, 400)}`, { evidence: evRun });
  const verdictFails = ctx.shimCalls().slice(shimOffset).filter((c) => c.kind === 'verdict' && c.verdict === 'FAIL').length;
  t.check('power run: no failure escalation and no evaluator-verdict gate', pipe.escalation === null && pipe.deadSeatEscalations.length === 0 && pipe.verdictGate === null && verdictFails === 0, pipe.escalation ?? (pipe.verdictGate ? `verdict gate ${JSON.stringify(pipe.verdictGate)}` : verdictFails ? `${verdictFails} evaluator FAIL answer(s)` : 'none'), { evidence: evRun });
  if (!completed) worktreeEvidence(ctx, t, 'power', view);
  t.info('power run units', pipe.units.map((u) => `${phaseOf(u)}=${u.status} (${u.assigned_cli})`).join(', '));
  t.info('power run gate kinds', pipe.gates.map((g) => `${g.phase}: ${g.kind} (${g.kindSource}) → ${g.decision}`).join(', ') || 'none');

  const reachedDeliver = pipe.units.some((u) => phaseOf(u) === 'deliver' && u.status !== 'pending' && u.status !== 'distributed') || pipe.deliverGateSeen || completed;
  const deliverWire = pipe.gates.some((g) => g.kind === 'deliver' && g.kindSource === 'wire');
  t.evidence('at-deliver-gate', atDeliver);
  if (reachedDeliver) t.check('a human DELIVER gate (wire kind) paused the power run before any push or PR', deliverWire && deliverPauseClean(atDeliver, session?.run_branch ?? null), `gates: ${pipe.gates.map((g) => `${g.phase}/${g.kind} (${g.kindSource})`).join(',') || 'none'}; at the gate: ${JSON.stringify(atDeliver)}`, { evidence: evRun });
  else t.info('deliver gate', `not judged — the power run ended before the deliver phase (${pipe.denials[0]?.slice(0, 160) ?? session?.status})`);

  const checks = eventsOfType(pipe.events, 'repoChecksEvaluated');
  t.check('the power build\'s own floor passed (repoChecksEvaluated on the build unit, test check passed)', creatorFloorPassed(pipe.events, buildUnit), checks.map((e) => `ord ${e.ord}: ${e.outcome} [${(e.checks ?? []).map((c) => `${c.name}=${c.outcome}`).join(',')}]`).join(' | ') || 'no evaluations', { evidence: evRun });

  // Delivery — judged from the LOCAL bare origin first (the artifact), then the gh shim's own record.
  const pcalls = ctx.shimCalls().slice(shimOffset);
  const runBranch = session?.run_branch ?? null;
  const originBranches = branches(origin, env, 'wicked/');
  const pushed = runBranch && originBranches.includes(runBranch) ? runBranch : null;
  const lsRemote = gitTry(corpus, env, 'ls-remote', '--heads', 'origin', runBranch ?? 'wicked/*');
  const ghCalls = pcalls.filter((c) => c.shim === 'gh');
  // The PR must be THIS run's: `gh pr create --head <run_branch>` from the run's own worktree.
  const real = (p) => { try { return realpathSync(p); } catch { return p; } };
  const prCreated = prForRun(ghCalls, runBranch, session?.workdir ?? null, real);
  const pushedFix = pushed ? gitTry(origin, env, 'show', `${pushed}:src/add.js`).stdout : '';
  const evDelivery = t.evidence('delivery', { runBranch, originBranches, lsRemote: lsRemote.stdout.trim().slice(0, 300), prCreated, ghCalls: ghCalls.map((c) => c.argv.slice(0, 4)), productDelivery: session?.delivery ?? null });
  t.check('power run branch pushed to the local bare origin (git ls-remote evidence)', pushed !== null && lsRemote.stdout.includes(`refs/heads/${runBranch}`), `origin refs: ${originBranches.join(',')}; run_branch ${runBranch}`, { evidence: evDelivery });
  t.check('gh shim opened THIS run\'s PR (--head <run_branch>, from the run worktree; no GitHub reached)', prCreated, ghCalls.map((c) => `${c.argv.slice(0, 4).join(' ')} @ ${c.cwd}`).join(' | ') || 'no gh calls', { evidence: evDelivery });
  t.check('the pushed power-run branch carries the correction (src/add.js returns a + b)', /a\s*\+\s*b/.test(pushedFix), pushedFix.trim().slice(0, 120), { evidence: evDelivery });
}
