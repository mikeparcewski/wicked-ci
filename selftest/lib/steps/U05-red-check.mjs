// U05 a red check routes somewhere (J5, hermetic): the stub's fix breaks a named test (scenario data, removed after);
// the run stops at a card that names it and offers a way forward, and nothing is delivered.
import { rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { runJourney } from '../journey.mjs';

export const id = 'U05';
export const name = 'a broken test is named on the card';

export async function run(ctx, t) {
  const scenario = join(ctx.L.root, 'scenario.json');
  writeFileSync(scenario, JSON.stringify({ fix: 'break' }));
  try {
    await runJourney(ctx, t, 'u05_red_check_named', { state: { origin: ctx.state.origin ?? null } });
  } finally {
    rmSync(scenario, { force: true });
  }
}
