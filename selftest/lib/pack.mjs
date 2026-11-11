// wicked-selftest pack: build Tier 1 packs from checkouts and write a set file that `wicked-selftest run --set` installs.
//
// Tier 1 is the recipe the :7702 dev copy uses: garden is exported as is (no build), studio is `npm ci` + `npm run
// build` with its dist stamped, and crew is `npm ci` + build with THAT studio dist bundled, then `npm pack`. core-ts and
// bus stay published (crew's pin resolves them) unless a set names them.
//
// Every build runs in a STAGING EXPORT under --out (`git archive HEAD` of each checkout), never in the checkout: the
// checkout is only read, so an interrupted or concurrent pack can't leave it stamped or half-built, and a pack holds
// exactly the recorded commit. A checkout with uncommitted or untracked changes is refused (they would not be in the
// export) unless --allow-dirty, which records that they were left out.
//
// TRUST: building runs the checkout's own code (npm scripts, tsc, vite). Run `pack` only on trees you trust (mains, your
// own branch) or inside a sandbox. A governed run's head is packed inside the floor's sandbox, never on the host. The
// build sees a constructed environment: PATH, a HOME, npm cache/config and temp dir under --out, and git with no
// system or global config and no inherited GIT_* routing. `--npm-cache <dir>` opts in to a shared npm cache.
import { cpSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { basename, delimiter, dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { gzipSync } from 'node:zlib';
import { npmArgv } from './proc.mjs';

export const PACK_HELP = `wicked-selftest pack — build Tier 1 packs from checkouts and write <out>/set.json

usage: wicked-selftest pack --out <dir> [--crew-src <dir>] [--studio-src <dir>] [--garden-src <dir>]
                            [--allow-dirty] [--npm-cache <dir>] [--build-slot "<prefix>"]

  --crew-src <dir>     a wicked-crew checkout: npm ci, build, bundle a studio dist, npm pack
  --studio-src <dir>   a wicked-studio checkout: npm ci, npm run build; its dist is bundled into crew
                       (needs --crew-src). Without it, crew bundles the studio its lockfile pins (build:with-studio).
  --garden-src <dir>   a wicked-garden checkout: exported as a tarball (no build)
  --out <dir>          where the staging exports, packs and set.json go (created; it must not exist yet)
  --allow-dirty        pack a checkout that has uncommitted or untracked changes (they are NOT included; recorded)
  --npm-cache <dir>    use this npm cache (default: a fresh one under --out)
  --build-slot "<p>"   a command prefix for the heavy steps, e.g. "build-slot --"

Every source is the checkout's HEAD commit, exported (tracked files only) and built under --out; the checkout itself is
never written. crew and studio versions are stamped "<package version>+st.<sha7>" in the export, so /health and the
studio bundle name what was built; garden keeps its own manifest version (crew reads it as is).`;

function parse(argv) {
  const o = { crewSrc: null, studioSrc: null, gardenSrc: null, out: null, buildSlot: [], allowDirty: false, npmCache: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => { const v = argv[i + 1]; if (v === undefined || v.startsWith('--')) throw new Error(`${a} needs a value`); i += 1; return v; };
    switch (a) {
      case '--crew-src': o.crewSrc = resolve(next()); break;
      case '--studio-src': o.studioSrc = resolve(next()); break;
      case '--garden-src': o.gardenSrc = resolve(next()); break;
      case '--out': o.out = resolve(next()); break;
      case '--build-slot': o.buildSlot = next().split(' ').filter(Boolean); break;
      case '--allow-dirty': o.allowDirty = true; break;
      case '--npm-cache': o.npmCache = resolve(next()); break;
      case '-h': case '--help': o.help = true; break;
      default: throw new Error(`unknown option ${a} (see --help)`);
    }
  }
  if (o.help) return o;
  if (!o.out) throw new Error('--out is required');
  if (!o.crewSrc && !o.gardenSrc) throw new Error('nothing to pack: give --crew-src and/or --garden-src');
  if (o.studioSrc && !o.crewSrc) throw new Error('--studio-src needs --crew-src (the studio dist ships inside crew)');
  for (const k of ['crewSrc', 'studioSrc']) if (o[k] && !existsSync(join(o[k], 'package.json'))) throw new Error(`${k}: ${o[k]} has no package.json`);
  if (o.gardenSrc && !existsSync(join(o.gardenSrc, '.claude-plugin', 'plugin.json'))) throw new Error(`gardenSrc: ${o.gardenSrc} has no .claude-plugin/plugin.json`);
  return o;
}

/** The build's environment: constructed, never inherited (no host HOME, npmrc, credentials or GIT_* routing). */
function buildEnv(stage, npmCache) {
  const home = join(stage, 'home');
  const tmp = join(stage, 'tmp');
  mkdirSync(home, { recursive: true });
  mkdirSync(tmp, { recursive: true });
  const npmrc = join(stage, 'npmrc');
  const npmrcGlobal = join(stage, 'npmrc-global');
  for (const f of [npmrc, npmrcGlobal]) if (!existsSync(f)) writeFileSync(f, '');
  const gitconfig = join(stage, 'gitconfig');
  if (!existsSync(gitconfig)) writeFileSync(gitconfig, '[core]\n\tfsmonitor = false\n');
  const env = {
    PATH: [dirname(process.execPath), ...(process.env.PATH ?? process.env.Path ?? '').split(delimiter)].filter(Boolean).join(delimiter),
    HOME: home, USERPROFILE: home, TMPDIR: tmp, TEMP: tmp, TMP: tmp, LANG: process.env.LANG ?? 'en_US.UTF-8',
    npm_config_cache: npmCache ?? join(stage, 'npm-cache'), npm_config_userconfig: npmrc, npm_config_globalconfig: npmrcGlobal,
    npm_config_audit: 'false', npm_config_fund: 'false', npm_config_update_notifier: 'false',
    GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: gitconfig, GIT_TERMINAL_PROMPT: '0',
    WICKED_STUDIO_SKIP_PREPARE: '1',
  };
  for (const k of ['SystemRoot', 'ComSpec', 'PATHEXT', 'WINDIR']) if (process.env[k]) env[k] = process.env[k]; // Windows process basics
  return env;
}

/** Argument-array execution, never a shell (a path with a space or a metacharacter stays one argument). */
function sh(argv, cwd, env, { capture = false, slot = [] } = {}) {
  const full = [...slot, ...argv];
  console.log(`$ (${basename(cwd)}) ${argv.map((a) => basename(a) === a ? a : `…/${basename(a)}`).join(' ')}`);
  const r = spawnSync(full[0], full.slice(1), { cwd, env, stdio: capture ? ['ignore', 'pipe', 'inherit'] : 'inherit', encoding: 'utf8', shell: false });
  if (r.error) throw new Error(`could not run ${argv[0]}: ${r.error.message}`);
  if (r.status !== 0) throw new Error(`failed (${r.status ?? r.signal}): ${argv.join(' ')} in ${cwd}`);
  return capture ? r.stdout.trim() : '';
}
const npm = (...a) => [...npmArgv(), ...a];

/** HEAD's sha and whether the tree has ANY change the export would leave out (staged, unstaged or untracked). */
/** git against a SOURCE checkout: read-only. Command-scoped config beats the checkout's own .git/config (no
 *  fsmonitor hook, no external archive filter), and --no-optional-locks keeps `status` from rewriting its index. */
const git = (dir, ...args) => ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', dir, ...args];

function gitFacts(dir, env) {
  const sha = sh(git(dir, 'rev-parse', '--verify', 'HEAD^{commit}'), dir, env, { capture: true });
  const dirty = sh(git(dir, 'status', '--porcelain', '--untracked-files=normal'), dir, env, { capture: true }) !== '';
  return { sha, dirty };
}

/** `git archive <sha>` of a checkout into <stage>/<name>: the exact recorded commit, tracked files only. */
function exportTree(src, sha, stage, name, env) {
  const dest = join(stage, name);
  mkdirSync(dest, { recursive: true });
  const tar = join(stage, `${name}.tar`);
  // The RECORDED commit, not HEAD again: the checkout may move while a long build runs.
  sh(git(src, 'archive', '--format=tar', '-o', tar, sha), src, env);
  sh(['tar', '-xf', tar, '-C', dest], stage, env);
  rmSync(tar, { force: true });
  return dest;
}
const pkgVersion = (dir) => JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8')).version;

export async function packMain(argv) {
  let o;
  try { o = parse(argv); } catch (err) { console.error(`wicked-selftest pack: ${err.message}`); console.error(PACK_HELP); return 2; }
  if (o.help) { console.log(PACK_HELP); return 0; }
  // --out must not exist: creating it is the claim (mkdir is atomic), so two packs can never share one output.
  mkdirSync(dirname(o.out), { recursive: true });
  try { mkdirSync(o.out); } catch (err) { console.error(`wicked-selftest pack: --out ${o.out} ${err.code === 'EEXIST' ? 'already exists (it must not: pass a new directory)' : `cannot be created: ${err.message}`}`); return 2; }
  const stage = join(o.out, '.stage');
  const env = buildEnv(stage, o.npmCache);
  const facts = {};
  for (const [k, dir] of [['crew', o.crewSrc], ['studio', o.studioSrc], ['garden', o.gardenSrc]]) {
    if (!dir) continue;
    facts[k] = gitFacts(dir, env);
    if (facts[k].dirty && !o.allowDirty) {
      console.error(`wicked-selftest pack: ${dir} has uncommitted or untracked changes; the pack is built from HEAD (${facts[k].sha.slice(0, 7)}) and would leave them out. Commit them, or pass --allow-dirty.`);
      return 2;
    }
  }
  const set = { $comment: 'written by wicked-selftest pack; install with: wicked-selftest run --set <this file>', built: { tier: 1, at: new Date().toISOString() } };
  const note = (f) => (f.dirty ? 'uncommitted/untracked changes were LEFT OUT (HEAD only, --allow-dirty)' : undefined);

  if (o.gardenSrc) {
    const g = facts.garden;
    const tgz = join(o.out, `wicked-garden-${g.sha.slice(0, 7)}.tgz`);
    // Only tracked files at the recorded commit: the shape of the tag tarball the published set installs. Plain tar
    // from git, gzipped here (no `tar.gz` archive filter a checkout's config could point at a command).
    const tar = join(stage, 'wicked-garden.tar');
    mkdirSync(stage, { recursive: true });
    sh(git(o.gardenSrc, 'archive', '--format=tar', '--prefix=wicked-garden/', '-o', tar, g.sha), o.gardenSrc, env);
    writeFileSync(tgz, gzipSync(readFileSync(tar)));
    rmSync(tar, { force: true });
    set.garden = basename(tgz);
    set.built.garden = { sha: g.sha, dirty: g.dirty, note: note(g) };
  }

  let studioDist = null;
  if (o.studioSrc) {
    const f = facts.studio;
    const st = exportTree(o.studioSrc, f.sha, stage, 'wicked-studio', env);
    sh(npm('ci'), st, env, { slot: o.buildSlot });
    sh(npm('run', 'build'), st, env, { slot: o.buildSlot });
    const version = `${pkgVersion(st)}+st.${f.sha.slice(0, 7)}`;
    const inv = join(st, 'dist', 'testid-inventory.json');
    if (!existsSync(inv)) throw new Error('studio dist has no testid-inventory.json (crew reads the bundle version from it)');
    const j = JSON.parse(readFileSync(inv, 'utf8')); j.studioVersion = version;
    writeFileSync(inv, `${JSON.stringify(j, null, 2)}\n`);
    studioDist = join(st, 'dist');
    set.built.studio = { sha: f.sha, dirty: f.dirty, version, note: note(f) };
  }

  if (o.crewSrc) {
    const f = facts.crew;
    const cr = exportTree(o.crewSrc, f.sha, stage, 'wicked-crew', env);
    const crPkg = join(cr, 'packages', 'crew');
    const pj = JSON.parse(readFileSync(join(crPkg, 'package.json'), 'utf8'));
    const version = `${pj.version}+st.${f.sha.slice(0, 7)}`;
    pj.version = version;
    writeFileSync(join(crPkg, 'package.json'), `${JSON.stringify(pj, null, 2)}\n`); // the EXPORT is stamped, never the checkout
    sh(npm('ci'), cr, env, { slot: o.buildSlot });
    if (studioDist) {
      sh(npm('run', 'build', '-w', 'packages/crew'), cr, env, { slot: o.buildSlot });
      const dest = join(crPkg, 'dist', 'studio');
      rmSync(dest, { recursive: true, force: true });
      cpSync(studioDist, dest, { recursive: true });
    } else {
      sh(npm('run', 'build:with-studio', '-w', 'packages/crew'), cr, env, { slot: o.buildSlot });
    }
    if (!existsSync(join(crPkg, 'dist', 'studio', 'index.html'))) throw new Error('crew dist has no studio bundle');
    const tgzName = sh(npm('pack', '--silent', '--pack-destination', o.out), crPkg, env, { capture: true }).split('\n').pop();
    set.crew = tgzName;
    set.built.crew = { sha: f.sha, dirty: f.dirty, version, studio: studioDist ? 'built from --studio-src' : "the studio crew's lockfile pins (build:with-studio)", note: note(f) };
  }

  writeFileSync(join(o.out, 'set.json.tmp'), `${JSON.stringify(set, null, 2)}\n`);
  renameSync(join(o.out, 'set.json.tmp'), join(o.out, 'set.json')); // published whole, or not at all
  console.log(`wicked-selftest pack: wrote ${join(o.out, 'set.json')} (the staging exports under ${stage} can be removed)`);
  return 0;
}
