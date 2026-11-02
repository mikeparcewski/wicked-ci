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

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const env = ctx.env;
  if (!ctx.state.corpus) throw new Error('S11 needs S03 (the corpus + origin) — run --steps S03,S11');
  const corpus = ctx.state.corpus;
  const origin = ctx.state.origin;

  const health = await api.get('/health');
  const caps = health.json?.capabilities ?? null;
  t.evidence('health-capabilities', { crew: ctx.versions.crew, coreTs: ctx.versions.coreTs, capabilities: caps });
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
  const pipe = await launchAndFollow(ctx, api, t, 'power', body);
  if (!pipe) return;
  const view = pipe.view;
  const session = view?.session ?? null;
  const power = session?.power ?? null;
  const evRun = '<evidence>/S11/power-run.json';
  t.evidence('power-state', power);

  t.check('power run reached a terminal state within the budget', !pipe.timedOut && view !== null, `status ${session?.status} after ${pipe.gates.length} gate(s)${pipe.aborted ? ' (aborted at the step ceiling)' : ''}`, { evidence: evRun });
  t.check('the launch is a power run (session.power.on)', power?.on === true, `power: ${JSON.stringify(power ? { available: power.available, on: power.on, refusedReason: power.refusedReason } : null)}`, { evidence: evRun });

  const turns = power?.orchestrator?.turns ?? null;
  t.check(`the build ran as one orchestrator session that handed off before the turn cap (turns < ${MAX_TURNS})`, typeof turns === 'number' && turns >= 1 && turns < MAX_TURNS, `orchestrator: ${JSON.stringify(power?.orchestrator ?? null)}`, { evidence: evRun });

  // The hand-off log keeps every record of a step (`running`, then its result), in order: a step's
  // outcome is its LAST record in the round.
  const steps = Array.isArray(power?.handoff?.steps) ? power.handoff.steps : [];
  const roundOf = (s) => (typeof s.round === 'number' ? s.round : 1);
  const lastRound = steps.reduce((m, s) => Math.max(m, roundOf(s)), 0);
  const outcome = new Map();
  for (const s of steps) if (roundOf(s) === lastRound) outcome.set(s.step, s.status);
  t.check('the hand-off ran and passed in one round (no send-back)', power?.handoff?.round === 1 && outcome.size > 0 && [...outcome.values()].every((v) => HANDOFF_OK.has(v)), `round ${power?.handoff?.round ?? null}: ${[...outcome].map(([k, v]) => `${k}=${v}`).join(', ') || 'no steps'}`, { evidence: evRun });

  const completed = session?.status === 'completed';
  t.check('power run completed', completed, `status ${session?.status}; ${pipe.denials.join(' | ').slice(0, 400)}`, { evidence: evRun });
  t.check('power run: no failure escalation', pipe.escalation === null && pipe.deadSeatEscalations.length === 0, pipe.escalation ?? 'none', { evidence: evRun });
  if (!completed) worktreeEvidence(ctx, t, 'power', view);
  t.info('power run units', pipe.units.map((u) => `${phaseOf(u)}=${u.status} (${u.assigned_cli})`).join(', '));
  t.info('power run gate kinds', pipe.gates.map((g) => `${g.phase}: ${g.kind} (${g.kindSource}) → ${g.decision}`).join(', ') || 'none');

  const reachedDeliver = pipe.units.some((u) => phaseOf(u) === 'deliver' && u.status !== 'pending' && u.status !== 'distributed') || pipe.deliverGateSeen || completed;
  if (reachedDeliver) t.check('a human DELIVER gate paused the power run before any push', pipe.deliverGateSeen, pipe.gates.map((g) => `${g.phase}/${g.kind}`).join(',') || 'none', { evidence: evRun });
  else t.info('deliver gate', `not judged — the power run ended before the deliver phase (${pipe.denials[0]?.slice(0, 160) ?? session?.status})`);

  const checks = eventsOfType(pipe.events, 'repoChecksEvaluated');
  t.check('repo-checks floor ran on the power build (repoChecksEvaluated emitted)', checks.length > 0, `${checks.length} evaluation(s)`, { evidence: evRun });

  // Delivery — judged from the LOCAL bare origin first (the artifact), then the gh shim's own record.
  const pcalls = ctx.shimCalls().slice(shimOffset);
  const runBranch = session?.run_branch ?? null;
  const originBranches = branches(origin, env, 'wicked/');
  const pushed = runBranch && originBranches.includes(runBranch) ? runBranch : null;
  const lsRemote = gitTry(corpus, env, 'ls-remote', '--heads', 'origin', runBranch ?? 'wicked/*');
  const ghCalls = pcalls.filter((c) => c.shim === 'gh');
  const prCreated = ghCalls.some((c) => c.argv[0] === 'pr' && c.argv[1] === 'create');
  const pushedFix = pushed ? gitTry(origin, env, 'show', `${pushed}:src/add.js`).stdout : '';
  const evDelivery = t.evidence('delivery', { runBranch, originBranches, lsRemote: lsRemote.stdout.trim().slice(0, 300), prCreated, ghCalls: ghCalls.map((c) => c.argv.slice(0, 4)), productDelivery: session?.delivery ?? null });
  t.check('power run branch pushed to the local bare origin (git ls-remote evidence)', pushed !== null && lsRemote.stdout.includes(`refs/heads/${runBranch}`), `origin refs: ${originBranches.join(',')}; run_branch ${runBranch}`, { evidence: evDelivery });
  t.check('gh shim opened the PR for the power run (no GitHub reached)', prCreated, ghCalls.map((c) => c.argv.slice(0, 2).join(' ')).join(' | ') || 'no gh calls', { evidence: evDelivery });
  t.check('the pushed power-run branch carries the correction (src/add.js returns a + b)', /a\s*\+\s*b/.test(pushedFix), pushedFix.trim().slice(0, 120), { evidence: evDelivery });
}
