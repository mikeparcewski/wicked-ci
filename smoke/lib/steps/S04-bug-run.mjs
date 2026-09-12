// S04 default-posture bug run — the seeded `bug` workflow launched the way the studio composer does
// (`humanConfirm: before:1`, `deliver: pr`) against the corpus with the MIXED roster: claude (signed in,
// answers), codex (401), copilot (quota), opencode (free tier, answers), pi (not installed, no login).
//
// Two halves, asserted on the wire:
//  ROUTING (the mixed run): whole-phase plan units (F-090); the engine benches codex / copilot / pi and
//    NAMES them in `unitDistributed.degradedReason`, no unit is seated on a dead seat (F-7R2-006 /
//    F-7R3-001); the intake gate pauses the run; a human gate before the deliver push (F-E2E-030).
//  PIPELINE: the repo-checks floor provisions `node_modules` INTO the worktree and passes (F-E2E-029a);
//    the branch lands on the LOCAL bare origin through the `gh` shim carrying the correction; `GET
//    /runs/:id/diff` answers after completion (F-087); `GET /runs/:id/acceptance` writes nothing into
//    the customer clone (F-E2E-013).
// When the mixed run cannot complete BECAUSE of the routing class (a judge or a unit seated on a dead
// seat — what core-ts 0.7.23 does today), the pipeline half is asserted on a second launch whose seat
// pool is the two live seats only, so every downstream seam is still exercised on this version. The
// routing checks stay EXPECTED-FAIL (policy) until core benches from every ballot round.
import { existsSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { ISSUE_TEXT, branches } from '../corpus.mjs';
import { gitTry } from '../proc.mjs';
import { eventsOfType, phaseOf, runEvents, unitDigest, waitTerminal } from '../runs.mjs';

export const id = 'S04';
export const name = 'bug-run (mixed roster)';

const BENCHED = ['codex', 'copilot', 'pi'];
const DEAD_SEAT_RE = /not logged in|unauthenticated|quota|ACP unavailable for '(codex|copilot|pi)'|cli `(codex|copilot|pi)`|seat '(codex|copilot|pi)'/i;

/** Launch + follow one run, answering gates the way an operator would. */
async function launchAndFollow(ctx, api, t, label, body) {
  const launch = await api.post('/runs', body);
  t.evidence(`${label}-launch`, { request: body, status: launch.status, response: launch.json ?? launch.text });
  t.check(`POST /runs 201 (${label})`, launch.status === 201, `status ${launch.status} ${launch.text?.slice(0, 300)}`);
  const runId = launch.json?.runId;
  if (!runId) return null;
  const out = { runId, deliverGateSeen: false, intakeGateSeen: false, escalation: null, deadSeatEscalations: [] };
  let decisions = 0;
  const { view, gates, timedOut } = await waitTerminal(api, runId, {
    ms: 420_000,
    onAwaiting: async (v, rec) => {
      const unit = v.units.find((u) => u.ord === (v.session.unit_ix ?? 0) + 1) ?? {};
      const phase = phaseOf(unit);
      rec.phase = phase;
      rec.assignedCli = unit.assigned_cli ?? null;
      decisions += 1;
      const prompt = String(rec.gate?.prompt ?? '');
      if (decisions > 6) { out.escalation = out.escalation ?? `${phase}: more than 6 gates — parking loop`; return 'cancel'; }
      const failed = /failed|escalat|REJECT|denied|could not/i.test(prompt);
      // A unit or its judge seated on a DEAD seat (the shims' own words) — the F-7R3-001 class: do what
      // an operator does (crew's approve-then-reassign to a live seat) and record the violation.
      if (failed && DEAD_SEAT_RE.test(prompt) && out.deadSeatEscalations.length < 3) {
        const alt = unit.assigned_cli === 'opencode' ? 'claude' : 'opencode';
        out.deadSeatEscalations.push({ phase, assignedCli: unit.assigned_cli ?? null, reassignedTo: alt, prompt: prompt.slice(0, 300) });
        return `reassign:${alt}`;
      }
      // Any other failure escalation is a seam the shims could not carry: record and cancel, never retry.
      if (failed) { out.escalation = out.escalation ?? `${phase}: ${prompt.slice(0, 400)}`; return 'cancel'; }
      // The intake gate: "Approve unit 1 before it runs: …" on the first unit.
      if ((v.session.unit_ix ?? 0) === 0 && /^Approve unit 1 before it runs/i.test(prompt)) { out.intakeGateSeen = true; return 'approve'; }
      // A gate on the deliver phase itself (the human confirmation before the push, F-E2E-030).
      if (phase === 'deliver') { out.deliverGateSeen = true; return 'approve'; }
      return 'approve';
    },
  });
  out.view = view;
  out.gates = gates;
  out.timedOut = timedOut;
  out.units = view?.units ?? [];
  out.events = await runEvents(api, runId);
  out.denials = out.units.filter((u) => u.denial_reason).map((u) => `${phaseOf(u)} (${u.assigned_cli}): ${String(u.denial_reason).slice(0, 300)}`);
  out.deadSeatDenial = out.denials.some((d) => DEAD_SEAT_RE.test(d));
  // Every unit's captured output (bounded) — what the seats actually said, beside the verdicts.
  out.outputs = {};
  for (const u of out.units) {
    const o = await api.get(`/runs/${encodeURIComponent(runId)}/units/${u.ord}/output`);
    out.outputs[phaseOf(u)] = o.status === 200 ? String(o.json?.output ?? '').slice(0, 2000) : `HTTP ${o.status}`;
  }
  t.evidence(`${label}-run`, { session: view?.session ?? null, units: out.units.map(unitDigest), gates, deadSeatEscalations: out.deadSeatEscalations, denials: out.denials, outputs: out.outputs });
  t.evidence(`${label}-events`, out.events);
  return out;
}

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const env = ctx.env;
  if (!ctx.state.corpus) throw new Error('S04 needs S03 (the corpus + origin) — run --steps S03,S04');
  const corpus = ctx.state.corpus;
  const origin = ctx.state.origin;
  const shimOffset = ctx.shimCalls().length;

  const roster = await api.get('/roster');
  t.evidence('roster-before-launch', roster.json);
  const seats = roster.json?.roster ?? [];
  const byKey = Object.fromEntries(seats.map((s) => [s.key, s]));
  t.check('roster lists the five seats', ['claude', 'codex', 'copilot', 'opencode', 'pi'].every((k) => byKey[k]), Object.keys(byKey).join(','));
  t.check('claude signed_in + council_eligible', byKey.claude?.auth === 'signed_in' && byKey.claude?.council_eligible === true, JSON.stringify({ auth: byKey.claude?.auth, eligible: byKey.claude?.council_eligible }));
  t.check('opencode not_required (free tier) + council_eligible', byKey.opencode?.auth === 'not_required' && byKey.opencode?.council_eligible === true, JSON.stringify({ auth: byKey.opencode?.auth, eligible: byKey.opencode?.council_eligible }));
  t.info('probe view of the seats to be benched', JSON.stringify(Object.fromEntries(BENCHED.map((k) => [k, { auth: byKey[k]?.auth, eligible: byKey[k]?.council_eligible }]))));
  t.info('pi credential', ctx.state.piCredential ? 'present (WICKED_SMOKE_PI_CREDENTIAL=1): the engine must learn not_installed from the ballot' : 'absent: pi benched by the launcher as signed out (the fresh-machine shape)');

  // ── the MIXED run ─────────────────────────────────────────────────────────────────────────────
  const base = { problem: ISSUE_TEXT, workflow: 'bug', humanConfirm: 'before:1', deliver: 'pr', repoRef: ctx.state.repoId ?? 'corpus' };
  const mixed = await launchAndFollow(ctx, api, t, 'mixed', base);
  if (!mixed) return;
  ctx.state.bugRunId = mixed.runId;
  const calls = ctx.shimCalls().slice(shimOffset);
  t.evidence('shim-calls-mixed', calls.map((c) => ({ shim: c.shim, kind: c.kind, cwd: c.cwd, argvHead: c.argv.slice(0, 3) })));

  t.check('mixed run reached a terminal state within the budget', !mixed.timedOut && mixed.view !== null, `status ${mixed.view?.session?.status} after ${mixed.gates.length} gate(s)`);
  t.check('intake gate paused the run (humanConfirm before:1)', mixed.intakeGateSeen, `gates: ${mixed.gates.map((g) => `${g.phase}/${g.decision}`).join(',')}`);
  const selected = eventsOfType(mixed.events, 'workflowSelected')[0];
  const phases = mixed.units.map(phaseOf);
  t.check('plan units == the def phases (+ deliver): triage, reproduce, fix, verify, deliver (F-090)', phases.join(',') === 'triage,reproduce,fix,verify,deliver', phases.join(','));
  t.check('workflowSelected.unitCount == 5', selected?.unitCount === 5, JSON.stringify(selected ?? null).slice(0, 200));

  // Seat routing — the engine had to learn from the ballots and NAME the benched seats.
  const dist = eventsOfType(mixed.events, 'unitDistributed');
  const reasons = dist.map((d) => d.degradedReason).filter((r) => typeof r === 'string' && r !== '');
  const seatFailed = eventsOfType(mixed.events, 'councilSeatFailed').map((e) => ({ cli: e.cli, kind: e.kind, reason: e.reason, round: e.round, ord: e.ord }));
  const evSeats = t.evidence('seat-routing', { distributed: dist.map((d) => ({ ord: d.ord, cli: d.cli, routingMethod: d.routingMethod, degradedReason: d.degradedReason })), councilSeatFailed: seatFailed, deadSeatEscalations: mixed.deadSeatEscalations, denials: mixed.denials });
  const joined = reasons.join('\n');
  for (const seat of BENCHED) {
    const named = new RegExp(`\\b${seat}\\b`, 'i').test(joined);
    const failedBallots = seatFailed.filter((f) => f.cli === seat && f.round === 1).map((f) => f.reason ?? f.kind);
    t.check(`${seat} benched and NAMED in degradedReason (F-7R2-006 / F-7R3-001)`, named, `named=${named}; round-1 ballots: ${failedBallots.join(',') || 'none'}; reasons: ${joined.slice(0, 200)}`, { finding: 'F-7R2-006', evidence: evSeats });
  }
  const routedTo = dist.filter((d) => d.routingMethod !== 'tool').map((d) => d.cli);
  t.check('no unit routed to a dead seat (signed out / quota / not installed)', routedTo.every((c) => !BENCHED.includes(c)), `routed: ${routedTo.join(',')}`, { finding: 'F-7R3-001', evidence: evSeats });
  t.check('no unit or judge was seated on a dead seat (no dead-seat escalation / denial) (F-7R3-001)', mixed.deadSeatEscalations.length === 0 && !mixed.deadSeatDenial, [...mixed.deadSeatEscalations.map((d) => `${d.phase} on ${d.assignedCli} → reassigned to ${d.reassignedTo}`), ...mixed.denials.filter((d) => DEAD_SEAT_RE.test(d))].join(' | ').slice(0, 400), { finding: 'F-7R3-001', evidence: evSeats });
  t.check('codex + copilot ballots were actually spawned (the engine had to learn, not the probe)', calls.some((c) => c.shim === 'codex') && calls.some((c) => c.shim === 'copilot'), `shims called: ${[...new Set(calls.map((c) => c.shim))].join(',')}`);
  t.check('pi was never spawned (not installed)', !calls.some((c) => c.shim === 'pi'), '');
  // A verify escalation whose underlying denial names a dead seat (the agent validator's rotation
  // landed on codex / copilot) is the same routing class, not a separate seam.
  const escalationIsDeadSeat = mixed.escalation !== null && mixed.deadSeatDenial;
  t.check('no other failure escalation in the mixed run (a seam the shims could not carry)', mixed.escalation === null, mixed.escalation ?? '', escalationIsDeadSeat ? { finding: 'F-7R3-001', evidence: evSeats } : {});
  const mixedCompleted = mixed.view?.session?.status === 'completed';
  const routingClass = !mixedCompleted && (mixed.deadSeatEscalations.length > 0 || mixed.deadSeatDenial);
  t.check('mixed run completed (dead seats benched, live seats carried every unit and judge)', mixedCompleted, `status ${mixed.view?.session?.status}; ${mixed.denials.join(' | ').slice(0, 300)}`, routingClass ? { finding: 'F-7R3-001', evidence: evSeats } : {});

  // The wicked-core shim must report the ENGINE's crate semver (crew#275 skew guard). When the table
  // guessed wrong, the engine's own message names the real one — adopt it before the pipeline launch.
  const mismatch = [...mixed.denials, ...mixed.gates.map((g) => String(g.gate?.prompt ?? ''))].join('\n').match(/engine \(napi addon\) is (\d+\.\d+\.\d+)/);
  let semverCorrected = false;
  if (mismatch && mismatch[1] !== ctx.versions.engineSemver) {
    writeFileSync(join(ctx.L.root, 'core-semver.txt'), mismatch[1]);
    t.info('engine semver', `the table said ${ctx.versions.engineSemver}, the engine says ${mismatch[1]} — corrected for the pipeline launch (add the pair to ENGINE_SEMVER_BY_CORE_TS)`);
    ctx.versions.engineSemver = mismatch[1];
    semverCorrected = true;
  }

  // ── the PIPELINE half: on the mixed run when it completed, else on a live-seat rerun ─────────
  let pipe = mixed;
  if (!mixedCompleted && (routingClass || semverCorrected)) {
    const live = seats.filter((s) => s.key === 'claude' || s.key === 'opencode');
    t.info('pipeline rerun', 'the mixed run could not complete because a unit/judge was seated on a dead seat (F-7R3-001) — re-launching with the two live seats only so the downstream seams are still exercised');
    pipe = await launchAndFollow(ctx, api, t, 'live', { ...base, clisJson: JSON.stringify(live) });
    if (!pipe) return;
  }
  const pcalls = ctx.shimCalls().slice(shimOffset);
  const view = pipe.view;
  const units = pipe.units;
  const events = pipe.events;
  const evRun = `<evidence>/S04/${pipe === mixed ? 'mixed' : 'live'}-run.json`;
  t.check('pipeline run reached a terminal state within the budget', !pipe.timedOut && view !== null, `status ${view?.session?.status} after ${pipe.gates.length} gate(s)`, { evidence: evRun });
  t.check('pipeline run completed', view?.session?.status === 'completed', `status ${view?.session?.status}; ${pipe.denials.join(' | ').slice(0, 400)}`, { evidence: evRun });
  t.check('pipeline run: no failure escalation', pipe.escalation === null && pipe.deadSeatEscalations.length === 0, pipe.escalation ?? pipe.deadSeatEscalations.map((d) => d.phase).join(','), { evidence: evRun });

  // Governance posture — F-E2E-030.
  t.check('a human DELIVER gate paused the run before any push (F-E2E-030)', pipe.deliverGateSeen, `gates: ${pipe.gates.map((g) => g.phase).join(',') || 'none besides intake'}`, { finding: 'F-E2E-030', evidence: evRun });

  // Verify floor — F-E2E-029a: node_modules provisioned INTO the worktree, checks ran and passed.
  const checks = eventsOfType(events, 'repoChecksEvaluated');
  const evChecks = t.evidence('repo-checks', checks);
  const lastChecks = checks[checks.length - 1];
  const report = lastChecks?.report ?? lastChecks ?? null;
  const runsList = report?.runs ?? report?.checks ?? [];
  const installRan = Array.isArray(runsList) && runsList.some((r) => /install/i.test(String(r.name ?? r.check ?? '')));
  const workdir = view?.session?.workdir ?? null;
  const nodeModulesInWorktree = typeof workdir === 'string' && existsSync(join(workdir, 'node_modules'));
  t.check('repo-checks floor ran (repoChecksEvaluated emitted)', checks.length > 0, `${checks.length} evaluation(s)`, { evidence: evChecks });
  t.check('repo checks passed', checks.length > 0 && (report?.passed === true || lastChecks?.passed === true), JSON.stringify(report).slice(0, 400), { evidence: evChecks });
  t.check('node_modules provisioned INTO the run worktree (F-E2E-029a)', installRan || nodeModulesInWorktree, `install check in report=${installRan}; node_modules present now=${nodeModulesInWorktree} (${workdir})`, { evidence: evChecks });

  // Delivery — the branch reached the local bare origin, never GitHub.
  const originBranches = branches(origin, env, 'wicked/');
  const runBranch = view?.session?.run_branch ?? null;
  const pushed = runBranch && originBranches.includes(runBranch) ? runBranch : originBranches[0] ?? null;
  t.check('run branch pushed to the local bare origin', pushed !== null, `origin refs: ${originBranches.join(',')}; run_branch ${runBranch}`);
  t.check('session.delivery == delivered', view?.session?.delivery === 'delivered', String(view?.session?.delivery));
  const ghCalls = pcalls.filter((c) => c.shim === 'gh');
  t.check('gh shim opened the PR (no GitHub reached)', ghCalls.some((c) => c.argv[0] === 'pr' && c.argv[1] === 'create'), ghCalls.map((c) => c.argv.slice(0, 2).join(' ')).join(' | '));
  const pushedFix = pushed ? gitTry(origin, env, 'show', `${pushed}:src/add.js`).stdout : '';
  t.check('the pushed branch carries the correction (src/add.js returns a + b)', /a\s*\+\s*b/.test(pushedFix), pushedFix.trim().slice(0, 120));

  // F-087 — the files view never goes dark after completion.
  const diff = await api.get(`/runs/${pipe.runId}/diff`);
  t.evidence('diff', { status: diff.status, source: diff.json?.source, bytes: diff.json?.diff?.length ?? null, truncated: diff.json?.truncated, error: diff.json?.error });
  t.check('GET /runs/:id/diff answers 200 after completion (F-087)', diff.status === 200, `status ${diff.status} ${diff.text?.slice(0, 200)}`);

  // F-E2E-013 — a GET must not write into the customer's checkout.
  const snapshot = () => gitTry(corpus, env, 'status', '--porcelain', '--ignored=matching').stdout.split('\n').filter(Boolean).filter((l) => !/wicked-worktrees/.test(l));
  const before = snapshot();
  const acc = await api.get(`/runs/${pipe.runId}/acceptance`);
  t.evidence('acceptance', acc.json ?? acc.text);
  t.check('GET /runs/:id/acceptance 200', acc.status === 200, `status ${acc.status}`);
  const created = snapshot().filter((l) => !before.includes(l));
  t.check('acceptance read created nothing in the customer clone (F-E2E-013)', created.length === 0 && !existsSync(join(corpus, '.wicked-testing')) && !existsSync(join(corpus, '.wicked-qe')), created.join(',').slice(0, 300));
  const ledgerErr = ctx.daemon.grepLog(/wicked-ledger\] SQLite write failed/, 0, 3);
  t.check('no "[wicked-ledger] SQLite write failed" in the daemon log', ledgerErr.length === 0, ledgerErr.join(' | ').slice(0, 300));
  t.evidence('shim-calls-all', pcalls.map((c) => ({ shim: c.shim, kind: c.kind, cwd: c.cwd })));
}
