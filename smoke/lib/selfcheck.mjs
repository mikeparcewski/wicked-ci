// `npm run check`: every module parses and the step registry is complete (no network, no daemon).
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { ALL_STEPS, parseSteps } from './args.mjs';
import { compare, satisfies } from './semver.mjs';
import { ExpectPolicy } from './expect.mjs';
import { seatFloorEnv } from './env.mjs';
import { chatSeatKey, judgeSeatBin } from './shims.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const stepFiles = readdirSync(join(here, 'steps')).filter((f) => f.endsWith('.mjs')).sort();
const ids = [];
for (const f of stepFiles) {
  const mod = await import(pathToFileURL(join(here, 'steps', f)).href);
  if (typeof mod.run !== 'function' || typeof mod.id !== 'string') throw new Error(`${f}: missing id/run`);
  ids.push(mod.id);
}
if (ids.join(',') !== ALL_STEPS.join(',')) throw new Error(`step registry mismatch: ${ids.join(',')}`);
for (const f of readdirSync(join(here, '..', 'shims')).filter((f) => f.endsWith('.mjs'))) {
  // Importing a shim would run it; a syntax check is enough here.
  const { spawnSync } = await import('node:child_process');
  const r = spawnSync(process.execPath, ['--check', join(here, '..', 'shims', f)], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`${f}: ${r.stderr}`);
}
if (parseSteps('S01..S03').join(',') !== 'S01,S02,S03') throw new Error('parseSteps range');
if (compare('0.7.32', '0.7.33') !== -1) throw new Error('semver compare');
if (!satisfies('0.7.23', '^0.7.23') || satisfies('0.8.0', '^0.7.23')) throw new Error('semver satisfies');
// The re-bound rules hold on the last affected version and stop on the fix (no silent expiry).
const edges = [
  ['F-SMOKE-003', { crew: '0.8.4' }, { crew: '0.8.5' }],
  ['F-087', { crew: '0.7.44', nodeMajor: 26 }, { crew: '0.7.45', nodeMajor: 26 }],
  ['F-E2E-002', { crew: '0.8.5' }, { crew: '0.8.6' }],
];
for (const [f, before, fixed] of edges) {
  if (!new ExpectPolicy(before).reasonFor(f)) throw new Error(`${f}: no reason on ${JSON.stringify(before)}`);
  if (new ExpectPolicy(fixed).reasonFor(f) !== null) throw new Error(`${f}: still expected on ${JSON.stringify(fixed)}`);
}
// C5 (crew 0.13.0): the host seat floor and the headless chat seat start exactly there.
if (seatFloorEnv({ crew: '0.12.4' }).WICKED_SEAT_FLOOR !== undefined || seatFloorEnv({ crew: '0.13.0' }).WICKED_SEAT_FLOOR !== 'host') throw new Error('seatFloorEnv C5 edge');
if (chatSeatKey({ c5: false }) !== 'acp-smoke' || chatSeatKey({ c5: true }) !== 'chat-smoke') throw new Error('chatSeatKey');
// C5: the judge seat rides a claude-stem launcher (the host floor's second governed seat for S04).
if (judgeSeatBin({ c5: false }) !== 'smoke-judge' || judgeSeatBin({ c5: true }) !== 'judge-seat/claude') throw new Error('judgeSeatBin');
// wicked-crew#1050: no harness module may write the bus's WAL/SHM sidecars through the filesystem.
// S05 used to truncate `bus.db-wal` under the live daemon. That loses every frame not yet
// checkpointed, and S10 then reported the corruption the harness had caused as a product failure.
const { readFileSync } = await import('node:fs');
const SIDECAR_WRITE = /\b(truncate|truncateSync|unlink|unlinkSync|rm|rmSync|writeFile|writeFileSync|appendFile|appendFileSync|open|openSync|rename|renameSync|copyFile|copyFileSync)\s*\([^;]*?-(wal|shm)\b/;
const harnessFiles = [
  ...readdirSync(here).filter((f) => f.endsWith('.mjs') && f !== 'selfcheck.mjs').map((f) => join(here, f)),
  ...stepFiles.map((f) => join(here, 'steps', f)),
];
for (const file of harnessFiles) {
  const m = SIDECAR_WRITE.exec(readFileSync(file, 'utf8'));
  if (m) throw new Error(`${file}: writes a SQLite WAL/SHM sidecar through the filesystem (${m[0].slice(0, 80)}) — this corrupts the live bus (wicked-crew#1050)`);
}
// Why the guard exists: truncating a live WAL corrupts the database, and the writer is not told.
// This holds on macOS and Linux. Two connections, one library, one process (no lock-loss seam).
let sqlite = null;
try { sqlite = await import('node:sqlite'); } catch { /* Node < 22.13 without --experimental-sqlite */ }
if (sqlite) {
  const { mkdtempSync, truncateSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const walTruncate = (truncate) => {
    const dir = mkdtempSync(join(tmpdir(), 'smoke-wal-'));
    const file = join(dir, 'bus.db');
    const open = () => { const d = new sqlite.DatabaseSync(file); d.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=2000; CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, payload TEXT)'); return d; };
    const daemon = open();
    const external = open();
    const put = (d, n) => { for (let i = 0; i < n; i++) d.prepare('INSERT INTO events(payload) VALUES(?)').run('y'.repeat(300)); };
    put(daemon, 200); daemon.exec('PRAGMA wal_checkpoint(PASSIVE)'); put(external, 50); put(daemon, 50);
    if (truncate) truncateSync(`${file}-wal`, 0);
    put(daemon, 50); // the long-lived writer keeps going; no error reaches it
    external.close(); daemon.close(); // the last close checkpoints the WAL into bus.db
    let verdict;
    try { const c = new sqlite.DatabaseSync(file, { readOnly: true }); verdict = c.prepare('PRAGMA integrity_check').all().map((r) => r.integrity_check).join(' | '); c.close(); } catch (err) { verdict = err.message; }
    rmSync(dir, { recursive: true, force: true });
    return verdict;
  };
  const clean = walTruncate(false);
  const truncated = walTruncate(true);
  if (clean !== 'ok') throw new Error(`wal control: integrity_check ${clean}`);
  if (truncated === 'ok') throw new Error('wal truncation no longer corrupts: revisit the S05 guard (wicked-crew#1050)');
} else {
  console.log('selfcheck: node:sqlite unavailable — WAL-truncation demonstration skipped');
}
console.log(`selfcheck ok: ${ids.length} steps, ${stepFiles.length} step modules`);
