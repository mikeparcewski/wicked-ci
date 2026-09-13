// S04 default-posture bug run — the seeded `bug` workflow launched the way the studio composer does
// (`humanConfirm: before:1`, `deliver: pr`) against the corpus with the MIXED roster: claude (signed in,
// answers), codex (401), copilot (quota), opencode (free tier, answers), pi (not installed, no login).
//
// Two halves, asserted on the wire:
//  ROUTING (the mixed run): whole-phase plan units (F-090); the engine benches codex / copilot / pi and
//    NAMES them in `unitDistributed.degradedReason`, no unit or judge is seated on a dead seat
//    (F-7R2-006 / F-7R3-001); the intake gate pauses the run; a human gate before the deliver push
//    (F-E2E-030).
//  PIPELINE: the repo-checks floor provisions `node_modules` INTO the worktree and passes (F-E2E-029a);
//    the branch lands on the LOCAL bare origin through the `gh` shim carrying the correction — judged
//    from the origin FIRST, with the product's `session.delivery` reported beside it (F-SMOKE-003);
//    `GET /runs/:id/diff` answers after completion (F-087); `GET /runs/:id/acceptance` writes nothing
//    into the customer clone (F-E2E-013).
// When the mixed run cannot complete BECAUSE of the routing class (a judge or a unit seated on a dead
// seat — what core-ts 0.7.23/0.7.24 do today), the pipeline half is asserted on a second launch whose
// seat pool is the two live seats only, so every downstream seam is still exercised on this version.
//
// GATES are judged by their KIND (`awaitingHuman.gateKind`, core-ts ≥ 0.7.24), never by prompt text:
// run_level / def → approve; deliver → approve (the push goes to the local bare origin through the
// `gh` shim); escalation / failure / triage → reassign to a live seat when the failure names a dead
// seat, otherwise record and cancel. On an engine without `gateKind` the fallback derives a kind from
// the cursor phase and the prompt's OPENING words and never cancels from a guess.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { ISSUE_TEXT, branches } from '../corpus.mjs';
import { gitTry } from '../proc.mjs';
import { eventsOfType, phaseOf, runEvents, unitDigest, waitTerminal } from '../runs.mjs';
import { gte } from '../semver.mjs';

export const id = 'S04';
export const name = 'bug-run (mixed roster)';

const BENCHED = ['codex', 'copilot', 'pi'];
const DEAD_SEAT_RE = /not logged in|unauthenticated|quota|ACP unavailable for '(codex|copilot|pi)'|cli `(codex|copilot|pi)`|seat '(codex|copilot|pi)'/i;
const ESCALATION_KINDS = new Set(['escalation', 'failure', 'triage']);

