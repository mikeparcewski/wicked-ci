// `npm run check` (pack part): `wicked-selftest pack` on disposable fixture checkouts with trivial build scripts (no
// product build, no network: the fixtures have no dependencies). Proves the contract the self-test relies on:
//   - the pack is built from an export of HEAD under --out, and the checkout is never written (byte-equal, clean);
//   - crew's version is stamped `+st.<sha7>` in the pack, and THIS studio's dist is the bundle inside it;
//   - garden is exported at HEAD with its own manifest version;
//   - a checkout with uncommitted or untracked changes is refused, and --allow-dirty records that they were left out;
//   - `run --set` accepts what pack wrote, and a bus tarball named as crew is refused by name.
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { packMain } from './pack.mjs';
import { readSet } from './args.mjs';
import { expectTarball, tarballManifest } from './install.mjs';

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
  const crewSha = repo(crew, {
    'package.json': JSON.stringify({ name: 'crew-root', private: true, workspaces: ['packages/crew'] }),
    'package-lock.json': JSON.stringify({ name: 'crew-root', lockfileVersion: 3, requires: true, packages: { '': { name: 'crew-root', workspaces: ['packages/crew'] }, 'node_modules/wicked-crew': { resolved: 'packages/crew', link: true }, 'packages/crew': { name: 'wicked-crew', version: '1.2.3' } } }),
    'packages/crew/package.json': crewPkg,
    'packages/crew/build.mjs': "import { mkdirSync, writeFileSync } from 'node:fs'; mkdirSync('dist/cli', { recursive: true }); writeFileSync('dist/cli/index.js', ''); if (process.argv[2] === 'studio') { mkdirSync('dist/studio', { recursive: true }); writeFileSync('dist/studio/index.html', '<!-- lockfile studio -->'); }\n",
  });
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
  if (set.built.crew.sha !== crewSha || set.built.crew.dirty !== false || set.built.garden.sha !== gardenSha) throw new Error(`set.json provenance: ${JSON.stringify(set.built)}`);
  const gm = run(['tar', '-xzOf', join(out, set.garden), 'wicked-garden/.claude-plugin/plugin.json'], base);
  if (JSON.parse(gm).version !== '12.0.0') throw new Error('garden export lost its manifest');
  // run --set accepts it; a pack under the wrong key is refused by name.
  const rs = readSet(join(out, 'set.json'));
  if (rs.crew !== join(out, set.crew) || rs.garden !== join(out, set.garden)) throw new Error(`readSet of a pack's set.json: ${JSON.stringify(rs)}`);
  let threw = false; try { expectTarball('wicked-bus', rs.crew, ENV); } catch { threw = true; }
  if (!threw) throw new Error('a crew tarball given as bus must be refused');
  if (expectTarball('wicked-crew', rs.crew, ENV) !== m.version) throw new Error('expectTarball returns the pack version');

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
