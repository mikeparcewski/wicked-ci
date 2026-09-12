#!/usr/bin/env node
// `codex` stand-in: SIGNED OUT. Its credential file exists (so crew's cheap probe says signed in) but
// every turn fails the way the real CLI does without a login — the engine must learn `not_logged_in`
// from the ballot and bench the seat (F-7R2-006).
import { isVersionProbe, record } from './_lib.mjs';

const { argv } = record('codex');
if (isVersionProbe(argv)) {
  console.log('codex-cli 0.0.0-smoke');
  process.exit(0);
}
process.stderr.write('Error: Not logged in. Run `codex login` to authenticate. (HTTP 401 Unauthorized)\n');
process.exit(1);
