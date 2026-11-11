// CLI argument parsing for wicked-selftest run (and its alias wicked-smoke). No dependencies; every flag takes
// `--flag value`.
import { readFileSync, statSync } from 'node:fs';
import { dirname, isAbsolute, resolve } from 'node:path';

export const ALL_STEPS = ['S01', 'S02', 'S03', 'S04', 'S11', 'S05', 'S06', 'S07', 'S08', 'U01', 'U02', 'U03', 'U04', 'U05', 'S12', 'S09', 'S10'];
/** Steps that run without `--steps`: S07 (interactive) stays opt-in (a cold `npx` fetch); S08 (chat)
 *  joined the default set in v2 with the ACP-speaking seat shim — see README. */
export const DEFAULT_STEPS = ['S01', 'S02', 'S03', 'S04', 'S11', 'S05', 'S06', 'S08', 'S09', 'S10'];

/** Saved step selections. `smoke` is the release smoke's set as it ran before the suite grew; `pr` is what a pull
 *  request and a governed run's floor run (no campaign fan-out, no bus soak); `release` is everything but the
 *  opt-in S07. A profile only selects steps; it never changes what a step asserts. */
export const PROFILES = {
  smoke: DEFAULT_STEPS,
  pr: ['S01', 'S02', 'S03', 'S04', 'S08', 'U01', 'U02', 'U03', 'U04', 'S10'],
  release: ALL_STEPS.filter((id) => id !== 'S07'),
  // `wicked-selftest serve`: boot, publish skills, onboard the fixture repo, then hold the daemon open.
  serve: ['S01', 'S02', 'S03'],
};

export const HELP = `wicked-selftest run — the wicked product self-test (alias: wicked-smoke)

usage: wicked-selftest run [options]      (or: wicked-smoke [options])

  Each of --crew, --bus and --core-ts takes an npm version, or a path to a local .tgz (e.g. from
  \`wicked-selftest pack\`). --garden takes a git tag, "latest", or a path to a local .tgz or directory.
  --crew <version|.tgz>   wicked-crew (default: latest)
  --core-ts <v|.tgz>      wicked-core-ts; "pinned" = whatever crew's range resolves (default: pinned)
  --bus <version|.tgz>    wicked-bus (default: latest)
  --garden <ref|path>     wicked-garden (default: latest)
  --set <file.json>       a set file {crew, coreTs, bus, garden}; relative paths resolve against the file's
                          directory; flags given after it override its entries
  --profile <name>        smoke | pr | release | serve (default: smoke); not with --steps
  --steps <list>          e.g. S01,S02,S04 or S01..S06 or all (default: the smoke profile, ${DEFAULT_STEPS.join(',')})
  --root <dir>            temp root for the whole run (default: $RUNNER_TEMP or the OS temp dir); must not exist
  --reuse-root            allow --root to point at an existing directory (its repos/ and state/ are cleared)
  --keep                  keep the temp root after S10 (default: removed)
  --report <path>         JSON report path (default: <root>/report.json, copied to --report-dir or, when the
                          root is removed and no --report-dir was given, to ./wicked-smoke-report.json)
  --report-dir <dir>      copy report + daemon log + shim log + evidence here (for CI artifacts)
  --expect-fail <list>    extra finding ids to treat as expected failures, e.g. F-E2E-030
  --expect-fail-steps <l> step ids whose failures are all expected, e.g. S05
  --no-expect-fail        disable every built-in expected-fail rule (strict mode)
  --allow-unexpected-pass do not fail the run when a labelled check unexpectedly passes (it is still printed)
  --assert-hermetic       fail if anything under the real $HOME changed during the run
  --step-timeout <secs>   per-step ceiling; raises the built-in ceilings (S01 boot 300 s, S04 540 s, S11 540 s, S05 420 s) when
                          larger (default: 300) — also the daemon's boot wait (a cold first boot publishes the
                          garden bundle with uv; minutes on a loaded workstation, seconds on a runner)
  --verbose               echo every HTTP call and shim invocation
  --python <path>         a Python with Playwright for the studio journeys (U steps); default $WICKED_SELFTEST_PYTHON.
                          Without one, the U steps are SKIPPED and named on the verdict line.
  --hold                  after the steps, keep the daemon up until Ctrl-C or <root>/stop (what the serve verb sets)
  -h, --help
`;

