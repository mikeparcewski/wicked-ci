// S05 bus health — F-E2E-021 class. The daemon holds six long-lived better-sqlite3 subscribers on the
// cross-product bus db; `GET /projects/:id/activity` opened the SAME file through a second SQLite
// library (node:sqlite) and its close dropped every POSIX lock the process held, so the next
// short-lived external `wicked-bus emit` believed it was the last connection, checkpointed and
// UNLINKED the WAL sidecars under the daemon → every poll logs "database disk image is malformed"
// forever, while /diagnostics.recentErrors stays []. This step reproduces the trigger sequence
// (launches → activity read → external emit, interleaved) and asserts BOTH halves: no malformed loop,
// and — when the bus does error — the error is visible in recentErrors.
import { existsSync, statSync, truncateSync } from 'node:fs';
import { join } from 'node:path';
import { cloneCorpus } from '../corpus.mjs';
import { run as runProc, sleep } from '../proc.mjs';
import { waitTerminal } from '../runs.mjs';

export const id = 'S05';
export const name = 'bus-health';

const MALFORMED = /database disk image is malformed|SQLITE_CORRUPT|SQLITE_NOTADB/;

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const env = ctx.env;
  if (!ctx.state.corpus) throw new Error('S05 needs S03 (the corpus) — run --steps S03,S05');
  const busDb = join(ctx.L.bus, 'bus.db');
  const logStart = ctx.daemon.logOffset();

  const project = await api.post('/projects', { name: 'smoke-bus' });
  const projectId = project.json?.project?.id;
  t.check('POST /projects 201', project.status === 201 && typeof projectId === 'string', `status ${project.status}`);
  if (!projectId) return;

  const externalEmit = (n) => {
    const r = runProc([process.execPath, ctx.tree.busCli, 'emit', '--type', 'wicked.estate.indexed', '--domain', 'wicked-estate', '--subdomain', 'estate.index', '--payload', JSON.stringify({ n, source: 'wicked-smoke', pad: 'y'.repeat(300) })], { env, cwd: ctx.L.root, timeoutMs: 30_000 });
    return r.status === 0;
  };
  const sidecars = () => ({
    wal: existsSync(`${busDb}-wal`) ? { ino: statSync(`${busDb}-wal`).ino, size: statSync(`${busDb}-wal`).size } : null,
    shm: existsSync(`${busDb}-shm`) ? { ino: statSync(`${busDb}-shm`).ino } : null,
  });

  const timeline = [];
  let emitsOk = 0;
  let emitsFailed = 0;
  let activityOk = 0;
  const runIds = [];
  for (let i = 1; i <= 8; i++) {
    const repo = cloneCorpus(ctx.L, env, ctx.state.corpus, `bus-${i}`);
    const reg = await api.post('/repos', { name: `bus-${i}`, rootPath: repo });
    const runId = reg.json?.onboardRunId;
    if (reg.status !== 201 || !runId) { timeline.push({ i, register: reg.status, body: reg.text?.slice(0, 200) }); continue; }
    runIds.push(runId);
    const { view } = await waitTerminal(api, runId, { ms: 60_000 });
    const act = await api.get(`/projects/${encodeURIComponent(projectId)}/activity`);
    if (act.status === 200) activityOk += 1;
    const ok = externalEmit(i);
    if (ok) emitsOk += 1; else emitsFailed += 1;
    // The daemon-side interleave: a member attach writes a project bus event between externals.
    const member = await api.post(`/projects/${encodeURIComponent(projectId)}/members`, { kind: 'crew.run', ref: runId });
    timeline.push({ i, run: view?.session?.status ?? null, activity: act.status, externalEmit: ok, member: member.status, sidecars: sidecars(), malformedSoFar: ctx.daemon.countInLog(MALFORMED, logStart) });
  }
  // A burst at the repro's cadence — DAEMON-side bus writes (a member attach emits a project event)
  // interleaved with external emits, an activity read (the second-library open/close) every third
  // iteration — so the WAL-sidecar race has the overlap it needs to show; stops at the first symptom.
  for (let n = 100; n < 140; n++) {
    const ok = externalEmit(n);
    if (ok) emitsOk += 1; else emitsFailed += 1;
    if (n % 3 === 0) await api.get(`/projects/${encodeURIComponent(projectId)}/activity`);
    if (n % 2 === 0 && runIds.length > 0) await api.post(`/projects/${encodeURIComponent(projectId)}/members`, { kind: 'crew.run', ref: runIds[n % runIds.length] });
    await sleep(100);
    if (ctx.daemon.countInLog(MALFORMED, logStart) > 0) break;
  }
  await sleep(2500);
  const malformed = ctx.daemon.countInLog(MALFORMED, logStart);
  const sample = ctx.daemon.grepLog(MALFORMED, logStart, 3);
  const evT = t.evidence('bus-timeline', { timeline, emitsOk, emitsFailed, activityOk, malformed, sample, sidecars: sidecars() });
  t.check('8 onboarding launches + activity reads + external emits all succeeded', runIds.length === 8 && emitsFailed === 0 && activityOk === 8, `runs ${runIds.length}/8, activity ${activityOk}/8, emits ok ${emitsOk} failed ${emitsFailed}`, { evidence: evT });
  t.check('daemon log has 0 "database disk image is malformed" lines after the loop (F-E2E-021)', malformed === 0, `${malformed} malformed line(s); first: ${sample[0]?.slice(0, 200) ?? ''}`, { finding: 'F-E2E-021', evidence: evT });

  const diag = await api.get('/diagnostics');
  const recent = Array.isArray(diag.json?.recentErrors) ? diag.json.recentErrors : [];
  const evD = t.evidence('diagnostics-after-loop', { recentErrors: recent, malformed });
  if (malformed > 0) {
    // The loop broke the bus: the product must SAY so.
    t.check('/diagnostics.recentErrors carries the bus error (F-E2E-021 visibility)', recent.some((e) => MALFORMED.test(String(e.line ?? e.message ?? ''))), `${recent.length} recent error(s)`, { finding: 'F-E2E-021', evidence: evD });
  } else {
    t.check('/diagnostics.recentErrors empty after a clean loop', recent.length === 0, JSON.stringify(recent).slice(0, 300), { evidence: evD });
    // WB-014 fault injection: replace the WAL sidecar under the live subscribers (what the wild
    // sequence did) and emit — the pollers must error, and the error must reach /diagnostics.
    const injOffset = ctx.daemon.logOffset();
    let injected = false;
    if (existsSync(`${busDb}-wal`)) {
      try { truncateSync(`${busDb}-wal`, 0); injected = true; } catch { /* windows may hold the file */ }
    }
    externalEmit(999);
    await sleep(3500);
    const errs = ctx.daemon.grepLog(/"level":(40|50)/, injOffset, 5);
    const diag2 = await api.get('/diagnostics');
    const recent2 = Array.isArray(diag2.json?.recentErrors) ? diag2.json.recentErrors : [];
    const evI = t.evidence('wb014-injection', { injected, daemonErrorLines: errs, recentErrors: recent2 });
    if (injected && errs.length > 0) {
      t.check('injected bus fault is visible in /diagnostics.recentErrors (F-E2E-021 visibility)', recent2.length > 0, `${errs.length} daemon error line(s), ${recent2.length} in recentErrors`, { finding: 'F-E2E-021', evidence: evI });
    } else {
      t.info('wb014 injection', injected ? 'the daemon logged no error after the WAL truncation (SQLite recovered) — visibility half not exercised' : 'WAL sidecar not present/truncatable — visibility half not exercised');
    }
  }
  ctx.state.busProjectId = projectId;
}
