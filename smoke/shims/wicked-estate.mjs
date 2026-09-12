#!/usr/bin/env node
// `wicked-estate` stand-in: the code-graph indexer the onboarding phases spawn (`index <root> --db …`,
// `clusters --annotate --db …`). Records its argv and exits 0 — the smoke asserts the ENGINE's routing
// and the daemon's wire, not the estate index (which has its own crate tests).
import { record } from './_lib.mjs';

const { argv } = record('wicked-estate');
if (argv[0] === '--version' || argv[0] === 'version') {
  console.log('wicked-estate 0.0.0-smoke');
  process.exit(0);
}
console.log(`wicked-estate shim: ${argv.slice(0, 2).join(' ')} ok`);
process.exit(0);
