// `npm run check` (pack part): `wicked-selftest pack` on disposable fixture checkouts with trivial build scripts (no
// product build, no network: the fixtures have no dependencies). Proves the contract the self-test relies on:
//   - the pack is built from an export of HEAD under --out, and the checkout is never written (byte-equal, clean);
//   - crew's version is stamped `+st.<sha7>` in the pack, and THIS studio's dist is the bundle inside it;
//   - garden is exported at HEAD with its own manifest version;
//   - a checkout with uncommitted or untracked changes is refused, and --allow-dirty records that they were left out;
//   - `run --set` accepts what pack wrote, and a bus tarball named as crew is refused by name.
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { isInside, packMain } from './pack.mjs';
import { parseArgs, readSet } from './args.mjs';
import { expectTarball, pinInsideCrew, tarballManifest } from './install.mjs';

const ENV = { ...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_AUTHOR_NAME: 'selfcheck', GIT_AUTHOR_EMAIL: 'selfcheck@example.invalid', GIT_COMMITTER_NAME: 'selfcheck', GIT_COMMITTER_EMAIL: 'selfcheck@example.invalid' };
function run(argv, cwd) {
  const r = spawnSync(argv[0], argv.slice(1), { cwd, env: ENV, encoding: 'utf8', shell: false });
  if (r.status !== 0) throw new Error(`${argv.join(' ')} in ${cwd}: ${r.status}\n${r.stdout}\n${r.stderr}`);
  return r.stdout.trim();
}
function repo(dir, files) {
  for (const [p, body] of Object.entries(files)) { mkdirSync(join(dir, p, '..'), { recursive: true }); writeFileSync(join(dir, p), body); }
  run(['git', 'init', '-q', '-b', 'main'], dir);
  run(['git', 'add', '-A'], dir);
  run(['git', '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'fixture'], dir);
  return run(['git', 'rev-parse', 'HEAD'], dir);
}
const quiet = async (fn) => { const log = console.log; const err = console.error; console.log = () => {}; console.error = () => {}; try { return await fn(); } finally { console.log = log; console.error = err; } };

const base = mkdtempSync(join(tmpdir(), 'selftest-pack-'));
try {
  const studio = join(base, 'studio');
  const crew = join(base, 'crew');
  const garden = join(base, 'garden');
  const studioPkg = JSON.stringify({ name: 'wicked-studio', version: '0.9.0', private: true, scripts: { build: 'node b.mjs' } }, null, 2);
  repo(studio, {
    'package.json': studioPkg,
    'package-lock.json': JSON.stringify({ name: 'wicked-studio', version: '0.9.0', lockfileVersion: 3, requires: true, packages: { '': { name: 'wicked-studio', version: '0.9.0' } } }),
    'b.mjs': "import { mkdirSync, writeFileSync } from 'node:fs'; mkdirSync('dist', { recursive: true }); writeFileSync('dist/index.html', '<!-- studio-fixture-marker -->'); writeFileSync('dist/testid-inventory.json', '{\"studioVersion\":\"0.9.0\"}');\n",
  });
  const crewPkg = JSON.stringify({ name: 'wicked-crew', version: '1.2.3', files: ['dist'], scripts: { build: 'node build.mjs', 'build:with-studio': 'node build.mjs studio' } }, null, 2);
  const crewFiles = {
    'package.json': JSON.stringify({ name: 'crew-root', private: true, workspaces: ['packages/crew', 'packages/crew-api-types'] }),
    'package-lock.json': JSON.stringify({ name: 'crew-root', lockfileVersion: 3, requires: true, packages: { '': { name: 'crew-root', workspaces: ['packages/crew', 'packages/crew-api-types'] }, 'node_modules/wicked-crew': { resolved: 'packages/crew', link: true }, 'node_modules/wicked-crew-api-types': { resolved: 'packages/crew-api-types', link: true }, 'packages/crew': { name: 'wicked-crew', version: '1.2.3' }, 'packages/crew-api-types': { name: 'wicked-crew-api-types', version: '0.228.0' } } }),
    'packages/crew/package.json': crewPkg,
    // crew's own wire types, a workspace package crew names as a devDependency (wicked-crew packages/crew-api-types).
    'packages/crew-api-types/package.json': JSON.stringify({ name: 'wicked-crew-api-types', version: '0.228.0', types: './index.d.ts', files: ['index.d.ts'] }, null, 2),
    'packages/crew-api-types/index.d.ts': 'export type Fixture = 1;\n',
    'packages/crew/build.mjs': "import { mkdirSync, writeFileSync } from 'node:fs'; mkdirSync('dist/cli', { recursive: true }); writeFileSync('dist/cli/index.js', ''); if (process.argv[2] === 'studio') { mkdirSync('dist/studio', { recursive: true }); writeFileSync('dist/studio/index.html', '<!-- lockfile studio -->'); }\n",
  };
  const crewSha = repo(crew, crewFiles);
  const gardenSha = repo(garden, { '.claude-plugin/plugin.json': JSON.stringify({ name: 'wicked-garden', version: '12.0.0' }), 'README.md': 'g' });

  const out = join(base, 'out dir');  // a space in the output path (argument arrays, no shell)
  const indexBefore = readFileSync(join(garden, '.git', 'index'));
  const code = await quiet(() => packMain(['--crew-src', crew, '--studio-src', studio, '--garden-src', garden, '--out', out]));
  if (code !== 0) throw new Error(`pack exited ${code}`);
  if (!readFileSync(join(garden, '.git', 'index')).equals(indexBefore)) throw new Error('pack rewrote a source checkout\'s index (optional locks)');
  if (await quiet(() => packMain(['--garden-src', garden, '--out', out])) !== 2) throw new Error('an existing --out must be refused (two packs never share one)');
  if (await quiet(() => packMain(['--garden-src', garden, '--out', join(garden, 'packs')])) !== 2 || existsSync(join(garden, 'packs'))) throw new Error('an --out inside a source checkout must be refused before anything is written');
  // The checkouts are only read.
  if (readFileSync(join(crew, 'packages', 'crew', 'package.json'), 'utf8') !== crewPkg) throw new Error('pack changed the crew checkout\'s package.json');
  if (readFileSync(join(studio, 'package.json'), 'utf8') !== studioPkg) throw new Error('pack changed the studio checkout');
  for (const d of [crew, studio, garden]) {
    if (run(['git', 'status', '--porcelain', '--untracked-files=normal'], d) !== '') throw new Error(`pack left changes in ${d}`);
    if (existsSync(join(d, 'node_modules')) || existsSync(join(d, 'dist')) || existsSync(join(d, 'packages', 'crew', 'dist'))) throw new Error(`pack built inside the checkout ${d}`);
  }
  const set = JSON.parse(readFileSync(join(out, 'set.json'), 'utf8'));
  const m = tarballManifest(join(out, set.crew), ENV);
  if (m.name !== 'wicked-crew' || m.version !== `1.2.3+st.${crewSha.slice(0, 7)}`) throw new Error(`crew pack is ${m.name}@${m.version}`);
  const html = run(['tar', '-xzOf', join(out, set.crew), 'package/dist/studio/index.html'], base);
  if (!html.includes('studio-fixture-marker')) throw new Error('the crew pack does not bundle the --studio-src dist');
  // crew's wire types are packed from the SAME export (wicked-ci: the pin step must resolve crew's own
  // `^0.2xx` devDependency without the registry, which may not have that version yet).
  const at = set.crewApiTypes ? tarballManifest(join(out, set.crewApiTypes), ENV) : null;
  if (at?.name !== 'wicked-crew-api-types' || at?.version !== `0.228.0+st.${crewSha.slice(0, 7)}`) throw new Error(`crew api-types pack is ${JSON.stringify(at)} (set.crewApiTypes ${set.crewApiTypes})`);
  if (!run(['tar', '-xzOf', join(out, set.crewApiTypes), 'package/index.d.ts'], base).includes('Fixture')) throw new Error('the api-types pack lacks index.d.ts');
  if (set.built.crew.sha !== crewSha || set.built.crew.dirty !== false || set.built.garden.sha !== gardenSha) throw new Error(`set.json provenance: ${JSON.stringify(set.built)}`);
  const gm = run(['tar', '-xzOf', join(out, set.garden), 'wicked-garden/.claude-plugin/plugin.json'], base);
  if (JSON.parse(gm).version !== '12.0.0') throw new Error('garden export lost its manifest');
  // run --set accepts it; a pack under the wrong key is refused by name.
  const rs = readSet(join(out, 'set.json'));
  if (rs.crew !== join(out, set.crew) || rs.garden !== join(out, set.garden)) throw new Error(`readSet of a pack's set.json: ${JSON.stringify(rs)}`);
  if (rs.crewApiTypes !== join(out, set.crewApiTypes)) throw new Error(`readSet drops the crew api-types pack: ${JSON.stringify(rs)}`);
  let threw = false; try { expectTarball('wicked-bus', rs.crew, ENV); } catch { threw = true; }
  if (!threw) throw new Error('a crew tarball given as bus must be refused');
  if (expectTarball('wicked-crew', rs.crew, ENV) !== m.version) throw new Error('expectTarball returns the pack version');

  // Tier 2: --core-src builds crates/wicked-core-ts (here a fixture build that writes a fake binding) and packs it with
  // the host's .node inside, the version stamped, and no scripts left to run at install.
  const core = join(base, 'core');
  const tsPkg = { name: 'wicked-core-ts', version: '0.15.0', main: 'index.js', files: ['index.js'], scripts: { build: 'node b.mjs', prepack: 'node -e "process.exit(1)"' } };
  const coreSha = repo(core, {
    'Cargo.toml': '[workspace]\nmembers = []\n\n[package]\nname = "wicked-core"\nversion = "0.4.7"\n',
    'src/gate_hook.rs': 'pub const GATE_PROTOCOL_VERSION: u32 = 3;\n',
    'crates/wicked-core-ts/package.json': JSON.stringify(tsPkg, null, 2),
    'crates/wicked-core-ts/package-lock.json': JSON.stringify({ name: 'wicked-core-ts', version: '0.15.0', lockfileVersion: 3, requires: true, packages: { '': { name: 'wicked-core-ts', version: '0.15.0' } } }),
    'crates/wicked-core-ts/index.js': 'module.exports = {};\n',
    // The fixture build writes through CARGO_TARGET_DIR (as cargo would), and the export's package.json gains the
    // platform optionalDependencies the real one carries (added after `npm ci`, so no registry is needed).
    'crates/wicked-core-ts/b.mjs': "import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'; import { join } from 'node:path'; writeFileSync('wicked-core-ts.fixture-host.node', 'core-fixture-binding'); mkdirSync(process.env.CARGO_TARGET_DIR, { recursive: true }); writeFileSync(join(process.env.CARGO_TARGET_DIR, 'built'), 'x'); const p = JSON.parse(readFileSync('package.json', 'utf8')); p.optionalDependencies = { 'wicked-core-ts-fixture-host': '0.15.0' }; writeFileSync('package.json', JSON.stringify(p));\n",
  });
  const out4 = join(base, 'out4');
  // A cargo target inside a source checkout is refused before anything is written.
  if (await quiet(() => packMain(['--core-src', core, '--out', join(base, 'out4x'), '--cargo-target', join(core, 'target')])) !== 2 || existsSync(join(core, 'target')) || existsSync(join(base, 'out4x'))) throw new Error('a --cargo-target inside a source checkout must be refused before anything is written');
  // …also through a symlink that points into the checkout, and a name that only starts with two dots is still inside.
  symlinkSync(core, join(base, 'core-link'));
  if (await quiet(() => packMain(['--core-src', core, '--out', join(base, 'out4y'), '--cargo-target', join(base, 'core-link', 'target')])) !== 2 || existsSync(join(core, 'target'))) throw new Error('a --cargo-target symlinked into a source checkout must be refused');
  if (await quiet(() => packMain(['--core-src', core, '--out', join(base, 'out4z'), '--cargo-target', join(core, '..target')])) !== 2 || existsSync(join(core, '..target'))) throw new Error('a --cargo-target named ..target inside a checkout must be refused');
  if (!isInside('/a/b', '/a/b/..c') || isInside('/a/b', '/a/bc') || isInside('/a/b', '/a') || !isInside('/a/b', '/a/b')) throw new Error('isInside segment rules');
  if (await quiet(() => packMain(['--core-src', core, '--out', out4, '--cargo-target', join(base, 'cargo-target')])) !== 0) throw new Error('pack --core-src');
  if (!existsSync(join(base, 'cargo-target', 'built'))) throw new Error('the Tier 2 build did not get --cargo-target as CARGO_TARGET_DIR');
  const s4 = JSON.parse(readFileSync(join(out4, 'set.json'), 'utf8'));
  if (s4.built.tier !== 2 || s4.built.core.sha !== coreSha || s4.built.core.binary !== 'wicked-core-ts.fixture-host.node') throw new Error(`Tier 2 provenance: ${JSON.stringify(s4.built)}`);
  // The engine's handshake facts, from the tree: the shim must answer what THIS engine speaks.
  if (s4.built.core.engineSemver !== '0.4.7' || s4.built.core.gateProtocol !== 3) throw new Error(`Tier 2 handshake facts: ${JSON.stringify(s4.built.core)}`);
  if (readSet(join(out4, 'set.json')).setBuilt?.core?.gateProtocol !== 3) throw new Error('readSet must carry the set\'s built block');
  // The facts belong to that engine pack: another --core-ts after --set leaves them behind (the shim must not announce
  // the pack's protocol for a published engine).
  if (parseArgs(['--set', join(out4, 'set.json')]).setBuilt?.core?.gateProtocol !== 3) throw new Error('run --set keeps the Tier 2 engine facts');
  if (parseArgs(['--set', join(out4, 'set.json'), '--core-ts', '0.7.24']).setBuilt?.core !== undefined) throw new Error('a --core-ts override must drop the Tier 2 engine facts');
  const cm = tarballManifest(join(out4, s4.coreTs), ENV);
  if (cm.name !== 'wicked-core-ts' || cm.version !== `0.15.0+st.${coreSha.slice(0, 7)}`) throw new Error(`core-ts pack is ${cm.name}@${cm.version}`);
  const full = JSON.parse(run(['tar', '-xzOf', join(out4, s4.coreTs), 'package/package.json'], base));
  if (full.scripts || full.optionalDependencies) throw new Error(`the core-ts pack must carry no scripts and no platform optionalDependencies: ${JSON.stringify({ scripts: full.scripts, optionalDependencies: full.optionalDependencies })}`);
  if (!full.files?.includes('wicked-core-ts.fixture-host.node')) throw new Error(`the core-ts pack's files must list the built binding: ${JSON.stringify(full.files)}`);
  if (run(['tar', '-xzOf', join(out4, s4.coreTs), 'package/wicked-core-ts.fixture-host.node'], base) !== 'core-fixture-binding') throw new Error('the core-ts pack does not carry the built binding');
  if (readSet(join(out4, 'set.json')).coreTs !== join(out4, s4.coreTs)) throw new Error('readSet of a Tier 2 set');
  if (expectTarball('wicked-core-ts', join(out4, s4.coreTs), ENV) !== cm.version) throw new Error('expectTarball of the core-ts pack');

  // The pin itself, offline (wicked-ci job 139069995630): an installed crew whose devDependency names its own api-types
  // range that no registry or cache has. Without the api-types pack the pin can't resolve the tree; with it, the pin
  // installs the engine pack, omits the dev package and leaves crew's manifest as it was.
  {
    const crewDir = join(base, 'installed-crew');
    mkdirSync(crewDir);
    const manifest = JSON.stringify({ name: 'wicked-crew', version: '1.2.3', dependencies: { 'wicked-core-ts': '^0.15.0' }, devDependencies: { 'wicked-crew-api-types': '^0.228.0' } }, null, 2);
    writeFileSync(join(crewDir, 'package.json'), manifest);
    writeFileSync(join(base, 'user-npmrc'), '');
    writeFileSync(join(base, 'global-npmrc'), '');
    const off = { ...ENV, npm_config_offline: 'true', npm_config_cache: join(base, 'npm-cache'), npm_config_userconfig: join(base, 'user-npmrc'), npm_config_globalconfig: join(base, 'global-npmrc') };
    const pin = { coreTs: join(out4, s4.coreTs), crewApiTypes: join(out, set.crewApiTypes) };
    // It must fail for THIS reason (the dev edge cannot resolve), not for anything else in the setup.
    let why = null; try { pinInsideCrew(crewDir, off, { coreTs: pin.coreTs }); } catch (err) { why = err.message; }
    if (why === null || !/ENOTCACHED|ETARGET|notarget/.test(why) || !why.includes('wicked-crew-api-types')) throw new Error(`the pin without crew's api-types pack must fail resolving it (the check would be vacuous): ${why}`);
    pinInsideCrew(crewDir, off, pin);
    const core = JSON.parse(readFileSync(join(crewDir, 'node_modules', 'wicked-core-ts', 'package.json'), 'utf8'));
    if (core.version !== cm.version) throw new Error(`the pin installed wicked-core-ts ${core.version}, not the pack's ${cm.version}`);
    if (existsSync(join(crewDir, 'node_modules', 'wicked-crew-api-types'))) throw new Error('the pin installed the dev-only api-types (--omit=dev)');
    if (readFileSync(join(crewDir, 'package.json'), 'utf8') !== manifest) throw new Error('the pin rewrote crew\'s package.json (--no-save)');
  }
  if (run(['git', 'status', '--porcelain', '--untracked-files=normal'], core) !== '' || existsSync(join(core, 'crates', 'wicked-core-ts', 'node_modules'))) throw new Error('pack --core-src built inside the checkout');

  // An api-types package whose declared types file is not committed (it would come from a build this pack never runs)
  // is refused, and no set is written (codex delta on wicked-ci#88).
  {
    const crewNoTypes = join(base, 'crew-no-types');
    repo(crewNoTypes, { ...crewFiles, 'packages/crew-api-types/package.json': JSON.stringify({ name: 'wicked-crew-api-types', version: '0.228.0', types: './gen/index.d.ts', files: ['gen', 'index.d.ts'] }, null, 2) });
    const outNoTypes = join(base, 'out-no-types');
    let why = null;
    try { await quiet(() => packMain(['--crew-src', crewNoTypes, '--out', outNoTypes])); } catch (err) { why = err.message; }
    if (!/api-types pack has no package\/gen\/index\.d\.ts/.test(why ?? '') || existsSync(join(outNoTypes, 'set.json'))) throw new Error(`an api-types pack without its types file must be refused, with no set written: ${why}`);
  }

  // Dirty trees: an untracked file is refused (exit 2, nothing written); --allow-dirty records it was left out.
  writeFileSync(join(garden, 'new-skill.md'), 'untracked');
  const out2 = join(base, 'out2');
  if (await quiet(() => packMain(['--garden-src', garden, '--out', out2])) !== 2) throw new Error('a dirty checkout must be refused');
  if (existsSync(join(out2, 'set.json'))) throw new Error('a refused pack wrote a set');
  const out3 = join(base, 'out3');
  if (await quiet(() => packMain(['--garden-src', garden, '--out', out3, '--allow-dirty'])) !== 0) throw new Error('--allow-dirty');
  const s3 = JSON.parse(readFileSync(join(out3, 'set.json'), 'utf8'));
  if (s3.built.garden.dirty !== true || !/LEFT OUT/.test(s3.built.garden.note ?? '')) throw new Error(`--allow-dirty must record the left-out changes: ${JSON.stringify(s3.built.garden)}`);
  if (run(['tar', '-tzf', join(out3, s3.garden)], base).includes('new-skill.md')) throw new Error('an untracked file reached the export');
  console.log('pack selfcheck ok');
} finally {
  rmSync(base, { recursive: true, force: true });
}
