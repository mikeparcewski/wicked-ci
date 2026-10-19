// Seat + tool shims: node scripts under smoke/shims/, launched through a tiny wrapper written into the
// run's bin dir (a POSIX `sh` exec on unix, a `.cmd` twin on Windows — both always written). The
// wrapper carries the ABSOLUTE node path, so the engine's env-stripped children resolve them without
// `/usr/bin/env` or a shell. `pi` and `agy` get NO wrapper: the "not installed" seat is real absence.
import { chmodSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { IS_WIN } from './env.mjs';

const SHIMS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'shims');

/** The third live seat's registry key (and shim name) — see its SEATS row. */
export const JUDGE_SEAT_KEY = 'smoke-judge';

/** The roster the mixed-auth run exercises. `present: false` = deliberately NOT on PATH. */
export const SEATS = [
  { key: 'claude', shim: 'claude', present: true, behaviour: 'answers (signed in)' },
  { key: 'codex', shim: 'codex', present: true, behaviour: 'exits 1 "Not logged in" (401 class)' },
  { key: 'copilot', shim: 'copilot', present: true, behaviour: 'exits 1 "exceeded your monthly quota"' },
  { key: 'opencode', shim: 'opencode', present: true, behaviour: 'answers (free tier, no credential)' },
  { key: 'pi', shim: null, present: false, behaviour: 'not installed (no binary on PATH; no credential either unless WICKED_SMOKE_PI_CREDENTIAL=1)' },
  // v2 (DES-L5 S-CHAT-01): the ONE seat that speaks ACP over stdio — what a chat turn runs on. Its
  // overlay record carries `[cli.acp]` (shims/acp-agent.mjs), `enabled_for_council = false` and
  // `seat_eligible_for_work = false`, so the S04 roster above is exactly what it was (it is never
  // seated for a unit); S08 names it with `clis: ['acp-smoke']`.
  { key: 'acp-smoke', shim: 'acp-agent', present: true, behaviour: 'answers every chat turn over ACP (initialize / session/new / session/prompt); sleeps WICKED_SMOKE_ACP_SLEEP_MS or a per-prompt smoke-acp-sleep-ms=<n> token first; council-disabled and work-ineligible until S08' },
  // C5 (crew >= 0.13.0): ACP is removed from the seats, so the chat seat is a HEADLESS shim on the
  // wrapped carrier (shims/chat-agent.mjs); the overlay writes it INSTEAD of acp-smoke on a C5 crew,
  // with the same posture: council-disabled AND work-ineligible (S08 re-enables both before its own
  // restart). The work flag is explicit: from crew 0.15.2 (crew#916) the two roles are separate and
  // an omitted `seat_eligible_for_work` defaults to TRUE, so a council-off seat would otherwise be
  // re-seated onto S04's review units as the distinct evaluator — and this shim prints no VERDICT.
  { key: 'chat-smoke', shim: 'chat-agent', present: true, behaviour: 'C5 crews: answers every chat step headlessly (`chat-agent -p "<prompt>"`); sleeps WICKED_SMOKE_ACP_SLEEP_MS or a per-prompt smoke-acp-sleep-ms=<n> token first; council-disabled and work-ineligible until S08' },
  // The THIRD live seat (core-ts >= 0.7.40, wicked-core#774): a judge must be identity-distinct from
  // the unit's seat AND its creator, and when every such seat is benched the gate fails closed
  // (`judge_unavailable`) instead of skipping the judge. With only claude + opencode live, the
  // `verify` unit (evaluator opencode, creator claude) had no judge left and the bug run could not
  // deliver (crew 0.8.5 release smoke, run 37762305091). A custom registry key (crew has no
  // credential rule for it: `auth: unknown`, council-eligible), written LAST so routing is unchanged.
  { key: JUDGE_SEAT_KEY, shim: 'smoke-judge', present: true, behaviour: 'answers (no credential rule — auth unknown, council-eligible); the distinct judge the verify unit needs' },
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
  // C5 (crew >= 0.13.0): the chat seat's launcher is NAMED `claude` — on the interim host floor the
  // engine runs a governed unit only on a binary whose file stem is `claude` (its gate hook) or a
  // bounded codex, whatever the seat key (wicked-core `host_floor_keeps_a_check`). A subdirectory so
  // the bare `claude` on PATH stays the claude seat's own shim. See shims/chat-agent.mjs.
  // The judge seat gets the same claude-stem launcher (`<bin>/judge-seat/claude`): on the host floor
  // it is the second seat that may take a governed unit, so the evaluator differs from the creator.
  for (const [shimName, dirName] of [['chat-agent', CHAT_SEAT_DIR], ['smoke-judge', JUDGE_SEAT_DIR]]) {
    const script = join(SHIMS_DIR, `${shimName}.mjs`);
    const dir = join(L.bin, dirName);
    mkdirSync(dir, { recursive: true });
    const unixPath = join(dir, 'claude');
    writeFileSync(unixPath, wrapperUnix(process.execPath, script));
    if (!IS_WIN) chmodSync(unixPath, 0o755);
    writeFileSync(join(dir, 'claude.cmd'), wrapperCmd(process.execPath, script));
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
 *     retried on the wrapped carrier. The v1 seat shims speak only the headless one-shot contract, so
 *     the overlay OMITS `[cli.acp]` on their records — the registry's documented wholesale-replace
 *     hatch "to run a seat wrapped".
 *
 * The LAST record, `smoke-judge`, is the third live seat (see its SEATS row): a plain headless
 * record like the v1 seats, council-enabled, written last.
 *
 * The SIXTH record is the v2 exception: `acp-smoke` is a NEW key (the merged registry appends a user
 * record whose key matches no built-in), its `[cli.acp]` names the ACP-speaking shim
 * (shims/acp-agent.mjs, stdio transport), and it is `enabled_for_council = false` AND
 * `seat_eligible_for_work = false` so the mixed-auth roster S04 asserts is untouched: it neither votes
 * nor is seated for a unit. The work flag is written explicitly because from crew 0.15.2 (crew#916,
 * wicked-core#572) the two roles are read separately and an omitted `seat_eligible_for_work` means
 * TRUE — the engine then re-seated S04's reproduce / verify / review units onto the chat seat as the
 * distinct evaluator, its shim printed no `VERDICT:` line, and the run was cancelled (crew 0.15.2
 * release smoke, run 39233376132). Engines before the split ignore the key (it is optional, default
 * true), so it is safe on every crew the harness installs; the C5 chat seat `chat-smoke` takes the
 * same posture. Before C5, `acp-smoke` is the seat S08 opens a chat on — the ONLY place the
 * daemon's ACP path (`chat_ensure` → spawn → initialize → session/new → session/prompt) runs in the
 * smoke; before it, "a chat turn completes" was unprovable here (F-RC1-110/111/112 landed live).
 *
 * `pi` is deliberately NOT overlaid: the built-in bare `pi` must fail to resolve — that is the
 * `not_installed` seat.
 */
export const ACP_SEAT_KEY = 'acp-smoke';

/** The chat seat on a C5 crew (>= 0.13.0): headless, no `[cli.acp]` (ACP is gone from the seats). */
export const CHAT_SEAT_KEY = 'chat-smoke';
/** Its launcher's directory under the run's bin dir: `<bin>/chat-seat/claude` execs shims/chat-agent.mjs. */
export const CHAT_SEAT_DIR = 'chat-seat';
/**
 * C5 (crew >= 0.13.0): the judge seat's launcher directory — `<bin>/judge-seat/claude` execs
 * shims/smoke-judge.mjs. On the host floor only a claude-stem binary or a bounded codex may take a
 * governed unit (wicked-core `host_floor_keeps_a_check`); from core-ts 0.12.1 (wicked-core#976) every
 * other seat is benched for governed work up front. With codex benched for worktree-bound runs and
 * opencode / copilot host-floor benched, claude would be the ONLY governed seat and a bug run's
 * review units could never have an evaluator distinct from the creator: the engine refuses the plan
 * at the scope step (NoEligibleSeat, wicked-core#747). So on C5 the third live seat rides the claude
 * carrier: it is the distinct EVALUATOR, and opencode (benched for governed work only, still allowed
 * to judge) is the distinct JUDGE.
 */
export const JUDGE_SEAT_DIR = 'judge-seat';

/** The overlay's launcher for the judge seat: the claude-stem wrapper on C5, the plain shim before. */
export function judgeSeatBin({ c5 = false } = {}) {
  return c5 ? `${JUDGE_SEAT_DIR}/claude` : 'smoke-judge';
}

/** The seat S08 speaks to on the installed crew: the headless chat seat on C5, the ACP seat before. */
export function chatSeatKey({ c5 = false } = {}) {
  return c5 ? CHAT_SEAT_KEY : ACP_SEAT_KEY;
}

/**
 * `acpSeatForCouncil` (S08, crew ≥ 0.8.2): the ACP seat is written `enabled_for_council = true` and
 * `seat_eligible_for_work = true` — the chat's `answer-N` step is a unit, and a council-enabled seat
 * with work off is reviewer-only (never given a unit). From
 * crew 0.8.2 an ask is a team PATH (DES-ASK-TEAM-CHAT-001 Amendment 6): `POST /chats` admits the
 * DEFAULT roster and seats NAMED in `clis` by ONE rule (`chatSeatAdmission`), and that rule refuses
 * a council-disabled seat ("disabled for the council, so it takes no turn") — the engine's roster
 * (`registry_roster`) does not even list one. So the seat the chat step speaks to must be
 * council-enabled for THAT daemon. S08 is the last step that convenes a seat (S09/S10 launch no
 * work), so it re-writes the overlay before its own restart and S04's mixed roster is untouched.
 */
export function writeCouncilOverlay(L, { acpSeatForCouncil = false, c5 = false } = {}) {
  const bin = (name) => join(L.bin, name).replace(/\\/g, '/');
  const seats = [
    { key: 'claude', display: 'Claude Code (smoke shim)', bin: bin('claude'), inv: `${bin('claude')} -p "{PROMPT}"` },
    { key: 'codex', display: 'Codex (smoke shim, signed out)', bin: bin('codex'), inv: `${bin('codex')} exec --skip-git-repo-check "{PROMPT}"` },
    { key: 'copilot', display: 'Copilot (smoke shim, quota)', bin: bin('copilot'), inv: `${bin('copilot')} -p "{PROMPT}"` },
    { key: 'opencode', display: 'OpenCode (smoke shim, free tier)', bin: bin('opencode'), inv: `${bin('opencode')} run "{PROMPT}"` },
    // C5 (crew >= 0.13.0): no seat speaks ACP — the chat seat is the headless `chat-smoke` record
    // (no `[cli.acp]`); before C5 it is the ACP stdio seat. Either way council-disabled AND
    // work-ineligible until S08 (both flags explicit — see the overlay doc above).
    c5
      ? { key: CHAT_SEAT_KEY, display: 'Chat seat (smoke shim, headless claude carrier)', bin: bin(`${CHAT_SEAT_DIR}/claude`), inv: `${bin(`${CHAT_SEAT_DIR}/claude`)} -p "{PROMPT}"`, council: acpSeatForCouncil, work: acpSeatForCouncil }
      : { key: ACP_SEAT_KEY, display: 'ACP seat (smoke shim, stdio)', bin: bin('acp-agent'), inv: `${bin('acp-agent')} -p "{PROMPT}"`, council: acpSeatForCouncil, work: acpSeatForCouncil, acp: bin('acp-agent') },
    // LAST, so the engine's seat order (and the S04 routing it asserts) is what it was; the judge
    // rotation reaches it after the dead seats. On C5 it launches through the claude-stem wrapper
    // (see JUDGE_SEAT_DIR), so the host floor lets it carry governed units.
    { key: JUDGE_SEAT_KEY, display: 'Judge seat (smoke shim, third live seat)', bin: bin(judgeSeatBin({ c5 })), inv: `${bin(judgeSeatBin({ c5 }))} -p "{PROMPT}"` },
  ];
  const toml = seats.map((s) => [
    '[[cli]]',
    `key = "${s.key}"`,
    `display_name = "${s.display}"`,
    `binary = "${s.bin}"`,
    `headless_invocation = '${s.inv}'`,
    `enabled_for_council = ${s.council === false ? 'false' : 'true'}`,
    // Only the chat seat declares its work role; every other record keeps the engine default (true).
    ...(typeof s.work === 'boolean' ? [`seat_eligible_for_work = ${s.work}`] : []),
    // `[cli.acp]` binds to the `[[cli]]` record above it (TOML sub-table of the last array element).
    // `acp_input_governance = true`: the engine dispatches a path's `answer-N` step (executes_code:
    // false) to a seat only when its ACP adapter is admitted to input governance; without it the
    // unit is REFUSED ("not admitted to input governance") and S08's turn never reaches the shim.
    ...(s.acp ? ['', '[cli.acp]', `binary = "${s.acp}"`, 'transport = "stdio"', 'acp_input_governance = true'] : []),
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
