// The PR-CI workflow's advisory contract, checked on its text (no YAML parser: the harness has no dependencies):
// every step before the pack has an `id` (the `steps` context only lists steps with one, so a failed step without it
// would be invisible to the pack's guard and the verdict) and `continue-on-error: ${{ inputs.advisory }}`, the pack
// is skipped when any of them failed, and the verdict reads the same outcomes. Skipped when the workflow is not
// beside the harness (an npm install of the suite).
import { existsSync, readFileSync } from 'node:fs';
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
  return problems;
}

const here = dirname(fileURLToPath(import.meta.url));
const wf = join(here, '..', '..', '.github', 'workflows', 'selftest.yml');
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (!existsSync(wf)) { console.log('workflow selfcheck skipped (no .github/workflows/selftest.yml beside the harness)'); process.exit(0); }
  const problems = checkSelftestWorkflow(readFileSync(wf, 'utf8'));
  // The check must catch what it is for: a setup step stripped of its id is reported.
  const mutated = readFileSync(wf, 'utf8').replace(/\n        id: setup1\n/, '\n');
  if (checkSelftestWorkflow(mutated).length === 0) problems.push('the check did not catch a setup step without an id (mutation)');
  if (problems.length) { console.error(`workflow selfcheck FAILED:\n  ${problems.join('\n  ')}`); process.exit(1); }
  console.log('workflow selfcheck ok');
}