export function parseArgs(argv) {
  const o = {
    crew: 'latest',
    coreTs: 'pinned',
    bus: 'latest',
    garden: 'latest',
    steps: DEFAULT_STEPS,
    root: undefined,
    reuseRoot: false,
    keep: false,
    report: undefined,
    reportDir: undefined,
    expectFail: [],
    expectFailSteps: [],
    noExpectFail: false,
    allowUnexpectedPass: false,
    assertHermetic: false,
    stepTimeout: 300,
    verbose: false,
    help: false,
    profile: null,
    hold: false,
    python: undefined,
  };
  let profile = null;
  let stepsGiven = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      const v = argv[i + 1];
      if (v === undefined || v.startsWith('--')) throw new Error(`${a} needs a value`);
      i += 1;
      return v;
    };
    switch (a) {
      case '--crew': o.crew = next(); break;
      case '--core-ts': o.coreTs = next(); break;
      case '--bus': o.bus = next(); break;
      case '--garden': o.garden = next(); break;
      case '--steps': if (profile !== null) throw new Error('--steps and --profile are exclusive'); o.steps = parseSteps(next()); stepsGiven = true; break;
      case '--profile': {
        if (stepsGiven) throw new Error('--steps and --profile are exclusive');
        profile = next();
        if (!Object.hasOwn(PROFILES, profile)) throw new Error(`unknown profile ${profile} (${Object.keys(PROFILES).join(', ')})`);
        o.steps = [...PROFILES[profile]]; o.profile = profile; break;
      }
      case '--set': Object.assign(o, readSet(next())); break;
      case '--root': o.root = next(); break;
      case '--reuse-root': o.reuseRoot = true; break;
      case '--keep': o.keep = true; break;
      case '--report': o.report = next(); break;
      case '--report-dir': o.reportDir = next(); break;
      case '--expect-fail': o.expectFail = next().split(',').map((s) => s.trim()).filter(Boolean); break;
      case '--expect-fail-steps': o.expectFailSteps = parseSteps(next()); break;
      case '--no-expect-fail': o.noExpectFail = true; break;
      case '--allow-unexpected-pass': o.allowUnexpectedPass = true; break;
      case '--assert-hermetic': o.assertHermetic = true; break;
      case '--step-timeout': o.stepTimeout = Number(next()); break;
      case '--verbose': o.verbose = true; break;
      case '--hold': o.hold = true; break;
      case '--python': o.python = next(); break;
      case '-h':
      case '--help': o.help = true; break;
      default: throw new Error(`unknown option ${a} (see --help)`);
    }
  }
  if (!Number.isFinite(o.stepTimeout) || o.stepTimeout <= 0) throw new Error('--step-timeout must be a positive number of seconds');
  if (o.profile === null && !stepsGiven) o.profile = 'smoke';
  for (const k of ['crew', 'coreTs', 'bus', 'garden']) o[k] = resolveSource(o[k], process.cwd(), k);
  // A Tier 2 set's engine facts describe ITS engine pack: another --core-ts (given after --set) leaves them behind.
  if (o.setBuilt?.core && o.setCoreTs !== o.coreTs) { const { core, ...rest } = o.setBuilt; o.setBuilt = rest; }
  return o;
}

/** A source that names a local file or directory (it starts with `.`, `/` or `~`, or ends in .tgz) is a local pack;
 *  anything else is an npm version / dist-tag or a git tag. */
export function isLocalSource(v) {
  return typeof v === 'string' && (/^(\.{1,2}[\\/]|[\\/]|~[\\/]|[A-Za-z]:[\\/])/.test(v) || /\.(tgz|tar\.gz)$/i.test(v));
}

/** Resolve one set entry, refusing anything that could silently test something else:
 *  - an empty or whitespace-bearing value (npm reads `wicked-crew@ ` as latest);
 *  - a local crew / bus / core-ts that is not a regular .tgz file (npm would run a source directory's `prepare`
 *    script and link the checkout into the install);
 *  - a local garden that is neither a .tgz file nor a directory;
 *  - a local path that does not exist. */
