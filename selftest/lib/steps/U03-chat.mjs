// U03 chat (J3, shape): a question typed in the studio chat gets an answer beneath it from a named helper; the UI's
// own requests opened the chat and sent the message.
import { runJourney } from '../journey.mjs';

export const id = 'U03';
export const name = 'chat answers under the question';

export async function run(ctx, t) {
  await runJourney(ctx, t, 'u03_chat_answer');
}
