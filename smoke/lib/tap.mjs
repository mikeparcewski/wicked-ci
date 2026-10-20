// Opt-in wire tap for the e2e certification runner (wicked-ci e2e/): when WICKED_SMOKE_TAP_DIR is set,
// every daemon API call, /ws frame and child-process run the harness makes is appended, one JSON line
// each, to <dir>/{http,ws,cli}.jsonl, stamped with the step that made it (and each step's start to
// steps.jsonl). Unset (the default), nothing
// is written and nothing changes: the smoke's own checks never read the tap.
import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const DIR = process.env.WICKED_SMOKE_TAP_DIR || '';
const CAP = 256 * 1024; // bound one recorded body; the tap is evidence, not a dump
if (DIR) mkdirSync(DIR, { recursive: true });

/** The step now running (set by the harness before each step). */
export function tapStep(stepId) {
  globalThis.__wickedSmokeStep = stepId;
  tap('steps', { start: stepId });
}

function bounded(v) {
  if (v === undefined) return null;
  try {
    const s = JSON.stringify(v);
    return s.length <= CAP ? v : { truncated: true, bytes: s.length, head: s.slice(0, 4096) };
  } catch {
    return null;
  }
}

/** Append one record of `kind` (http | ws | cli). Never throws. */
export function tap(kind, record) {
  if (!DIR) return;
  try {
    const line = JSON.stringify({ step: globalThis.__wickedSmokeStep ?? null, t: Date.now(), ...record, ...(record.res !== undefined ? { res: bounded(record.res) } : {}), ...(record.frame !== undefined ? { frame: bounded(record.frame) } : {}) });
    appendFileSync(join(DIR, `${kind}.jsonl`), line + '\n');
  } catch { /* the tap must never fail a step */ }
}

export const TAPPING = Boolean(DIR);
