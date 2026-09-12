// S08 chat — OPT-IN in v1 (`--steps S08`). A chat warms its seats over ACP (`opencode acp`,
// `claude-agent-acp`): the v1 seat shims speak only the headless one-shot contract, so a real chat
// turn cannot complete here. What IS asserted: the daemon admits/refuses chat seats through the same
// standing the roster shows (signed-out seats refused by name, F-2R2-009), the open/list/close routes
// answer, and a refused turn is HONEST on the wire (an error body naming the seat/transport, no hang).
// TODO(v2): an ACP-speaking shim (initialize / session.new / prompt) so chatSend receives an answer.
export const id = 'S08';
export const name = 'chat (opt-in)';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const chatId = `smoke-chat-${Date.now().toString(36)}`;
  const t0 = Date.now();
  const open = await api.post('/chats', { chatId, clis: ['codex'] });
  const ev = t.evidence('chat-open-signed-out', { status: open.status, ms: Date.now() - t0, body: open.json ?? open.text?.slice(0, 500) });
  t.check('POST /chats answered (no hang)', open.status !== 0 && Date.now() - t0 < 60_000, `status ${open.status} in ${Date.now() - t0} ms`, { evidence: ev });
  const refusals = JSON.stringify(open.json ?? {});
  t.check('a signed-out seat (codex) is refused BY NAME or the open is an honest error', /codex/.test(refusals) && (/refus|signed out|not logged|unauthori/i.test(refusals) || open.status >= 400), refusals.slice(0, 300), { evidence: ev });
  if (open.status >= 200 && open.status < 300) {
    const list = await api.get(`/chats/${encodeURIComponent(chatId)}`);
    t.check('GET /chats/:id answers', list.status === 200, `status ${list.status}`);
    const close = await api.del(`/chats/${encodeURIComponent(chatId)}`);
    t.check('DELETE /chats/:id answers', close.status >= 200 && close.status < 300, `status ${close.status}`);
  }
  t.info('TODO', 'chatSend with a real answer needs an ACP-speaking shim (v2)');
}
