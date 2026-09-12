// Seat + tool shims: node scripts under smoke/shims/, launched through a tiny wrapper written into the
// run's bin dir (a POSIX `sh` exec on unix, a `.cmd` twin on Windows — both always written). The
// wrapper carries the ABSOLUTE node path, so the engine's env-stripped children resolve them without
// `/usr/bin/env` or a shell. `pi` and `agy` get NO wrapper: the "not installed" seat is real absence.
import { chmodSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { IS_WIN } from './env.mjs';

const SHIMS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'shims');

/** The roster the mixed-auth run exercises. `present: false` = deliberately NOT on PATH. */
export const SEATS = [
  { key: 'claude', shim: 'claude', present: true, behaviour: 'answers (signed in)' },
  { key: 'codex', shim: 'codex', present: true, behaviour: 'exits 1 "Not logged in" (401 class)' },
  { key: 'copilot', shim: 'copilot', present: true, behaviour: 'exits 1 "exceeded your monthly quota"' },
  { key: 'opencode', shim: 'opencode', present: true, behaviour: 'answers (free tier, no credential)' },
  { key: 'pi', shim: null, present: false, behaviour: 'not installed (no binary on PATH; no credential either unless WICKED_SMOKE_PI_CREDENTIAL=1)' },
];

/** Tools the engine/daemon spawn that must never reach the real thing (or are absent on a fresh
 *  machine and would fail the run): `gh` (deliver), `wicked-estate` (onboarding index), `wicked-core`
 *  (the CLI the wrapped claude carrier probes to arm input governance — see shims/wicked-core.mjs). */
export const TOOLS = ['gh', 'wicked-estate', 'wicked-core'];

function wrapperUnix(node, script) {
  return `#!/bin/sh\nexec "${node}" "${script}" "$@"\n`;
}

function wrapperCmd(node, script) {
  return `@echo off\r\n"${node}" "${script}" %*\r\n`;
}

export function writeShims(L) {
  mkdirSync(L.bin, { recursive: true });
  const written = [];
  const names = [...SEATS.filter((s) => s.present).map((s) => s.shim), ...TOOLS];
  for (const name of names) {
    const script = join(SHIMS_DIR, `${name}.mjs`);
    if (!existsSync(script)) throw new Error(`missing shim script ${script}`);
    const unixPath = join(L.bin, name);
    writeFileSync(unixPath, wrapperUnix(process.execPath, script));
    if (!IS_WIN) chmodSync(unixPath, 0o755);
    writeFileSync(join(L.bin, `${name}.cmd`), wrapperCmd(process.execPath, script));
    written.push(name);
  }
  return written;
}

/**
 * The council registry overlay `$HOME/.config/wicked-council/clis.toml` (HOME is hermetic). Two
 * reasons it is REQUIRED for a deterministic smoke, both observed live on crew 0.7.32:
 *
 *  1. The daemon PREPENDS its bundled ACP bridges' `node_modules/.bin` to PATH at boot
 *     (`core/bridge-path.ts`), and that directory carries a REAL `codex` (`@openai/codex`, a
 *     dependency of `codex-acp`) — so a bare `codex` in the built-in record resolves to the real CLI
 *     ahead of any shim and the ballot makes a network call to OpenAI with whatever key it finds.
 *     The overlay pins every shimmed seat's `binary` / `headless_invocation` to the ABSOLUTE shim path.
 *  2. Every built-in seat has an `[cli.acp]` block; a worker turn on such a seat goes over the ACP
 *     transport (`claude-agent-acp` → the real Claude Agent SDK) and an auth refusal there is NOT
 *     retried on the wrapped carrier. The v1 shims speak only the headless one-shot contract, so the
 *     overlay OMITS `[cli.acp]` — the registry's documented wholesale-replace hatch "to run a seat
 *     wrapped". (An ACP-speaking shim is the v2 item that lets S08 chat complete.)
 *
 * `pi` is deliberately NOT overlaid: the built-in bare `pi` must fail to resolve — that is the
 * `not_installed` seat.
 */
