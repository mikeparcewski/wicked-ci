// Child-process helpers: argv arrays only (no shell), captured output, bounded time.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { IS_WIN } from './env.mjs';

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
  return {
    status: r.status,
    signal: r.signal,
    error: r.error ? String(r.error.message ?? r.error) : null,
    stdout: r.stdout ?? '',
    stderr: r.stderr ?? '',
  };
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
  return spawn(cmd, args, { cwd, env, stdio: ['ignore', logFd, logFd], windowsHide: true });
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
