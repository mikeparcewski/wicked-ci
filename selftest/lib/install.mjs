// Install a SET into the hermetic root: wicked-crew + wicked-bus (the prebuilt wicked-core-ts platform package rides
// crew's pin), and the wicked-garden plugin laid out the way Claude Code's marketplace cache does — the same tree crew
// seeds its skills root from on a customer machine. Each comes from npm / its git tag (the published set), or from a
// local pack (`wicked-selftest pack`, or any .tgz / garden directory). This module never builds anything.
import { createWriteStream, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, appendFileSync } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { basename, dirname, join, resolve } from 'node:path';
import { isLocalSource } from './args.mjs';
import { globalLibDir } from './env.mjs';
import { mustRun, npmArgv, run } from './proc.mjs';
import { maxVersion } from './semver.mjs';

const GARDEN_REPO = 'https://github.com/mikeparcewski/wicked-garden.git';
const GARDEN_TARBALL = (tag) => `https://github.com/mikeparcewski/wicked-garden/archive/refs/tags/${tag}.tar.gz`;

function readPkg(dir) {
  return JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'));
}

/** Resolve the installed tree: crew dir, bus CLI, core-ts (nested or hoisted), platform package. */
export function installedTree(L) {
  const lib = globalLibDir(L);
  const crewDir = join(lib, 'wicked-crew');
  const busDir = join(lib, 'wicked-bus');
  const nestedCore = join(crewDir, 'node_modules', 'wicked-core-ts');
  const coreDir = existsSync(nestedCore) ? nestedCore : join(lib, 'wicked-core-ts');
  const platform = `wicked-core-ts-${process.platform}-${process.arch}${process.platform === 'linux' ? guessLibc() : ''}`;
  const platformDirCandidates = [join(crewDir, 'node_modules', platform), join(coreDir, 'node_modules', platform), join(lib, platform)];
  const platformDir = platformDirCandidates.find((p) => existsSync(p)) ?? null;
  return {
    lib,
    crewDir,
    crewBin: join(crewDir, 'dist', 'cli', 'index.js'),
    busDir,
    busCli: join(busDir, 'commands', 'cli.js'),
    coreDir,
    platformPkgName: platform,
    platformDir,
    studioIndex: join(crewDir, 'dist', 'studio', 'index.html'),
    studioInventory: join(crewDir, 'dist', 'studio', 'testid-inventory.json'),
  };
}

function guessLibc() {
  // napi-rs names linux packages `-gnu` / `-musl`; the glibc case is what every GitHub runner is.
  try {
    const rel = process.report?.getReport?.();
    if (rel && rel.header && rel.header.glibcVersionRuntime) return '-gnu';
    if (rel && rel.sharedObjects && rel.sharedObjects.some((s) => /musl/.test(s))) return '-musl';
  } catch { /* fall through */ }
  return '-gnu';
}

export function installedVersions(L) {
  const t = installedTree(L);
  const v = { crew: null, bus: null, coreTs: null, coreTsPlatform: null, studioBundle: null, coreTsRange: null };
  try { v.crew = readPkg(t.crewDir).version; v.coreTsRange = readPkg(t.crewDir).dependencies?.['wicked-core-ts'] ?? null; } catch { /* missing */ }
  try { v.bus = readPkg(t.busDir).version; } catch { /* missing */ }
  try { v.coreTs = readPkg(t.coreDir).version; } catch { /* missing */ }
  try { v.coreTsPlatform = t.platformDir ? readPkg(t.platformDir).version : null; } catch { /* missing */ }
  try { v.studioBundle = JSON.parse(readFileSync(t.studioInventory, 'utf8')).studioVersion ?? null; } catch { /* headless */ }
  return v;
}

/** A plugin version is one path component: semver, nothing else. The manifest is the artifact's own data, so a
 *  version like `../../x` must never reach a recursive delete (the cache dir is under the hermetic root). */
export const GARDEN_VERSION_RE = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

/** Move a staged garden tree into the marketplace-cache layout under the root: the manifest's version is validated,
 *  and the destination is proven to sit directly under the cache dir before anything is removed or renamed. */
