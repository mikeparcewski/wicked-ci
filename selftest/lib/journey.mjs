// The bridge from a harness step to a studio journey: run `journeys/driver.py <journey>` (Python Playwright) against
// THIS run's daemon, then fold the journey's typed checks into the step. The browser reaches only the daemon's origin
// (the driver aborts every other host), and its HOME is under the run root, so a journey adds no network and no
// state outside the root (the hermetic $HOME scan holds with journeys on).
//
// A journey needs a Python with Playwright (`--python`, or WICKED_SELFTEST_PYTHON; browsers from
// PLAYWRIGHT_BROWSERS_PATH or Playwright's default cache). Without one the step is SKIPPED and names why: never a
// pass. A journey that leaves no result, or no checks, is an ERROR.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
export const JOURNEYS_DIR = join(here, '..', 'journeys');

/** The Python that runs journeys, or a reason there is none. Probed once per run. */
export function journeyPython(ctx) {
  if (ctx.state.journeyPython !== undefined) return ctx.state.journeyPython;
  const raw = ctx.opts.python ?? process.env.WICKED_SELFTEST_PYTHON ?? null;
  // A path (not a bare name looked up on PATH) is resolved against where the harness was started, so the probe and
  // the launch (cwd = journeys/) run the same interpreter.
  const py = raw && /[\\/]/.test(raw) ? resolve(raw) : raw;
  let r;
  if (!py) r = { python: null, why: 'no Python with Playwright was given (--python or WICKED_SELFTEST_PYTHON)' };
  else {
    const p = spawnSync(py, ['-I', '-B', '-c', 'import playwright.sync_api'], { encoding: 'utf8', env: journeyEnv(ctx.L?.root), timeout: 60_000 });
    r = p.status === 0 ? { python: py, why: null } : { python: null, why: `${py} cannot import playwright (${(p.stderr || p.error?.message || '').trim().slice(-200)})` };
  }
  ctx.state.journeyPython = r;
  return r;
}

/** Where Playwright keeps its browsers when PLAYWRIGHT_BROWSERS_PATH is not set (its documented defaults). */
function defaultBrowsersPath() {
  const home = homedir();
  if (process.platform === 'darwin') return join(home, 'Library', 'Caches', 'ms-playwright');
  if (process.platform === 'win32') return join(process.env.LOCALAPPDATA ?? join(home, 'AppData', 'Local'), 'ms-playwright');
  return join(process.env.XDG_CACHE_HOME ?? join(home, '.cache'), 'ms-playwright');
}

/** PLAYWRIGHT_BROWSERS_PATH as the journey (cwd journeys/) must see it: a relative path resolved against the start
 *  directory; Playwright's literal "0" (browsers inside the package) kept as is; unset = Playwright's default dir. */
export function browsersPath(v) {
  if (!v) return defaultBrowsersPath();
  return v === '0' ? v : resolve(v);
}

/** The browser's environment. HOME and the XDG dirs are UNDER THE RUN ROOT, so Chromium's own writes (fontconfig
 *  cache, crash dumps, profile bits) never land in the operator's home; the browsers are read from where Playwright
 *  installed them. No product state and no credential variable crosses over. */
function journeyEnv(root) {
  const home = root ? join(root, 'browser-home') : homedir();
  if (root) mkdirSync(home, { recursive: true });
  const env = {
    PATH: process.env.PATH ?? '', HOME: home, USERPROFILE: home, LANG: process.env.LANG ?? 'en_US.UTF-8', PYTHONDONTWRITEBYTECODE: '1',
    XDG_CACHE_HOME: join(home, '.cache'), XDG_CONFIG_HOME: join(home, '.config'), XDG_DATA_HOME: join(home, '.local', 'share'),
    // Resolved here: the journey runs from journeys/, so a relative path would point somewhere else.
    PLAYWRIGHT_BROWSERS_PATH: browsersPath(process.env.PLAYWRIGHT_BROWSERS_PATH),
  };
  // Playwright makes its browser profile and artifacts under os.tmpdir(): keep that under the root as well.
  const tmp = root ? join(home, 'tmp') : null;
  if (tmp) { mkdirSync(tmp, { recursive: true }); env.TMPDIR = tmp; env.TMP = tmp; env.TEMP = tmp; } else if (process.env.TMPDIR) env.TMPDIR = process.env.TMPDIR;
  for (const k of ['SystemRoot', 'LOCALAPPDATA']) if (process.env[k]) env[k] = process.env[k];
  return env;
}

/** Run one journey and fold its result into the step trace `t`. `state` is what the journey may read. */
export async function runJourney(ctx, t, journey, { state = {}, timeoutMs } = {}) {
  await ctx.ensureDaemon();
  const { python, why } = journeyPython(ctx);
  if (!python) { t.skip(why); return null; }
  const out = t.dir;
  const argv = ['-I', '-B', join(JOURNEYS_DIR, 'driver.py'), journey, '--origin', ctx.daemon.origin, '--out', out, '--state', JSON.stringify(state)];
  const logLines = [];
  const code = await new Promise((resolve) => {
    const child = spawn(python, argv, { cwd: JOURNEYS_DIR, env: journeyEnv(ctx.L.root), stdio: ['ignore', 'pipe', 'pipe'], signal: ctx.signal ?? undefined });
    const take = (b) => { for (const l of b.toString().split('\n')) if (l) { logLines.push(l); if (ctx.opts.verbose || / CHECK | ERROR/.test(l)) ctx.log(`    | ${l.slice(0, 220)}`); } };
    child.stdout.on('data', take);
    child.stderr.on('data', take);
    let timer = null;
    if (timeoutMs) timer = setTimeout(() => child.kill('SIGKILL'), timeoutMs);
    child.on('error', (e) => { logLines.push(`spawn error: ${e.message}`); clearTimeout(timer); resolve(-1); });
    child.on('close', (c) => { clearTimeout(timer); resolve(c); });
  });
  t.evidence('journey-log', logLines.join('\n'));
  const resPath = join(out, 'result.json');
  if (!existsSync(resPath)) throw new Error(`journey ${journey} left no result.json (exit ${code}); see ${t.stepId}/journey-log.json`);
  const res = JSON.parse(readFileSync(resPath, 'utf8'));
  const checks = Object.entries(res.checks ?? {});
  // A journey that crashed, or recorded no checks of its own, is an ERROR: never a failed assertion that
  // --expect-fail-steps could waive.
  if (!res.journey_checks) throw new Error(`journey ${journey} recorded no checks of its own (${res.error ?? 'no error'})`);
  if (res.error) throw new Error(`journey ${journey} did not run to its end: ${res.error}`);
  for (const [name, c] of checks) {
    const { ok, ...detail } = c;
    t.check(name, ok, JSON.stringify(detail), { evidence: `${t.stepId}/result.json` });
  }
  t.info('shots', (res.shots ?? []).join(', '));
  t.info('ui sent', (res.writes ?? []).join('; ') || 'nothing');
  if (res.blocked?.length) t.info('blocked off-origin requests', res.blocked.slice(0, 10).join('; '));
  return res;
}
