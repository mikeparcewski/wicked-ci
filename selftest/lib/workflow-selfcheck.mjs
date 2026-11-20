// The PR-CI workflow's advisory contract, checked on its text (no YAML parser: the harness has no dependencies):
// every step before the pack has an `id` (the `steps` context only lists steps with one, so a failed step without it
// would be invisible to the pack's guard and the verdict) and `continue-on-error: ${{ inputs.advisory }}`, the pack
// is skipped when any of them failed, and the verdict reads the same outcomes. Advisory mode publishes the verdict as
// a check run whose CONCLUSION is the verdict (wicked-ci #76): the shipped Verdict step is run against fake reports
// (its label), and the shipped publish step against a stub `gh`, asserting the conclusion, title, name and summary it
// POSTs. Skipped when the workflow is not beside the harness (an npm install of the suite).
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

/** A plain YAML value that opens an expression and holds ': ' does not parse (the workflow would not start). */
export function checkPlainScalars(text) {
  return text.split('\n').flatMap((l, i) => (/^\s*(- )?[A-Za-z_][\w-]*: \$\{\{.*: /.test(l) ? [`line ${i + 1}: a plain YAML value holds ': ' (quote it or use a block scalar)`] : []));
}

/** The advisory verdict (wicked-ci #76): a job of its own that publishes a check run whose CONCLUSION is the verdict. */
const RUN_NAME = "${{ format('wicked-selftest {0} · {1}{2}', inputs.profile, inputs.under_test, inputs.advisory && ' · advisory run' || '') }}";

/** The `verdict` job's text (from `  verdict:` to the next job or the end), or null. */
function verdictJobText(text) {
  const at = text.search(/^  verdict:\s*$/m);
  if (at < 0) return null;
  const rest = text.slice(at).split('\n');
  const end = rest.findIndex((l, i) => i > 0 && /^  \S/.test(l));
  return rest.slice(0, end < 0 ? undefined : end).join('\n');
}

/** The verdict job's DISPLAY name (#78; nothing reads it): the label, for checks lists that show only names. */
const VERDICT_NAME = "${{ format('wicked-selftest {0} · {1}: {2} (advisory, not blocking)', inputs.profile, inputs.under_test, needs.selftest.outputs.label || 'COULD-NOT-RUN (the run job wrote no verdict)') }}";
/** The shipped bindings the publish step reads (the harness supplies its own values, so each is checked as text). */
const BINDINGS = [
  ['LABEL', '${{ needs.selftest.outputs.label }}'],
  ['OWN_TREE', "${{ inputs.head_ref == '' && github.event_name != 'pull_request_target' }}"],
  ['CHECK_NAME', "${{ format('wicked-selftest {0} · {1} · {2}{3} · advisory verdict', inputs.profile, inputs.under_test, inputs.os, inputs.artifact_suffix != '' && format(' · {0}', inputs.artifact_suffix) || '') }}"],
  ['GH_TOKEN', '${{ github.token }}'],
  ['REPO', '${{ github.repository }}'],
];

export function checkVerdictJob(text) {
  const problems = [];
  // The run check says it RAN (advisory) and keeps its blocking-mode name; the verdict is the verdict check run.
  if (!text.includes(`\n    name: ${RUN_NAME}\n`)) problems.push('the run job is not named as an advisory run');
  if (!/^      overall: \$\{\{ steps\.verdict\.outputs\.overall \}\}$/m.test(text)) problems.push('the run job does not export the verdict');
  if (!/^      label: \$\{\{ steps\.verdict\.outputs\.label \}\}$/m.test(text)) problems.push('the run job does not export the verdict label');
  const job = verdictJobText(text);
  if (job === null) return [...problems, 'no `verdict` job (an advisory run would show only a green check over its verdict)'];
  if (!/^    needs: selftest$/m.test(job)) problems.push('the verdict job does not need the run job');
  if (!/^    if: \$\{\{ !cancelled\(\) && inputs\.advisory \}\}$/m.test(job)) problems.push('the verdict job does not run after a failed run job, or runs in blocking mode');
  if (!/^    permissions:\n      checks: write\b/m.test(job)) problems.push('the verdict job does not hold checks: write (the check run cannot be published)');
  if (/^permissions:\n  (?!contents: read\n\n)/m.test(text)) problems.push('the workflow-level permissions are no longer contents: read only');
  if (!/^          OVERALL: \$\{\{ needs\.selftest\.outputs\.overall \}\}$/m.test(job)) problems.push('the verdict is not read from the run job\'s validated overall');
  if (!/^          RUN_RESULT: \$\{\{ needs\.selftest\.result \}\}$/m.test(job)) problems.push('the verdict ignores the run job\'s result');
  if (!/^          HEAD_SHA: \$\{\{ github\.event\.pull_request\.head\.sha \|\| github\.sha \}\}$/m.test(job)) problems.push('the check run is not attached to the pull request head');
  for (const [k, v] of BINDINGS) if (!job.includes(`\n          ${k}: ${v}\n`)) problems.push(`the publish step's ${k} is not bound to ${v}`);
  const name = (job.match(/^    name: >-\n      (.*)$/m) ?? [])[1] ?? '';
  if (name !== VERDICT_NAME) problems.push(`the verdict job's display name is not the label: ${name || '(no block-scalar name)'}`);
  return problems;
}

/** The publish step's bash, as shipped (the `run: |` block of the verdict job's only step). */
export function publishScript(text) {
  const job = verdictJobText(text);
  if (job === null) return null;
  const lines = job.split('\n');
  const runAt = lines.findIndex((l) => /^        run: \|$/.test(l));
  if (runAt < 0) return null;
  const body = [];
  for (let i = runAt + 1; i < lines.length && (lines[i] === '' || /^          /.test(lines[i])); i++) body.push(lines[i].slice(10));
  return body.join('\n');
}

/** Run the shipped publish step with a stub `gh` that records the POSTed body; returns { status, body, args, stdout }. */
export function runPublish(text, { overall = '', label = '', runResult = 'success', headSha = 'abc123', ghFails = false, ownTree = 'true' }) {
  const script = publishScript(text);
  if (!script) throw new Error('no publish step script');
  const dir = mkdtempSync(join(tmpdir(), 'wst-publish-'));
  try {
    const bin = join(dir, 'bin'); spawnSync(process.execPath, ['-e', `require('fs').mkdirSync(${JSON.stringify(bin)})`]);
    const rec = join(dir, 'posted.json'); const args = join(dir, 'args');
    // The stub: `gh api -X POST <path> --input <file>` copies <file> to posted.json (or fails, as a 403 would).
    writeFileSync(join(bin, 'gh'), `#!/usr/bin/env bash\nprintf '%s\\n' "$*" > ${JSON.stringify(args)}\n` +
      `[ "$GH_FAILS" = 1 ] && { echo 'HTTP 403: Resource not accessible by integration' >&2; exit 1; }\n` +
      `while [ $# -gt 0 ]; do [ "$1" = --input ] && cp "$2" ${JSON.stringify(rec)}; shift; done\necho '{"id":1}'\n`, { mode: 0o755 });
    const sep = process.platform === 'win32' ? ';' : ':';
    const env = { ...process.env, PATH: `${bin}${sep}${dirname(process.execPath)}${sep}${process.env.PATH ?? ''}`,
      GH_TOKEN: 'x', REPO: 'o/r', HEAD_SHA: headSha, OVERALL: overall, LABEL: label, RUN_RESULT: runResult,
      CHECK_NAME: 'wicked-selftest pr · core · advisory verdict', DETAILS_URL: 'https://example.invalid/run', RUNNER_TEMP: dir,
      GH_FAILS: ghFails ? '1' : '0', OWN_TREE: ownTree };
    const r = spawnSync('bash', ['--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', script], { env, encoding: 'utf8' });
    if (r.error && r.error.code === 'ENOENT') return null;
    const body = existsSync(rec) ? JSON.parse(readFileSync(rec, 'utf8')) : null;
    return { status: r.status, body, args: existsSync(args) ? readFileSync(args, 'utf8').trim() : '', stdout: r.stdout + r.stderr };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** The CONCLUSION each verdict publishes (wicked-ci #76, reopened): success only for a PASS, neutral otherwise. */
export function checkVerdictConclusions(text) {
  const problems = [];
  const cases = [
    ['PASS', { overall: 'PASS', label: 'PASS' }, 'success'],
    ['PASS with expected failures', { overall: 'PASS (with expected failures)', label: 'PASS (with expected failures)' }, 'success'],
    ['FAIL', { overall: 'FAIL', label: 'FAIL U04' }, 'neutral'],
    ['UNEXPECTED-PASS', { overall: 'UNEXPECTED-PASS (retire the labels)', label: 'UNEXPECTED-PASS U02' }, 'neutral'],
    ['COULD-NOT-RUN', { overall: 'COULD-NOT-RUN (pack exited 1)', label: 'COULD-NOT-RUN pack' }, 'neutral'],
    ['PASS with skipped steps', { overall: 'PASS — SKIPPED U03', label: 'PASS (SKIPPED U03)' }, 'neutral'],
    ['no verdict (run job died)', { overall: '', label: '', runResult: 'failure' }, 'neutral'],
    ['PASS but the run job failed', { overall: 'PASS', label: 'PASS', runResult: 'failure' }, 'neutral'],
    ['label and verdict disagree', { overall: 'FAIL', label: 'PASS' }, 'neutral'],
    ['PASS on another tree (head_ref / pull_request_target)', { overall: 'PASS', label: 'PASS', ownTree: 'false' }, 'neutral'],
  ];
  for (const [what, opts, want] of cases) {
    const r = runPublish(text, opts);
    if (r === null) return ['bash is not available: the conclusions were not checked'];
    if (r.status !== 0) { problems.push(`${what}: the publish step failed (${r.status}): ${r.stdout.trim().split('\n').pop()}`); continue; }
    if (!r.body) { problems.push(`${what}: no check run was posted`); continue; }
    if (r.body.conclusion !== want) problems.push(`${what}: concluded ${r.body.conclusion}, expected ${want}`);
    if (r.body.status !== 'completed' || r.body.head_sha !== 'abc123') problems.push(`${what}: the check run is not completed on the head sha`);
    if (!/^api -X POST repos\/o\/r\/check-runs --input /.test(r.args)) problems.push(`${what}: not a POST to the Checks API (${r.args})`);
    const title = (opts.label || 'COULD-NOT-RUN (the run job wrote no verdict)') + (opts.ownTree === 'false' ? ' (another tree was tested)' : '');
    if (r.body.output?.title !== title) problems.push(`${what}: the title is not the run job's label (${r.body.output?.title})`);
    if (r.body.name !== 'wicked-selftest pr · core · advisory verdict') problems.push(`${what}: the check run is not posted under CHECK_NAME`);
    if (!String(r.body.output?.summary ?? '').startsWith(`Verdict: ${opts.overall || 'none (the run job wrote no verdict)'}\n`)) problems.push(`${what}: the summary does not lead with the verdict line`);
  }
  const denied = runPublish(text, { overall: 'FAIL', label: 'FAIL U04', ghFails: true });
  if (denied && (denied.status === 0 || !/^::error::.*checks: write/m.test(denied.stdout))) problems.push('a check run that could not be published did not fail the job with an ::error:: naming checks: write');
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
  const problems = [...checkSelftestWorkflow(text), ...checkVerdictLabels(text), ...checkVerdictConclusions(text)];
  // The check must catch what it is for: a setup step stripped of its id is reported.
  const mutated = text.replace(/\n        id: setup1\n/, '\n');
  if (checkSelftestWorkflow(mutated).length === 0) problems.push('the check did not catch a setup step without an id (mutation)');
  // ... and the advisory verdict check going missing, or concluding anything but the verdict (wicked-ci #76).
  const noVerdictJob = text.slice(0, text.search(/^  # Advisory only: the suite's verdict/m));
  if (checkVerdictJob(noVerdictJob).length === 0) problems.push('the check did not catch a missing verdict job (mutation)');
  const alwaysGreen = text.replace(/\n          conclusion=neutral\n/, '\n          conclusion=success\n');
  if (alwaysGreen === text || checkVerdictConclusions(alwaysGreen).length === 0) problems.push('the check did not catch a verdict that always concludes success (mutation)');
  const failIsPass = text.replace("'PASS' | 'PASS (with expected failures)')", "'PASS' | 'PASS (with expected failures)' | 'FAIL')");
  if (failIsPass === text || checkVerdictConclusions(failIsPass).length === 0) problems.push('the check did not catch FAIL concluding success (mutation)');
  const readsLabel = text.replace('case "$OVERALL" in', 'case "$LABEL" in');
  if (readsLabel === text || checkVerdictConclusions(readsLabel).length === 0) problems.push('the check did not catch the conclusion read from the label (mutation)');
  const noWrite = text.replace(/\n    permissions:\n      checks: write[^\n]*\n/, '\n');
  if (noWrite === text || checkVerdictJob(noWrite).length === 0) problems.push('the check did not catch the verdict job without checks: write (mutation)');
  const mergeSha = text.replace('HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}', 'HEAD_SHA: ${{ github.sha }}');
  if (mergeSha === text || checkVerdictJob(mergeSha).length === 0) problems.push('the check did not catch the check run attached to the merge commit (mutation)');
  const swallowed = text.replace(/\n            exit 1\n          fi\n          echo "wicked-selftest \(advisory\)/, '\n          fi\n          echo "wicked-selftest (advisory)');
  if (swallowed === text || checkVerdictConclusions(swallowed).length === 0) problems.push('the check did not catch a publish failure that leaves the job green (mutation)');
  const noOwnTree = text.replace('if [ "$RUN_RESULT" = success ] && [ "$OWN_TREE" = true ]; then', 'if [ "$RUN_RESULT" = success ]; then');
  if (noOwnTree === text || checkVerdictConclusions(noOwnTree).length === 0) problems.push('the check did not catch a PASS on another tree concluding success (mutation)');
  for (const [k] of BINDINGS) {
    const unbound = text.replace(new RegExp(`\\n          ${k}: [^\\n]*\\n`), '\n');
    if (unbound === text || checkVerdictJob(unbound).length === 0) problems.push(`the check did not catch the publish step's ${k} unbound (mutation)`);
  }
  const noLabelOut = text.replace(/\n      label: \$\{\{ steps\.verdict\.outputs\.label \}\}\n/, '\n');
  if (noLabelOut === text || checkVerdictJob(noLabelOut).length === 0) problems.push('the check did not catch the run job not exporting the label (mutation)');
  const noAnnotation = text.replace('echo "::error::could not publish', 'echo "could not publish');
  if (noAnnotation === text || checkVerdictConclusions(noAnnotation).length === 0) problems.push('the check did not catch a publish failure without an ::error:: annotation (mutation)');
  const unusedLabel = text.replace("· {1}: {2} (advisory, not blocking)', inputs.profile", "· {1}: PASS (advisory, not blocking)', inputs.profile");
  if (unusedLabel === text || checkVerdictJob(unusedLabel).length === 0) problems.push('the check did not catch a display name that ignores the label (mutation)');
  const plain = text + "\n    name: ${{ format('a: {0}', inputs.profile) }}\n";
  if (checkPlainScalars(plain).length === 0) problems.push("the check did not catch a plain YAML name holding ': ' (mutation)");
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