export function placeGarden(L, staging, label) {
  const manifestPath = join(staging, '.claude-plugin', 'plugin.json');
  // The manifest is the artifact's data: a link on its path could make the installer read (and echo) a host file.
  for (const p of [join(staging, '.claude-plugin'), manifestPath]) {
    const st = lstatSync(p, { throwIfNoEntry: false });
    if (st === undefined) throw new Error(`garden ${label}: no .claude-plugin/plugin.json (not a garden plugin tree)`);
    if (st.isSymbolicLink() || !(p === manifestPath ? st.isFile() : st.isDirectory())) throw new Error(`garden ${label}: ${p.slice(staging.length + 1)} must be a plain ${p === manifestPath ? 'file' : 'directory'}, not a link`);
  }
  let version;
  try { version = JSON.parse(readFileSync(manifestPath, 'utf8')).version; } catch { throw new Error(`garden ${label}: .claude-plugin/plugin.json is not JSON`); }
  if (typeof version !== 'string' || !GARDEN_VERSION_RE.test(version)) throw new Error(`garden ${label}: .claude-plugin/plugin.json version ${JSON.stringify(version)} is not a semver`);
  const cacheDir = resolve(L.claude, 'plugins', 'cache', 'wicked-garden', 'wicked-garden');
  mkdirSync(cacheDir, { recursive: true });
  const dest = resolve(cacheDir, version);
  if (dirname(dest) !== cacheDir) throw new Error(`garden ${label}: destination ${dest} escapes the plugin cache`);
  rmSync(dest, { recursive: true, force: true });
  renameSync(staging, dest);
  return { version, dest };
}

/** The `name` and `version` inside a local npm tarball (`package/package.json`), read without installing it. */
export function tarballManifest(tgz, env) {
  const r = mustRun(['tar', '-xzOf', tgz, 'package/package.json'], { env, timeoutMs: 120_000 });
  try { const j = JSON.parse(r.stdout); return { name: j.name, version: j.version }; } catch { throw new Error(`${basename(tgz)}: package/package.json is not JSON`); }
}

/** A local pack must be the package its set key names, so a bus tarball given as core-ts can't leave the published
 *  engine under test. Returns the tarball's version, which the install is then checked against. */
export function expectTarball(name, v, env) {
  if (!isLocalSource(v)) return null;
  const m = tarballManifest(v, env);
  if (m.name !== name) throw new Error(`${basename(v)} is ${m.name ?? 'an unnamed package'}, not ${name}`);
  return m.version;
}

