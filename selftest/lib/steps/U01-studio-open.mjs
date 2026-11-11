// U01 studio open (J1, J8): the Desk and the Nerve Center render from the daemon's own studio bundle, the rail tile's
// tone equals the page, and a service the daemon reports down (no wicked-estate in the hermetic root) reads down.
import { runJourney } from '../journey.mjs';

export const id = 'U01';
export const name = 'studio open (Desk, Nerve Center)';

export async function run(ctx, t) {
  await runJourney(ctx, t, 'u01_studio_open');
}
