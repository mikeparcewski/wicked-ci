// `--assert-hermetic`: prove the run wrote NOTHING under the operator's real HOME. Snapshot the
// mtime/size of $HOME's entries before the install and compare after teardown: depth 1 everywhere,
// and a FULL (bounded) walk under the directories the wicked family and the CLIs are known to write —
// so an in-place modification of `~/.config/wicked-council/clis.toml` or a new file four levels down
// in `~/.claude/plugins/cache/…` is detected, not only a touched top-level directory. Paths are
// reported `~/<name>` — never the absolute home.
import { lstatSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

/** Roots walked fully (bounded by MAX_ENTRIES): what the product, its seats and the harness could
 *  touch — plus the macOS user folders a hosted runner image keeps (near-empty there), so a bare
 *  mtime move on one of them can be classified (see TRANSIENT below) instead of failing blind. */
const DEEP = ['.claude', '.config', '.wicked', '.wicked-crew', '.wicked-worker', '.something-wicked', '.wicked-brain', '.npm', '.codex', '.copilot', '.pi', '.local', '.cargo', '.gemini', '.cache', 'wicked-interactive', 'Movies', 'Music', 'Pictures', 'Public'];
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
  const walked = [];
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
      else walked.push(name);
    }
  }
  return { home, at: Date.now(), entries: out, truncated, walked };
}

/**
 * Compare two snapshots; returns {ok, changed: ['~/.claude/plugins/…', …], transient: [...],
 * truncated: [...]} (new, removed or touched). `ignore` lists absolute paths whose subtree is the
 * run's own (a `--root` under HOME).
 *
 * TRANSIENT: a directory whose own mtime moved while NOTHING recorded beneath it changed, inside a
 * root the scan walked COMPLETELY (both snapshots, not truncated) — a child was created and removed
 * during the run. A hosted macOS runner does this to `~/Movies` on its own (selftest run 34722047107,
 * 2026-09-12: `CHANGED under $HOME: ~/Movies` with nothing inside, on a leg whose twin was clean);
 * it is reported, kept in the JSON, and does NOT fail the scan — a leak leaves a file, and a file
 * anywhere under a walked root is still `changed`. A bare mtime move on a directory the scan did
 * NOT walk (e.g. `~/Library`) stays a real change: nothing proves it was empty-handed.
 */
export function compareHome(before, after, { ignore = [] } = {}) {
  const home = after.home;
  const ignored = (k) => ignore.some((p) => { const rel = p.startsWith(home) ? p.slice(home.length).replace(/^[\\/]+/, '') : null; return rel !== null && (k === rel || k.startsWith(`${rel}/`)); });
  const raw = [];
  for (const [k, v] of after.entries) {
    if (ignored(k)) continue;
    if (!before.entries.has(k)) raw.push({ key: k, kind: 'new', type: v.split(':')[2] });
    else if (before.entries.get(k) !== v) raw.push({ key: k, kind: 'modified', type: v.split(':')[2] });
  }
  for (const k of before.entries.keys()) if (!ignored(k) && !after.entries.has(k)) raw.push({ key: k, kind: 'removed', type: before.entries.get(k).split(':')[2] });
  const walkedBoth = new Set((after.walked ?? []).filter((w) => (before.walked ?? []).includes(w)));
  const hasChangedChild = (k) => raw.some((c) => c.key.startsWith(`${k}/`));
  const isTransient = (c) => c.kind === 'modified' && c.type === 'd' && walkedBoth.has(c.key.split('/')[0]) && !hasChangedChild(c.key);
  const label = (c) => `~/${c.key}${c.kind === 'new' ? ' (new)' : c.kind === 'removed' ? ' (removed)' : ''}`;
  const transient = raw.filter(isTransient).map((c) => `~/${c.key} (transient: mtime moved, nothing beneath it changed)`);
  const changed = raw.filter((c) => !isTransient(c)).map(label);
  // Directories report a touched mtime when a child changed — keep the deepest entries first so the
  // actual file is what the reader sees, and rank wicked-relevant paths ahead.
  const rank = (s) => (/wicked|claude|codex|copilot|\.pi\b|opencode|npm|config/.test(s) ? 0 : 1);
  changed.sort((a, b) => rank(a) - rank(b) || b.split('/').length - a.split('/').length || a.localeCompare(b));
  const truncated = [...new Set([...(before.truncated ?? []), ...(after.truncated ?? [])])];
  return { ok: changed.length === 0, changed, transient, truncated };
}
