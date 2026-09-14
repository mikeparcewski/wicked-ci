// The daemon under test: `node <crew>/dist/cli/index.js serve --port <free> --db <state>/core.db`,
// hermetic env, stdout+stderr appended to <root>/daemon.log. Start waits for /health; stop sends
// SIGTERM and measures how long the exit took (S10 asserts ≤ 10 s).
import { closeSync, existsSync, openSync, readFileSync, appendFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { hermeticEnv } from './env.mjs';
import { spawnLogged, sleep } from './proc.mjs';

export function freePort() {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

export class Daemon {
  /** `bootTimeoutMs`: how long a start (and a re-check) may wait for /health — the CLI passes the
   *  step budget (`--step-timeout`, ≥ 300 s), because a COLD first boot publishes the garden bundle
   *  (`uv sync` of its pyproject) and took 11 minutes on a loaded workstation where a runner takes 5 s. */
  constructor(L, crewBin, log, { bootTimeoutMs = 300_000 } = {}) {
    this.L = L;
    this.crewBin = crewBin;
    this.log = log;
    this.bootTimeoutMs = bootTimeoutMs;
    this.child = null;
    this.port = null;
    this.env = null;
    this.starts = 0;
    this.lastStopMs = null;
    this.lastExitCode = null;
    this.healthy = false;
  }

  /** Wait until /health answers (a start that timed out may still come up under host load). */
  async waitHealthy({ timeoutMs = this.bootTimeoutMs } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (!this.child) throw new Error(`daemon is not running (last exit ${this.lastExitCode})`);
      try {
        const res = await fetch(`${this.origin}/api/v1/health`);
        if (res.ok) { this.healthy = true; return; }
      } catch { /* not yet */ }
      await sleep(500);
    }
    throw new Error(`daemon still not healthy after ${timeoutMs / 1000}s; tail:\n${this.logTail(20)}`);
  }

  get origin() {
    return `http://127.0.0.1:${this.port}`;
  }

  /**
   * `extraEnv`: variables laid OVER the hermetic env for this and every later start until replaced
   * (a step that needs the daemon booted with a product knob — S08's `WICKED_CHAT_TURN_SECS` — says
   * so here rather than reaching into the env). Pass `{}` to clear.
   */
  async start({ timeoutMs = this.bootTimeoutMs, extraEnv } = {}) {
    if (this.child) throw new Error('daemon already running');
    this.port = this.port ?? (await freePort());
    if (extraEnv !== undefined) this.extraEnv = extraEnv;
    this.env = { ...hermeticEnv(this.L, this.port), ...(this.extraEnv ?? {}) };
    this.starts += 1;
    this.healthy = false;
    const fd = openSync(this.L.daemonLog, 'a');
    const extra = Object.entries(this.extraEnv ?? {}).map(([k, v]) => `${k}=${v}`).join(' ');
    appendFileSync(this.L.daemonLog, `\n===== wicked-smoke daemon start #${this.starts} port=${this.port} ${new Date().toISOString()}${extra ? ` ${extra}` : ''} =====\n`);
    const argv = [process.execPath, this.crewBin, 'serve', '--port', String(this.port), '--db', `${this.L.state}/core.db`];
    this.log(`daemon: start #${this.starts} on :${this.port}${extra ? ` (${extra})` : ''}`);
    const t0 = Date.now();
    this.child = spawnLogged(argv, { cwd: this.L.root, env: this.env, logFd: fd });
    this.exited = new Promise((resolve) => {
      this.child.on('exit', (code, signal) => {
        this.lastExitCode = code ?? signal;
        this.child = null;
        closeSync(fd);
        resolve({ code, signal });
      });
    });
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (!this.child) throw new Error(`daemon exited during boot (code ${this.lastExitCode}); tail:\n${this.logTail(30)}`);
      try {
        const res = await fetch(`${this.origin}/api/v1/health`);
        if (res.ok) {
          this.bootMs = Date.now() - t0;
          if (this.firstBootMs === undefined) this.firstBootMs = this.bootMs;
          this.healthy = true;
          this.log(`daemon: healthy after ${(this.bootMs / 1000).toFixed(1)}s`);
          return;
        }
      } catch { /* not yet */ }
      await sleep(500);
    }
    throw new Error(`daemon did not become healthy within ${timeoutMs / 1000}s; tail:\n${this.logTail(30)}`);
  }

  /** SIGTERM, wait up to `graceMs`, then SIGKILL. Returns {exitedInTime, ms}. */
  async stop({ graceMs = 10_000 } = {}) {
    if (!this.child) return { exitedInTime: true, ms: 0, alreadyDown: true };
    const t0 = Date.now();
    this.healthy = false;
    this.child.kill('SIGTERM');
    const outcome = await Promise.race([this.exited, sleep(graceMs).then(() => null)]);
    const ms = Date.now() - t0;
    if (outcome === null) {
      this.log(`daemon: did not exit within ${graceMs} ms after SIGTERM — SIGKILL`);
      try { this.child?.kill('SIGKILL'); } catch { /* gone */ }
      await Promise.race([this.exited, sleep(5000)]);
      this.lastStopMs = ms;
      return { exitedInTime: false, ms };
    }
    this.lastStopMs = ms;
    this.log(`daemon: exited in ${ms} ms (${JSON.stringify(outcome)})`);
    return { exitedInTime: true, ms, outcome };
  }

  async restart(opts = {}) {
    await this.stop();
    await this.start(opts);
  }

  logText() {
    return existsSync(this.L.daemonLog) ? readFileSync(this.L.daemonLog, 'utf8') : '';
  }

  logTail(n) {
    return this.logText().split('\n').slice(-n).join('\n');
  }

  /** Count log lines matching `re` since the given offset (default: whole log). */
  countInLog(re, sinceOffset = 0) {
    const text = this.logText().slice(sinceOffset);
    let n = 0;
    for (const line of text.split('\n')) if (re.test(line)) n += 1;
    return n;
  }

  logOffset() {
    return this.logText().length;
  }

  /** Lines matching `re` since offset (bounded). */
  grepLog(re, sinceOffset = 0, max = 20) {
    const out = [];
    for (const line of this.logText().slice(sinceOffset).split('\n')) {
      if (re.test(line)) { out.push(line.slice(0, 400)); if (out.length >= max) break; }
    }
    return out;
  }
}
