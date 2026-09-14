// Shared by every seat shim: argv → prompt, prompt → turn kind, one NDJSON call record per invocation.
// A shim is a stand-in for a coding-agent CLI the engine spawns headlessly (`claude -p "<prompt>"`,
// `codex exec … "<prompt>"`, `opencode run "<prompt>"`), for a council BALLOT, an agent JUDGE turn, or a
// WORKER turn. It never calls a model and never touches the network.
import { appendFileSync, existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

/** The shim name of this process, for records appended after {@link record} (the verdict line). */
let currentShim = 'shim';

export function record(shim, extra = {}) {
  currentShim = shim;
  const log = process.env.WICKED_SMOKE_SHIM_LOG;
  const argv = process.argv.slice(2);
  const prompt = promptOf(argv);
  const rec = {
    t: new Date().toISOString(),
    shim,
    cwd: process.cwd(),
    argv: argv.map((a) => (a.length > 200 ? `${a.slice(0, 200)}…(${a.length})` : a)),
    kind: prompt ? kindOf(prompt) : 'noprompt',
    promptHead: prompt ? prompt.slice(0, 600) : null,
    ...extra,
  };
  if (log) {
    try { appendFileSync(log, `${JSON.stringify(rec)}\n`); } catch { /* the log is diagnostics only */ }
  }
  return { argv, prompt, kind: rec.kind };
}

/**
 * One more NDJSON record for a shim that does several things per process (the ACP seat records one
 * line per JSON-RPC method, after {@link record} logged the spawn). Same log, same shape (`t` +
 * `shim` + whatever the caller adds); diagnostics only — a write failure is swallowed like above.
 */
export function appendRecord(rec) {
  const log = process.env.WICKED_SMOKE_SHIM_LOG;
  if (!log) return;
  try { appendFileSync(log, `${JSON.stringify({ t: new Date().toISOString(), ...rec })}\n`); } catch { /* diagnostics only */ }
}

/**
 * The prompt is ONE argv element. The engine's wrapped runner places it after a `--` guard when the
 * preceding token is not a flag, or as the value of `-p` (claude) / the positional after `exec` (codex)
 * / `run` (opencode); it also injects flags whose VALUES can be longer than the prompt — the
 * `--disallowedTools` rule list (`Read(…),Edit(…),Bash(sudo:*),…`), `--settings`, `--plugin-dir` — so
 * "the longest argument" is wrong. Resolution: the element after `--`; else the element after `-p`
 * that is not itself a flag; else the longest element that is not a flag value.
 */
export function promptOf(argv) {
  const guard = argv.indexOf('--');
  if (guard >= 0 && argv[guard + 1] !== undefined) return argv[guard + 1];
  const FLAGS_WITH_VALUE = new Set(['--settings', '--setting-sources', '--permission-mode', '--disallowedTools', '--allowedTools', '--plugin-dir', '--output-format', '--model', '--mcp-config', '--add-dir', '--append-system-prompt', '--system-prompt', '-C', '--cd', '--sandbox', '-m', '--agent', '--format']);
  const values = new Set();
  for (let i = 0; i < argv.length; i++) if (FLAGS_WITH_VALUE.has(argv[i]) && argv[i + 1] !== undefined) values.add(i + 1);
  const p = argv.indexOf('-p');
  if (p >= 0) {
    for (let i = p + 1; i < argv.length; i++) {
      if (values.has(i)) { i += 0; continue; }
      if (argv[i].startsWith('-')) continue;
      return argv[i];
    }
  }
  let best = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (values.has(i) || a.startsWith('-')) continue;
    if (/^(Read|Edit|Write|Bash)\(/.test(a)) continue;
    if (best === null || a.length > best.length) best = a;
  }
  return best && best.length > 20 ? best : null;
}

/** ballot | judge | triage | worker */
export function kindOf(prompt) {
  if (/RECOMMENDATION/.test(prompt) && /TOP[_ ]RISK/i.test(prompt)) return 'ballot';
  if (/^You are a strict reviewer/.test(prompt.trim()) || (/\bCRITERION:/.test(prompt) && /\bWORK:/.test(prompt))) return 'judge';
  // The engine's FAILURE TRIAGE judge: asked after a unit fails, answers one of three DECISION lines.
  if (/DECISION: RETRY_WITH_FLAG/.test(prompt) && /DECISION: ESCALATE/.test(prompt)) return 'triage';
  return 'worker';
}

/** The failure-triage verdict: a human decides (the smoke never lets a shim retry a broken seam). */
export const TRIAGE_ESCALATE = 'DECISION: ESCALATE\nsmoke shim: a failed unit is a seam for a human (or the harness) to judge, never a blind retry.';

export function isVersionProbe(argv) {
  return argv.length > 0 && argv.every((a) => a === '--version' || a === '-v' || a === 'version' || a === '-V');
}

export const BALLOT = ['RECOMMENDATION: 1', 'TOP_RISK: none', 'CHANGE_MY_MIND: no', 'DISQUALIFIER: none'].join('\n');

/**
 * The evaluator-verdict convention (wicked-core #498, core-ts ≥ 0.7.26): the engine appends ONE sentence
 * to every EVALUATOR unit's prompt — `||| VERDICT (evaluator unit): make the LAST line of your output
 * exactly VERDICT: PASS or VERDICT: FAIL, findings above it; no verdict line = FAIL (human gate)` — and
 * from core-ts 0.7.27 (FIX-IT-ALL L1 PR-1A, core #488) an evaluator output whose last VERDICT line is
 * not PASS is DENIED into an escalation gate (`gateEscalated.condition: verdict_not_pass`,
 * `denialSource: evaluator_verdict`) instead of being recorded PASS. A shim that never says
 * `VERDICT: PASS` would therefore park every review unit on 0.7.27, so an evaluator turn ends with the
 * line — and S04 can arm ONE deliberate `VERDICT: FAIL` (F-RC1-131) through a token file the shim
 * consumes: `WICKED_SMOKE_VERDICT_FAIL_ONCE` names the path; while the file exists the next evaluator
 * turn renames it away (the consume) and answers FAIL with a finding above the line.
 */
export const EVALUATOR_CONVENTION_RE = /VERDICT \(evaluator unit\): make the LAST line of your output exactly VERDICT: PASS or VERDICT: FAIL/;
export const VERDICT_FAIL_ONCE_ENV = 'WICKED_SMOKE_VERDICT_FAIL_ONCE';

export function isEvaluatorPrompt(prompt) {
  return EVALUATOR_CONVENTION_RE.test(prompt);
}

/** Consume the fail-once token when armed: `true` exactly once per token (the rename is the claim). */
export function consumeFailOnce() {
  const token = process.env[VERDICT_FAIL_ONCE_ENV];
  if (!token || !existsSync(token)) return false;
  try {
    renameSync(token, `${token}.consumed-${process.pid}-${Date.now()}`);
    return true;
  } catch {
    return false; // another evaluator turn claimed it first
  }
}

/**
 * The lines an evaluator turn ends with (empty for a non-evaluator prompt), recorded in the shim log
 * as `kind: 'verdict'` so the harness can prove which turn answered what.
 */
export function verdictLines(prompt) {
  if (!isEvaluatorPrompt(prompt)) return [];
  const fail = consumeFailOnce();
  appendRecord({ shim: currentShim, kind: 'verdict', verdict: fail ? 'FAIL' : 'PASS', failOnceConsumed: fail, cwd: process.cwd(), argv: [] });
  if (fail) {
    return ['', 'Finding (deliberate, wicked-smoke S-L1): the harness armed ONE failing verdict to prove the evaluator-verdict gate parks the run instead of recording PASS (F-RC1-131). Nothing about the change itself is wrong; approve to retry and this seat answers PASS.', 'VERDICT: FAIL'];
  }
  return ['', 'VERDICT: PASS'];
}
export const JUDGE_PASS = ['PASS', 'the work meets the criterion (smoke shim: deterministic judge)', 'PASS'].join('\n');

/**
 * The WORKER turn. The only phase allowed to change the tree is the `fix` phase of the seeded `bug`
 * workflow — the prompt the engine builds carries the phase id in its scope line, and the fixed issue
 * text never contains the word "fix", so the match is unambiguous. Read-only phases (triage /
 * reproduce / verify) print prose and touch nothing (the worktree guard would deny them otherwise).
 */
export function workerTurn(prompt) {
  const body = workerBody(prompt);
  const verdict = verdictLines(prompt);
  return verdict.length === 0 ? body : `${body}\n${verdict.join('\n')}`;
}

/** The turn's prose (and the fix phase's write) — the verdict line, when owed, comes after it. */
function workerBody(prompt) {
  const cwd = process.cwd();
  const target = join(cwd, 'src', 'add.js');
  // The engine spells the phase out: "… ||| PHASE SCOPE: this is the <phase> phase. …" — read it from
  // there; the free-text fallback stays for a def that words its scope differently.
  const scoped = prompt.match(/PHASE SCOPE: this is the (\w[\w-]*) phase/i);
  const phase = scoped ? scoped[1].toLowerCase() : /\bfix\b/i.test(prompt) ? 'fix' : /\btriage\b/i.test(prompt) ? 'triage' : /\breproduce\b/i.test(prompt) ? 'reproduce' : /\bverify\b|\breview\b/i.test(prompt) ? 'verify' : 'unknown';
  // The engine's SUBSTANCE gate rejects a governed unit whose Ok output carries neither ≥ 200 trimmed
  // chars of prose nor a worktree change ("phase produced no reviewable substance") — every answer
  // below is a full deliverable, not a one-liner.
  const footer = ['', '— wicked-smoke seat shim (deterministic stand-in for the coding-agent CLI; no model was called). '
    + 'Evidence for this turn is the text above and, where applicable, the diff in the worktree; the engine re-derives done from those, never from this sentence.'].join('\n');
  if (phase === 'fix' && existsSync(target)) {
    const src = readFileSync(target, 'utf8');
    if (/a\s*-\s*b/.test(src)) {
      writeFileSync(target, src.replace(/a\s*-\s*b/, 'a + b'));
      return ['## Fix applied', '', 'Root cause: `add()` in `src/add.js` returned `a - b` — a sign error that makes every caller receive the difference instead of the sum.', 'Change: `return a - b;` → `return a + b;` (one line, one file). The exported name and `test/add.test.js` are unchanged, as the issue requires.', 'Verification: `node --test test/` — `add returns the sum` and `sum folds with add` both pass after the change.', 'Changed files: src/add.js', footer].join('\n');
    }
    return ['## Fix — nothing to change', '', '`src/add.js` already returns `a + b`; the correction described in the issue is present in this worktree. No file was modified in this turn; the verification in the next phase re-runs the repository checks against this state.', footer].join('\n');
  }
  if (phase === 'triage') return ['## Triage', '', 'Defect: `add(a, b)` in `src/add.js` returns `a - b` (the difference) where the sum is expected. Severity: high — every caller of `add()` (including `sum()` in `src/index.js`) gets the wrong value.', 'Scope: one arithmetic operator on one line of one file; no API change, no test change needed.', 'Reproduction: `npm test` runs `test/add.test.js`, which expects `add(2, 3) === 5` and gets `-1`.', 'Plan: the fix phase changes `a - b` to `a + b` in `src/add.js`; the verify phase re-runs `npm test`.', footer].join('\n');
  if (phase === 'reproduce') return ['## Reproduction', '', 'Ran the repository check: `npm test` → `node --test test/`.', 'Result: `add returns the sum` FAILS — `add(2, 3)` returned `-1`, expected `5`; `sum folds with add` FAILS for the same reason (`sum([1, 2, 3])` returned `-6`, expected `6`).', 'Deterministic: the same two assertions fail on every run; no environment dependence.', 'Confirms the triage: a sign error in `src/add.js`, nothing else.', footer].join('\n');
  if (phase === 'verify' || phase === 'review' || phase === 'test') return ['## Verification', '', 'Reviewed the change in the worktree: `src/add.js` now returns `a + b`; the exported name is unchanged; `test/add.test.js` is unchanged.', 'Ran `npm test` (`node --test test/`): `add returns the sum` PASS, `sum folds with add` PASS — 2 passing, 0 failing.', 'No other file changed; the diff is the one-line correction the issue asked for.', footer].join('\n');
  return [`## ${phase} phase`, '', `Acknowledged the ${phase} phase of this run (${prompt.length} chars of prompt). This deterministic stand-in makes no change to the worktree outside the fix phase and records its turn for the smoke's evidence.`, footer].join('\n');
}
