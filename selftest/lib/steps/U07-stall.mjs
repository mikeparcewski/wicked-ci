// U07 a stalled run reads stalled (J8, hermetic): the stub's fix turn sits silent and idle (scenario `fix: stall`,
// removed after), like a wedged seat. With the watchdog's threshold at its minimum (1 minute; escalation and the
// silent-turn rung off, so nothing reassigns the unit away), the Nerve Center must call the run stalled, never working.
// EXPECTED-FAIL (F-CREW-1501) while the engine's working heartbeat re-arms crew's watchdog; only the heartbeat's own
// signature (the run, still in its silent turn, read as "working") carries that label.
import { readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { runJourney } from '../journey.mjs';

export const id = 'U07';
export const name = 'a stalled run reads stalled';

const KNOBS = { workerStallMinutes: 1, workerStallEscalateMinutes: 0, workerSilentTurnMinutes: 0 };
const TAG = 'U07: the fix turn will stall';
const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const scenario = join(ctx.L.root, 'scenario.json');
  const marker = join(ctx.L.root, 'stall-started');
  rmSync(marker, { force: true }); // a marker left by an earlier, interrupted run must never stand in for this one
  const got = await api.get('/settings');
  if (got.status !== 200 || typeof got.json?.settings !== 'object') throw new Error(`GET /settings answered ${got.status}: ${got.text.slice(0, 200)}`);
  const before = got.json.settings;
  let journeyErr = null;
  try {
    // Setup, not the person's path: the threshold a person would wait 15 minutes for, shortened to the minimum.
    const set = await api.put('/settings', KNOBS);
    if (set.status !== 200) throw new Error(`PUT /settings for the stall threshold answered ${set.status}: ${set.text.slice(0, 200)}`);
    const now = (await api.get('/settings')).json?.settings ?? {};
    const effective = Object.entries(KNOBS).every(([k, v]) => now[k] === v);
    t.check('the stall knobs are in effect (threshold 1 min, escalation and silent-turn off)', effective, JSON.stringify(Object.fromEntries(Object.keys(KNOBS).map((k) => [k, now[k]]))));
    if (!effective) return;
    writeFileSync(scenario, JSON.stringify({ fix: 'stall', stall_s: 900 }));
    try {
      await runJourney(ctx, t, 'u07_stall_reads_stalled', { state: { stallMarker: marker, tag: TAG } });
    } catch (err) {
      journeyErr = err;
    }
  } finally {
    rmSync(scenario, { force: true });
    // Cleanup is checked, not hoped for: the stalled run would hold its seat for the steps after this one, and the
    // knobs must read as they did. Found by its own words, so a journey that failed after launching still cleans up.
    let launched = null;
    try { launched = JSON.parse(readFileSync(join(t.dir, 'result.json'), 'utf8')).state?.runId ?? null; } catch { /* no result */ }
    const runs = (await api.get('/runs?limit=100')).json?.runs ?? [];
    const mine = runs.filter((r) => (r.session?.id === launched || String(r.session?.problem ?? '').includes(TAG)) && !TERMINAL.has(r.session?.status));
    for (const r of mine) {
      const c = await api.post(`/runs/${r.session.id}/cancel`, {});
      let status = null;
      for (let i = 0; i < 30 && !TERMINAL.has(status); i++) {
        // The run's status as the runs list reports it (the list is what every journey reads too).
        status = ((await api.get('/runs?limit=100')).json?.runs ?? []).find((x) => x.session?.id === r.session.id)?.session?.status ?? null;
        if (!TERMINAL.has(status)) await new Promise((res) => setTimeout(res, 1000));
      }
      t.check(`cleanup: the stalled run ${r.session.id.slice(0, 8)} is cancelled`, c.status >= 200 && c.status < 300 && TERMINAL.has(status), `cancel ${c.status}; status ${status}`);
    }
    const restore = Object.fromEntries(Object.keys(KNOBS).filter((k) => typeof before[k] === 'number').map((k) => [k, before[k]]));
    if (Object.keys(restore).length) {
      const r = await api.put('/settings', restore);
      t.check('cleanup: the stall knobs are restored', r.status === 200, `PUT ${r.status} ${JSON.stringify(restore)}`);
    }
    rmSync(marker, { force: true });
  }
  if (journeyErr) throw journeyErr;
}
