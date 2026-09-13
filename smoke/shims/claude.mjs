#!/usr/bin/env node
// `claude` stand-in: a SIGNED-IN seat that answers every turn. Ballots vote option 1, judge turns
// PASS, worker turns follow shims/_lib.mjs workerTurn (the fix phase applies the corpus correction).
// Output is plain text: the engine's claude stream-json adapter passes non-JSON lines through as deltas.
import { BALLOT, JUDGE_PASS, TRIAGE_ESCALATE, isVersionProbe, record, workerTurn } from './_lib.mjs';

const { argv, prompt, kind } = record('claude');
if (isVersionProbe(argv)) {
  console.log('2.0.0-smoke (Claude Code shim)');
  process.exit(0);
}
if (!prompt) {
  console.log('claude shim: no prompt');
  process.exit(0);
}
if (kind === 'ballot') console.log(BALLOT);
else if (kind === 'judge') console.log(JUDGE_PASS);
else if (kind === 'triage') console.log(TRIAGE_ESCALATE);
else console.log(workerTurn(prompt));
process.exit(0);
