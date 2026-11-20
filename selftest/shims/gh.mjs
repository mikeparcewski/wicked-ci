#!/usr/bin/env node
// `gh` stand-in for the deliver phase: never reaches GitHub. `pr create` prints a PR URL on a reserved
// host; `api user -q .login` prints the smoke identity; `pr checks` answers one green required check (crew#1624); every other verb succeeds silently.
import { record } from './_lib.mjs';

const { argv } = record('gh');
const [verb, sub] = argv;
if (verb === '--version') { console.log('gh version 0.0.0-smoke'); process.exit(0); }
// crew#1624's PR-checks watch reads the base branch's rules (an array) and its protection (an object) through
// `gh api`; both answer "nothing required by name", the one check below is what the watch then waits on.
if (verb === 'api' && /\/rules\/branches\//.test(sub || '')) { console.log('[]'); process.exit(0); }
if (verb === 'api' && /^repos\/[^/]+\/[^/]+\/branches\//.test(sub || '')) { console.log('{}'); process.exit(0); }
if (verb === 'api') { console.log('smoke-bot'); process.exit(0); }
if (verb === 'auth') { console.log('gh shim: auth ok'); process.exit(0); }
if (verb === 'pr' && sub === 'create') { console.log('https://example.invalid/wicked-smoke/corpus/pull/1'); process.exit(0); }
if (verb === 'pr' && sub === 'view' && argv.includes('.baseRefName')) { console.log('main'); process.exit(0); }
if (verb === 'pr' && sub === 'view') { console.log('{"url":"https://example.invalid/wicked-smoke/corpus/pull/1","state":"OPEN"}'); process.exit(0); }
// One required check, already green: an empty list would make the watch wait out its no-checks grace.
if (verb === 'pr' && sub === 'checks') { console.log('[{"name":"smoke","bucket":"pass","link":"","workflow":"smoke"}]'); process.exit(0); }
if (verb === 'pr') { console.log('https://example.invalid/wicked-smoke/corpus/pull/1'); process.exit(0); }
console.log(`gh shim: ${argv.join(' ')}`);
process.exit(0);
