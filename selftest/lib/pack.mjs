// wicked-selftest pack: build Tier 1 packs from checkouts and write a set file that `wicked-selftest run --set` installs.
//
// Tier 1 is the recipe the :7702 dev copy uses: garden is exported as is (no build), studio is `npm ci` + `npm run
// build` with its dist stamped, and crew is `npm ci` + build with THAT studio dist bundled, then `npm pack`. core-ts and
// bus stay published (crew's pin resolves them) unless a set names them.
//
// TRUST: building runs the checkout's own code (npm scripts, tsc, vite). Run `pack` only on trees you trust (mains, your
// own branch) or inside a sandbox. A governed run's head is packed inside the floor's sandbox, never on the host.
// `pack` writes only under --out and inside each checkout's build output (node_modules, dist); it restores the crew
// package.json it stamps.
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

export const PACK_HELP = `wicked-selftest pack — build Tier 1 packs from checkouts and write <out>/set.json

usage: wicked-selftest pack --out <dir> [--crew-src <dir>] [--studio-src <dir>] [--garden-src <dir>]
                            [--build-slot "<prefix>"]

  --crew-src <dir>     a wicked-crew checkout: npm ci, build, bundle a studio dist, npm pack
  --studio-src <dir>   a wicked-studio checkout: npm ci, npm run build; its dist is bundled into crew
                       (needs --crew-src). Without it, crew bundles the studio its lockfile pins (build:with-studio).
  --garden-src <dir>   a wicked-garden checkout: its tracked files at HEAD, exported as a tarball (no build)
  --out <dir>          where the packs and set.json go (created; must be empty or absent)
  --build-slot "<p>"   a command prefix for the heavy steps, e.g. "build-slot --"

Each version is stamped "<package version>+st.<sha7>" so /health and the studio bundle name what was built. A checkout
with uncommitted changes is packed as it is and recorded "dirty": true.`;

function parse(argv) {
  const o = { crewSrc: null, studioSrc: null, gardenSrc: null, out: null, buildSlot: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => { const v = argv[i + 1]; if (v === undefined || v.startsWith('--')) throw new Error(`${a} needs a value`); i += 1; return v; };
    switch (a) {
      case '--crew-src': o.crewSrc = resolve(next()); break;
      case '--studio-src': o.studioSrc = resolve(next()); break;
      case '--garden-src': o.gardenSrc = resolve(next()); break;
      case '--out': o.out = resolve(next()); break;
      case '--build-slot': o.buildSlot = next().split(' ').filter(Boolean); break;
      case '-h': case '--help': o.help = true; break;
      default: throw new Error(`unknown option ${a} (see --help)`);
    }
  }
  if (o.help) return o;
  if (!o.out) throw new Error('--out is required');
  if (!o.crewSrc && !o.gardenSrc) throw new Error('nothing to pack: give --crew-src and/or --garden-src');
  if (o.studioSrc && !o.crewSrc) throw new Error('--studio-src needs --crew-src (the studio dist ships inside crew)');
  for (const k of ['crewSrc', 'studioSrc', 'gardenSrc']) if (o[k] && !existsSync(join(o[k], 'package.json'))) throw new Error(`${k}: ${o[k]} has no package.json`);
  return o;
}

const npmBin = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function sh(argv, cwd, { capture = false, slot = [] } = {}) {
  const full = [...slot, ...argv];
  console.log(`$ (${basename(cwd)}) ${argv.join(' ')}`);
  const r = spawnSync(full[0], full.slice(1), {
    cwd, stdio: capture ? ['ignore', 'pipe', 'inherit'] : 'inherit', encoding: 'utf8', shell: process.platform === 'win32',
    env: { ...process.env, GIT_CONFIG_COUNT: '1', GIT_CONFIG_KEY_0: 'core.fsmonitor', GIT_CONFIG_VALUE_0: 'false', npm_config_audit: 'false', npm_config_fund: 'false', npm_config_update_notifier: 'false' },
  });
  if (r.status !== 0) throw new Error(`failed (${r.status ?? r.signal}): ${argv.join(' ')} in ${cwd}`);
  return capture ? r.stdout.trim() : '';
}

