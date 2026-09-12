// Step execution, assertion collection, PASS/FAIL/EXPECTED-FAIL classification, JSON report and the
// GitHub step summary. One line per step on stdout; every failing check names its evidence file.
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const STATUS = { PASS: 'PASS', FAIL: 'FAIL', XFAIL: 'EXPECTED-FAIL', SKIP: 'SKIPPED', ERROR: 'ERROR' };

/** Collects one step's checks + evidence. */
export class StepTrace {
  constructor(stepId, evidenceRoot, log) {
    this.stepId = stepId;
    this.dir = join(evidenceRoot, stepId);
    mkdirSync(this.dir, { recursive: true });
    this.log = log;
    this.checks = [];
    this.notes = [];
    this.evidenceFiles = [];
  }

  /** Write a JSON evidence file; returns its path. */
  evidence(name, obj) {
    const p = join(this.dir, `${name}.json`);
    writeFileSync(p, typeof obj === 'string' ? obj : JSON.stringify(obj, null, 1));
    this.evidenceFiles.push(p);
    return p;
  }

  /**
   * One assertion. `opts.finding` names the acceptance finding this check detects; when the run's
   * expected-fail policy lists that finding, a failure is EXPECTED-FAIL (reason attached) rather than
   * FAIL. `opts.evidence` is a path or short string the operator can follow.
   */
  check(name, ok, detail, opts = {}) {
    const c = { name, ok: Boolean(ok), detail: detail === undefined ? null : String(detail).slice(0, 2000), finding: opts.finding ?? null, evidence: opts.evidence ?? null, expected: null };
    this.checks.push(c);
    return c;
  }

  info(name, detail) {
    this.notes.push({ name, detail: detail === undefined ? null : String(detail).slice(0, 2000) });
  }
}

/** The result of one step after classification. */
export function classify(trace, policy, stepExpectedFail) {
  let anyFail = false;
  let anyUnexpected = false;
  for (const c of trace.checks) {
    if (c.ok) continue;
    anyFail = true;
    const reason = (c.finding && policy.reasonFor(c.finding)) || (stepExpectedFail ? `step listed in --expect-fail-steps` : null);
    if (reason) c.expected = reason;
    else anyUnexpected = true;
  }
  if (!anyFail) return STATUS.PASS;
  return anyUnexpected ? STATUS.FAIL : STATUS.XFAIL;
}

export function fmtSecs(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Print the one-line verdict + failing checks. */
export function printStep(result, log) {
  const tag = result.status.padEnd(13);
  log(`${result.id} ${result.name.padEnd(28)} ${tag} ${fmtSecs(result.ms)}`);
  for (const c of result.checks) {
    if (c.ok) continue;
    const label = c.expected ? `expected-fail (${c.finding ?? 'step'}: ${c.expected})` : 'FAIL';
    log(`    - ${c.name}: ${label}${c.detail ? ` — ${c.detail}` : ''}${c.evidence ? ` [${c.evidence}]` : ''}`);
  }
  if (result.error) log(`    ! ${result.error}`);
}

/** Markdown for $GITHUB_STEP_SUMMARY. */
export function summaryMarkdown(report) {
  const lines = [];
  lines.push(`## wicked-smoke — ${report.overall} (${fmtSecs(report.wallMs)})`);
  lines.push('');
  lines.push(`crew ${report.versions.crew} · core-ts ${report.versions.coreTs} · bus ${report.versions.bus} · garden ${report.versions.garden} · studio bundle ${report.versions.studioBundle ?? 'n/a'} · ${report.host.platform}/${report.host.arch} node ${report.host.node}`);
  lines.push('');
  lines.push('| step | name | status | secs | notes |');
  lines.push('|---|---|---|---|---|');
  for (const s of report.steps) {
    const failing = s.checks.filter((c) => !c.ok).map((c) => `${c.name}${c.expected ? ` (expected: ${c.finding ?? 'step'})` : ''}`);
    lines.push(`| ${s.id} | ${s.name} | ${s.status} | ${(s.ms / 1000).toFixed(1)} | ${failing.join('<br>') || (s.error ? s.error.slice(0, 200) : '')} |`);
  }
  if (report.hermetic) {
    lines.push('');
    lines.push(`hermetic scan: ${report.hermetic.ok ? 'clean' : `CHANGED under $HOME: ${report.hermetic.changed.join(', ')}`}`);
  }
  return lines.join('\n') + '\n';
}

export function writeSummaryIfCi(report) {
  const p = process.env.GITHUB_STEP_SUMMARY;
  if (!p) return;
  try { appendFileSync(p, summaryMarkdown(report)); } catch { /* not fatal */ }
}