export function resolveSource(v, base = process.cwd(), key = 'crew') {
  if (typeof v !== 'string' || v.trim() === '' || v !== v.trim()) throw new Error(`${key}: ${JSON.stringify(v)} is not a version, tag or pack path`);
  if (!isLocalSource(v)) {
    // A version or tag never holds whitespace (npm reads `wicked-crew@ ` as latest); a PATH may (`C:\\Users\\Jane Doe\\…`).
    if (!/^[0-9A-Za-z][0-9A-Za-z.+_~^<>=*-]*$/.test(v)) throw new Error(`${key}: ${JSON.stringify(v)} is not a version or tag`);
    return v;
  }
  const home = process.env.HOME ?? process.env.USERPROFILE ?? '';
  const p = v.startsWith('~') ? resolve(home, v.slice(2)) : (isAbsolute(v) ? v : resolve(base, v));
  let st;
  try { st = statSync(p); } catch { throw new Error(`${key}: local source ${v} does not exist`); }
  const tarball = st.isFile() && /\.(tgz|tar\.gz)$/i.test(p);
  if (key === 'garden' ? !(tarball || st.isDirectory()) : !tarball) {
    throw new Error(`${key}: local source ${v} must be a .tgz file${key === 'garden' ? ' or a directory' : ' (a source directory is refused: build it with `wicked-selftest pack`)'}`);
  }
  return p;
}

/** `--set <file.json>`: {crew?, coreTs?, bus?, garden?}; unknown keys are refused so a typo can't fall back to npm latest. */
export function readSet(file) {
  const abs = resolve(file);
  let d;
  try { d = JSON.parse(readFileSync(abs, 'utf8')); } catch (err) { throw new Error(`--set ${file}: ${err.message}`); }
  if (d === null || typeof d !== 'object' || Array.isArray(d)) throw new Error(`--set ${file}: not a JSON object`);
  // `built` (what `pack` recorded) rides along: the engine's handshake facts for a Tier 2 set, tied to the engine pack
  // they describe (parseArgs drops them when --core-ts names another engine).
  const out = { setBuilt: d.built && typeof d.built === 'object' ? { ...d.built } : null };
  for (const [k, v] of Object.entries(d)) {
    if (k === '$comment' || k === 'built') continue;
    if (!['crew', 'coreTs', 'bus', 'garden'].includes(k)) throw new Error(`--set ${file}: unknown key ${k} (crew, coreTs, bus, garden)`);
    try { out[k] = resolveSource(v, dirname(abs), k); } catch (err) { throw new Error(`--set ${file}: ${err.message}`); }
  }
  out.setCoreTs = out.coreTs ?? null;
  return out;
}

/** `S01,S03` | `S01..S06` | `all` | `` (empty = none) */
export function parseSteps(spec) {
  const s = spec.trim();
  if (s === '') return [];
  if (s.toLowerCase() === 'all') return [...ALL_STEPS];
  const out = new Set();
  for (const part of s.split(',').map((p) => p.trim()).filter(Boolean)) {
    const range = part.match(/^([SU])(\d\d)\.\.([SU])(\d\d)$/i);
    if (range) {
      // A range is NUMERIC within ONE family (S01..S11 = every API step from 1 to 11; U01..U02 = the studio journeys),
      // never a slice of the run order: ALL_STEPS runs S11 right after S04, so a positional slice would drop S05-S10
      // (codex on #61), and a U step never rides an S range.
      const fam = range[1].toUpperCase();
      const lo = Number(range[2]);
      const hi = Number(range[4]);
      const a = `${fam}${range[2]}`; const b = `${range[3].toUpperCase()}${range[4]}`;
      if (range[3].toUpperCase() !== fam || !ALL_STEPS.includes(a) || !ALL_STEPS.includes(b) || lo > hi) throw new Error(`bad step range ${part}`);
      for (const id of ALL_STEPS) if (id[0] === fam && Number(id.slice(1)) >= lo && Number(id.slice(1)) <= hi) out.add(id);
    } else {
      const id = part.toUpperCase();
      if (!ALL_STEPS.includes(id)) throw new Error(`unknown step ${part}`);
      out.add(id);
    }
  }
  return ALL_STEPS.filter((id) => out.has(id));
}
