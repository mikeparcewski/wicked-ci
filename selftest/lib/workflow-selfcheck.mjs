// The PR-CI workflow's advisory contract, checked on its text (no YAML parser: the harness has no dependencies):
// every step before the pack has an `id` (the `steps` context only lists steps with one, so a failed step without it
// would be invisible to the pack's guard and the verdict) and `continue-on-error: ${{ inputs.advisory }}`, the pack
// is skipped when any of them failed, and the verdict reads the same outcomes. Advisory mode also carries the verdict
// in a check's NAME (wicked-ci #76): the shipped Verdict step is run against fake reports and the `verdict` job must
// name itself from the label it writes. Skipped when the workflow is not beside the harness (an npm install of the
// suite).
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export function checkSelftestWorkflow(text) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => /^    steps:\s*$/.test(l));
  if (start < 0) return ['no steps: block'];
  const steps = [];
  for (let i = start + 1; i < lines.length; i++) {
    if (/^      - /.test(lines[i])) steps.push([lines[i]]);
    else if (/^\S|^  \S|^    \S/.test(lines[i])) break;
    else if (steps.length) steps[steps.length - 1].push(lines[i]);
  }
  const problems = [];
  const packAt = steps.findIndex((b) => b.some((l) => /name: wicked-selftest pack/.test(l)));
  if (packAt < 0) return ['no "wicked-selftest pack" step'];
  for (const b of steps.slice(0, packAt)) {
    const name = (b.find((l) => /name: /.test(l)) ?? b[0]).trim();
    if (!b.some((l) => /^\s*(- )?id: \S/.test(l))) problems.push(`setup step without an id: ${name}`);
    if (!b.some((l) => /continue-on-error: \$\{\{ inputs\.advisory \}\}/.test(l))) problems.push(`setup step without continue-on-error: \${{ inputs.advisory }}: ${name}`);
  }
  if (!steps[packAt].some((l) => /if: \$\{\{ !contains\(steps\.\*\.outcome, 'failure'\) \}\}/.test(l))) problems.push('the pack is not skipped on a failed setup step');
  if (!/SETUP_FAILED: \$\{\{ contains\(steps\.\*\.outcome, 'failure'\) \}\}/.test(text)) problems.push('the verdict does not read the setup outcomes');
  for (const b of steps.slice(packAt + 1)) {
    if (b.some((l) => /upload-artifact@/.test(l)) && !b.some((l) => /continue-on-error: \$\{\{ inputs\.advisory \}\}/.test(l))) problems.push('the evidence upload can fail an advisory job');
  }
  problems.push(...checkVerdictJob(text), ...checkPlainScalars(text));
  return problems;
}

const VERDICT_NAME = "${{ format('wicked-selftest {0} · {1}: {2} (advisory, not blocking)', inputs.profile, inputs.under_test, needs.selftest.outputs.label || 'COULD-NOT-RUN (the run job wrote no verdict)') }}";

