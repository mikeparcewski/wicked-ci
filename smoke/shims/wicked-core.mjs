#!/usr/bin/env node
// `wicked-core` CLI stand-in. The ENGINE the smoke exercises is the wicked-core-ts napi addon inside
// crew; the separate `wicked-core` CLI binary is what the WRAPPED claude carrier probes to arm INPUT
// governance (`wicked-core gate-hook --protocol-version`, then a PreToolUse hook that calls
// `wicked-core gate-hook` per tool call). A customer without the cargo-installed CLI gets
// "(could not arm input governance: could not run `wicked-core gate-hook --protocol-version`)" and
// the unit fails — observed on crew 0.7.32 with the wrapped carrier. The engine also REQUIRES the
// CLI's semantic version to equal its own crate version (crew#275 skew guard), so the shim reports the
// version the harness discovered for the installed addon (`<root>/core-semver.txt`) and allows every
// hook call (the shim seats never invoke tools, so no hook call happens in practice).
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { record } from './_lib.mjs';

const { argv } = record('wicked-core');
function engineSemver() {
  const root = process.env.WICKED_SMOKE_ROOT;
  const f = root ? join(root, 'core-semver.txt') : null;
  if (f && existsSync(f)) { const v = readFileSync(f, 'utf8').trim(); if (v) return v; }
  return process.env.WICKED_SMOKE_CORE_SEMVER || '0.0.0-smoke';
}
if (argv[0] === '--version' || argv[0] === 'version') {
  console.log(`wicked-core ${engineSemver()}`);
  process.exit(0);
}
if (argv[0] === 'gate-hook') {
  if (argv.includes('--protocol-version')) {
    console.log(`wicked-core gate-hook protocol 1 semver ${engineSemver()}`);
    process.exit(0);
  }
  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (d) => { input += d; });
  process.stdin.on('end', () => {
    console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow', permissionDecisionReason: 'wicked-smoke shim: allow' } }));
    process.exit(0);
  });
} else {
  console.log(`wicked-core shim: ${argv.join(' ')}`);
  process.exit(0);
}
