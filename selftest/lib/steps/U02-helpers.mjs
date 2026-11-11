// U02 helpers (J2, hermetic half): every stub seat has a row on Helpers and reads as it is (signed in = Ready,
// signed out = Not ready with a way forward on the row).
import { runJourney } from '../journey.mjs';

export const id = 'U02';
export const name = 'helpers read as they are';

export async function run(ctx, t) {
  // The fixture variant this run wrote: whether pi has a credential, and whether S08 enabled the chat seat.
  await runJourney(ctx, t, 'u02_helpers_state', { state: { piCredential: Boolean(ctx.state.piCredential), chatSeat: ctx.state.chatSeat ?? null } });
}