export function writeCouncilOverlay(L) {
  const bin = (name) => join(L.bin, name).replace(/\\/g, '/');
  const seats = [
    { key: 'claude', display: 'Claude Code (smoke shim)', bin: bin('claude'), inv: `${bin('claude')} -p "{PROMPT}"` },
    { key: 'codex', display: 'Codex (smoke shim, signed out)', bin: bin('codex'), inv: `${bin('codex')} exec --skip-git-repo-check "{PROMPT}"` },
    { key: 'copilot', display: 'Copilot (smoke shim, quota)', bin: bin('copilot'), inv: `${bin('copilot')} -p "{PROMPT}"` },
    { key: 'opencode', display: 'OpenCode (smoke shim, free tier)', bin: bin('opencode'), inv: `${bin('opencode')} run "{PROMPT}"` },
  ];
  const toml = seats.map((s) => [
    '[[cli]]',
    `key = "${s.key}"`,
    `display_name = "${s.display}"`,
    `binary = "${s.bin}"`,
    `headless_invocation = '${s.inv}'`,
    'enabled_for_council = true',
    '',
  ].join('\n')).join('\n');
  const dir = join(L.home, '.config', 'wicked-council');
  mkdirSync(dir, { recursive: true });
  const path = join(dir, 'clis.toml');
  writeFileSync(path, `# written by wicked-smoke — see smoke/lib/shims.mjs writeCouncilOverlay\n${toml}`);
  return path;
}

/**
 * Host tools the PRODUCT needs that are not wicked-* artifacts and must not be shimmed: `uv` (crew's
 * skills seed runs `uv sync` for the garden bundle's pyproject — a missing uv BLOCKS the publish) and
 * a Python for uv to find. Each is resolved from the HOST PATH once and exposed through a wrapper that
 * execs the absolute binary — never by putting the host directory on the hermetic PATH (that would
 * leak a real `pi` or `claude` next to it). Returns {found: [...], missing: [...]}.
 */
export const PASSTHROUGH_TOOLS = ['uv', 'python3', 'python'];

export function writePassthroughs(L) {
  const found = [];
  const missing = [];
  for (const name of PASSTHROUGH_TOOLS) {
    const abs = resolveOnHostPath(name);
    if (!abs) { missing.push(name); continue; }
    const unixPath = join(L.bin, name);
    writeFileSync(unixPath, `#!/bin/sh\nexec "${abs}" "$@"\n`);
    if (!IS_WIN) chmodSync(unixPath, 0o755);
    writeFileSync(join(L.bin, `${name}.cmd`), `@echo off\r\n"${abs}" %*\r\n`);
    found.push(`${name} -> ${abs}`);
  }
  return { found, missing };
}

function resolveOnHostPath(name) {
  const dirs = (process.env.PATH ?? process.env.Path ?? '').split(IS_WIN ? ';' : ':').filter(Boolean);
  const exts = IS_WIN ? (process.env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';') : [''];
  for (const d of dirs) {
    for (const ext of exts) {
      const p = join(d, name + ext.toLowerCase());
      if (existsSync(p)) return p;
      const P = join(d, name + ext);
      if (existsSync(P)) return P;
    }
  }
  return null;
}

/**
 * Credential ARTIFACTS the daemon's cheap sign-in probe reads (seat-signin.ts) under the worker home,
 * so crew hands the engine a roster where codex / copilot look signed in and the ENGINE has to learn
 * the truth from the ballot (401, quota) — the F-7R2-006 / F-7R3-001 class. opencode gets nothing
 * (free tier, `auth: not_required`); claude gets a completed-login marker.
 *
 * `pi` gets NO credential by default: a fresh machine without pi has no pi login either, so crew's
 * probe reads `signed_out` and the launcher benches it ("pi (signed out — launcher)"). With
 * `WICKED_SMOKE_PI_CREDENTIAL=1` the harness writes one, and the engine has to learn `not_installed`
 * from the ballot's spawn failure instead. OBSERVED on core-ts 0.7.23 / crew 0.7.32 (wicked-smoke
 * run, 2026-09-12): the ballot ledger benched codex (not_logged_in) and copilot (quota_exhausted)
 * but NOT pi after four `spawn_failed / not_installed` round-1 ballots, `evaluator_distinct` seated
 * both review units on the not-installed pi, and the run escalated ("ACP unavailable for 'pi'").
 * That is the F-7R3-001 class still open for `not_installed`; the opt-in keeps it reproducible.
 */
export const PI_CREDENTIAL_ENV = 'WICKED_SMOKE_PI_CREDENTIAL';

export function writeSeatCredentials(L, { piCredential = process.env[PI_CREDENTIAL_ENV] === '1' } = {}) {
  const w = (rel, content) => {
    const p = join(L.worker, ...rel);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, content);
  };
  w(['claude', '.claude.json'], JSON.stringify({ oauthAccount: { emailAddress: 'smoke@example.invalid', accountUuid: 'smoke' } }, null, 1));
  w(['codex', 'auth.json'], JSON.stringify({ OPENAI_API_KEY: 'smoke-expired-key' }));
  w(['copilot', 'config.json'], JSON.stringify({ lastLoggedInUser: 'smoke-bot', loggedInUsers: ['smoke-bot'] }));
  if (piCredential) w(['pi', 'auth.json'], JSON.stringify({ token: 'smoke-token' }));
  return { piCredential };
}
