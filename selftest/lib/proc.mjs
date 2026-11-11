// Child-process helpers: argv arrays only (no shell), captured output, bounded time.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { IS_WIN } from './env.mjs';
import { tap } from './tap.mjs';

/** Run `argv` to completion; returns {status, stdout, stderr}. Never throws on a non-zero exit. */
export function run(argv, { cwd, env, timeoutMs = 600_000, input } = {}) {
  const [cmd, ...args] = argv;
  const r = spawnSync(cmd, args, {
    cwd,
    env,
    encoding: 'utf8',
    timeout: timeoutMs,
    input,
    maxBuffer: 64 * 1024 * 1024,
    windowsHide: true,
  });
  const out = {
    status: r.status,
    signal: r.signal,
    error: r.error ? String(r.error.message ?? r.error) : null,
    stdout: r.stdout ?? '',
    stderr: r.stderr ?? '',
  };
  tap('cli', { argv, code: out.status, signal: out.signal, stdout: out.stdout.slice(-16384), stderr: out.stderr.slice(-16384) });
  return out;
}

/** Like {@link run} but throws with the tail of both streams when the exit is non-zero. */
export function mustRun(argv, opts = {}) {
  const r = run(argv, opts);
  if (r.status !== 0) {
    const tail = (s) => s.split('\n').slice(-25).join('\n');
    throw new Error(`\`${argv.join(' ')}\` exited ${r.status ?? r.signal ?? r.error}\n${tail(r.stdout)}\n${tail(r.stderr)}`);
  }
  return r;
}

/** Spawn detached-from-terminal but tracked; stdout+stderr appended to `logFd`. */
export function spawnLogged(argv, { cwd, env, logFd }) {
  const [cmd, ...args] = argv;
  const child = spawn(cmd, args, { cwd, env, stdio: ['ignore', logFd, logFd], windowsHide: true });
  tap('cli', { argv, spawned: true, pid: child.pid ?? null, code: null, stdout: '(to the log file)', stderr: '' });
  child.on('exit', (code, signal) => tap('cli', { argv, exited: true, code, signal, stdout: '(to the log file)', stderr: '' }));
  return child;
}

/** git with a pinned no-sign identity, in `cwd`. Throws on failure. */
export function git(cwd, env, ...args) {
  return mustRun(['git', '-c', 'commit.gpgsign=false', ...args], { cwd, env }).stdout.trim();
}

export function gitTry(cwd, env, ...args) {
  return run(['git', '-c', 'commit.gpgsign=false', ...args], { cwd, env });
}

/**
 * The npm CLI entry the same node that runs us ships with — `node <npm-cli.js>` is the one invocation
 * that is byte-identical on macOS / Linux / Windows (no `.cmd` shim, no shell). Falls back to `npm` on
 * PATH when the bundled copy is not where node installs put it.
 */
export function npmArgv() {
  const nodeDir = dirname(process.execPath);
  const candidates = IS_WIN
    ? [join(nodeDir, 'node_modules', 'npm', 'bin', 'npm-cli.js')]
    : [join(nodeDir, '..', 'lib', 'node_modules', 'npm', 'bin', 'npm-cli.js'), join(nodeDir, 'node_modules', 'npm', 'bin', 'npm-cli.js')];
  for (const c of candidates) if (existsSync(c)) return [process.execPath, c];
  return [IS_WIN ? 'npm.cmd' : 'npm'];
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll `fn` until it returns a non-null value or the deadline passes (returns null then). */
export async function until(fn, { ms = 60_000, every = 500 } = {}) {
  const deadline = Date.now() + ms;
  let last = null;
  while (Date.now() < deadline) {
    last = await fn();
    if (last !== null && last !== undefined && last !== false) return last;
    await sleep(every);
  }
  return null;
}

/**
 * Every process still running whose command line names the run root, other than this harness: what the daemon left
 * behind (a document bridge, a seat CLI) after it was stopped. Each is sent SIGTERM, then SIGKILL after `graceMs`, so
 * a self-test never leaves a process holding its (about to be removed) root. Returns what it found. POSIX only (`ps`);
 * on Windows it reports that it could not look.
 */
export async function sweepRoot(root, { graceMs = 3000 } = {}) {
  if (process.platform === 'win32') return { swept: [], note: 'not checked on Windows' };
  const list = () => {
    const r = spawnSync('ps', ['-ax', '-o', 'pid=,ppid=,command='], { encoding: 'utf8' });
    if (r.status !== 0) return [];
    const rows = r.stdout.split('\n').map((l) => l.trim().match(/^(\d+)\s+(\d+)\s+(.*)$/)).filter(Boolean).map((m) => ({ pid: Number(m[1]), ppid: Number(m[2]), command: m[3] }));
    // This harness and every process ABOVE it (a wrapper whose argv names the root, e.g. `job … --root <root>`) are
    // not leftovers: only what the daemon left behind is.
    const parent = new Map(rows.map((x) => [x.pid, x.ppid]));
    const mine = new Set();
    for (let p = process.pid; p > 1 && !mine.has(p); p = parent.get(p) ?? 0) mine.add(p);
    return rows.filter((x) => !mine.has(x.pid) && x.command.includes(root));
  };
  const found = list();
  for (const x of found) { try { process.kill(x.pid, 'SIGTERM'); } catch { /* gone */ } }
  if (found.length) await sleep(graceMs);
  for (const x of list()) { try { process.kill(x.pid, 'SIGKILL'); } catch { /* gone */ } }
  return { swept: found.map((x) => ({ pid: x.pid, command: x.command.split(root).join('<root>').slice(0, 300) })) };
}
