// `--assert-hermetic`: prove the run wrote NOTHING under the operator's real HOME. Snapshot the mtimes
// of $HOME's entries (depth 1, plus the directories the wicked family and the CLIs are known to write)
// before install, compare after teardown. Paths are reported `~/<name>` — never the absolute home.
import { lstatSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const DEEP = ['.claude', '.config', '.wicked', '.wicked-crew', '.wicked-worker', '.something-wicked', '.npm', '.codex', '.copilot', '.pi', '.local'];

function statMap(root, rel, out, depth) {
  let entries;
  try { entries = readdirSync(join(root, rel)); } catch { return; }
  for (const name of entries) {
    const r = rel ? `${rel}/${name}` : name;
    let st;
    try { st = lstatSync(join(root, r)); } catch { continue; }
    out.set(r, `${st.mtimeMs}:${st.size}:${st.isDirectory() ? 'd' : 'f'}`);
    if (depth > 0 && st.isDirectory() && (rel !== '' || DEEP.includes(name))) statMap(root, r, out, depth - 1);
  }
}

export function snapshotHome() {
  const home = homedir();
  const out = new Map();
  statMap(home, '', out, 1);
  return { home, at: Date.now(), entries: out };
}

/** Compare two snapshots; returns {ok, changed: ['~/.claude/plugins', …]} (new, removed or touched). */
export function compareHome(before, after) {
  const changed = [];
  for (const [k, v] of after.entries) {
    if (!before.entries.has(k)) changed.push(`~/${k} (new)`);
    else if (before.entries.get(k) !== v) changed.push(`~/${k}`);
  }
  for (const k of before.entries.keys()) if (!after.entries.has(k)) changed.push(`~/${k} (removed)`);
  // A shell history or a cache file the operator's own session touched is noise for THIS check
  // only when it is not one of the roots the run could have reached; report everything, let the
  // reader judge, but rank the wicked-relevant ones first.
  changed.sort((a, b) => Number(/wicked|claude|codex|copilot|\.pi|opencode|npm|config/.test(b)) - Number(/wicked|claude|codex|copilot|\.pi|opencode|npm|config/.test(a)));
  return { ok: changed.length === 0, changed };
}
