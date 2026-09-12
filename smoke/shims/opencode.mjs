#!/usr/bin/env node
// `opencode` stand-in: the FREE-TIER seat (no credential file; crew reads `auth: not_required`). Answers
// like claude so the council has two live seats and the evaluator can be identity-distinct from the
// creator. `opencode acp` (the ACP transport crew's chat would use) is NOT implemented — see README.
import { BALLOT, JUDGE_PASS, TRIAGE_ESCALATE, isVersionProbe, record, workerTurn } from './_lib.mjs';

const { argv, prompt, kind } = record('opencode');
if (isVersionProbe(argv)) {
  console.log('1.17.18-smoke');
  process.exit(0);
}
if (argv[0] === 'acp') {
  process.stderr.write('opencode shim: ACP transport not implemented in wicked-smoke v1\n');
  process.exit(2);
}
if (!prompt) {
  console.log('opencode shim: no prompt');
  process.exit(0);
}
if (kind === 'ballot') console.log(BALLOT);
else if (kind === 'judge') console.log(JUDGE_PASS);
else if (kind === 'triage') console.log(TRIAGE_ESCALATE);
else console.log(workerTurn(prompt));
process.exit(0);
