// U07 a stalled run reads stalled (J8, hermetic): the stub's fix turn sits silent and idle (scenario `fix: stall`,
// removed after), like a wedged seat. With the watchdog's threshold at its minimum (1 minute; escalation and the
// silent-turn rung off, so nothing reassigns the unit away), the Nerve Center must call the run stalled, never working.
// EXPECTED-FAIL (F-CREW-1501) while the engine's working heartbeat re-arms crew's watchdog.
import { rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { runJourney } from '../journey.mjs';

export const id = 'U07';
export const name = 'a stalled run reads stalled';

const KNOBS = ['workerStallMinutes', 'workerStallEscalateMinutes', 'workerSilentTurnMinutes'];

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const scenario = join(ctx.L.root, 'scenario.json');
  const marker = join(ctx.L.root, 'stall-started');
  const before = (await api.get('/settings')).json ?? {};
  // Setup, not the person's path: the threshold a person would wait 15 minutes for, shortened to the minimum.
  const set = await api.put('/settings', { workerStallMinutes: 1, workerStallEscalateMinutes: 0, workerSilentTurnMinutes: 0 });
  if (set.status !== 200) throw new Error(`PUT /settings for the stall threshold answered ${set.status}: ${set.text.slice(0, 200)}`);
  writeFileSync(scenario, JSON.stringify({ fix: 'stall', stall_s: 900 }));
  let res = null;
  try {
    res = await runJourney(ctx, t, 'u07_stall_reads_stalled', { state: { stallMarker: marker } });
  } finally {
    rmSync(scenario, { force: true });
    rmSync(marker, { force: true });
    // The stalled run would hold its seat for the steps after this one: cancel it, and put the knobs back.
    const rid = res?.state?.runId;
    if (rid) await api.post(`/runs/${rid}/cancel`, {});
    const restore = Object.fromEntries(KNOBS.filter((k) => typeof before[k] === 'number').map((k) => [k, before[k]]));
    if (Object.keys(restore).length) await api.put('/settings', restore);
  }
}
