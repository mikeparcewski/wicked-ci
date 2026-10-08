// `npm run check`: every module parses and the step registry is complete (no network, no daemon).
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { ALL_STEPS, parseSteps } from './args.mjs';
import { compare, satisfies } from './semver.mjs';
import { ExpectPolicy } from './expect.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const stepFiles = readdirSync(join(here, 'steps')).filter((f) => f.endsWith('.mjs')).sort();
const ids = [];
for (const f of stepFiles) {
  const mod = await import(pathToFileURL(join(here, 'steps', f)).href);
  if (typeof mod.run !== 'function' || typeof mod.id !== 'string') throw new Error(`${f}: missing id/run`);
  ids.push(mod.id);
}
if (ids.join(',') !== ALL_STEPS.join(',')) throw new Error(`step registry mismatch: ${ids.join(',')}`);
for (const f of readdirSync(join(here, '..', 'shims')).filter((f) => f.endsWith('.mjs'))) {
  // Importing a shim would run it; a syntax check is enough here.
  const { spawnSync } = await import('node:child_process');
  const r = spawnSync(process.execPath, ['--check', join(here, '..', 'shims', f)], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`${f}: ${r.stderr}`);
}
if (parseSteps('S01..S03').join(',') !== 'S01,S02,S03') throw new Error('parseSteps range');
if (compare('0.7.32', '0.7.33') !== -1) throw new Error('semver compare');
if (!satisfies('0.7.23', '^0.7.23') || satisfies('0.8.0', '^0.7.23')) throw new Error('semver satisfies');
// The re-bound rules hold on the last affected version and stop on the fix (no silent expiry).
const edges = [
  ['F-SMOKE-003', { crew: '0.8.4' }, { crew: '0.8.5' }],
  ['F-087', { crew: '0.7.44', nodeMajor: 26 }, { crew: '0.7.45', nodeMajor: 26 }],
  ['F-E2E-002', { crew: '0.8.5' }, { crew: '0.8.6' }],
];
for (const [f, before, fixed] of edges) {
  if (!new ExpectPolicy(before).reasonFor(f)) throw new Error(`${f}: no reason on ${JSON.stringify(before)}`);
  if (new ExpectPolicy(fixed).reasonFor(f) !== null) throw new Error(`${f}: still expected on ${JSON.stringify(fixed)}`);
}
console.log(`selfcheck ok: ${ids.length} steps, ${stepFiles.length} step modules`);
