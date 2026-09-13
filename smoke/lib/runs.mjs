// Run-lifecycle helpers over the daemon API: read a run, its events, wait for a terminal state while
// answering human gates through a callback that receives the gate's KIND (never only its prompt).
import { sleep } from './proc.mjs';

export const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'archived']);

export async function runView(api, runId) {
  const r = await api.get(`/runs/${encodeURIComponent(runId)}`);
  if (r.status !== 200 || !r.json?.run) return null;
  return r.json.run;
}

export async function runEvents(api, runId) {
  const r = await api.get(`/runs/${encodeURIComponent(runId)}/events`);
  if (r.status !== 200) return [];
  return Array.isArray(r.json?.events) ? r.json.events : Array.isArray(r.json) ? r.json : [];
}

/**
 * Why the run paused. core-ts ≥ 0.7.24 says so on the wire — `awaitingHuman.gateKind`: `run_level` |
 * `def` | `deliver` | `terminal` | `escalation` | `failure` | `triage` (additive, review of core#456
 * F7) — and a consumer keys on that, never on the prompt's wording. Older engines carry no kind; for
 * them the LAST-RESORT fallback derives one from the cursor unit's phase and the prompt's opening
 * words, and says so (`source: 'fallback'`) so the caller can refuse to take an irreversible action
 * on a guess.
 */
export function gateKindOf({ events, ord, unitPhase, prompt }) {
  const frames = events.filter((e) => e.type === 'awaitingHuman' && (ord === undefined || e.ord === ord));
  const last = frames[frames.length - 1];
  if (last && typeof last.gateKind === 'string' && last.gateKind !== '') return { kind: last.gateKind, source: 'wire' };
  const p = String(prompt ?? '');
  if (unitPhase === 'deliver') return { kind: 'deliver', source: 'fallback' };
  if (/^Approve unit \d+ before it runs/i.test(p)) return { kind: 'run_level', source: 'fallback' };
  if (/^Approve delivery before unit \d+ runs/i.test(p)) return { kind: 'deliver', source: 'fallback' };
  if (/^Unit \d+ failed|^Unit \d+ verdict is NOT PASS|escalat/i.test(p)) return { kind: 'escalation', source: 'fallback' };
  return { kind: 'unknown', source: 'fallback' };
}

/**
 * Poll until the run is terminal. `onAwaiting(view, record)` is invoked once per distinct gate with
 * `record.kind` / `record.kindSource` filled in; return `'approve'`, `'cancel'`, `'reassign:<cli>'`, or
 * anything else to leave the gate parked. `signal` (AbortSignal) ends the wait early with
 * `timedOut: true, aborted: true`. Returns {view, gates, timedOut}.
 */
export async function waitTerminal(api, runId, { ms = 120_000, every = 500, onAwaiting = null, signal = null } = {}) {
  const deadline = Date.now() + ms;
  const gates = [];
  let lastGateKey = null;
  let view = null;
  while (Date.now() < deadline) {
    if (signal?.aborted) return { view, gates, timedOut: true, aborted: true };
    view = await runView(api, runId);
    if (view === null) { await sleep(every); continue; }
    const status = view.session.status;
    if (TERMINAL.has(status)) return { view, gates, timedOut: false };
    if (status === 'awaiting_human' && onAwaiting) {
      const gate = await api.get(`/runs/${encodeURIComponent(runId)}/gate`);
      // One gate = one decision: the same unit can pause twice (intake, then an escalation after a
      // failed attempt), so the key carries the gate's own identity, not only the cursor.
      const key = `${view.session.unit_ix}:${view.session.attempt}:${gate.json?.receivedAt ?? ''}:${String(gate.json?.prompt ?? '').slice(0, 64)}`;
      if (key !== lastGateKey) {
        lastGateKey = key;
        const unit = view.units.find((u) => u.ord === (view.session.unit_ix ?? 0) + 1) ?? view.units[view.session.unit_ix] ?? null;
        const events = await runEvents(api, runId);
        const { kind, source } = gateKindOf({ events, ord: unit?.ord, unitPhase: phaseOf(unit), prompt: gate.json?.prompt });
        const record = { at: new Date().toISOString(), key, unitIx: view.session.unit_ix, unitId: unit?.id ?? null, unitStatus: unit?.status ?? null, kind, kindSource: source, gate: gate.json ?? gate.text };
        const decision = await onAwaiting(view, record);
        record.decision = decision;
        gates.push(record);
        if (decision === 'approve') {
          const r = await api.post(`/runs/${encodeURIComponent(runId)}/resume`);
          record.resumeStatus = r.status;
          record.resumeBody = r.json ?? r.text?.slice(0, 300);
          await sleep(1000);
        } else if (typeof decision === 'string' && decision.startsWith('reassign:')) {
          // crew's approve-then-reassign in one call (wave 6, F-7R2-007): the gate is approved and
          // the cursor unit re-dispatched to the requested seat.
          const cli = decision.slice('reassign:'.length);
          const r = await api.post(`/runs/${encodeURIComponent(runId)}/reassign`, { cli });
          record.reassignStatus = r.status;
          record.reassignBody = r.json ?? r.text?.slice(0, 300);
          await sleep(1000);
        } else if (decision === 'cancel') {
          const r = await api.post(`/runs/${encodeURIComponent(runId)}/cancel`);
          record.cancelStatus = r.status;
        }
      }
    }
    await sleep(every);
  }
  return { view, gates, timedOut: true };
}

/** The phase id from a unit id like `<run>:fix` (crew's unit ids) — falls back to the raw id. */
export function phaseOf(unit) {
  const id = String(unit?.id ?? '');
  const ix = id.lastIndexOf(':');
  return ix >= 0 ? id.slice(ix + 1) : id;
}

export function eventsOfType(events, type) {
  return events.filter((e) => e.type === type);
}

/** Bounded, serialisable view of a unit for evidence files. */
export function unitDigest(u) {
  return {
    ord: u.ord,
    id: u.id,
    status: u.status,
    assigned_cli: u.assigned_cli ?? null,
    tool_cmd: u.tool_cmd ?? null,
    role: u.role ?? null,
    stage: u.stage ?? null,
    routing: u.routing ?? null,
    denial_reason: u.denial_reason ?? null,
    description: typeof u.description === 'string' ? u.description.slice(0, 300) : null,
  };
}
