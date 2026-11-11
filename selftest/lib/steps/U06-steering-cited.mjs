// U06 steering applies (J7, hermetic): a rule imported on the Steering page is in force for the next governed run,
// and the run cites it. The journey reads the stub seats' call log for what the engine handed the rule check.
import { runJourney } from '../journey.mjs';

export const id = 'U06';
export const name = 'an imported steering rule is cited';

export async function run(ctx, t) {
  await runJourney(ctx, t, 'u06_steering_cited', { state: { origin: ctx.state.origin ?? null, shimLog: ctx.L.shimLog } });
}
