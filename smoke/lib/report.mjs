// Step execution, assertion collection, PASS / FAIL / EXPECTED-FAIL / UNEXPECTED-PASS classification,
// JSON report and the GitHub step summary. One line per step on stdout; every failing check names its
// evidence file; a labelled check that unexpectedly PASSES is surfaced so the label gets retired.
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const STATUS = { PASS: 'PASS', FAIL: 'FAIL', XFAIL: 'EXPECTED-FAIL', XPASS: 'UNEXPECTED-PASS', SKIP: 'SKIPPED', ERROR: 'ERROR' };

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
   * FAIL — and a PASS is UNEXPECTED-PASS (the label must be retired). `opts.evidence` is a path or
   * short string the operator can follow.
   */
  check(name, ok, detail, opts = {}) {
    const c = { name, ok: Boolean(ok), detail: detail === undefined ? null : String(detail).slice(0, 2000), finding: opts.finding ?? null, evidence: opts.evidence ?? null, expected: null, unexpectedPass: null };
    this.checks.push(c);
    return c;
  }

  info(name, detail) {
    this.notes.push({ name, detail: detail === undefined ? null : String(detail).slice(0, 2000) });
  }
}

/**
 * Classify one step. Precedence: FAIL (an unlabelled failure) > UNEXPECTED-PASS (a labelled check
 * that passed while its finding is still expected to fail — the label is stale, or the product
 * changed) > EXPECTED-FAIL > PASS.
 */
export function classify(trace, policy, stepExpectedFail) {
  let anyFail = false;
  let anyUnexpected = false;
  let anyXpass = false;
  for (const c of trace.checks) {
    const reason = c.finding ? policy.reasonFor(c.finding) : null;
    if (c.ok) {
      if (reason) {
        c.unexpectedPass = reason;
        // A flaky finding's pass is disclosed, not a verdict change (see expect.mjs FLAKY).
        if (typeof policy.isFlaky === 'function' && policy.isFlaky(c.finding)) c.flaky = true;
        else anyXpass = true;
      }
      continue;
    }
    anyFail = true;
    const why = reason || (stepExpectedFail ? 'step listed in --expect-fail-steps' : null);
    if (why) c.expected = why;
    else anyUnexpected = true;
  }
  if (anyUnexpected) return STATUS.FAIL;
  if (anyXpass) return STATUS.XPASS;
  if (anyFail) return STATUS.XFAIL;
  return STATUS.PASS;
}

export function fmtSecs(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Print the one-line verdict + failing / unexpectedly passing checks. */
export function printStep(result, log) {
  const tag = result.status.padEnd(15);
  log(`${result.id} ${result.name.padEnd(28)} ${tag} ${fmtSecs(result.ms)}`);
  for (const c of result.checks) {
    if (c.ok && c.unexpectedPass) {
      if (c.flaky) log(`    ~ ${c.name}: passed this time — ${c.finding} is a timing-dependent class (fails on every unloaded runner); disclosed, not a verdict (${c.detail ?? ''})`);
      else log(`    + ${c.name}: UNEXPECTED-PASS — retire the label (${c.finding}: ${c.unexpectedPass})${c.detail ? ` — ${c.detail}` : ''}`);
      continue;
    }
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
    const notes = [];
    for (const c of s.checks) {
      if (!c.ok) notes.push(`${c.name}${c.expected ? ` (expected: ${c.finding ?? 'step'})` : ' (FAIL)'}`);
      else if (c.unexpectedPass && c.flaky) notes.push(`${c.name} (passed this time — ${c.finding} is timing-dependent)`);
      else if (c.unexpectedPass) notes.push(`${c.name} (UNEXPECTED-PASS — retire ${c.finding})`);
    }
    lines.push(`| ${s.id} | ${s.name} | ${s.status} | ${(s.ms / 1000).toFixed(1)} | ${notes.join('<br>') || (s.error ? s.error.slice(0, 200) : '')} |`);
  }
  if (report.hermetic) {
    lines.push('');
    lines.push(`hermetic scan: ${report.hermetic.ok ? 'clean' : `CHANGED under $HOME: ${report.hermetic.changed.join(', ')}`}`);
  }
  const xpass = report.steps.flatMap((s) => s.checks.filter((c) => c.ok && c.unexpectedPass && !c.flaky).map((c) => `${s.id}: ${c.name} (${c.finding})`));
  if (xpass.length) {
    lines.push('');
    lines.push(`**UNEXPECTED-PASS — retire these labels in \`smoke/lib/expect.mjs\`:** ${xpass.join('; ')}`);
  }
  return lines.join('\n') + '\n';
}

export function writeSummaryIfCi(report) {
  const p = process.env.GITHUB_STEP_SUMMARY;
  if (!p) return;
  try { appendFileSync(p, summaryMarkdown(report)); } catch { /* not fatal */ }
}
