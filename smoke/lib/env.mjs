// The hermetic run layout + environment. EVERYTHING the daemon, npm, git, the shims and the seats
// touch lives under ONE temp root: the operator's HOME, CLAUDE_CONFIG_DIR, ~/.wicked-*, the live
// daemon and the operator's PATH binaries are never reachable from here.
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, delimiter } from 'node:path';
import { homedir } from 'node:os';

export const IS_WIN = process.platform === 'win32';

/** Directory layout under the run root. Every path is created by {@link ensureLayout}. */
export function layout(root) {
  return {
    root,
    home: join(root, 'home'),
    npm: join(root, 'npm'),
    npmCache: join(root, 'npm-cache'),
    state: join(root, 'state'),
    bus: join(root, 'bus'),
    worker: join(root, 'worker'),
    claude: join(root, 'claude'),
    tmp: join(root, 'tmp'),
    workflows: join(root, 'workflows'),
    steeringInbox: join(root, 'steering-inbox'),
    interactive: join(root, 'interactive', 'docs'),
    bin: join(root, 'bin'),
    wickedHome: join(root, 'wicked-home'),
    repos: join(root, 'repos'),
    evidence: join(root, 'evidence'),
    daemonLog: join(root, 'daemon.log'),
    shimLog: join(root, 'shim-calls.ndjson'),
    installLog: join(root, 'install.log'),
  };
}

export function ensureLayout(L) {
  for (const k of ['home', 'npm', 'npmCache', 'state', 'bus', 'worker', 'claude', 'tmp', 'workflows', 'steeringInbox', 'interactive', 'bin', 'wickedHome', 'repos', 'evidence']) {
    mkdirSync(L[k], { recursive: true });
  }
  // A git identity for every commit made under this root (the deliver phase commits in the worktree;
  // HOME is hermetic so the operator's ~/.gitconfig is never read).
  const gitconfig = join(L.home, '.gitconfig');
  if (!existsSync(gitconfig)) {
    writeFileSync(gitconfig, '[user]\n\tname = wicked-smoke\n\temail = smoke@example.invalid\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n');
  }
  // The engine's deliver phase (and every Tool phase) runs `bash -lc …` — a LOGIN shell. macOS's
  // /etc/profile runs path_helper, which puts /etc/paths (incl. /usr/local/bin, where GitHub's macOS
  // runners keep a REAL `gh`) AHEAD of the inherited PATH. The hermetic HOME's profile puts the shim
  // dir back in front, so `gh`, `wicked-core` and the seats resolve to the shims under a login shell
  // too (the same idiom crew's own deliver e2e uses).
  const profile = `# written by wicked-smoke\nexport PATH="${L.bin.replace(/"/g, '\\"')}:$PATH"\n`;
  for (const name of ['.bash_profile', '.profile', '.zprofile']) {
    const p = join(L.home, name);
    if (!existsSync(p)) writeFileSync(p, profile);
  }
}

/** Where `npm install -g` puts a package's tree under our prefix (npm's own platform layout). */
export function globalLibDir(L) {
  return IS_WIN ? join(L.npm, 'node_modules') : join(L.npm, 'lib', 'node_modules');
}

/** Where `npm install -g` puts bin links under our prefix. */
export function globalBinDir(L) {
  return IS_WIN ? L.npm : join(L.npm, 'bin');
}

/**
 * The PATH the daemon (and everything it spawns) sees. Shims first, then the temp npm prefix, then the
 * node that runs this harness, then the SYSTEM directories only — never the operator's `~/.local/bin`,
 * `~/.cargo/bin`, homebrew, or wherever a real `claude`/`pi` might live. On Windows the system PATH is
 * kept minus anything under the user profile (git / bash / tar live in system locations on runners).
 */
export function hermeticPath(L) {
  const parts = [L.bin, globalBinDir(L), dirname(process.execPath)];
  if (IS_WIN) {
    const profile = (process.env.USERPROFILE ?? homedir()).toLowerCase();
    for (const p of (process.env.PATH ?? process.env.Path ?? '').split(delimiter)) {
      if (p && !p.toLowerCase().startsWith(profile)) parts.push(p);
    }
  } else {
    for (const p of ['/usr/bin', '/bin', '/usr/sbin', '/sbin']) if (existsSync(p)) parts.push(p);
  }
  return [...new Set(parts)].join(delimiter);
}

/** The environment for the daemon, npm, git and every child of theirs. `port` sets WICKED_CREW_API. */
export function hermeticEnv(L, port) {
  const env = {
    PATH: hermeticPath(L),
    HOME: L.home,
    LANG: process.env.LANG ?? 'C.UTF-8',
    TERM: 'dumb',
    NO_COLOR: '1',
    FORCE_COLOR: '0',
    CI: process.env.CI ?? '1',
    npm_config_prefix: L.npm,
    npm_config_cache: L.npmCache,
    npm_config_update_notifier: 'false',
    npm_config_fund: 'false',
    npm_config_audit: 'false',
    npm_config_loglevel: 'error',
    GIT_CONFIG_GLOBAL: join(L.home, '.gitconfig'),
    GIT_TERMINAL_PROMPT: '0',
    CLAUDE_CONFIG_DIR: L.claude,
    WICKED_HOME: L.wickedHome,
    WICKED_WORKER_HOME: L.worker,
    WICKED_CREW_SYSTEM_SETTINGS: join(L.root, 'system-settings.json'),
    WICKED_CREW_PROJECT_SETTINGS: join(L.state, 'project-settings.json'),
    WICKED_WORKFLOWS_DIR: L.workflows,
    WICKED_STEERING_INBOX_DIR: L.steeringInbox,
    WICKED_INTERACTIVE_ROOT: L.interactive,
    WICKED_BUS_DATA_DIR: L.bus,
    WICKED_MEMORY_EMBEDDER: 'hash',
    WICKED_SMOKE_ROOT: L.root,
    WICKED_SMOKE_SHIM_LOG: L.shimLog,
  };
  if (port !== undefined) env.WICKED_CREW_API = `http://127.0.0.1:${port}`;
  // The process temp dir. On macOS / Windows it lives under the root like everything else. On Linux
  // the engine's validator and checks sandboxes are `bwrap … --tmpfs <std::env::temp_dir()>` with the
  // run dir and the coverage store re-bound inside — a TMPDIR under the run root masked the engine's
  // own scratch there and the pinned evidence floor answered "no coverage report was produced … the
  // script denied before writing one" (observed on ubuntu-latest, 2026-09-12), while the same run on
  // macOS passed. Linux therefore keeps the system temp dir, exactly the configuration wicked-crew's
  // own deliver e2e runs under on its runners; what the engine writes there is ephemeral runner state.
  if (process.platform !== 'linux') {
    env.TMPDIR = L.tmp;
    env.TEMP = L.tmp;
    env.TMP = L.tmp;
  }
  if (IS_WIN) {
    env.USERPROFILE = L.home;
    env.APPDATA = join(L.home, 'AppData', 'Roaming');
    env.LOCALAPPDATA = join(L.home, 'AppData', 'Local');
    for (const k of ['SystemRoot', 'SYSTEMROOT', 'ComSpec', 'COMSPEC', 'PATHEXT', 'SystemDrive', 'windir', 'PROGRAMFILES', 'ProgramFiles', 'ProgramData']) {
      if (process.env[k] !== undefined) env[k] = process.env[k];
    }
  }
  // Runners need the toolchain proxies (rustup) only for cargo corpora — not ours; nothing else leaks.
  return env;
}