/** Launch + follow one run, answering gates by kind the way an operator would. */
async function launchAndFollow(ctx, api, t, label, body) {
  const launch = await api.post('/runs', body);
  t.evidence(`${label}-launch`, { request: body, status: launch.status, response: launch.json ?? launch.text });
  t.check(`POST /runs 201 (${label})`, launch.status === 201, `status ${launch.status} ${launch.text?.slice(0, 300)}`);
  const runId = launch.json?.runId;
  if (!runId) return null;
  const out = { runId, deliverGateSeen: false, intakeGateSeen: false, escalation: null, deadSeatEscalations: [], guessedKinds: [] };
  let decisions = 0;
  // The wait budget is whatever is left of the step's ceiling (raised with --step-timeout on a loaded
  // host), never a second, smaller clock of its own.
  const budgetMs = Math.max(30_000, (ctx.stepDeadline ?? Date.now() + 420_000) - Date.now() - 5_000);
  const { view, gates, timedOut, aborted } = await waitTerminal(api, runId, {
    ms: budgetMs,
    signal: ctx.signal,
    onAwaiting: async (v, rec) => {
      const unit = v.units.find((u) => u.ord === (v.session.unit_ix ?? 0) + 1) ?? {};
      const phase = phaseOf(unit);
      rec.phase = phase;
      rec.assignedCli = unit.assigned_cli ?? null;
      decisions += 1;
      const prompt = String(rec.gate?.prompt ?? '');
      if (rec.kindSource === 'fallback') out.guessedKinds.push(`${phase}: ${rec.kind}`);
      if (decisions > 6) { out.escalation = out.escalation ?? `${phase}: more than 6 gates — parking loop`; return 'cancel'; }
      switch (rec.kind) {
        case 'run_level':
        case 'def':
          if ((v.session.unit_ix ?? 0) === 0) out.intakeGateSeen = true;
          return 'approve';
        case 'deliver':
          out.deliverGateSeen = true;
          return 'approve'; // the push goes to the LOCAL bare origin; `gh` is the shim
        case 'terminal':
          return 'approve';
        case 'escalation':
        case 'failure':
        case 'triage': {
          // A unit or its judge seated on a DEAD seat (the shims' own words) — the F-7R3-001 class:
          // crew's approve-then-reassign to a live seat, recorded as the violation it is.
          if (DEAD_SEAT_RE.test(prompt) && out.deadSeatEscalations.length < 3) {
            const alt = unit.assigned_cli === 'opencode' ? 'claude' : 'opencode';
            out.deadSeatEscalations.push({ phase, assignedCli: unit.assigned_cli ?? null, reassignedTo: alt, kind: rec.kind, kindSource: rec.kindSource, prompt: prompt.slice(0, 300) });
            return `reassign:${alt}`;
          }
          // A dead-seat JUDGE: the prompt ("Unit N verdict is NOT PASS …") does not name the seat, the
          // unit's denial_reason does ("no eligible seat produced a verdict (copilot (… quota …))").
          // Recorded as the same F-7R3-001 class; no reassign can seat a different judge, so a WIRE
          // kind ends the run (the pipeline half re-runs on the live seats).
          const denial = String(unit.denial_reason ?? '');
          if (DEAD_SEAT_RE.test(denial)) out.deadSeatEscalations.push({ phase, assignedCli: unit.assigned_cli ?? null, reassignedTo: null, via: 'denial_reason (judge seat)', kind: rec.kind, kindSource: rec.kindSource, prompt: prompt.slice(0, 300), denial: denial.slice(0, 300) });
          // Any other failure escalation is a seam the shims could not carry. Cancel only on a WIRE
          // kind; a guessed kind approves once (retry) so a text guess is never irreversible.
          out.escalation = out.escalation ?? `${phase} [${rec.kind}/${rec.kindSource}]: ${prompt.slice(0, 400)}`;
          return rec.kindSource === 'wire' ? 'cancel' : 'approve';
        }
        default:
          // Unknown kind (older engine, unfamiliar prompt): approve — never cancel from a guess.
          if ((v.session.unit_ix ?? 0) === 0) out.intakeGateSeen = true;
          if (phase === 'deliver') out.deliverGateSeen = true;
          return 'approve';
      }
    },
  });
  out.view = view;
  out.gates = gates;
  out.timedOut = timedOut;
  out.aborted = Boolean(aborted);
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
  t.evidence(`${label}-run`, { session: view?.session ?? null, units: out.units.map(unitDigest), gates, deadSeatEscalations: out.deadSeatEscalations, denials: out.denials, guessedKinds: out.guessedKinds, outputs: out.outputs });
  t.evidence(`${label}-events`, out.events);
  return out;
}

