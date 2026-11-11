// The FIXED corpus: smoke/fixtures/corpus copied into the run root and initialised as a git repo with
// one commit, plus a local BARE origin the deliver phase pushes to. Same bytes every run → the same
// plan, the same checks, the same diff.
import { cpSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { git } from './proc.mjs';

const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures', 'corpus');

/** Copy the fixture to `<repos>/<name>`, `git init -b main`, commit. Returns the path. */
export function initCorpus(L, env, name) {
  const dest = join(L.repos, name);
  if (existsSync(dest)) throw new Error(`corpus ${name} already exists at ${dest}`);
  mkdirSync(dest, { recursive: true });
  cpSync(FIXTURE, dest, { recursive: true });
  git(dest, env, 'init', '-q', '-b', 'main');
  git(dest, env, 'config', 'user.email', 'smoke@example.invalid');
  git(dest, env, 'config', 'user.name', 'wicked-smoke');
  git(dest, env, 'add', '-A');
  git(dest, env, 'commit', '-q', '-m', 'corpus: initial commit (add() returns the difference — the seeded bug)');
  return dest;
}

/** A bare origin for `repoPath`; sets `origin` and pushes main so the engine's base resolution sees it. */
export function attachBareOrigin(L, env, repoPath, name) {
  const bare = join(L.root, `${name}-origin.git`);
  git(L.root, env, 'init', '-q', '--bare', bare);
  git(repoPath, env, 'remote', 'add', 'origin', bare);
  git(repoPath, env, 'push', '-q', '-u', 'origin', 'main');
  return bare;
}

/** A fresh clone of an initialised corpus (its own origin = the source), for fan-outs and bus loops. */
export function cloneCorpus(L, env, sourcePath, name) {
  const dest = join(L.repos, name);
  git(L.repos, env, 'clone', '-q', sourcePath, dest);
  git(dest, env, 'config', 'user.email', 'smoke@example.invalid');
  git(dest, env, 'config', 'user.name', 'wicked-smoke');
  return dest;
}

export function corpusHasBug(repoPath) {
  try {
    return /a\s*-\s*b/.test(readFileSync(join(repoPath, 'src', 'add.js'), 'utf8'));
  } catch {
    return false;
  }
}

/** Branches under refs/heads in a repo (bare or not). */
export function branches(repoPath, env, pattern = '') {
  const out = git(repoPath, env, 'for-each-ref', '--format=%(refname:short)', `refs/heads/${pattern}`);
  return out.split('\n').map((s) => s.trim()).filter(Boolean);
}

/** The fixed issue text the bug run is launched with. Deliberately free of the word "fix": the
 *  phase scope the engine appends is the only place a worker turn can read its phase from. */
export const ISSUE_TEXT =
  'add(a, b) in src/add.js returns the difference instead of the sum, so `npm test` fails on test/add.test.js ' +
  '(expected add(2, 3) === 5). Correct the arithmetic in src/add.js only; keep the exported name and the test file unchanged.';
