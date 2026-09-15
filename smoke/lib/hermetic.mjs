// `--assert-hermetic`: prove the run wrote NOTHING under the operator's real HOME. Snapshot the
// mtime/size of $HOME's entries before the install and compare after teardown: a FULL (bounded) walk
// under the directories the wicked family and the CLIs are known to write — so an in-place
// modification of `~/.config/wicked-council/clis.toml` or a new file four levels down in
// `~/.claude/plugins/cache/…` is detected, not only a touched top-level directory — a SHALLOW record
// (the directory, its children, its grandchildren) of `~/Library` on macOS, watched where a
// third-party tool writes and with Apple's own churn classed as runner noise, and depth 1 everywhere
// else. Paths are reported `~/<name>` — never the absolute home.
import { lstatSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

/** Roots walked fully (bounded by MAX_ENTRIES): what the product, its seats and the harness could touch. */
const DEEP = ['.claude', '.config', '.wicked', '.wicked-crew', '.wicked-worker', '.something-wicked', '.wicked-brain', '.npm', '.codex', '.copilot', '.pi', '.local', '.cargo', '.gemini', '.cache', 'wicked-interactive'];
/** The macOS user media folders: a hosted macOS runner's OWN system daemons write there during a run
 *  (`photoanalysisd` under `~/Pictures/Photos Library.photoslibrary/…` — selftest run 34744141719;
 *  a bare mtime move on `~/Movies` — run 34722047107), nothing wicked does. Changes there are reported
 *  as `noise` (printed, kept in the JSON), never a leak; they are not walked. */
const RUNNER_NOISE = new Set(['Movies', 'Music', 'Pictures', 'Public']);
/** `~/Library` (macOS) is recorded SHALLOWLY — itself, its children, its grandchildren — because it is
 *  a real leak target (`Caches/ms-playwright`, `Application Support/<tool>`, `Preferences/<tool>`,
 *  `Logs/<tool>`, `LaunchAgents/<tool>.plist`) AND a hosted macOS runner's own daemons churn it for the
 *  whole run (selftest 34746373419: `Preferences/com.apple.*.plist`, `Caches/com.apple.*`, `Biome/tmp`,
 *  `Daemon Containers/<UUID>`, `Application Scripts/group.com.apple.*`, `PrivateCloudCompute` …). The
 *  scan therefore WATCHES only the subtrees a third-party tool writes to, and inside them treats
 *  Apple's own entries (`com.apple.*`, `group.com.apple.*`, a UUID, and the named leaves below) as
 *  runner noise. Everything else under `~/Library` is Apple's state — noise by construction.
 *  `Preferences/pbs.plist` is Apple's pasteboard server (com.apple.pbs) preference file, the one
 *  Apple leaf under Preferences without a `com.apple.` prefix: a hosted macOS runner rewrote it
 *  during smoke run 34798471429 (crew 0.7.34 leg) as the ONLY change under $HOME — nothing wicked
 *  touches the pasteboard. `Application Support/locationaccessstored` is Apple's location-access
 *  store (locationd family), created by the runner image during selftest run 34799139356
 *  (previous-set leg) as the only change under $HOME — same class, same prefix-less name. */
const LIBRARY = 'Library';
const LIBRARY_WATCHED = new Set(['Application Support', 'Caches', 'Preferences', 'Logs', 'LaunchAgents', 'Python', 'pnpm', 'Developer', 'Containers', 'HTTPStorages', 'WebKit', 'Saved Application State']);
const LIBRARY_APPLE_LEAVES = new Set(['Caches/CloudKit', 'Preferences/ByHost', 'Preferences/diagnostics_agent.plist', 'Preferences/pbs.plist', 'Application Support/locationaccessstored', 'Application Support/CloudDocs', 'Application Support/AddressBook', 'Application Support/CallHistoryDB', 'Application Support/CallHistoryTransactions', 'Application Support/Knowledge', 'Application Support/FileProvider', 'Application Support/iCloud', 'Logs/DiagnosticReports', 'Logs/CoreSimulator', 'Logs/hca.log', 'Application Support/CrashReporter']); // hca.log: a macOS system agent's log the hosted runner appends to (selftest 34748419498). `Application Support/CrashReporter` is Apple's crash-reporter STATE dir: a hosted macOS runner rewrote it (heavy Apple-services churn — PrivateCloudCompute / appleintelligencereporting / managedappdistributionagent all new) as the only non-allowlisted change during smoke run 34911097402 (crew 0.7.35 / core-ts 0.7.27 / garden 12.37.2 leg), while every step passed, the daemon log had 0 crash signals and teardown/bus-integrity were clean — the sibling `Logs/DiagnosticReports` (where per-process `.ips` crash payloads actually land) is already allowlisted for the same reason: a real wicked crash is caught by the daemon log / a failed step / a dirty teardown, never by this $HOME scan. A leaf not listed here reads as a real change NAMING the path — extend the list, never the subtree.
const APPLE_SEGMENT = /^(com\.apple\.|group\.com\.apple\.|[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$)/i;
/** Is this `Library/…` entry Apple's own churn (noise) rather than a place a tool leak would show? */
function isAppleLibraryNoise(key) {
  const segs = key.split('/');
  if (segs[0] !== LIBRARY || segs.length < 2) return false;
  const sub = segs[1];
  if (!LIBRARY_WATCHED.has(sub)) return true; // Biome, Daemon Containers, Application Scripts, Group Containers, PrivateCloudCompute, Shortcuts, ContainerManager, Accounts, …
  if (segs.length < 3) return false; // the watched subtree itself: judged by its children
  const leaf = segs[2];
  return APPLE_SEGMENT.test(leaf) || LIBRARY_APPLE_LEAVES.has(`${sub}/${leaf}`);
}
/** Upper bound on entries recorded per root — `~/.npm/_cacache` or `~/.cargo/registry` can hold
 *  hundreds of thousands of files; past the bound the root is recorded as far as the budget reached
 *  and the snapshot says so (`truncated`). Entries are visited in SORTED order so the cut falls at the
 *  same place in both snapshots — an unsorted readdir moved the cut and a stale file read "(new)". */
const MAX_ENTRIES = 20_000;
/** How deep `~/Library` is recorded: itself (1), its children (2), its grandchildren (3). */
const SHALLOW_DEPTH = 3;

function walk(root, rel, out, budget, depth, maxDepth) {
  if (depth >= maxDepth) return;
  let entries;
  try { entries = readdirSync(join(root, rel)).sort(); } catch { return; }
  for (const name of entries) {
    if (budget.left <= 0) { budget.truncated = true; return; }
    const r = `${rel}/${name}`;
    let st;
    try { st = lstatSync(join(root, r)); } catch { continue; }
    budget.left -= 1;
    out.set(r, `${st.mtimeMs}:${st.size}:${st.isDirectory() ? 'd' : st.isSymbolicLink() ? 'l' : 'f'}`);
    if (st.isDirectory()) walk(root, r, out, budget, depth + 1, maxDepth);
  }
}

export function snapshotHome() {
  const home = homedir();
  const out = new Map();
  const truncated = [];
  /** per top-level root: the depth its entries were recorded to (Infinity = fully walked), complete or not */
  const recorded = {};
  let top;
  try { top = readdirSync(home).sort(); } catch { top = []; }
  for (const name of top) {
    let st;
    try { st = lstatSync(join(home, name)); } catch { continue; }
    out.set(name, `${st.mtimeMs}:${st.size}:${st.isDirectory() ? 'd' : st.isSymbolicLink() ? 'l' : 'f'}`);
    if (!st.isDirectory() || RUNNER_NOISE.has(name)) continue;
    const deep = DEEP.includes(name);
    if (!deep && name !== LIBRARY) continue; // every other top-level dir: recorded by its own mtime only
    const budget = { left: MAX_ENTRIES, truncated: false };
    walk(home, name, out, budget, 1, deep ? Infinity : SHALLOW_DEPTH);
    if (budget.truncated) truncated.push(`~/${name}`);
    recorded[name] = { depth: deep ? Infinity : SHALLOW_DEPTH, complete: !budget.truncated };
  }
  return { home, at: Date.now(), entries: out, truncated, recorded };
}

/**
 * Compare two snapshots; returns {ok, changed: ['~/.claude/plugins/…', …], noise: [...],
 * truncated: [...]} (new, removed or touched). `ignore` lists absolute paths whose subtree is the
 * run's own (a `--root` under HOME).
 *
 * NOISE — reported, kept in the JSON, never a leak — is exactly three classes:
 *  - RUNNER_NOISE: anything under the macOS user media folders (the runner image's own daemons write
 *    there, see above);
 *  - APPLE LIBRARY: Apple's own entries under `~/Library` (see isAppleLibraryNoise);
 *  - TRANSIENT / NOISE-ONLY PARENT: a directory whose own mtime moved while NONE of its recorded
 *    DIRECT children changed — or whose changed recorded descendants are ALL noise — the children
 *    having been recorded completely in BOTH snapshots (a directory's mtime moves only when a direct
 *    child is added, removed or renamed: a child created and removed during the run, or Apple's).
 *    A hosted macOS runner does this to `~/Library` by itself (selftest run 34745299650). A leak
 *    leaves a file, and a recorded file that is new / removed / modified is still `changed`.
 * A bare mtime move on a directory whose children were NOT recorded (deeper than the record, or past
 * the entry budget) stays a real change: nothing proves it was empty-handed.
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
  // Were a directory's DIRECT children recorded, completely, in both snapshots?
  const childrenRecorded = (key) => {
    const root = key.split('/')[0];
    const depth = key.split('/').length;
    const b = before.recorded?.[root];
    const a = after.recorded?.[root];
    return Boolean(b && a && b.complete && a.complete && depth + 1 <= a.depth && depth + 1 <= b.depth);
  };
  const isRunnerNoise = (c) => RUNNER_NOISE.has(c.key.split('/')[0]);
  const isApple = (c) => isAppleLibraryNoise(c.key);
  // Deepest first, so a parent directory is judged after every descendant has been classified.
  const ordered = [...raw].sort((a, b) => b.key.split('/').length - a.key.split('/').length);
  const noiseKeys = new Set();
  const reason = new Map();
  for (const c of ordered) {
    if (isRunnerNoise(c)) { noiseKeys.add(c.key); reason.set(c.key, 'runner noise: the macOS user media folders are written by the runner image\'s own daemons'); continue; }
    if (isApple(c)) { noiseKeys.add(c.key); reason.set(c.key, 'runner noise: Apple\'s own state under ~/Library'); continue; }
    if (c.kind === 'modified' && c.type === 'd' && childrenRecorded(c.key)) {
      const descendants = raw.filter((d) => d.key.startsWith(`${c.key}/`));
      if (descendants.length === 0) { noiseKeys.add(c.key); reason.set(c.key, 'transient: mtime moved, nothing beneath it changed'); continue; }
      if (descendants.every((d) => noiseKeys.has(d.key))) { noiseKeys.add(c.key); reason.set(c.key, 'only runner-noise entries changed beneath it'); continue; }
    }
  }
  const label = (c) => `~/${c.key}${c.kind === 'new' ? ' (new)' : c.kind === 'removed' ? ' (removed)' : ''}`;
  const noise = raw.filter((c) => noiseKeys.has(c.key)).map((c) => `${label(c)} (${reason.get(c.key)})`);
  const changed = raw.filter((c) => !noiseKeys.has(c.key)).map(label);
  // Directories report a touched mtime when a child changed — keep the deepest entries first so the
  // actual file is what the reader sees, and rank wicked-relevant paths ahead.
  const rank = (s) => (/wicked|claude|codex|copilot|\.pi\b|opencode|npm|config/.test(s) ? 0 : 1);
  changed.sort((a, b) => rank(a) - rank(b) || b.split('/').length - a.split('/').length || a.localeCompare(b));
  const truncated = [...new Set([...(before.truncated ?? []), ...(after.truncated ?? [])])];
  return { ok: changed.length === 0, changed, noise, truncated };
}
