#!/usr/bin/env node
// wicked-smoke: the compatibility name for `wicked-selftest run` (the smoke harness grew into the self-test suite;
// callers that pin a wicked-ci SHA or call `wicked-smoke` keep the same flags, steps and report).
import { runMain } from '../lib/main.mjs';

runMain(process.argv.slice(2)).then((code) => process.exit(code), (err) => { console.error(err); process.exit(1); });
