// wicked-selftest pack: build Tier 1 packs from checkouts and write a set file that `wicked-selftest run --set` installs.
//
// Tier 1 is the recipe the :7702 dev copy uses: garden is exported as is (no build), studio is `npm ci` + `npm run
// build` with its dist stamped, and crew is `npm ci` + build with THAT studio dist bundled, then `npm pack`. core-ts and
// bus stay published (crew's pin resolves them) unless a set names them.
//
// Tier 2 (`--core-src`) also builds the engine addon from a wicked-core checkout: `npm ci` + `npm run build` (napi
// build --platform --release, so cargo and a Rust toolchain must be on PATH) in crates/wicked-core-ts, then packs that
// package with the host's .node INSIDE it (index.js loads a local binding before the platform package) and without
// the platform optionalDependencies, so the install can't pull a published binary instead.
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
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { basename, delimiter, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { spawnSync } from 'node:child_process';
import { homedir } from 'node:os';
import { gzipSync } from 'node:zlib';
import { npmArgv } from './proc.mjs';

export const PACK_HELP = `wicked-selftest pack — build Tier 1 packs from checkouts and write <out>/set.json

usage: wicked-selftest pack --out <dir> [--crew-src <dir>] [--studio-src <dir>] [--garden-src <dir>] [--core-src <dir>]
                            [--allow-dirty] [--npm-cache <dir>] [--cargo-target <dir>] [--build-slot "<prefix>"]

  --crew-src <dir>     a wicked-crew checkout: npm ci, build, bundle a studio dist, npm pack
  --studio-src <dir>   a wicked-studio checkout: npm ci, npm run build; its dist is bundled into crew
                       (needs --crew-src). Without it, crew bundles the studio its lockfile pins (build:with-studio).
  --garden-src <dir>   a wicked-garden checkout: exported as a tarball (no build)
  --core-src <dir>     a wicked-core checkout (Tier 2): napi-build crates/wicked-core-ts for this host and pack it
                       with the binary inside; crew installs it instead of its pinned wicked-core-ts
  --out <dir>          where the staging exports, packs and set.json go (created; it must not exist yet)
  --allow-dirty        pack a checkout that has uncommitted or untracked changes (they are NOT included; recorded)
  --npm-cache <dir>    use this npm cache (default: a fresh one under --out)
  --cargo-target <dir> CARGO_TARGET_DIR for the Tier 2 build (default: under the staging export), so CI can cache it.
                       CARGO_HOME and RUSTUP_HOME are the host's (the build's HOME is a fresh one under --out)
  --build-slot "<p>"   a command prefix for the heavy steps, e.g. "build-slot --"

Every source is the checkout's HEAD commit, exported (tracked files only) and built under --out; the checkout itself is
never written. crew, studio and core-ts versions are stamped "<package version>+st.<sha7>" in the export, so /health and the
studio bundle name what was built; garden keeps its own manifest version (crew reads it as is).`;

function parse(argv) {
  const o = { crewSrc: null, studioSrc: null, gardenSrc: null, coreSrc: null, out: null, buildSlot: [], allowDirty: false, npmCache: null, cargoTarget: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => { const v = argv[i + 1]; if (v === undefined || v.startsWith('--')) throw new Error(`${a} needs a value`); i += 1; return v; };
    switch (a) {
      case '--crew-src': o.crewSrc = resolve(next()); break;
      case '--studio-src': o.studioSrc = resolve(next()); break;
      case '--garden-src': o.gardenSrc = resolve(next()); break;
      case '--core-src': o.coreSrc = resolve(next()); break;
      case '--cargo-target': o.cargoTarget = resolve(next()); break;
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
  if (!o.crewSrc && !o.gardenSrc && !o.coreSrc) throw new Error('nothing to pack: give --crew-src, --garden-src and/or --core-src');
  if (o.studioSrc && !o.crewSrc) throw new Error('--studio-src needs --crew-src (the studio dist ships inside crew)');
  for (const k of ['crewSrc', 'studioSrc']) if (o[k] && !existsSync(join(o[k], 'package.json'))) throw new Error(`${k}: ${o[k]} has no package.json`);
  if (o.gardenSrc && !existsSync(join(o.gardenSrc, '.claude-plugin', 'plugin.json'))) throw new Error(`gardenSrc: ${o.gardenSrc} has no .claude-plugin/plugin.json`);
  if (o.coreSrc && !existsSync(join(o.coreSrc, CORE_TS_DIR, 'package.json'))) throw new Error(`coreSrc: ${o.coreSrc} has no ${CORE_TS_DIR}/package.json`);
  return o;
}

const CORE_TS_DIR = join('crates', 'wicked-core-ts');

/** The build's environment: constructed, never inherited (no host HOME, npmrc, credentials or GIT_* routing). Rust's
 *  toolchain homes are the one exception, by path only: rustup's proxies find no toolchain under a fresh HOME. */
function buildEnv(stage, npmCache, cargoTarget) {
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
  env.CARGO_HOME = process.env.CARGO_HOME ?? join(homedir(), '.cargo');
  env.RUSTUP_HOME = process.env.RUSTUP_HOME ?? join(homedir(), '.rustup');
  env.CARGO_TARGET_DIR = cargoTarget ?? join(stage, 'cargo-target');
  for (const k of ['CARGO_BUILD_JOBS', 'RUSTC_WRAPPER', 'SCCACHE_DIR']) if (process.env[k]) env[k] = process.env[k];
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
/** A path with symlinks resolved: the real path of its nearest existing ancestor, plus the part that does not exist yet. */
export function realish(p) {
  const abs = resolve(p);
  let head = abs;
  const tail = [];
  for (;;) {
    try { return join(realpathSync(head), ...tail); } catch { /* not there yet */ }
    const up = dirname(head);
    if (up === head) return abs;
    tail.unshift(basename(head));
    head = up;
  }
}
/** `child` is `parent` or under it (`..` counts only as a whole segment: `..target` is a name, not a step up). */
export function isInside(parent, child) {
  const rel = relative(parent, child);
  return rel === '' || !(rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel));
}
/** An exclusive lock as a directory (mkdir is atomic) holding the owner's pid. A lock whose owner is gone is taken
 *  over; a live owner is waited on (up to `waitMs`). Returns the release function. */
export async function lockDir(path, { waitMs = 60 * 60_000, pollMs = 2000 } = {}) {
  const t0 = Date.now();
  mkdirSync(dirname(path), { recursive: true });
  for (;;) {
    try {
      mkdirSync(path);
      writeFileSync(join(path, 'pid'), String(process.pid));
      return () => rmSync(path, { recursive: true, force: true });
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
    }
    let owner = NaN;
    try { owner = Number(readFileSync(join(path, 'pid'), 'utf8')); } catch { /* being written, or gone */ }
    let alive = true;
    if (Number.isInteger(owner) && owner > 0) { try { process.kill(owner, 0); } catch (e) { alive = e.code === 'EPERM'; } }
    if (!alive) { rmSync(path, { recursive: true, force: true }); continue; }
    if (Date.now() - t0 > waitMs) throw new Error(`the cargo target lock ${path} is still held by pid ${owner}`);
    console.log(`wicked-selftest pack: waiting for the cargo target lock ${path} (pid ${owner})`);
    await new Promise((r) => setTimeout(r, pollMs));
  }
}
const pkgVersion = (dir) => JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8')).version;

export async function packMain(argv) {
  let o;
  try { o = parse(argv); } catch (err) { console.error(`wicked-selftest pack: ${err.message}`); console.error(PACK_HELP); return 2; }
  if (o.help) { console.log(PACK_HELP); return 0; }
  // --out may not sit inside a source checkout: its own files would make a clean tree read dirty, and the checkout
  // must stay unwritten. Checked before anything is created.
  // The same holds for the Tier 2 cargo target: a build writing into a checkout would leave it dirty. Compared as
  // REAL paths (a symlinked target into a checkout is inside it), with `..` as a whole path segment only.
  for (const src of [o.crewSrc, o.studioSrc, o.gardenSrc, o.coreSrc].filter(Boolean)) {
    for (const [flag, dir] of [['--out', o.out], ['--cargo-target', o.cargoTarget]]) {
      if (!dir) continue;
      if (isInside(realish(src), realish(dir))) { console.error(`wicked-selftest pack: ${flag} ${dir} is inside the source checkout ${src}; choose a directory outside it`); return 2; }
    }
  }
  // --out must not exist: creating it is the claim (mkdir is atomic), so two packs can never share one output.
  mkdirSync(dirname(o.out), { recursive: true });
  try { mkdirSync(o.out); } catch (err) { console.error(`wicked-selftest pack: --out ${o.out} ${err.code === 'EEXIST' ? 'already exists (it must not: pass a new directory)' : `cannot be created: ${err.message}`}`); return 2; }
  const stage = join(o.out, '.stage');
  const env = buildEnv(stage, o.npmCache, o.cargoTarget);
  const facts = {};
  for (const [k, dir] of [['crew', o.crewSrc], ['studio', o.studioSrc], ['garden', o.gardenSrc], ['core', o.coreSrc]]) {
    if (!dir) continue;
    facts[k] = gitFacts(dir, env);
    if (facts[k].dirty && !o.allowDirty) {
      console.error(`wicked-selftest pack: ${dir} has uncommitted or untracked changes; the pack is built from HEAD (${facts[k].sha.slice(0, 7)}) and would leave them out. Commit them, or pass --allow-dirty.`);
      return 2;
    }
  }
  const set = { $comment: 'written by wicked-selftest pack; install with: wicked-selftest run --set <this file>', built: { tier: o.coreSrc ? 2 : 1, at: new Date().toISOString() } };
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

  if (o.coreSrc) {
    const f = facts.core;
    const co = exportTree(o.coreSrc, f.sha, stage, 'wicked-core', env);
    const ts = join(co, CORE_TS_DIR);
    sh(npm('ci'), ts, env, { slot: o.buildSlot });
    // napi copies the library out of the cargo target AFTER cargo releases its own lock, so two packs sharing one
    // --cargo-target could each ship the other's binary: the whole build-and-copy holds a lock on that target.
    const release = o.cargoTarget ? await lockDir(`${realish(o.cargoTarget)}.selftest-lock`) : () => {};
    try {
      sh(npm('run', 'build'), ts, env, { slot: o.buildSlot });
    } finally {
      release();
    }
    const nodes = readdirSync(ts).filter((n) => /^wicked-core-ts\.[a-z0-9_-]+\.node$/.test(n));
    if (nodes.length !== 1) throw new Error(`core-ts build left ${nodes.length} wicked-core-ts.<triple>.node files in ${CORE_TS_DIR} (want exactly the host's one): ${nodes.join(', ') || 'none'}`);
    const pj = JSON.parse(readFileSync(join(ts, 'package.json'), 'utf8'));
    const version = `${pj.version}+st.${f.sha.slice(0, 7)}`;
    pj.version = version;
    pj.files = [...new Set([...(pj.files ?? []), nodes[0]])];
    delete pj.optionalDependencies; // a published platform binary must not ride in beside the one built here
    delete pj.scripts; // the pack is installed, never built again (no prepare/install hook from the export)
    writeFileSync(join(ts, 'package.json'), `${JSON.stringify(pj, null, 2)}\n`);
    const tgzName = sh(npm('pack', '--silent', '--pack-destination', o.out), ts, env, { capture: true }).split('\n').pop();
    set.coreTs = tgzName;
    // What the `wicked-core` CLI shim must answer for this engine (its gate-hook handshake): the engine crate's version
    // and its gate protocol, read from the tree the addon was built from. A published set has neither; the run then
    // keeps its table and its defaults.
    const engineSemver = readFileSync(join(co, 'Cargo.toml'), 'utf8').match(/^\[package\][^[]*?^version\s*=\s*"([^"]+)"/m)?.[1] ?? null;
    let gateProtocol = null;
    try { gateProtocol = Number(readFileSync(join(co, 'src', 'gate_hook.rs'), 'utf8').match(/pub const GATE_PROTOCOL_VERSION: u32 = (\d+);/)?.[1]) || null; } catch { /* no such file in this tree */ }
    set.built.core = { sha: f.sha, dirty: f.dirty, version, binary: nodes[0], engineSemver, gateProtocol, note: note(f) };
  }

  writeFileSync(join(o.out, 'set.json.tmp'), `${JSON.stringify(set, null, 2)}\n`);
  renameSync(join(o.out, 'set.json.tmp'), join(o.out, 'set.json')); // published whole, or not at all
  console.log(`wicked-selftest pack: wrote ${join(o.out, 'set.json')} (the staging exports under ${stage} can be removed)`);
  return 0;
}
