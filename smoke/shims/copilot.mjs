#!/usr/bin/env node
// `copilot` stand-in: QUOTA-EXHAUSTED. Looks signed in to the probe, fails every turn with the real
// CLI's quota message — the engine must bench it `quota_exhausted` and never route a unit to it
// (F-7R3-001).
import { isVersionProbe, record } from './_lib.mjs';

const { argv } = record('copilot');
if (isVersionProbe(argv)) {
  console.log('0.0.0-smoke');
  process.exit(0);
}
process.stderr.write("You've exceeded your monthly quota for premium requests. Upgrade your plan or wait for the quota to reset.\n");
process.exit(1);
