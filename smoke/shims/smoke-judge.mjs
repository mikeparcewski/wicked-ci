#!/usr/bin/env node
// `smoke-judge` stand-in: a THIRD live seat (a custom registry key, no credential rule in crew — the
// roster reads `auth: unknown`, which is council-eligible). It answers like claude / opencode.
// WHY it exists (crew 0.8.5 release smoke, run 37762305091): from core-ts 0.7.40 (wicked-core#774)
// a unit's judge must be a seat identity-distinct from BOTH the unit's seat and its creator, and
// when the only such seats are benched the gate fails closed (`judge_unavailable`) instead of
// skipping the judge. With two live seats the `verify` unit (evaluator on opencode, creator claude)
// had no distinct judge left, so the bug run could never deliver. It is written LAST in the overlay,
// so the routing S04 asserts (claude / copilot first, copilot re-seated to opencode) is unchanged;
// the engine's judge rotation reaches it after the dead seats.
import { BALLOT, JUDGE_PASS, TRIAGE_ESCALATE, isVersionProbe, record, workerTurn } from './_lib.mjs';

const { argv, prompt, kind } = record('smoke-judge');
if (isVersionProbe(argv)) {
  console.log('0.0.0-smoke (judge seat shim)');
  process.exit(0);
}
if (!prompt) {
  console.log('smoke-judge shim: no prompt');
  process.exit(0);
}
if (kind === 'ballot') console.log(BALLOT);
else if (kind === 'judge') console.log(JUDGE_PASS);
else if (kind === 'triage') console.log(TRIAGE_ESCALATE);
else console.log(workerTurn(prompt));
process.exit(0);
