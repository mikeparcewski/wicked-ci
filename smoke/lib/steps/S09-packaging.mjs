// S09 packaging — the INSTALLED tree (what the customer's `npm i -g` produced), no network:
// the prebuilt wicked-core-ts platform package for this host resolves at the pinned version, the
// studio dist is inside the tarball, and nothing the roster displays (`headless_invocation`,
// `login_invocation`, `binary`) points outside the temp root (F-004: a hard-coded operator path).
import { existsSync } from 'node:fs';
import { run as runProc } from '../proc.mjs';
import { satisfies } from '../semver.mjs';

export const id = 'S09';
export const name = 'packaging';

const ABS = /^(?:\/|[A-Za-z]:[\\/])/;

export async function run(ctx, t) {
  const v = ctx.versions;
  const tree = ctx.tree;
  t.check('wicked-core-ts installed', typeof v.coreTs === 'string', String(v.coreTs));

  // crew#493 (F-003): `wicked-crew --version` answers for THIS install — three `<name> <version>`
  // lines that must equal what the installed tree holds (crew's package.json, the wicked-core-ts it
  // resolves, dist/studio's testid-inventory marker) — and consults no daemon. "Unknown command"
  // before crew 0.7.35; EXPECTED-FAIL below that (lib/expect.mjs).
  const ver = runProc([process.execPath, tree.crewBin, '--version'], { env: ctx.env, cwd: ctx.L.root, timeoutMs: 30_000 });
  const gotLines = ver.stdout.trimEnd().split('\n');
  const wantLines = [`wicked-crew ${v.crew}`, `wicked-core-ts ${v.coreTs ?? 'unknown'}`, `wicked-studio ${v.studioBundle ?? 'none'}`];
  const evV = t.evidence('cli-version', { status: ver.status, stdout: ver.stdout.slice(0, 500), stderr: ver.stderr.slice(0, 500), want: wantLines });
  t.check('wicked-crew --version == installed crew / core-ts / studio versions, exit 0 (crew#493)', ver.status === 0 && ver.stderr === '' && gotLines.length === 3 && gotLines.every((l, i) => l === wantLines[i]), `exit ${ver.status}; got ${JSON.stringify(gotLines).slice(0, 300)}; want ${JSON.stringify(wantLines)}`, { finding: 'F-003', evidence: evV });
  t.check(`platform package ${tree.platformPkgName} present`, tree.platformDir !== null, String(tree.platformDir));
  t.check('platform package version == wicked-core-ts version (six-package release train in step)', v.coreTsPlatform === v.coreTs, `${v.coreTsPlatform} vs ${v.coreTs}`);
  t.check(`crew's pin ${v.coreTsRange} resolves to the installed ${v.coreTs}`, typeof v.coreTsRange === 'string' && satisfies(v.coreTs, v.coreTsRange), `${v.coreTs} in ${v.coreTsRange}`);
  t.check('dist/studio/index.html present in the crew tarball', existsSync(tree.studioIndex), tree.studioIndex);
  t.check('dist/studio/testid-inventory.json carries studioVersion', typeof v.studioBundle === 'string', String(v.studioBundle));
  t.check('wicked-bus CLI present', existsSync(tree.busCli), tree.busCli);

  if (!ctx.daemon.child) { t.info('roster', 'daemon not running (S01 not selected) — F-004 roster check skipped'); return; }
  const api = ctx.api();
  const roster = await api.get('/roster');
  const ev = t.evidence('roster', roster.json);
  const outside = [];
  for (const seat of roster.json?.roster ?? []) {
    for (const field of ['headless_invocation', 'login_invocation', 'binary']) {
      const val = seat[field];
      if (typeof val !== 'string') continue;
      for (const tok of val.split(/\s+/)) {
        const clean = tok.replace(/^["']|["']$/g, '');
        if (ABS.test(clean) && !clean.startsWith(ctx.L.root)) outside.push(`${seat.key}.${field}: ${clean}`);
      }
    }
  }
  t.check('roster invocations reference no path outside the temp root (F-004)', outside.length === 0, outside.join(' | ').slice(0, 400), { evidence: ev });
}
