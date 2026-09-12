// CLI argument parsing for wicked-smoke. No dependencies; every flag takes `--flag value`.

export const ALL_STEPS = ['S01', 'S02', 'S03', 'S04', 'S05', 'S06', 'S07', 'S08', 'S09', 'S10'];
/** Steps that run without `--steps`: S07 (interactive) and S08 (chat) are opt-in in v1 — see README. */
export const DEFAULT_STEPS = ['S01', 'S02', 'S03', 'S04', 'S05', 'S06', 'S09', 'S10'];

export const HELP = `wicked-smoke — artifact-level smoke harness for the wicked-* seams

usage: node bin/wicked-smoke.mjs [options]

  --crew <version>        wicked-crew npm version (default: latest)
  --core-ts <version>     wicked-core-ts version; "pinned" = whatever crew's range resolves (default: pinned)
  --bus <version>         wicked-bus npm version (default: latest)
  --garden <ref>          wicked-garden git tag (12.34.0 / v12.34.0) or "latest" (default: latest)
  --steps <list>          e.g. S01,S02,S04 or S01..S06 or all (default: ${DEFAULT_STEPS.join(',')})
  --root <dir>            temp root for the whole run (default: $RUNNER_TEMP or the OS temp dir)
  --keep                  keep the temp root after S10 (default: removed)
  --report <path>         JSON report path (default: <root>/report.json)
  --report-dir <dir>      copy report + daemon log + shim log + evidence here (for CI artifacts)
  --expect-fail <list>    extra finding ids to treat as expected failures, e.g. F-E2E-030
  --expect-fail-steps <l> step ids whose failures are all expected, e.g. S05
  --no-expect-fail        disable every built-in expected-fail rule (strict mode)
  --assert-hermetic       fail if anything under the real $HOME changed mtime during the run
  --step-timeout <secs>   per-step ceiling (default: 300)
  --verbose               echo every HTTP call and shim invocation
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
    keep: false,
    report: undefined,
    reportDir: undefined,
    expectFail: [],
    expectFailSteps: [],
    noExpectFail: false,
    assertHermetic: false,
    stepTimeout: 300,
    verbose: false,
    help: false,
  };
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
      case '--steps': o.steps = parseSteps(next()); break;
      case '--root': o.root = next(); break;
      case '--keep': o.keep = true; break;
      case '--report': o.report = next(); break;
      case '--report-dir': o.reportDir = next(); break;
      case '--expect-fail': o.expectFail = next().split(',').map((s) => s.trim()).filter(Boolean); break;
      case '--expect-fail-steps': o.expectFailSteps = parseSteps(next()); break;
      case '--no-expect-fail': o.noExpectFail = true; break;
      case '--assert-hermetic': o.assertHermetic = true; break;
      case '--step-timeout': o.stepTimeout = Number(next()); break;
      case '--verbose': o.verbose = true; break;
      case '-h':
      case '--help': o.help = true; break;
      default: throw new Error(`unknown option ${a} (see --help)`);
    }
  }
  return o;
}

/** `S01,S03` | `S01..S06` | `all` | `` (empty = none) */
export function parseSteps(spec) {
  const s = spec.trim();
  if (s === '' ) return [];
  if (s.toLowerCase() === 'all') return [...ALL_STEPS];
  const out = new Set();
  for (const part of s.split(',').map((p) => p.trim()).filter(Boolean)) {
    const range = part.match(/^(S\d\d)\.\.(S\d\d)$/i);
    if (range) {
      const a = ALL_STEPS.indexOf(range[1].toUpperCase());
      const b = ALL_STEPS.indexOf(range[2].toUpperCase());
      if (a < 0 || b < 0 || a > b) throw new Error(`bad step range ${part}`);
      for (const id of ALL_STEPS.slice(a, b + 1)) out.add(id);
    } else {
      const id = part.toUpperCase();
      if (!ALL_STEPS.includes(id)) throw new Error(`unknown step ${part}`);
      out.add(id);
    }
  }
  return ALL_STEPS.filter((id) => out.has(id));
}
