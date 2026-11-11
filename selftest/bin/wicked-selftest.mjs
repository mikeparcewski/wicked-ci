#!/usr/bin/env node
// wicked-selftest: the wicked product self-test (one versioned suite for humans, PR CI, governed runs and the
// release smoke).
//   wicked-selftest run [options]    install a set, boot an ephemeral hermetic daemon, run the profile, tear down
//   wicked-selftest pack [options]   build Tier 1 packs from checkouts and write a set file (trusted trees only)
//   wicked-selftest --help
import { runMain } from '../lib/main.mjs';
import { packMain, PACK_HELP } from '../lib/pack.mjs';
import { HELP } from '../lib/args.mjs';

const [verb, ...rest] = process.argv.slice(2);
const usage = `wicked-selftest <run|pack> [options]\n\n  run   ${HELP.split('\n').slice(2).join('\n  ')}\n\n${PACK_HELP}`;
let p;
if (verb === 'run') p = runMain(rest);
else if (verb === 'pack') p = packMain(rest);
else if (verb === undefined || verb === '-h' || verb === '--help' || verb === 'help') { console.log(usage); p = Promise.resolve(0); }
else { console.error(`wicked-selftest: unknown verb ${verb} (run | pack)`); p = Promise.resolve(2); }
p.then((code) => process.exit(code), (err) => { console.error(err); process.exit(1); });
