// S12 shared checkout (wicked-core#1373): a SECOND daemon on the same host, with its own state home, port, bus and
// worker home, registers the SAME fixture clone and restarts. The first daemon's worktrees in that clone must survive
// the second's boot reaper. Labelled EXPECTED-FAIL (F-CORE-1373) until core-ts ships the owner-scoped reaper.
// The second daemon is stopped in every outcome; it never shares anything with the operator's daemons.
import { existsSync, mkdirSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { Daemon } from '../daemon.mjs';
import { seatFloorEnv } from '../env.mjs';
import { apiClient } from '../http.mjs';

export const id = 'S12';
export const name = 'shared checkout (two daemons)';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const corpus = ctx.state.corpus;
  if (!corpus) { t.skip('needs S03 (the fixture clone)'); return; }
  const wtDir = join(corpus, 'wicked-worktrees');
  const before = existsSync(wtDir) ? readdirSync(wtDir) : [];
  t.evidence('worktrees-before', before);
  if (before.length === 0) { t.skip('the first daemon left no worktree in the clone (nothing to protect)'); return; }
  const root = ctx.L.root;
  const L2 = { ...ctx.L, state: join(root, 'b', 'state'), bus: join(root, 'b', 'bus'), worker: join(root, 'b', 'worker'), tmp: join(root, 'b', 'tmp'),
    wickedHome: join(root, 'b', 'wicked-home'), interactive: join(root, 'b', 'interactive', 'docs'), steeringInbox: join(root, 'b', 'steering-inbox'), daemonLog: join(root, 'daemon-b.log') };
  for (const k of ['state', 'bus', 'worker', 'tmp', 'wickedHome', 'interactive', 'steeringInbox']) mkdirSync(L2[k], { recursive: true });
  const b = new Daemon(L2, ctx.tree.crewBin, ctx.log, { bootTimeoutMs: ctx.daemon.bootTimeoutMs, baseEnv: seatFloorEnv(ctx.versions) });
  (ctx.extraDaemons ??= []).push(b); // a signal stops it too
  try {
    await b.start();
    if (ctx.signal?.aborted) return; // the step's ceiling passed: stop here (finally stops b)
    const api = apiClient(b.origin, { log: ctx.log });
    const reg = await api.post('/repos', { name: 'corpus-shared', rootPath: corpus });
    t.check('the second daemon registers the same clone', reg.status >= 200 && reg.status < 300, `POST /repos ${reg.status}`);
    if (ctx.signal?.aborted) return;
    await b.restart();
    if (ctx.signal?.aborted) return;
    const after = existsSync(wtDir) ? readdirSync(wtDir) : [];
    t.evidence('worktrees-after', after);
    const lost = before.filter((w) => !after.includes(w));
    t.check("the first daemon's worktrees survive the second daemon's restart", lost.length === 0, `${lost.length} of ${before.length} removed: ${lost.join(', ')}`, { finding: 'F-CORE-1373' });
  } finally {
    if (b.child) await b.stop();
  }
}
