// U06 steering applies (J7, hermetic): a rule imported on the Steering page is in force for the next governed run,
// and the run cites it. The journey stops at the review's rule-check card; the step then cancels that run (checked),
// so the steps after it never inherit a parked run. The imported rule stays, as any rule a person imports would.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { runJourney } from '../journey.mjs';

export const id = 'U06';
export const name = 'an imported steering rule is cited';

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);
const TAG = 'U06: a steering rule applies'; // in the journey's intent: finds its run when no result names it

export async function run(ctx, t) {
  try {
    await runJourney(ctx, t, 'u06_steering_cited', { state: { origin: ctx.state.origin ?? null, shimLog: ctx.L.shimLog } });
  } finally {
    let launched = null;
    try { launched = JSON.parse(readFileSync(join(t.dir, 'result.json'), 'utf8')).state?.runId ?? null; } catch { /* no result */ }
    const api = ctx.daemon?.child ? ctx.api() : null;
    const listed = api ? await api.get('/runs?limit=100') : null;
    if (listed && listed.status !== 200) t.check('cleanup: the runs list answers (to find the parked run)', false, `GET /runs ${listed.status}`);
    const runs = listed?.json?.runs ?? [];
    const ids = new Set([launched, ...runs.filter((r) => String(r.session?.problem ?? '').includes(TAG)).map((r) => r.session.id)].filter(Boolean));
    for (const rid of api ? ids : []) {
      if (TERMINAL.has(runs.find((r) => r.session?.id === rid)?.session?.status)) continue;
      const c = await api.post(`/runs/${rid}/cancel`, {});
      let status = null;
      for (let i = 0; i < 30 && !TERMINAL.has(status); i++) {
        status = ((await api.get('/runs?limit=100')).json?.runs ?? []).find((x) => x.session?.id === rid)?.session?.status ?? null;
        if (!TERMINAL.has(status)) await new Promise((res) => setTimeout(res, 1000));
      }
      t.check(`cleanup: the parked run ${rid.slice(0, 8)} is cancelled`, c.status >= 200 && c.status < 300 && TERMINAL.has(status), `cancel ${c.status}; status ${status}`);
    }
  }
}
