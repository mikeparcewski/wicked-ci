// `--assert-hermetic`: prove the run wrote NOTHING under the operator's real HOME. Snapshot the
// mtime/size of $HOME's entries before the install and compare after teardown: depth 1 everywhere,
// and a FULL (bounded) walk under the directories the wicked family and the CLIs are known to write —
// so an in-place modification of `~/.config/wicked-council/clis.toml` or a new file four levels down
// in `~/.claude/plugins/cache/…` is detected, not only a touched top-level directory. Paths are
// reported `~/<name>` — never the absolute home.
import { lstatSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

/** Roots walked fully (bounded by MAX_ENTRIES): what the product, its seats and the harness could touch. */
const DEEP = ['.claude', '.config', '.wicked', '.wicked-crew', '.wicked-worker', '.something-wicked', '.wicked-brain', '.npm', '.codex', '.copilot', '.pi', '.local', '.cargo', '.gemini', '.cache', 'wicked-interactive'];
/** Upper bound on entries recorded per deep root — `~/.npm/_cacache` or `~/.cargo/registry` can hold
 *  hundreds of thousands of files; past the bound the root is recorded by its own mtime only and the
 *  snapshot says so. */
const MAX_ENTRIES = 20_000;

function walk(root, rel, out, budget) {
  let entries;
  try { entries = readdirSync(join(root, rel)); } catch { return; }
  for (const name of entries) {
    if (budget.left <= 0) { budget.truncated = true; return; }
    const r = `${rel}/${name}`;
    let st;
    try { st = lstatSync(join(root, r)); } catch { continue; }
    budget.left -= 1;
    out.set(r, `${st.mtimeMs}:${st.size}:${st.isDirectory() ? 'd' : st.isSymbolicLink() ? 'l' : 'f'}`);
    if (st.isDirectory()) walk(root, r, out, budget);
  }
}

export function snapshotHome() {
  const home = homedir();
  const out = new Map();
  const truncated = [];
  let top;
  try { top = readdirSync(home); } catch { top = []; }
  for (const name of top) {
    let st;
    try { st = lstatSync(join(home, name)); } catch { continue; }
    out.set(name, `${st.mtimeMs}:${st.size}:${st.isDirectory() ? 'd' : st.isSymbolicLink() ? 'l' : 'f'}`);
    if (st.isDirectory() && DEEP.includes(name)) {
      const budget = { left: MAX_ENTRIES, truncated: false };
      walk(home, name, out, budget);
      if (budget.truncated) truncated.push(`~/${name}`);
    }
  }
  return { home, at: Date.now(), entries: out, truncated };
}

/** Compare two snapshots; returns {ok, changed: ['~/.claude/plugins/…', …], truncated: [...]} (new,
 *  removed or touched). `ignore` lists absolute paths whose subtree is the run's own (a `--root` under HOME). */
export function compareHome(before, after, { ignore = [] } = {}) {
  const home = after.home;
  const ignored = (k) => ignore.some((p) => { const rel = p.startsWith(home) ? p.slice(home.length).replace(/^[\\/]+/, '') : null; return rel !== null && (k === rel || k.startsWith(`${rel}/`)); });
  const changed = [];
  for (const [k, v] of after.entries) {
    if (ignored(k)) continue;
    if (!before.entries.has(k)) changed.push(`~/${k} (new)`);
    else if (before.entries.get(k) !== v) changed.push(`~/${k}`);
  }
  for (const k of before.entries.keys()) if (!ignored(k) && !after.entries.has(k)) changed.push(`~/${k} (removed)`);
  // Directories report a touched mtime when a child changed — keep the deepest entries first so the
  // actual file is what the reader sees, and rank wicked-relevant paths ahead.
  const rank = (s) => (/wicked|claude|codex|copilot|\.pi\b|opencode|npm|config/.test(s) ? 0 : 1);
  changed.sort((a, b) => rank(a) - rank(b) || b.split('/').length - a.split('/').length || a.localeCompare(b));
  const truncated = [...new Set([...(before.truncated ?? []), ...(after.truncated ?? [])])];
  return { ok: changed.length === 0, changed, truncated };
}
