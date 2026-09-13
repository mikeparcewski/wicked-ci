#!/usr/bin/env node
// wicked-smoke — install the PUBLISHED wicked-* artifacts into a hermetic temp root, boot the daemon
// with shimmed seats, and assert the cross-repo seams on the wire (S01–S10). One line per step, a JSON
// report, non-zero exit on any FAIL or UNEXPECTED-PASS (EXPECTED-FAIL and SKIPPED never fail the run).
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import * as fsSync from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { ALL_STEPS, HELP, parseArgs } from '../lib/args.mjs';
import { ensureLayout, hermeticEnv, layout } from '../lib/env.mjs';
import { engineSemverFor, installGarden, installNpm, installedTree, installedVersions } from '../lib/install.mjs';
import { writeCouncilOverlay, writePassthroughs, writeSeatCredentials, writeShims } from '../lib/shims.mjs';
import { Daemon } from '../lib/daemon.mjs';
import { apiClient } from '../lib/http.mjs';
import { ExpectPolicy } from '../lib/expect.mjs';
import { STATUS, StepTrace, classify, printStep, writeSummaryIfCi } from '../lib/report.mjs';
import { compareHome, snapshotHome } from '../lib/hermetic.mjs';

const here = dirname(fileURLToPath(import.meta.url));
/** Built-in per-step ceilings (seconds); `--step-timeout` RAISES them when larger, never lowers. S01's
 *  ceiling is also the daemon's BOOT wait (a cold first boot publishes the garden bundle). */
const STEP_CEILINGS = { S01: 300, S04: 540, S05: 420 };

/** chmod u+w every directory under `dir` (no symlink following) so a recursive remove can proceed. */
function makeWritable(dir) {
  const { lstatSync, chmodSync } = fsSync;
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    let st;
    try { st = lstatSync(d); } catch { continue; }
    if (!st.isDirectory()) continue;
    try { chmodSync(d, (st.mode & 0o777) | 0o700); } catch { /* best effort */ }
    let entries = [];
    try { entries = readdirSync(d); } catch { continue; }
    for (const e of entries) stack.push(join(d, e));
  }
}