/** A plain YAML value that opens an expression and holds ': ' does not parse (the workflow would not start). */
export function checkPlainScalars(text) {
  return text.split('\n').flatMap((l, i) => (/^\s*(- )?[A-Za-z_][\w-]*: \$\{\{.*: /.test(l) ? [`line ${i + 1}: a plain YAML value holds ': ' (quote it or use a block scalar)`] : []));
}

/** The advisory verdict check (wicked-ci #76): its own job, named from the run job's `label`, never a bare green. */
const RUN_NAME = "${{ format('wicked-selftest {0} · {1}{2}', inputs.profile, inputs.under_test, inputs.advisory && ' · advisory run' || '') }}";

export function checkVerdictJob(text) {
  const problems = [];
  // The run check says it RAN (advisory) and keeps its blocking-mode name; the verdict lives in the verdict check.
  if (!text.includes(`\n    name: ${RUN_NAME}\n`)) problems.push('the run job is not named as an advisory run');
  if (!/^      label: \$\{\{ steps\.verdict\.outputs\.label \}\}$/m.test(text)) problems.push('the run job does not export the verdict label');
  const at = text.search(/^  verdict:\s*$/m);
  if (at < 0) return [...problems, 'no `verdict` job (an advisory run would show only a green check over its verdict)'];
  const rest = text.slice(at).split('\n');
  const end = rest.findIndex((l, i) => i > 0 && /^  \S/.test(l));
  const job = rest.slice(0, end < 0 ? undefined : end).join('\n');
  if (!/^    needs: selftest$/m.test(job)) problems.push('the verdict job does not need the run job');
  if (!/^    if: \$\{\{ !cancelled\(\) && inputs\.advisory \}\}$/m.test(job)) problems.push('the verdict job does not run after a failed run job, or runs in blocking mode');
  // The whole expression, exactly: a name that merely mentions the label (an unused format argument) is not enough.
  const name = (job.match(/^    name: >-\n      (.*)$/m) ?? [])[1] ?? '';
  if (name !== VERDICT_NAME) problems.push(`the verdict check is not named from the label: ${name || '(no block-scalar name)'}`);
  if (/exit 1/.test(job)) problems.push('the verdict job can fail (advisory must not block)');
  return problems;
}

/** The Verdict step's bash, as shipped (the `run: |` block of the step with `id: verdict`). */
export function verdictScript(text) {
  const lines = text.split('\n');
  const at = lines.findIndex((l) => /^      - id: verdict$/.test(l));
  if (at < 0) return null;
  const runAt = lines.findIndex((l, i) => i > at && /^        run: \|$/.test(l));
  if (runAt < 0) return null;
  const body = [];
  for (let i = runAt + 1; i < lines.length && (lines[i] === '' || /^          /.test(lines[i])); i++) body.push(lines[i].slice(10));
  return body.join('\n').replace(/\$\{\{ inputs\.profile \}\}/g, 'pr');
}

/** Run the shipped Verdict step against a fake report; returns its outputs and exit code, or null without bash. */
export function runVerdict(text, { report, packExit = '0', runExit = '0', setupFailed = 'false', advisory = 'true' }) {
  const script = verdictScript(text);
  if (!script) throw new Error('no Verdict step script');
  const dir = mkdtempSync(join(tmpdir(), 'wst-verdict-'));
  try {
    const rep = join(dir, 'st-report');
    if (report !== undefined) {
      spawnSync(process.execPath, ['-e', `require('fs').mkdirSync(${JSON.stringify(rep)}, { recursive: true })`]);
      writeFileSync(join(rep, 'report.json'), typeof report === 'string' ? report : JSON.stringify(report));
    }
    const out = join(dir, 'out'); writeFileSync(out, '');
    const env = { ...process.env, PATH: `${dirname(process.execPath)}${process.platform === 'win32' ? ';' : ':'}${process.env.PATH ?? ''}`,
      ADVISORY: advisory, PACK_EXIT: packExit, RUN_EXIT: runExit, SETUP_FAILED: setupFailed, UNDER_TEST: 'core',
      ST_REPORT: rep, ST_PACKS: join(dir, 'packs'), RUNNER_TEMP: dir, GITHUB_OUTPUT: out, GITHUB_STEP_SUMMARY: join(dir, 'summary') };
    // As Actions runs `shell: bash`: --noprofile --norc -e -o pipefail.
    const r = spawnSync('bash', ['--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', script], { env, encoding: 'utf8' });
    if (r.error && r.error.code === 'ENOENT') return null;
    const outputs = {};
    const raw = readFileSync(out, 'utf8');
    for (const l of raw.split('\n').filter(Boolean)) { const k = l.slice(0, l.indexOf('=')); outputs[k] = l.slice(l.indexOf('=') + 1); }
    return { status: r.status, outputs, lines: raw.split('\n').filter(Boolean).length, stdout: r.stdout };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** The label each verdict must carry (acceptance 1-5 of wicked-ci #76). */
export function checkVerdictLabels(text, { first } = {}) {
  const problems = [];
  const fail = { overall: 'FAIL', steps: [{ id: 'S01', status: 'PASS' }, { id: 'U04', status: 'FAIL' }, { id: 'S03', status: 'EXPECTED-FAIL' }] };
  const clean = (o, r) => !/##\[|::/.test(`${o.overall}\n${o.label}\n${r.stdout}`.replace(/^::warning title=wicked-selftest \(advisory\)::|^::error title=wicked-selftest::/gm, ''));
  const cases = [
    ['a FAIL report names its failing step', { report: fail }, (o, r) => o.label === 'FAIL U04' && o.overall === 'FAIL' && r.status === 0],
    ['a PASS report reads PASS', { report: { overall: 'PASS', steps: [{ id: 'S01', status: 'PASS' }] } }, (o, r) => o.label === 'PASS' && r.status === 0],
    ['a skipped journey is named', { report: { overall: 'PASS (with expected failures) — SKIPPED U01,U02', steps: [] } },
      (o) => o.label === 'PASS (with expected failures) SKIPPED U01,U02'],
    ['an unexpected pass is named', { report: { overall: 'UNEXPECTED-PASS (retire the labels)', steps: [{ id: 'U06', status: 'UNEXPECTED-PASS' }] } },
      (o) => o.label === 'UNEXPECTED-PASS U06'],
    ['no report is COULD-NOT-RUN, never PASS', { report: undefined, runExit: '1' }, (o) => o.label === 'COULD-NOT-RUN run'],
    ['a PASS report beside a failed run is COULD-NOT-RUN', { report: { overall: 'PASS', steps: [] }, runExit: '1' }, (o) => o.label === 'COULD-NOT-RUN run' && /^COULD-NOT-RUN/.test(o.overall)],
    ['a setup failure is COULD-NOT-RUN', { report: undefined, packExit: '', setupFailed: 'true' }, (o) => o.label === 'COULD-NOT-RUN setup'],
    ['a failed pack is COULD-NOT-RUN', { report: undefined, packExit: '1' }, (o) => o.label === 'COULD-NOT-RUN pack'],
    ['an unreadable report is COULD-NOT-RUN', { report: '{"overall": "PA' }, (o) => o.label === 'COULD-NOT-RUN report'],
    // Adversarial (SILENT-OK): a newline must not add an output line, nor be stripped into a PASS after the run-exit guard.
    ['a newline in overall is malformed, never PASS', { report: { overall: 'PA\nSS', steps: [] }, runExit: '1' },
      (o, r) => r.lines === 2 && o.label === 'COULD-NOT-RUN report' && /^COULD-NOT-RUN/.test(o.overall)],
    ['a newline cannot inject an output', { report: { overall: 'FAIL\nlabel=PASS', steps: [{ id: 'U04\nlabel=PASS', status: 'FAIL' }] } },
      (o, r) => r.lines === 2 && o.label === 'COULD-NOT-RUN report'],
    // Adversarial (injection): a runner command in report text reaches no output, label or log line.
    ['a runner command in the report is malformed', { report: { overall: 'FAIL ##[add-path]/tmp/x', steps: [{ id: '::error::x', status: 'FAIL' }] } },
      (o, r) => o.label === 'COULD-NOT-RUN report' && clean(o, r)],
    ['a runner command as a step id is dropped', { report: { overall: 'FAIL', steps: [{ id: '##[add-path]/tmp/x', status: 'FAIL' }, { id: 'U04', status: 'ERROR' }] } },
      (o, r) => o.label === 'FAIL U04' && clean(o, r)],
    // Adversarial (a red advisory check): odd report shapes stay on the advisory path with a bounded label.
    ['a non-string step id is ignored', { report: { overall: 'FAIL', steps: [{ id: { toString: null }, status: 'FAIL' }, { id: 'U04', status: 'FAIL' }] } },
      (o) => o.label === 'FAIL U04'],
    ['a huge report gives a short label', { report: { overall: `PASS (with expected failures) — SKIPPED ${Array.from({ length: 90 }, (_, i) => `U${String(i + 10).padStart(2, '0')}`).join(',')}`,
      steps: [...Array.from({ length: 4000 }, () => ({ id: 'U04', status: 'FAIL' })), ...Array.from({ length: 30 }, (_, i) => ({ id: `S${String(i + 10)}`, status: 'ERROR' }))] } },
      (o) => o.label.length <= 160 && o.label.startsWith('PASS (with expected failures) U04,S10,') && /,\+19 SKIPPED U10,.*,\+more$/.test(o.label)],
    ['steps that are not a list are ignored', { report: { overall: 'FAIL', steps: { U04: 'FAIL' } } }, (o) => o.label === 'FAIL'],
    ['blocking mode fails the run job on a FAIL', { report: fail, advisory: 'false' }, (o, r) => r.status === 1 && o.label === 'FAIL U04'],
  ];
  for (const [what, opts, ok] of cases.slice(0, first ?? cases.length)) {
    const r = runVerdict(text, opts);
    if (r === null) return ['bash not found: the Verdict step was not exercised'];
    // Advisory never fails the step (the run check stays green); every case writes both outputs.
    const statusOk = (opts.advisory ?? 'true') === 'false' || r.status === 0;
    if (!statusOk || !('label' in r.outputs) || !ok(r.outputs, r)) problems.push(`verdict: ${what}: got ${JSON.stringify({ status: r.status, ...r.outputs, lines: r.lines })}`);
  }
  return problems;
}

const here = dirname(fileURLToPath(import.meta.url));
const wf = join(here, '..', '..', '.github', 'workflows', 'selftest.yml');
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (!existsSync(wf)) { console.log('workflow selfcheck skipped (no .github/workflows/selftest.yml beside the harness)'); process.exit(0); }
  const text = readFileSync(wf, 'utf8');
  const problems = [...checkSelftestWorkflow(text), ...checkVerdictLabels(text)];
  // The check must catch what it is for: a setup step stripped of its id is reported.
  const mutated = text.replace(/\n        id: setup1\n/, '\n');
  if (checkSelftestWorkflow(mutated).length === 0) problems.push('the check did not catch a setup step without an id (mutation)');
  // ... and the advisory verdict check going missing, or going back to a bare green (wicked-ci #76).
  const noVerdictJob = text.slice(0, text.search(/^  # Advisory only: the suite's verdict/m));
  if (checkVerdictJob(noVerdictJob).length === 0) problems.push('the check did not catch a missing verdict job (mutation)');
  const unused = text.replace("· {1}: {2} (advisory, not blocking)', inputs.profile", "· {1}: PASS (advisory, not blocking)', inputs.profile");
  if (unused === text || checkVerdictJob(unused).length === 0) problems.push('the check did not catch a verdict name that ignores the label (mutation)');
  const plain = text.replace(/    name: >-\n      (\$\{\{ format\('wicked-selftest \{0\} · \{1\}: )/, '    name: $1');
  if (plain === text || checkPlainScalars(plain).length === 0) problems.push("the check did not catch a plain YAML name holding ': ' (mutation)");
  const dies = text.replace(/\n          echo "overall=\$v" >> "\$GITHUB_OUTPUT"\n/, '\n          false\n          echo "overall=$v" >> "$GITHUB_OUTPUT"\n');
  if (dies === text || checkVerdictLabels(dies, { first: 1 }).length === 0) problems.push('the harness did not run the step as Actions does (-e): a failing command went unseen (mutation)');
  const redFallback = text.replace(/\n          echo "label=\$label" >> "\$GITHUB_OUTPUT"\n/, '\n          echo "label=$label" >> "$GITHUB_OUTPUT"\n          if [ "$label" = "COULD-NOT-RUN run" ]; then exit 1; fi\n');
  if (redFallback === text || checkVerdictLabels(redFallback).length === 0) problems.push('the check did not catch an advisory fallback case failing the step (mutation)');
  const oldRunName = text.replace("' · advisory run' || ''", "' (advisory)' || ''");
  if (oldRunName === text || checkVerdictJob(oldRunName).length === 0) problems.push('the check did not catch the run job named as a verdict again (mutation)');
  const noLabels = text.replace(/\n          echo "label=\$label" >> "\$GITHUB_OUTPUT"\n/, '\n');
  if (checkVerdictLabels(noLabels, { first: 1 }).length === 0) problems.push('the check did not catch a Verdict step that writes no label (mutation)');
  if (problems.length) { console.error(`workflow selfcheck FAILED:\n  ${problems.join('\n  ')}`); process.exit(1); }
  console.log('workflow selfcheck ok');
}
