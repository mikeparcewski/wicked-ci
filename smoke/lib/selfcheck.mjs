// `npm run check`: every module parses and the step registry is complete (no network, no daemon).
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { ALL_STEPS, parseSteps } from './args.mjs';
import { compare, satisfies } from './semver.mjs';
import { ExpectPolicy } from './expect.mjs';
import { seatFloorEnv } from './env.mjs';
import { chatSeatKey, judgeSeatBin, writeCouncilOverlay } from './shims.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const stepFiles = readdirSync(join(here, 'steps')).filter((f) => f.endsWith('.mjs')).sort();
const ids = [];
for (const f of stepFiles) {
  const mod = await import(pathToFileURL(join(here, 'steps', f)).href);
  if (typeof mod.run !== 'function' || typeof mod.id !== 'string') throw new Error(`${f}: missing id/run`);
  ids.push(mod.id);
}
// Every step module is registered and every registered step has a module. ALL_STEPS is the RUN order,
// not the file order: S11 (the power-mode bug run) runs right after S04 on the same corpus, and S10's
// teardown stays last.
if ([...ids].sort().join(',') !== [...ALL_STEPS].sort().join(',')) throw new Error(`step registry mismatch: ${ids.join(',')}`);
if (ALL_STEPS.indexOf('S11') !== ALL_STEPS.indexOf('S04') + 1 || ALL_STEPS.at(-1) !== 'S10') throw new Error(`step order: ${ALL_STEPS.join(',')}`);
for (const f of readdirSync(join(here, '..', 'shims')).filter((f) => f.endsWith('.mjs'))) {
  // Importing a shim would run it; a syntax check is enough here.
  const { spawnSync } = await import('node:child_process');
  const r = spawnSync(process.execPath, ['--check', join(here, '..', 'shims', f)], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`${f}: ${r.stderr}`);
}
if (parseSteps('S01..S03').join(',') !== 'S01,S02,S03') throw new Error('parseSteps range');
// Ranges are NUMERIC, ordered by the run order (S11 runs right after S04): no step is silently dropped.
if (parseSteps('S01..S11').length !== ALL_STEPS.length || !parseSteps('S01..S11').includes('S10')) throw new Error(`parseSteps S01..S11: ${parseSteps('S01..S11')}`);
if (parseSteps('S05..S11').join(',') !== 'S11,S05,S06,S07,S08,S09,S10') throw new Error(`parseSteps S05..S11: ${parseSteps('S05..S11')}`);
if (parseSteps('S10..S11').join(',') !== 'S11,S10' || parseSteps('S04..S05').join(',') !== 'S04,S05') throw new Error('parseSteps S10..S11 / S04..S05');
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
// crew 0.15.2 (crew#916): an omitted `seat_eligible_for_work` means true, so the chat seat must say
// false beside `enabled_for_council = false` (S01-S07), and true beside true (S08's re-write).
{
  const { mkdtempSync, readFileSync: readOverlay, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const root = mkdtempSync(join(tmpdir(), 'smoke-selfcheck-overlay-'));
  try {
    for (const c5 of [false, true]) {
      for (const on of [false, true]) {
        const toml = readOverlay(writeCouncilOverlay({ bin: join(root, 'bin'), home: root }, { c5, acpSeatForCouncil: on }), 'utf8');
        const records = toml.split('[[cli]]').slice(1);
        const chat = records.find((r) => r.includes(`key = "${chatSeatKey({ c5 })}"`)) ?? '';
        if (!chat.includes(`enabled_for_council = ${on}`) || !chat.includes(`seat_eligible_for_work = ${on}`)) throw new Error(`overlay: chat seat roles (c5 ${c5}, council ${on})`);
        if (records.filter((r) => r.includes('seat_eligible_for_work')).length !== 1) throw new Error('overlay: only the chat seat declares its work role');
      }
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}
// wicked-crew#1050: the harness must not write the bus's WAL/SHM sidecars through the filesystem.
// S05 used to truncate `bus.db-wal` under the live daemon. That loses every frame not yet
// checkpointed, and S10 then reported the corruption the harness had caused as a product failure.
// The guard is a textual heuristic. It catches DIRECT fs mutation calls whose arguments name a
// `-wal`/`-shm` path, in every smoke module with comments stripped. An alias or a precomputed path
// variable gets past it, so review still owns the rule.
const { readFileSync } = await import('node:fs');
const SIDECAR_WRITE = /\b(truncate|truncateSync|ftruncate|ftruncateSync|unlink|unlinkSync|rm|rmSync|writeFile|writeFileSync|appendFile|appendFileSync|rename|renameSync|copyFile|copyFileSync|createWriteStream)\s*\([^;)]*?-(wal|shm)\b/;
const smokeRoot = join(here, '..');
const harnessFiles = readdirSync(smokeRoot, { recursive: true })
  .map(String)
  .filter((f) => f.endsWith('.mjs') && !f.split(/[\\/]/).includes('node_modules'))
  .map((f) => join(smokeRoot, f))
  .filter((f) => f !== fileURLToPath(import.meta.url));
for (const file of harnessFiles) {
  const code = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  const m = SIDECAR_WRITE.exec(code);
  if (m) throw new Error(`${file}: writes a SQLite WAL/SHM sidecar through the filesystem (${m[0].slice(0, 80)}) — this corrupts the live bus (wicked-crew#1050)`);
}
// Why the guard exists. Truncate a live WAL while a connection with warm pages keeps writing (two
// connections, one library, one process, so there is no lock-loss seam). The demonstration passes
// when SQLite either refuses the write or reports corruption afterwards. It fails only on a SILENT
// "ok", and on a verification error that is not corruption. Seen 3/3 on macOS (Node 26) and 3/3
// on Linux (Node 22): the write goes through and integrity_check reads "malformed".
let sqlite = null;
try { sqlite = await import('node:sqlite'); } catch { /* Node < 22.13 without --experimental-sqlite */ }
if (sqlite) {
  const { mkdtempSync, truncateSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const CORRUPT = /malformed|not a database|btreeInitPage|corrupt/i;
  const walTruncate = (truncate) => {
    const dir = mkdtempSync(join(tmpdir(), 'smoke-wal-'));
    const file = join(dir, 'bus.db');
    const handles = [];
    try {
      const open = (opts = {}) => { const d = new sqlite.DatabaseSync(file, opts); handles.push(d); return d; };
      const init = (d) => { d.exec('PRAGMA page_size=4096; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=2000; CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, payload TEXT)'); return d; };
      const daemon = init(open());
      const external = init(open());
      const put = (d, n) => { for (let i = 0; i < n; i++) d.prepare('INSERT INTO events(payload) VALUES(?)').run('y'.repeat(300)); };
      put(daemon, 200); daemon.exec('PRAGMA wal_checkpoint(PASSIVE)'); put(external, 50); put(daemon, 50);
      if (truncate) truncateSync(`${file}-wal`, 0);
      let writeError = null;
      try { put(daemon, 50); } catch (err) { writeError = err.message; } // the long-lived writer goes on
      external.close(); daemon.close(); // the last close checkpoints the WAL into bus.db
      let verdict;
      try { verdict = open({ readOnly: true }).prepare('PRAGMA integrity_check').all().map((r) => r.integrity_check).join(' | '); } catch (err) { verdict = err.message; }
      return { verdict, writeError };
    } finally {
      for (const d of handles) { try { if (d.isOpen !== false) d.close(); } catch { /* already closed */ } }
      rmSync(dir, { recursive: true, force: true });
    }
  };
  const clean = walTruncate(false);
  if (clean.verdict !== 'ok' || clean.writeError) throw new Error(`wal control: ${JSON.stringify(clean)}`);
  const cut = walTruncate(true);
  if (!cut.writeError && cut.verdict === 'ok') throw new Error('wal truncation went unnoticed and left the db intact: revisit the S05 guard (wicked-crew#1050)');
  if (!cut.writeError && !CORRUPT.test(cut.verdict)) throw new Error(`wal demonstration: verification failed for another reason: ${cut.verdict}`);
} else {
  console.log('selfcheck: node:sqlite unavailable — WAL-truncation demonstration skipped');
}
// S02's skills settle (crew >= 0.16.2 publishes skills in the background after listen; wicked-ci#59).
{
  const { settledDiagnostics } = await import(pathToFileURL(join(here, 'steps', 'S02-skills.mjs')).href);
  const answer = (state) => ({ status: 200, json: { skills: { state } } });
  const fakeApi = (states, { hangFrom = Infinity } = {}) => {
    let n = 0;
    return { calls: () => n, get: async () => { const i = n++; if (i >= hangFrom) return new Promise(() => {}); return answer(states[Math.min(i, states.length - 1)]); } };
  };
  const infos = [];
  const t = { info: (k, v) => infos.push([k, v]) };
  // An older crew (never `publishing`): one read, no wait, no note.
  let api = fakeApi(['published']);
  let d = await settledDiagnostics(api, t, 'old', { pollMs: 5 });
  if (d.json.skills.state !== 'published' || api.calls() !== 1 || infos.length !== 0) throw new Error('settle: an older crew must be read once, with no note');
  // A terminal non-published state is returned at once (never masked by waiting).
  api = fakeApi(['config-error']);
  d = await settledDiagnostics(api, t, 'refused', { pollMs: 5 });
  if (d.json.skills.state !== 'config-error' || api.calls() !== 1) throw new Error('settle: a refused state must be returned at once');
  // publishing -> published: waits it out and notes the wait once.
  api = fakeApi(['publishing', 'publishing', 'published']);
  d = await settledDiagnostics(api, t, 'boot', { pollMs: 5 });
  if (d.json.skills.state !== 'published' || api.calls() !== 3 || infos.length !== 1) throw new Error(`settle: publishing must be waited out (calls ${api.calls()}, notes ${infos.length})`);
  // Stuck publishing: bounded by the budget, the last answer (still publishing) is returned for the checks to fail on.
  api = fakeApi(['publishing']);
  let t0 = Date.now();
  d = await settledDiagnostics(api, t, 'stuck', { pollMs: 5, budgetMs: 60 });
  if (d.json.skills.state !== 'publishing' || Date.now() - t0 > 1_000) throw new Error('settle: a stuck publish must end at the budget');
  // A request that never answers is bounded by the budget too (status 0, no state).
  api = fakeApi(['publishing'], { hangFrom: 1 });
  t0 = Date.now();
  d = await settledDiagnostics(api, t, 'hung', { pollMs: 5, budgetMs: 80 });
  if (d.status !== 0 || d.json !== null || Date.now() - t0 > 2_500) throw new Error('settle: a hung request must end at the budget (+ at most 1 s) with status 0');
  // The step's abort stops the wait with a throw, so S02 never goes on to mutate the skills root.
  const ac = new AbortController();
  api = fakeApi(['publishing']);
  setTimeout(() => ac.abort(), 30);
  let threw = false;
  try { await settledDiagnostics(api, t, 'aborted', { pollMs: 5, budgetMs: 10_000, signal: ac.signal }); } catch { threw = true; }
  if (!threw) throw new Error('settle: an aborted step must throw');
  // An already-aborted signal throws before the first request.
  api = fakeApi(['published']);
  threw = false;
  try { await settledDiagnostics(api, t, 'pre-aborted', { signal: AbortSignal.abort() }); } catch { threw = true; }
  if (!threw || api.calls() !== 0) throw new Error('settle: a pre-aborted step must not read');
}
// Power mode (crew >= 0.16.11, wicked-core src/power.rs): a seat shim answers the ORCHESTRATOR turn
// protocol: the first orchestrator turn applies the corpus fix and ends with `HANDOFF:` (the LAST marker
// line wins); a turn over a tree that already holds it declares `NO CHANGE NEEDED:` and hands off; a
// phased prompt is answered as before (no marker line).
{
  const { spawnSync } = await import('node:child_process');
  const { mkdtempSync, mkdirSync, writeFileSync, readFileSync: readSrc, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const dir = mkdtempSync(join(tmpdir(), 'wicked-smoke-orch-'));
  try {
    mkdirSync(join(dir, 'src'));
    writeFileSync(join(dir, 'src', 'add.js'), 'export function add(a, b) {\n  return a - b;\n}\n');
    const shim = (prompt) => spawnSync(process.execPath, [join(here, '..', 'shims', 'claude.mjs'), '-p', prompt], { cwd: dir, encoding: 'utf8', env: { ...process.env, WICKED_SMOKE_SHIM_LOG: '' } });
    const markers = (out) => out.split('\n').map((l) => l.trim()).filter((l) => /^(HANDOFF|CHECKPOINT):/.test(l));
    const brief = 'CONTEXT (prior phases of this run): none.\n\nFix add(a, b) in src/add.js. [power mode] You are the ORCHESTRATOR for this whole change: one session, many turns, no phase gates.';
    let r = shim(brief);
    if (r.status !== 0 || !/a \+ b/.test(readSrc(join(dir, 'src', 'add.js'), 'utf8'))) throw new Error(`orchestrator: the first turn must apply the fix (${r.stderr})`);
    if (markers(r.stdout).at(-1)?.startsWith('HANDOFF:') !== true) throw new Error(`orchestrator: the first turn must end with HANDOFF: (${r.stdout.slice(-200)})`);
    r = shim('Invoke your skill; then: [power mode] Turn 2 of at most 12 of the same change. Continue from where you stopped.');
    if (!/^NO CHANGE NEEDED:/m.test(r.stdout) || markers(r.stdout).at(-1)?.startsWith('HANDOFF:') !== true) throw new Error(`orchestrator: a turn over the fixed tree must declare NO CHANGE NEEDED: and hand off (${r.stdout.slice(0, 300)})`);
    writeFileSync(join(dir, 'src', 'add.js'), 'export function add(a, b) {\n  return a - b;\n}\n');
    r = shim('Triage the defect. ||| PHASE SCOPE: this is the triage phase. Do not change files.');
    if (markers(r.stdout).length !== 0 || !/a - b/.test(readSrc(join(dir, 'src', 'add.js'), 'utf8'))) throw new Error('orchestrator: a phased prompt must be answered as before (no marker line, no write outside the fix phase)');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
// S11's judgements read the real wire and fail on missing evidence (codex on #61).
{
  const { orchestratorHandedOff, handoffPassed, prForRun, healthUsable, deliverPauseClean, creatorFloorPassed } = await import(pathToFileURL(join(here, 'steps', 'S11-power-bug-run.mjs')).href);
  const units = [{ ord: 1, role: 'neutral', assigned_cli: 'claude' }, { ord: 3, role: 'creator', assigned_cli: 'claude' }, { ord: 4, role: 'evaluator', assigned_cli: 'smoke-judge' }, { ord: 5, role: 'evaluator', assigned_cli: 'smoke-judge' }, { ord: 7, role: 'neutral', assigned_cli: 'bash' }];
  const good = {
    orchestrator: { cli: 'claude', ord: 3, turns: 1, sessionRestarts: 0 },
    turnLog: [{ turn: 1, cli: 'claude', outcome: 'handoff' }],
    handoff: { round: 1, steps: [
      { step: 'rescore', ord: 3, round: 1, status: 'passed' }, { step: 'checks', ord: 3, round: 1, status: 'passed' },
      { step: 'qe', ord: 4, round: 1, status: 'running' }, { step: 'qe', ord: 4, round: 1, status: 'passed' },
      { step: 'review', ord: 5, round: 1, status: 'running' }, { step: 'review', ord: 5, round: 1, status: 'passed' }] },
  };
  const o = orchestratorHandedOff(good, units);
  if (!o.ok || !handoffPassed(good, units, o.buildUnit).ok) throw new Error('S11: the recorded good run must pass');
  if (orchestratorHandedOff({ orchestrator: { turns: 1 } }, units).ok) throw new Error('S11: a bare turn count must not prove a hand-off');
  if (orchestratorHandedOff({ ...good, turnLog: [{ turn: 1, cli: 'claude', outcome: 'checkpoint' }] }, units).ok) throw new Error('S11: a build that ended on a checkpoint must not pass');
  if (orchestratorHandedOff({ ...good, orchestrator: { ...good.orchestrator, ord: 4 } }, units).ok) throw new Error('S11: the orchestrator must sit on the creator unit');
  if (orchestratorHandedOff({ ...good, orchestrator: { ...good.orchestrator, turns: 12 }, turnLog: Array.from({ length: 12 }, (_, i) => ({ turn: i + 1, cli: 'claude', outcome: i === 11 ? 'handoff' : 'checkpoint' })) }, units).ok) throw new Error('S11: a hand-off at the turn cap must not pass');
  if (orchestratorHandedOff({ ...good, orchestrator: { ...good.orchestrator, turns: 2, sessionRestarts: 1 }, turnLog: [{ turn: 1, cli: 'claude', outcome: 'checkpoint' }, { turn: 2, cli: 'smoke-judge', outcome: 'handoff' }] }, units).ok) throw new Error('S11: a second seat or a session restart must not pass as one session');
  if (orchestratorHandedOff({ ...good, orchestrator: { ...good.orchestrator, cli: 'smoke-judge' }, turnLog: [{ turn: 1, cli: 'smoke-judge', outcome: 'handoff' }] }, units).ok) throw new Error('S11: an orchestrator other than the creator unit\'s seat must not pass');
  if (orchestratorHandedOff({ ...good, orchestrator: { ...good.orchestrator, turns: 2 }, turnLog: [{ turn: 2, cli: 'claude', outcome: 'checkpoint' }, { turn: 1, cli: 'claude', outcome: 'handoff' }] }, units).ok) throw new Error('S11: out-of-order turns must not pass');
  if (handoffPassed({ handoff: { round: 1, steps: [{ status: 'passed' }] } }, units, o.buildUnit).ok) throw new Error('S11: a row without identity must not pass');
  if (handoffPassed({ handoff: { round: 1, steps: [{ step: 'rescore', ord: 3, round: 1, status: 'passed' }] } }, units, o.buildUnit).ok) throw new Error('S11: a lone rescore must not pass');
  if (handoffPassed({ handoff: { round: 1, steps: good.handoff.steps.filter((r) => r.ord !== 5) } }, units, o.buildUnit).ok) throw new Error('S11: a missing evaluator unit must not pass');
  if (handoffPassed({ handoff: { round: 2, steps: good.handoff.steps.map((r) => ({ ...r, round: 2 })) } }, units, o.buildUnit).ok) throw new Error('S11: a second round must not pass');
  if (handoffPassed({ handoff: { round: 1, steps: [...good.handoff.steps, { step: 'review', ord: 5, round: 1, status: 'failed' }] } }, units, o.buildUnit).ok) throw new Error('S11: a final failed record must not pass');
  if (handoffPassed({ handoff: { round: 1, steps: good.handoff.steps.map((r) => (r.ord > 3 ? { ...r, step: 'checks' } : r)) } }, units, o.buildUnit).ok) throw new Error('S11: build steps under evaluator ordinals must not stand for evaluator steps');
  if (handoffPassed({ handoff: { round: 1, steps: good.handoff.steps.filter((r) => r.step !== 'rescore') } }, units, o.buildUnit).ok) throw new Error('S11: a hand-off without its re-score must not pass');
  // /health: only a JSON object may be interpreted (an array is malformed); an older crew's object without capabilities is usable.
  if (!healthUsable({ status: 200, json: { ok: true } }) || healthUsable({ status: 200, json: [] }) || healthUsable({ status: 200, json: null }) || healthUsable({ status: 500, json: {} })) throw new Error('S11: healthUsable');
  // The deliver pause names the final branch, before any push or PR.
  const pause = { runBranch: 'wicked/run-a', onOrigin: false, prCreates: 0 };
  if (!deliverPauseClean(pause, 'wicked/run-a')) throw new Error('S11: a clean deliver pause must pass');
  if (deliverPauseClean({ ...pause, runBranch: null, onOrigin: null }, 'wicked/run-a') || deliverPauseClean(pause, 'wicked/run-b') || deliverPauseClean({ ...pause, onOrigin: true }, 'wicked/run-a') || deliverPauseClean({ ...pause, prCreates: 1 }, 'wicked/run-a') || deliverPauseClean(null, 'wicked/run-a')) throw new Error('S11: a pause without the branch, after a push or PR, or for another branch must not pass');
  // The build's own floor: its ord, passed, with a passing test check.
  const floorEv = { type: 'repoChecksEvaluated', ord: 3, passed: true, outcome: 'passed', checks: [{ name: 'install', outcome: 'passed' }, { name: 'test', outcome: 'passed' }] };
  if (!creatorFloorPassed([floorEv], o.buildUnit)) throw new Error('S11: the build floor must pass');
  if (creatorFloorPassed([{ ...floorEv, ord: 4 }], o.buildUnit) || creatorFloorPassed([{ ...floorEv, passed: false, outcome: 'failed' }], o.buildUnit) || creatorFloorPassed([{ ...floorEv, outcome: 'not_run' }], o.buildUnit) || creatorFloorPassed([{ ...floorEv, checks: [] }], o.buildUnit) || creatorFloorPassed([floorEv], null)) throw new Error('S11: another unit\'s, a failed, an unrun or an empty floor must not pass');
  const calls = [{ argv: ['pr', 'create', '--head', 'wicked/run-a', '--title', 't'], cwd: '/w/run-a' }];
  if (!prForRun(calls, 'wicked/run-a', '/w/run-a')) throw new Error('S11: this run\'s PR must be found');
  if (prForRun(calls, 'wicked/run-b', '/w/run-b') || prForRun([{ argv: ['pr', 'create', '--head', 'wicked/run-a'], cwd: '/w/other' }], 'wicked/run-a', '/w/run-a') || prForRun(calls, null, '/w/run-a')) throw new Error('S11: another run\'s PR (head or worktree) must not count');
}
// S11 never passes on a broken /health or a launch without a runId (codex on #61).
{
  const { run: runS11 } = await import(pathToFileURL(join(here, 'steps', 'S11-power-bug-run.mjs')).href);
  const trace = () => { const checks = []; return { checks, check: (name, ok) => checks.push({ name, ok: Boolean(ok) }), info: () => {}, evidence: () => '<evidence>' }; };
  const ctxWith = (api) => ({ ensureDaemon: async () => {}, api: () => api, env: {}, state: { corpus: '/nonexistent/corpus', origin: '/nonexistent/origin' }, shimCalls: () => [], versions: { crew: '0.16.12' } });
  let t = trace();
  await runS11(ctxWith({ get: async () => ({ status: 500, json: null, text: 'boom' }) }), t);
  if (!t.checks.some((c) => c.name.startsWith('GET /health') && !c.ok)) throw new Error('S11: a 500 /health must fail, not skip');
  t = trace();
  await runS11(ctxWith({ get: async () => ({ status: 200, json: [] }) }), t);
  if (!t.checks.some((c) => c.name.startsWith('GET /health') && !c.ok)) throw new Error('S11: a malformed 200 /health (an array) must fail, not skip');
  t = trace();
  await runS11(ctxWith({ get: async () => ({ status: 200, json: { capabilities: {} } }) }), t);
  if (t.checks.length !== 1 || !t.checks[0].ok) throw new Error('S11: a valid /health without powerMode is noted, not judged');
  t = trace();
  const roster = { roster: [{ key: 'claude' }, { key: 'opencode' }, { key: 'smoke-judge' }] };
  await runS11(ctxWith({
    get: async (path) => (path === '/health' ? { status: 200, json: { capabilities: { powerMode: true } } } : { status: 200, json: roster }),
    post: async () => ({ status: 201, json: {}, text: '{}' }),
  }), t);
  if (!t.checks.some((c) => c.name === 'the power launch answered a runId' && !c.ok)) throw new Error('S11: a 201 without a runId must fail');
}
console.log(`selfcheck ok: ${ids.length} steps, ${stepFiles.length} step modules`);