async function main() {
  let opts;
  try { opts = parseArgs(process.argv.slice(2)); } catch (err) { console.error(err.message); console.error(HELP); return 2; }
  if (opts.help) { console.log(HELP); return 0; }

  const wall0 = Date.now();
  const log = (line) => console.log(line);
  const root = resolve(opts.root ?? join(process.env.RUNNER_TEMP && process.env.RUNNER_TEMP !== '' ? process.env.RUNNER_TEMP : tmpdir(), `wicked-smoke-${Date.now().toString(36)}`));
  // A root that already exists is a previous run's (a `--keep`): its repos/state would make S03 fail
  // "corpus already exists" and the install would reuse whatever tree is there — refuse unless asked.
  if (existsSync(root) && readdirSync(root).length > 0) {
    if (!opts.reuseRoot) { console.error(`wicked-smoke: --root ${root} is not empty (a previous run's?). Pass --reuse-root to clear its repos/, state/, bus/, evidence/ and re-use the installed tree, or choose another --root.`); return 2; }
    for (const sub of ['repos', 'state', 'bus', 'evidence', 'worker', 'home', 'tmp', 'interactive']) { makeWritable(join(root, sub)); rmSync(join(root, sub), { recursive: true, force: true }); }
    for (const f of readdirSync(root)) if (/-origin\.git$/.test(f) || /^(daemon\.log|shim-calls\.ndjson|report\.json|core-semver\.txt)$/.test(f)) rmSync(join(root, f), { recursive: true, force: true });
  }
  const L = layout(root);
  ensureLayout(L);
  log(`wicked-smoke: root ${root}`);
  log(`wicked-smoke: host ${process.platform}/${process.arch} node ${process.version}`);
  const homeBefore = opts.assertHermetic ? snapshotHome() : null;
  if (homeBefore?.truncated?.length) log(`wicked-smoke: hermetic scan bounded under ${homeBefore.truncated.join(', ')} (more than the entry budget — recorded by mtime only there)`);
  const env = hermeticEnv(L);

  // ── install the published set ──
  const install0 = Date.now();
  let versions;
  let garden = { version: null, tag: null };
  try {
    versions = installNpm(L, env, { crew: opts.crew, bus: opts.bus, coreTs: opts.coreTs }, log);
    garden = await installGarden(L, env, opts.garden, log);
  } catch (err) {
    log(`install FAILED: ${err.message}`);
    return 1;
  }
  versions.garden = garden.version;
  const tree = installedTree(L);
  log(`wicked-smoke: installed crew ${versions.crew} · core-ts ${versions.coreTs} (${tree.platformPkgName} ${versions.coreTsPlatform}) · bus ${versions.bus} · garden ${versions.garden} · studio bundle ${versions.studioBundle} in ${((Date.now() - install0) / 1000).toFixed(1)}s`);
  const shims = writeShims(L);
  const engineSemver = engineSemverFor(versions.coreTs);
  writeFileSync(join(root, 'core-semver.txt'), engineSemver.semver);
  versions.engineSemver = engineSemver.semver;
  log(`wicked-smoke: engine crate semver for the wicked-core shim: ${engineSemver.semver} (${engineSemver.source})`);
  const creds = writeSeatCredentials(L);
  const pass = writePassthroughs(L);
  const overlay = writeCouncilOverlay(L);
  log(`wicked-smoke: shims on PATH: ${shims.join(', ')}; absent by design: pi (${creds.piCredential ? 'credential present — the engine must learn not_installed from the ballot' : 'no credential — benched by the launcher as signed out'}), agy; council overlay ${overlay.replace(root, '<root>')}`);
  log(`wicked-smoke: host passthroughs: ${pass.found.join(', ') || 'none'}${pass.missing.length ? ` (missing on host: ${pass.missing.join(', ')})` : ''}`);
  if (pass.missing.includes('uv')) log('wicked-smoke: WARNING — `uv` is not on the host PATH; crew BLOCKS the skills publish without it (S02 will say so). Install uv (https://docs.astral.sh/uv/).');

  // The policy sees the host too: some findings trigger only on a node major (compile cache in the
  // checks scratch) or a platform (the Linux bwrap floor denial).
  versions.nodeMajor = Number(process.versions.node.split('.')[0]);
  versions.platform = process.platform;
  const policy = new ExpectPolicy(versions, { extra: opts.expectFail, disabled: opts.noExpectFail });
  log(`wicked-smoke: expected-fail policy active: ${Object.keys(policy.active()).join(', ') || 'none'}`);
  const daemon = new Daemon(L, tree.crewBin, log, { bootTimeoutMs: Math.max(STEP_CEILINGS.S01, opts.stepTimeout) * 1000 });
  const ctx = {
    L, env, opts, log, tree, versions, daemon, policy, state: { piCredential: creds.piCredential }, signal: null,
    api: () => apiClient(daemon.origin, { log, verbose: opts.verbose }),
    async ensureDaemon() {
      // Both waits are bounded by what is left of the current step's budget (never a second clock).
      const remaining = () => Math.max(30_000, (ctx.stepDeadline ?? Date.now() + daemon.bootTimeoutMs) - Date.now() - 5_000);
      if (!daemon.child) await daemon.start({ timeoutMs: remaining() });
      else if (!daemon.healthy) await daemon.waitHealthy({ timeoutMs: remaining() });
    },
    shimCalls() {
      if (!existsSync(L.shimLog)) return [];
      return readFileSync(L.shimLog, 'utf8').split('\n').filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
    },
  };

  // ── steps ──
  const results = [];
  const selected = ALL_STEPS.filter((id) => opts.steps.includes(id));
  const stepFiles = readdirSync(join(here, '..', 'lib', 'steps'));
  for (const stepId of ALL_STEPS) {
    const file = stepFiles.find((f) => f.startsWith(`${stepId}-`));
    const mod = await import(pathToFileURL(join(here, '..', 'lib', 'steps', file)).href);
    if (!selected.includes(stepId)) {
      results.push({ id: stepId, name: mod.name, status: STATUS.SKIP, ms: 0, checks: [], notes: [{ name: 'skipped', detail: 'not in --steps' }], error: null });
      continue;
    }
    const t = new StepTrace(stepId, L.evidence, log);
    const t0 = Date.now();
    let error = null;
    const ceiling = Math.max(STEP_CEILINGS[stepId] ?? 0, opts.stepTimeout) * 1000;
    // The ceiling ABORTS the step: the signal reaches every wait loop (runs.mjs) so a timed-out step
    // stops polling, approving and writing evidence instead of running on under the next step.
    const ac = new AbortController();
    ctx.signal = ac.signal;
    ctx.stepDeadline = Date.now() + ceiling;
    try {
      let timer;
      await Promise.race([
        mod.run(ctx, t),
        new Promise((_, reject) => { timer = setTimeout(() => { ac.abort(); reject(new Error(`step ceiling ${ceiling / 1000}s exceeded (raise with --step-timeout)`)); }, ceiling); }),
      ]).finally(() => clearTimeout(timer));
    } catch (err) {
      error = err instanceof Error ? `${err.message}` : String(err);
    }
    ctx.signal = null;
    const ms = Date.now() - t0;
    let status = classify(t, policy, opts.expectFailSteps.includes(stepId));
    if (error) status = STATUS.ERROR;
    const result = { id: stepId, name: mod.name, status, ms, checks: t.checks, notes: t.notes, error, evidence: t.evidenceFiles.map((p) => p.replace(root, '<root>')) };
    results.push(result);
    printStep(result, log);
    if (status === STATUS.ERROR && stepId !== 'S10') log(`    (continuing; daemon log tail follows)\n${daemon.logTail(8).split('\n').map((l) => '    | ' + l.slice(0, 220)).join('\n')}`);
  }
  if (daemon.child) await daemon.stop();

  // ── hermetic scan ──
  let hermetic = null;
  if (homeBefore) {
    hermetic = compareHome(homeBefore, snapshotHome(), { ignore: [root] });
    log(`hermetic: ${hermetic.ok ? 'clean — nothing under $HOME changed' : `CHANGED under $HOME: ${hermetic.changed.slice(0, 40).join(', ')}${hermetic.changed.length > 40 ? ` … (+${hermetic.changed.length - 40})` : ''}`}${hermetic.noise?.length ? ` (noise, not a leak — ${hermetic.noise.length} entr${hermetic.noise.length === 1 ? 'y' : 'ies'}, all in the report: ${hermetic.noise.slice(0, 6).join(', ')}${hermetic.noise.length > 6 ? ` … (+${hermetic.noise.length - 6})` : ''})` : ''}${hermetic.truncated.length ? ` (scan bounded under ${hermetic.truncated.join(', ')})` : ''}`);
  }

  // ── report ──
  const failed = results.filter((r) => r.status === STATUS.FAIL || r.status === STATUS.ERROR);
  const xpass = results.filter((r) => r.status === STATUS.XPASS);
  const overall = failed.length > 0 || (hermetic && !hermetic.ok)
    ? 'FAIL'
    : xpass.length > 0
      ? 'UNEXPECTED-PASS (retire the labels)'
      : results.some((r) => r.status === STATUS.XFAIL) ? 'PASS (with expected failures)' : 'PASS';
  const report = {
    tool: 'wicked-smoke', schema: 2, at: new Date().toISOString(), overall, wallMs: Date.now() - wall0,
    host: { platform: process.platform, arch: process.arch, node: process.version, ci: Boolean(process.env.GITHUB_ACTIONS), loadavg: (await import('node:os')).loadavg().map((x) => Math.round(x)) },
    daemon: { firstBootMs: daemon.firstBootMs ?? null, starts: daemon.starts, port: daemon.port },
    requested: { crew: opts.crew, coreTs: opts.coreTs, bus: opts.bus, garden: opts.garden, steps: selected },
    versions, expectedFailPolicy: policy.active(), shims, root: opts.keep ? root : null,
    unexpectedPasses: results.flatMap((r) => r.checks.filter((c) => c.ok && c.unexpectedPass).map((c) => ({ step: r.id, check: c.name, finding: c.finding, reason: c.unexpectedPass, flaky: Boolean(c.flaky) }))),
    steps: results, hermetic,
  };
  // The report lives under the root (as --help says); it is copied out to --report-dir, and — when the
  // root is about to be removed with no --report-dir — to ./wicked-smoke-report.json so nothing is lost.
  const reportPath = opts.report ?? join(root, 'report.json');
  mkdirSync(dirname(reportPath), { recursive: true });
  writeFileSync(reportPath, JSON.stringify(report, null, 1));
  const copies = [];
  if (opts.reportDir) {
    mkdirSync(opts.reportDir, { recursive: true });
    cpSync(reportPath, join(opts.reportDir, 'report.json'));
    copies.push(join(opts.reportDir, 'report.json'));
    for (const [src, name] of [[L.daemonLog, 'daemon.log'], [L.shimLog, 'shim-calls.ndjson'], [L.installLog, 'install.log']]) {
      if (existsSync(src)) cpSync(src, join(opts.reportDir, name));
    }
    if (existsSync(L.evidence)) cpSync(L.evidence, join(opts.reportDir, 'evidence'), { recursive: true });
  } else if (!opts.keep && reportPath.startsWith(root)) {
    cpSync(reportPath, join(process.cwd(), 'wicked-smoke-report.json'));
    copies.push(join(process.cwd(), 'wicked-smoke-report.json'));
  }
  writeSummaryIfCi(report);
  log(`wicked-smoke: ${overall} in ${((Date.now() - wall0) / 1000).toFixed(1)}s — report ${reportPath}${copies.length ? ` (copied to ${copies.join(', ')})` : ''}${opts.reportDir ? ` (+ daemon log, shim calls, evidence in ${opts.reportDir})` : ''}`);
  if (xpass.length > 0) log(`wicked-smoke: UNEXPECTED-PASS in ${xpass.map((r) => r.id).join(', ')} — a labelled check passed while its finding is still expected to fail: retire or re-bound the label in smoke/lib/expect.mjs${opts.allowUnexpectedPass ? ' (allowed by --allow-unexpected-pass)' : ''}`);
  if (!opts.keep) {
    // The skills store locks published generations read-only (dirs 0555) — on Linux `rm` of their
    // children needs the write bit back first.
    try { makeWritable(root); rmSync(root, { recursive: true, force: true }); log('wicked-smoke: temp root removed'); } catch (err) { log(`wicked-smoke: could not remove temp root: ${err.message}`); }
    if (failed.length > 0) log('wicked-smoke: re-run with --keep (and --report-dir) to inspect the daemon log and evidence');
  } else log(`wicked-smoke: temp root kept at ${root}`);
  if (failed.length > 0 || (hermetic && !hermetic.ok)) return 1;
  if (xpass.length > 0 && !opts.allowUnexpectedPass) return 3;
  return 0;
}

main().then((code) => process.exit(code), (err) => { console.error(err); process.exit(1); });