/** Post-denial worktree state — what F-SMOKE-001 (the Linux floor denial) needs for triage from the artifact. */
function worktreeEvidence(ctx, t, label, view) {
  const wd = view?.session?.workdir;
  if (typeof wd !== 'string' || !existsSync(wd)) return t.evidence(`${label}-worktree-after`, { workdir: wd ?? null, present: false });
  const env = ctx.env;
  const status = gitTry(wd, env, 'status', '--porcelain', '--untracked-files=all');
  const diffStat = gitTry(wd, env, 'diff', '--stat');
  const diff = gitTry(wd, env, 'diff', '--', 'src/add.js');
  const gitDir = gitTry(wd, env, 'rev-parse', '--absolute-git-dir');
  let addJs = null;
  try { addJs = readFileSync(join(wd, 'src', 'add.js'), 'utf8').slice(0, 600); } catch { /* absent */ }
  return t.evidence(`${label}-worktree-after`, {
    workdir: wd, present: true, gitDir: gitDir.stdout.trim() || gitDir.stderr.slice(0, 200),
    statusPorcelain: status.stdout.split('\n').filter(Boolean).slice(0, 60), statusExit: status.status, statusStderr: status.stderr.slice(0, 300),
    diffStat: diffStat.stdout.slice(0, 1500), addJsDiff: diff.stdout.slice(0, 1500), addJs,
    nodeModulesPresent: existsSync(join(wd, 'node_modules')), tmpScratchPresent: existsSync(join(wd, 'tmp', 'wicked-checks')),
  });
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

  // The deliverGate WIRE (crew ≥ 0.7.33, api-types 0.37.0): `GET /health.capabilities.deliverGate`
  // is version-derived from the installed addon (≥ 0.7.24 keeps the engine gate). Untagged: on a
  // crew that declares the capability it must agree with the engine actually installed — a stale
  // studio composer promise ("pauses at the deliver gate") is exactly the composition drift this
  // smoke exists for. Older crews carry no `capabilities`; recorded, not judged.
  const health = await api.get('/health');
  const caps = health.json?.capabilities ?? null;
  const evCaps = t.evidence('health-capabilities', { crew: ctx.versions.crew, coreTs: ctx.versions.coreTs, capabilities: caps });
  if (ctx.versions.crew && gte(ctx.versions.crew, '0.7.33')) {
    const engineHasGate = Boolean(ctx.versions.coreTs && gte(ctx.versions.coreTs, '0.7.24'));
    t.check(`GET /health.capabilities.deliverGate == ${engineHasGate} (crew ${ctx.versions.crew} on core-ts ${ctx.versions.coreTs})`, caps?.deliverGate === engineHasGate, `capabilities: ${JSON.stringify(caps)}`, { evidence: evCaps });
  } else t.info('health.capabilities', caps ? JSON.stringify(caps) : `absent (crew ${ctx.versions.crew} predates the 0.7.33 wire)`);

  // ── the MIXED run ─────────────────────────────────────────────────────────────────────────────
  const base = { problem: ISSUE_TEXT, workflow: 'bug', humanConfirm: 'before:1', deliver: 'pr', repoRef: ctx.state.repoId ?? 'corpus' };
  const mixed = await launchAndFollow(ctx, api, t, 'mixed', base);
  if (!mixed) return;
  ctx.state.bugRunId = mixed.runId;
  const calls = ctx.shimCalls().slice(shimOffset);
  t.evidence('shim-calls-mixed', calls.map((c) => ({ shim: c.shim, kind: c.kind, cwd: c.cwd, argvHead: c.argv.slice(0, 3) })));

  t.check('mixed run reached a terminal state within the budget', !mixed.timedOut && mixed.view !== null, `status ${mixed.view?.session?.status} after ${mixed.gates.length} gate(s)${mixed.aborted ? ' (aborted at the step ceiling)' : ''}`);
  t.check('intake gate paused the run (humanConfirm before:1)', mixed.intakeGateSeen, `gates: ${mixed.gates.map((g) => `${g.phase}/${g.kind}${g.kindSource === 'fallback' ? '?' : ''}/${g.decision}`).join(',')}`);
  t.info('gate kinds', mixed.gates.map((g) => `${g.phase}: ${g.kind} (${g.kindSource})`).join(', ') || 'none');
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
    // codex / copilot must be learned from the BALLOT (the F-7R2-006 ledger class). pi carries no
    // credential, so crew's launcher benches it BEFORE any ballot ("pi (signed out — launcher)") — a
    // different mechanism that works today, hence no finding tag on that check.
    const opts = seat === 'pi' ? { evidence: evSeats } : { finding: 'F-7R2-006', evidence: evSeats };
    t.check(`${seat} benched and NAMED in degradedReason (${seat === 'pi' ? 'launcher bench, crew standing' : 'ballot ledger, F-7R2-006 / F-7R3-001'})`, named, `named=${named}; round-1 ballots: ${failedBallots.join(',') || 'none'}; reasons: ${joined.slice(0, 200)}`, opts);
  }
  const routedTo = dist.filter((d) => d.routingMethod !== 'tool').map((d) => d.cli);
  t.check('no unit routed to a dead seat (signed out / quota / not installed)', routedTo.every((c) => !BENCHED.includes(c)), `routed: ${routedTo.join(',')}`, { finding: 'F-7R3-001', evidence: evSeats });
  t.check('no unit or judge was seated on a dead seat (no dead-seat escalation / denial) (F-7R3-001)', mixed.deadSeatEscalations.length === 0 && !mixed.deadSeatDenial, [...mixed.deadSeatEscalations.map((d) => (d.reassignedTo ? `${d.phase} on ${d.assignedCli} → reassigned to ${d.reassignedTo}` : `${d.phase}: judge on a dead seat (${d.via})`)), ...mixed.denials.filter((d) => DEAD_SEAT_RE.test(d))].join(' | ').slice(0, 400), { finding: 'F-7R3-001', evidence: evSeats });
  t.check('codex + copilot ballots were actually spawned (the engine had to learn, not the probe)', calls.some((c) => c.shim === 'codex') && calls.some((c) => c.shim === 'copilot'), `shims called: ${[...new Set(calls.map((c) => c.shim))].join(',')}`);
  // pi from the WIRE (no shim exists to record a call): never routed, and every council outcome for it is the not-installed spawn failure or the launcher's bench.
  const piOutcomes = seatFailed.filter((f) => f.cli === 'pi').map((f) => `${f.kind}/${f.reason ?? '-'}`);
  t.check('pi never routed; its only council outcomes are not_installed / benched', !routedTo.includes('pi') && piOutcomes.every((o) => /spawn_failed\/not_installed|^benched\//.test(o)), `routed pi=${routedTo.includes('pi')}; outcomes: ${[...new Set(piOutcomes)].join(',') || 'none (benched by the launcher before any ballot)'}`);
  const escalationIsDeadSeat = mixed.escalation !== null && mixed.deadSeatDenial;
  t.check('no other failure escalation in the mixed run (a seam the shims could not carry)', mixed.escalation === null, mixed.escalation ?? '', escalationIsDeadSeat ? { finding: 'F-7R3-001', evidence: evSeats } : {});
  const mixedCompleted = mixed.view?.session?.status === 'completed';
  const routingClass = !mixedCompleted && (mixed.deadSeatEscalations.length > 0 || mixed.deadSeatDenial);
  t.check('mixed run completed (dead seats benched, live seats carried every unit and judge)', mixedCompleted, `status ${mixed.view?.session?.status}; ${mixed.denials.join(' | ').slice(0, 300)}`, routingClass ? { finding: 'F-7R3-001', evidence: evSeats } : {});
  if (!mixedCompleted) worktreeEvidence(ctx, t, 'mixed', mixed.view);

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
  const label = pipe === mixed ? 'mixed' : 'live';
  const pcalls = ctx.shimCalls().slice(shimOffset);
  const view = pipe.view;
  const events = pipe.events;
  const evRun = `<evidence>/S04/${label}-run.json`;
  t.check('pipeline run reached a terminal state within the budget', !pipe.timedOut && view !== null, `status ${view?.session?.status} after ${pipe.gates.length} gate(s)${pipe.aborted ? ' (aborted at the step ceiling)' : ''}`, { evidence: evRun });
  const pipeCompleted = view?.session?.status === 'completed';
  // F-SMOKE-001 (Linux): the pinned evidence floor's denial signature on the fix unit. When it is what
  // stopped the run, every downstream pipeline check is a CASCADE of that one finding and carries its
  // tag; on any other failure they stay untagged (a real regression must read FAIL).
  const FLOOR_DENIAL_RE = /no coverage report was produced.*denied before writing one/i;
  const floorDenied = !pipeCompleted && pipe.denials.some((d) => /^fix \(/.test(d) && FLOOR_DENIAL_RE.test(d));
  const cascade = (extra = {}) => (floorDenied ? { finding: 'F-SMOKE-001', evidence: evRun, ...extra } : { evidence: evRun, ...extra });
  t.check('pipeline run completed', pipeCompleted, `status ${view?.session?.status}; ${pipe.denials.join(' | ').slice(0, 400)}`, cascade());
  // Not part of the cascade: a floor denial ends the run WITHOUT an escalation gate, so this check
  // legitimately passes there — tagging it would read as an unexpected pass.
  t.check('pipeline run: no failure escalation', pipe.escalation === null && pipe.deadSeatEscalations.length === 0, pipe.escalation ?? pipe.deadSeatEscalations.map((d) => d.phase).join(','), { evidence: evRun });
  if (!pipeCompleted && pipe !== mixed) worktreeEvidence(ctx, t, 'live', view);
  t.info('pipeline gate kinds', pipe.gates.map((g) => `${g.phase}: ${g.kind} (${g.kindSource}) → ${g.decision}`).join(', ') || 'none');
  const reachedDeliver = pipe.units.some((u) => phaseOf(u) === 'deliver' && u.status !== 'pending' && u.status !== 'distributed') || pipe.deliverGateSeen || pipeCompleted;

  // The default posture never opts out of the gate: `session.auto_deliver` (api-types 0.37.0, absent
  // on an engine that predates the gate) must not read true on a launch that sent no `deliverGate`.
  t.check('session.auto_deliver is not true under the default posture (no deliverGate sent)', view?.session?.auto_deliver !== true, `auto_deliver: ${JSON.stringify(view?.session?.auto_deliver ?? null)}`, { evidence: evRun });
  // Governance posture — F-E2E-030: a gate of kind `deliver` (wire) paused the run before the push.
  // Judged only when the run got as far as the deliver phase; a run that died earlier says nothing
  // about the gate (the earlier failure is already on the record above).
  if (reachedDeliver) t.check('a human DELIVER gate paused the run before any push (F-E2E-030)', pipe.deliverGateSeen, `gates: ${pipe.gates.map((g) => `${g.phase}/${g.kind}`).join(',') || 'none besides intake'}`, { finding: 'F-E2E-030', evidence: evRun });
  else t.info('deliver gate', `not judged — the pipeline run ended before the deliver phase (${pipe.denials[0]?.slice(0, 160) ?? view?.session?.status})`);

  // Verify floor — F-E2E-029a: node_modules provisioned INTO the worktree, checks ran and passed.
  const checks = eventsOfType(events, 'repoChecksEvaluated');
  const evChecks = t.evidence('repo-checks', checks);
  const lastChecks = checks[checks.length - 1];
  const report = lastChecks?.report ?? lastChecks ?? null;
  const runsList = report?.runs ?? report?.checks ?? [];
  const installRan = Array.isArray(runsList) && runsList.some((r) => /install/i.test(String(r.name ?? r.check ?? '')));
  const workdir = view?.session?.workdir ?? null;
  const nodeModulesInWorktree = typeof workdir === 'string' && existsSync(join(workdir, 'node_modules'));
  t.check('repo-checks floor ran (repoChecksEvaluated emitted)', checks.length > 0, `${checks.length} evaluation(s)`, cascade({ evidence: evChecks }));
  t.check('repo checks passed', checks.length > 0 && (report?.passed === true || lastChecks?.passed === true), JSON.stringify(report).slice(0, 400), cascade({ evidence: evChecks }));
  t.check('node_modules provisioned INTO the run worktree (F-E2E-029a)', installRan || nodeModulesInWorktree, `install check in report=${installRan}; node_modules present now=${nodeModulesInWorktree} (${workdir})`, cascade({ evidence: evChecks }));

  // Delivery — judged from the LOCAL bare origin first (the artifact), then the product's own word.
  const originBranches = branches(origin, env, 'wicked/');
  const runBranch = view?.session?.run_branch ?? null;
  const pushed = runBranch && originBranches.includes(runBranch) ? runBranch : null;
  const lsRemote = gitTry(corpus, env, 'ls-remote', '--heads', 'origin', runBranch ?? 'wicked/*');
  const ghCalls = pcalls.filter((c) => c.shim === 'gh');
  const prCreated = ghCalls.some((c) => c.argv[0] === 'pr' && c.argv[1] === 'create');
  const pushedFix = pushed ? gitTry(origin, env, 'show', `${pushed}:src/add.js`).stdout : '';
  const evDelivery = t.evidence('delivery', { runBranch, originBranches, lsRemote: lsRemote.stdout.trim().slice(0, 300), prCreated, ghCalls: ghCalls.map((c) => c.argv.slice(0, 4)), productDelivery: view?.session?.delivery ?? null, deliverOutputHead: (pipe.outputs?.deliver ?? '').slice(0, 400), deliverOutputBytes: (pipe.outputs?.deliver ?? '').length });
  t.check('run branch pushed to the local bare origin (git ls-remote evidence)', pushed !== null && lsRemote.stdout.includes(`refs/heads/${runBranch}`), `origin refs: ${originBranches.join(',')}; run_branch ${runBranch}`, cascade({ evidence: evDelivery }));
  t.check('gh shim opened the PR (no GitHub reached)', prCreated, ghCalls.map((c) => c.argv.slice(0, 2).join(' ')).join(' | '), cascade({ evidence: evDelivery }));
  t.check('the pushed branch carries the correction (src/add.js returns a + b)', /a\s*\+\s*b/.test(pushedFix), pushedFix.trim().slice(0, 120), cascade({ evidence: evDelivery }));
  const delivered = pushed !== null && prCreated;
  const productSays = view?.session?.delivery ?? null;
  // The product's wire value beside the evidence: when the branch IS on the origin and the PR WAS
  // opened but the wire says otherwise, that disagreement is F-SMOKE-003 (the deliver output cap).
  // Tagged UNCONDITIONALLY: a tag attached only on failure could never surface as UNEXPECTED-PASS, so
  // the label would outlive the fix; the finding is FLAKY, so a `delivered` reading prints as
  // "~ passed this time" (disclosure), never as a verdict.
  t.check('session.delivery agrees with the origin evidence (delivered ⇔ branch pushed + PR opened) (F-SMOKE-003)', delivered ? productSays === 'delivered' : productSays !== 'delivered', `product: ${productSays}; evidence: pushed=${pushed !== null} prCreated=${prCreated}; deliver output ${(pipe.outputs?.deliver ?? '').length} chars captured`, { finding: 'F-SMOKE-003', evidence: evDelivery });

  // F-087 — the files view never goes dark after completion. Observed by this harness (node ≥ 24
  // hosts): the route shells `git diff --no-index -- /dev/null <untracked file>` per untracked file
  // and answers 500 when one of the checks' compile-cache files under `tmp/wicked-checks/` cannot be
  // diffed — the same "not robust to what the worktree holds" class as F-087.
  const diff = await api.get(`/runs/${pipe.runId}/diff`);
  const evDiff = t.evidence('diff', { status: diff.status, source: diff.json?.source, bytes: diff.json?.diff?.length ?? null, truncated: diff.json?.truncated, error: diff.json?.error });
  t.check('GET /runs/:id/diff answers 200 after completion (F-087)', diff.status === 200, `status ${diff.status} ${diff.text?.slice(0, 200)}`, { finding: 'F-087', evidence: evDiff });

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
