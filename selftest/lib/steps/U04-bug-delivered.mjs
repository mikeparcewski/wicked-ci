// U04 governed bug, delivered (J4, hermetic): a bug fix launched from New job, steered on its cards and delivered to a
// PR, all through studio. The hermetic roster has one signed-in work CLI, so the engine finds no judge distinct from
// the creator and asks the person: the journey answers those cards with the person's own labelled judgment, the way
// a user with a single signed-in CLI must (the thin-roster path; a second signed-in CLI removes those cards).
import { runJourney } from '../journey.mjs';

export const id = 'U04';
export const name = 'bug fix delivered through studio';

export async function run(ctx, t) {
  await runJourney(ctx, t, 'u04_bug_delivered', { state: { origin: ctx.state.origin ?? null } });
}