/** `npm install -g` the requested crew + bus into the prefix; optionally pin core-ts inside crew. */
export function installNpm(L, env, { crew, bus, coreTs }, log) {
  const npm = npmArgv();
  const want = { crew: expectTarball('wicked-crew', crew, env), bus: expectTarball('wicked-bus', bus, env), coreTs: expectTarball('wicked-core-ts', coreTs, env) };
  const specs = [npmSpec('wicked-crew', crew), npmSpec('wicked-bus', bus)];
  log(`install: ${specs.join(' ')} -> ${L.npm}`);
  const t0 = Date.now();
  const r = mustRun([...npm, 'install', '-g', '--no-fund', '--no-audit', '--loglevel=error', ...specs], { env, cwd: L.root, timeoutMs: 600_000 });
  appendFileSync(L.installLog, `$ npm install -g ${specs.join(' ')}\n${r.stdout}\n${r.stderr}\n`);
  log(`install: npm done in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  if (coreTs && coreTs !== 'pinned' && coreTs !== 'latest') {
    const t = installedTree(L);
    log(`install: pinning wicked-core-ts@${coreTs} inside ${t.crewDir}`);
    const r2 = mustRun([...npm, 'install', '--prefix', t.crewDir, '--no-save', '--no-package-lock', '--omit=dev', '--no-fund', '--no-audit', '--loglevel=error', npmSpec('wicked-core-ts', coreTs)], { env, cwd: t.crewDir, timeoutMs: 600_000 });
    appendFileSync(L.installLog, `$ npm install --prefix crew wicked-core-ts@${coreTs}\n${r2.stdout}\n${r2.stderr}\n`);
  }
  const got = installedVersions(L);
  // What was installed IS the pack that was named (not a published copy npm resolved instead).
  for (const k of ['crew', 'bus', 'coreTs']) if (want[k] !== null && got[k] !== want[k]) throw new Error(`the installed ${k} is ${got[k]}, not the local pack's ${want[k]}`);
  return got;
}

/** An npm install spec: a local pack is its absolute path (npm installs a tarball file as is), else `<name>@<version>`. */
export function npmSpec(name, v) {
  return isLocalSource(v) ? v : `${name}@${v}`;
}

/** The git tag for a `--garden` ref: `latest` → the highest release tag; `12.34.0` → `v12.34.0`. */
export function resolveGardenTag(ref, env) {
  if (ref === 'latest') {
    const r = mustRun(['git', 'ls-remote', '--tags', '--refs', GARDEN_REPO], { env, timeoutMs: 120_000 });
    const tags = r.stdout.split('\n').map((l) => l.split('\t')[1] ?? '').filter(Boolean).map((t) => t.replace('refs/tags/', ''));
    const best = maxVersion(tags.map((t) => t.replace(/^v/, '')));
    if (!best) throw new Error('could not resolve the latest wicked-garden tag');
    return `v${best}`;
  }
  return ref.startsWith('v') ? ref : `v${ref}`;
}

/**
 * Lay the garden plugin down as `<CLAUDE_CONFIG_DIR>/plugins/cache/wicked-garden/wicked-garden/<version>`
 * — the marketplace-cache layout crew's skills seed discovers (plugin-source tier 2). Returns the
 * plugin version read from its manifest.
 */
export async function installGarden(L, env, ref, log) {
  if (isLocalSource(ref)) return installGardenLocal(L, env, ref, log);
  const tag = resolveGardenTag(ref, env);
  const url = GARDEN_TARBALL(tag);
  const tgz = join(L.tmp, `wicked-garden-${tag}.tgz`);
  log(`install: wicked-garden ${tag} from its tag tarball`);
  const t0 = Date.now();
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok || !res.body) throw new Error(`garden tarball ${url} -> HTTP ${res.status}`);
  await pipeline(Readable.fromWeb(res.body), createWriteStream(tgz));
  const staging = join(L.tmp, `garden-staging-${Date.now()}`);
  mkdirSync(staging, { recursive: true });
  // `tar` is on every GitHub runner (bsdtar on Windows/macOS, GNU tar on Linux); both take these flags.
  mustRun(['tar', '-xzf', tgz, '-C', staging, '--strip-components=1'], { env, timeoutMs: 300_000 });
  const { version, dest } = placeGarden(L, staging, tag);
  rmSync(tgz, { force: true });
  log(`install: garden ${version} laid out at plugins/cache/... in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  return { tag, version, path: dest };
}

/** A local garden: a .tgz (`npm pack` output has a `package/` top dir, a GitHub archive `wicked-garden-<tag>/`; both
 *  strip one component) or a directory (a git checkout is exported with `git archive HEAD`, so only TRACKED files at
 *  HEAD go in — what a tag tarball holds; a plain directory is copied without .git and node_modules). */
async function installGardenLocal(L, env, src, log) {
  const { cpSync, statSync } = await import('node:fs');
  const staging = join(L.tmp, `garden-staging-${Date.now()}`);
  mkdirSync(staging, { recursive: true });
  const t0 = Date.now();
  if (statSync(src).isDirectory()) {
    if (existsSync(join(src, '.git'))) {
      const tar = join(L.tmp, `garden-local-${Date.now()}.tar`);
      mustRun(['git', '-c', 'core.fsmonitor=false', '-C', src, 'archive', '--format=tar', '-o', tar, 'HEAD'], { env, timeoutMs: 300_000 });
      mustRun(['tar', '-xf', tar, '-C', staging], { env, timeoutMs: 300_000 });
      rmSync(tar, { force: true });
    } else {
      cpSync(src, staging, { recursive: true, filter: (p) => !/[\\/](\.git|node_modules)([\\/]|$)/.test(p.slice(src.length)) });
    }
  } else {
    mustRun(['tar', '-xzf', src, '-C', staging, '--strip-components=1'], { env, timeoutMs: 300_000 });
  }
  const { version, dest } = placeGarden(L, staging, basename(src));
  log(`install: garden ${version} from the local ${basename(src)} laid out at plugins/cache/... in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  return { tag: `local:${basename(src)}`, version, path: dest };
}

/**
 * The engine CRATE version the installed wicked-core-ts addon was built from — what the wrapped claude
 * carrier demands the `wicked-core` CLI's `gate-hook --protocol-version` line report as `semver`
 * (crew#275 skew guard; the addon exports no version of its own). Known pairs below; anything else is
 * the latest known value, and S04 self-corrects from the engine's own mismatch message ("engine (napi
 * addon) is X") before its pipeline launch. `WICKED_SMOKE_CORE_SEMVER` overrides.
 */
const ENGINE_SEMVER_BY_CORE_TS = { '0.7.21': '0.4.0', '0.7.22': '0.4.0', '0.7.23': '0.4.0', '0.7.24': '0.4.0' };

export function engineSemverFor(coreTs) {
  if (process.env.WICKED_SMOKE_CORE_SEMVER) return { semver: process.env.WICKED_SMOKE_CORE_SEMVER, source: 'env' };
  if (coreTs && ENGINE_SEMVER_BY_CORE_TS[coreTs]) return { semver: ENGINE_SEMVER_BY_CORE_TS[coreTs], source: 'table' };
  return { semver: '0.4.0', source: 'default (latest known pair) — S04 self-corrects from the engine message' };
}

/** Best-effort: `npm view <pkg> version` for the report when `latest` was requested (network). */
export function npmViewVersion(pkg, env) {
  const r = run([...npmArgv(), 'view', pkg, 'version', '--loglevel=error'], { env, timeoutMs: 60_000 });
  return r.status === 0 ? r.stdout.trim() : null;
}

export function listDir(p) {
  try { return readdirSync(p); } catch { return []; }
}
