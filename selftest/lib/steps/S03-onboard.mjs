// S03 onboard — `POST /repos` (register + onboard the corpus) through the REAL engine with the roster
// the daemon actually hands it for a tool-only workflow (`clis: []`). F-E2E-011 class: the run must get
// PAST distribution, every unit is a Tool executor, no "no eligible seat" refusal. Then the customer-
// visible debris (F-E2E-012) — asserted as the customer sees it and labelled.
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { attachBareOrigin, branches, initCorpus } from '../corpus.mjs';
import { gitTry } from '../proc.mjs';
import { eventsOfType, runEvents, unitDigest, waitTerminal } from '../runs.mjs';

export const id = 'S03';
export const name = 'onboard';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const env = ctx.env;

  const corpus = initCorpus(ctx.L, env, 'corpus');
  const origin = attachBareOrigin(ctx.L, env, corpus, 'corpus');
  ctx.state.corpus = corpus;
  ctx.state.origin = origin;

  const reg = await api.post('/repos', { name: 'corpus', rootPath: corpus });
  const ev = t.evidence('post-repos', reg.json ?? reg.text);
  t.check('POST /repos 201', reg.status === 201, `status ${reg.status} ${reg.text?.slice(0, 200)}`, { evidence: ev });
  const runId = reg.json?.onboardRunId;
  t.check('onboardRunId returned', typeof runId === 'string' && runId.length > 0, String(runId));
  ctx.state.repoId = reg.json?.repo?.id ?? 'corpus';
  if (!runId) return;

  const { view, timedOut } = await waitTerminal(api, runId, { ms: 120_000 });
  const events = await runEvents(api, runId);
  t.evidence('onboard-run', { session: view?.session ?? null, units: (view?.units ?? []).map(unitDigest) });
  t.evidence('onboard-events', events);
  t.check('onboarding reached a terminal state', !timedOut && view !== null, `status ${view?.session?.status}`);
  t.check('onboarding completed', view?.session?.status === 'completed', `status ${view?.session?.status}; denials: ${(view?.units ?? []).map((u) => u.denial_reason).filter(Boolean).join(' | ').slice(0, 300)}`);
  t.check('session.clis == [] (tool-only workflow convenes no council)', Array.isArray(view?.session?.clis) && view.session.clis.length === 0, JSON.stringify(view?.session?.clis));

  const started = eventsOfType(events, 'sessionStarted')[0];
  t.check('sessionStarted.cliCount == 0', started?.cliCount === 0, JSON.stringify(started ?? null).slice(0, 200));
  const refusals = events.filter((e) => e.type === 'error' && /council distribution failed|no eligible seat/i.test(String(e.message ?? '')));
  t.check('no "council distribution failed / no eligible seat" refusal (F-E2E-011)', refusals.length === 0, JSON.stringify(refusals).slice(0, 300));
  const units = view?.units ?? [];
  t.check('every unit is a Tool executor (assigned_cli wicked-estate, tool_cmd set)', units.length > 0 && units.every((u) => u.assigned_cli === 'wicked-estate' && Array.isArray(u.tool_cmd)), units.map((u) => `${u.id.split(':').pop()}:${u.assigned_cli}`).join(','));
  const dist = eventsOfType(events, 'unitDistributed');
  t.check('unitDistributed.routingMethod == tool for every unit', dist.length === units.length && dist.every((d) => d.routingMethod === 'tool'), dist.map((d) => `${d.ord}:${d.routingMethod}:${d.cli}`).join(','));
  t.check('every unit done', units.every((u) => u.status === 'done'), units.map((u) => u.status).join(','));

  // The estate shim was really spawned with the bound placeholders.
  const calls = ctx.shimCalls().filter((c) => c.shim === 'wicked-estate');
  t.check('wicked-estate index + clusters --annotate were spawned', calls.some((c) => c.argv[0] === 'index' && c.argv.includes(corpus)) && calls.some((c) => c.argv[0] === 'clusters'), calls.map((c) => c.argv.slice(0, 2).join(' ')).join(' | '));

  // Repo graph state as crew reports it (the estate is shimmed, so `ready` cannot be asserted here).
  const repos = await api.get('/repos');
  const repo = (repos.json?.repos ?? []).find((r) => r.id === ctx.state.repoId);
  t.info('repo record', JSON.stringify({ code_graph_db: repo?.code_graph_db, findings: repo?.findings }).slice(0, 300));
  t.check('repo registered with a code_graph_db under the temp root', typeof repo?.code_graph_db === 'string' && repo.code_graph_db.startsWith(ctx.L.root), String(repo?.code_graph_db));

  // F-E2E-012 — debris in the customer's clone after a tool-only run (labelled by the policy).
  const wickedBranches = branches(corpus, env, 'wicked/');
  const worktreeDir = join(corpus, 'wicked-worktrees');
  const debris = { branches: wickedBranches, worktreeDirExists: existsSync(worktreeDir), worktrees: gitTry(corpus, env, 'worktree', 'list', '--porcelain').stdout.split('\n').filter((l) => l.startsWith('worktree ')).length };
  const ev2 = t.evidence('git-debris', debris);
  t.check('no wicked/<run-id> branch left by a tool-only onboarding (F-E2E-012)', wickedBranches.length === 0, `${wickedBranches.length} branch(es): ${wickedBranches.join(',')}`, { finding: 'F-E2E-012', evidence: ev2 });
  t.check('no wicked-worktrees/ dir left in the clone (F-E2E-012)', !debris.worktreeDirExists, `${worktreeDir} exists=${debris.worktreeDirExists}`, { finding: 'F-E2E-012', evidence: ev2 });
  const porcelain = gitTry(corpus, env, 'status', '--porcelain').stdout.trim();
  t.check('git status --porcelain clean in the customer clone', porcelain === '', porcelain.slice(0, 300));
}