function gitFacts(dir) {
  const sha = sh(['git', 'rev-parse', 'HEAD'], dir, { capture: true });
  const dirty = sh(['git', 'status', '--porcelain', '--untracked-files=no'], dir, { capture: true }) !== '';
  return { sha, dirty };
}
const pkgVersion = (dir) => JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8')).version;

export async function packMain(argv) {
  let o;
  try { o = parse(argv); } catch (err) { console.error(`wicked-selftest pack: ${err.message}`); console.error(PACK_HELP); return 2; }
  if (o.help) { console.log(PACK_HELP); return 0; }
  if (existsSync(o.out) && readdirSync(o.out).length > 0) { console.error(`wicked-selftest pack: --out ${o.out} is not empty`); return 2; }
  mkdirSync(o.out, { recursive: true });
  const set = { $comment: 'written by wicked-selftest pack; install with: wicked-selftest run --set <this file>', built: { tier: 1, at: new Date().toISOString() } };

  if (o.gardenSrc) {
    const g = gitFacts(o.gardenSrc);
    const tgz = join(o.out, `wicked-garden-${g.sha.slice(0, 7)}.tgz`);
    // Only tracked files at HEAD: the shape of the tag tarball the published set installs.
    sh(['git', 'archive', '--format=tar.gz', '--prefix=wicked-garden/', '-o', tgz, 'HEAD'], o.gardenSrc);
    set.garden = basename(tgz);
    set.built.garden = { sha: g.sha, dirty: g.dirty, note: g.dirty ? 'uncommitted changes are NOT in the export (HEAD only)' : undefined };
  }

  let studioDist = null;
  if (o.studioSrc) {
    const s = gitFacts(o.studioSrc);
    sh([npmBin, 'ci'], o.studioSrc, { slot: o.buildSlot });
    sh([npmBin, 'run', 'build'], o.studioSrc, { slot: o.buildSlot });
    const version = `${pkgVersion(o.studioSrc)}+st.${s.sha.slice(0, 7)}`;
    const inv = join(o.studioSrc, 'dist', 'testid-inventory.json');
    if (!existsSync(inv)) throw new Error('studio dist has no testid-inventory.json (crew reads the bundle version from it)');
    const j = JSON.parse(readFileSync(inv, 'utf8')); j.studioVersion = version;
    writeFileSync(inv, `${JSON.stringify(j, null, 2)}\n`);
    studioDist = join(o.studioSrc, 'dist');
    set.built.studio = { sha: s.sha, dirty: s.dirty, version };
  }

  if (o.crewSrc) {
    const c = gitFacts(o.crewSrc);
    const crPkg = join(o.crewSrc, 'packages', 'crew');
    const pjPath = join(crPkg, 'package.json');
    const original = readFileSync(pjPath, 'utf8');
    const version = `${JSON.parse(original).version}+st.${c.sha.slice(0, 7)}`;
    sh([npmBin, 'ci'], o.crewSrc, { slot: o.buildSlot });
    let tgzName;
    try {
      const pj = JSON.parse(original); pj.version = version;
      writeFileSync(pjPath, `${JSON.stringify(pj, null, 2)}\n`);
      if (studioDist) {
        sh([npmBin, 'run', 'build', '-w', 'packages/crew'], o.crewSrc, { slot: o.buildSlot });
        const dest = join(crPkg, 'dist', 'studio');
        rmSync(dest, { recursive: true, force: true });
        cpSync(studioDist, dest, { recursive: true });
      } else {
        sh([npmBin, 'run', 'build:with-studio', '-w', 'packages/crew'], o.crewSrc, { slot: o.buildSlot });
      }
      if (!existsSync(join(crPkg, 'dist', 'studio', 'index.html'))) throw new Error('crew dist has no studio bundle');
      tgzName = sh([npmBin, 'pack', '--silent', '--pack-destination', o.out], crPkg, { capture: true }).split('\n').pop();
    } finally {
      writeFileSync(pjPath, original); // restore the stamped package.json byte for byte
    }
    set.crew = tgzName;
    set.built.crew = { sha: c.sha, dirty: c.dirty, version, studio: studioDist ? 'built from --studio-src' : "the studio crew's lockfile pins (build:with-studio)" };
  }

  writeFileSync(join(o.out, 'set.json'), `${JSON.stringify(set, null, 2)}\n`);
  console.log(`wicked-selftest pack: wrote ${join(o.out, 'set.json')}`);
  return 0;
}
