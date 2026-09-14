// S10 teardown — SIGTERM → the daemon exits within 10 s; the bus db passes PRAGMA integrity_check
// afterwards (F-E2E-021b — the FILE survives even when the daemon's connections did not); the temp
// root is removed by the CLI after the report is written (unless --keep).
import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { run as runProc } from '../proc.mjs';

export const id = 'S10';
export const name = 'teardown';

export async function run(ctx, t) {
  const stop = await ctx.daemon.stop({ graceMs: 10_000 });
  t.check('daemon exited within 10 s of SIGTERM', stop.exitedInTime, `${stop.ms} ms${stop.alreadyDown ? ' (was already down)' : ''}`);

  // crew#551 (F-RC1-044): with the daemon gone — the operator's "it worked before the reboot" moment —
  // `wicked-crew status --port <port>` must answer with ONE remedy line on stderr and a non-zero exit,
  // never the `TypeError: fetch failed … ECONNREFUSED` stack it printed through main().catch. Fixed in
  // crew 0.7.35 (`daemonFetch` in cli/index.ts); EXPECTED-FAIL below that (lib/expect.mjs).
  if (ctx.daemon.port) {
    const status = runProc([process.execPath, ctx.tree.crewBin, 'status', '--port', String(ctx.daemon.port)], { env: ctx.env, cwd: ctx.L.root, timeoutMs: 30_000 });
    const stack = /^\s+at /m.test(status.stderr);
    const remedy = /no daemon answering on 127\.0\.0\.1:\d+/.test(status.stderr) && /start it with `wicked-crew serve`/.test(status.stderr);
    const evS = t.evidence('status-after-sigterm', { status: status.status, stdout: status.stdout.slice(0, 500), stderr: status.stderr.slice(0, 1500) });
    t.check('wicked-crew status after SIGTERM: exit ≠ 0, one remedy line, no stack (crew#551)', status.status !== 0 && remedy && !stack && status.stdout === '', `exit ${status.status}; remedy ${remedy}; stack frame ${stack}; stdout ${status.stdout.length} B; stderr lines ${status.stderr.trim().split('\n').length}`, { finding: 'F-RC1-044', evidence: evS });
  }
  const busDb = join(ctx.L.bus, 'bus.db');
  if (!existsSync(busDb)) { t.info('bus.db', 'absent — no bus write happened in this run'); }
  else {
    let verdict = null;
    let via = null;
    try {
      const req = createRequire(join(ctx.tree.busDir, 'package.json'));
      const Database = req('better-sqlite3');
      const db = new Database(busDb, { readonly: true });
      verdict = db.pragma('integrity_check', { simple: true });
      db.close();
      via = 'better-sqlite3 (the bus\'s own library)';
    } catch (err) {
      t.info('integrity_check', `better-sqlite3 unavailable (${err.message}); falling back to node:sqlite`);
      try {
        const { DatabaseSync } = await import('node:sqlite');
        const db = new DatabaseSync(busDb, { readOnly: true });
        verdict = db.prepare('PRAGMA integrity_check').get()?.integrity_check ?? null;
        db.close();
        via = 'node:sqlite';
      } catch (err2) { verdict = `unavailable: ${err2.message}`; }
    }
    t.check('bus.db PRAGMA integrity_check == ok (F-E2E-021b)', verdict === 'ok', `${verdict} via ${via}`);
  }
  const coreDb = join(ctx.L.state, 'core.db');
  t.check('core.db present under the temp root', existsSync(coreDb), coreDb);
  t.info('temp root', ctx.opts.keep ? `kept: ${ctx.L.root}` : 'removed by the CLI after the report is written');
}
