// S08 chat — the chat wire end to end on a REAL daemon + REAL engine addon + REAL garden snapshot,
// with only the agent shimmed (shims/acp-agent.mjs speaks ACP over stdio; DES-L5 S-CHAT-01). v1 could
// only open/list/close: every seat shim spoke the headless one-shot contract, so `POST /chats` on a
// v1 seat refused at warm-up and a turn could never complete here — which is exactly why
// F-RC1-110 (the unnamed 300 s budget), F-RC1-111 (an evicted seat cannot be re-seated) and
// F-RC1-112 (no transcript) were found live and not by this harness.
//
// What runs, on a daemon restarted with `WICKED_CHAT_TURN_SECS=5` (the budget under test; the
// product reads the variable at call time, so it needs a boot):
//   1. F-2R2-009 (kept from v1): a seat that cannot take a chat turn (codex — signed out, and
//      overlaid without `[cli.acp]`) is refused BY NAME, the open answers honestly (no hang).
//   2. `POST /chats {clis: [acp-smoke]}` → 201, the seat warm; the daemon log carries the
//      "handed skills gen" line (the seat received the published skills snapshot) — F-RC1-113.
//   3. A turn: `POST /chats/:id/messages` → 202 `seats` names the seat; on /ws at least one
//      `chatDelta` then a `chatReply {ok: true}` for it; the shim log shows the turn reached it over
//      ACP (`session/prompt`); the reply carries `usage` — F-RC1-116; `GET /chats/:id.messages` has
//      the user message + the seat reply — F-RC1-112.
//   4. Budget: a turn whose prompt makes the shim sleep 20 s → `chatReply {ok: false}` within the
//      5 s budget (+ grace), naming the seat; the text names the budget variable and the re-seat
//      remedy — F-RC1-110; the seat is gone from `GET /chats/:id.seats` (evicted).
//   5. Re-seat: the next send with `targets: [acp-smoke]` → 202 `seats` includes it again and an
//      `ok: true` `chatReply` follows (the engine re-warms on the next ensure; F-RC1-111 is the
//      studio never sending `targets` — asserted at the wire it must send).
//   6. `DELETE /chats/:id` → 2xx, `chatClosed {reason: "requested"}` on /ws, `GET /chats/:id` reads
//      `seats: []` and `messages: []` (the transcript goes with the chat) — F-RC1-112.
// Labels (`lib/expect.mjs`) carry the checks the PUBLISHED set is known to fail; everything else must
// pass today. Real crew, real core-ts napi, real garden snapshot (S02) — only the agent is a shim.
import { ACP_SEAT_KEY } from '../shims.mjs';
import { openFrames } from '../ws.mjs';

export const id = 'S08';
export const name = 'chat';

/** The per-turn budget the daemon is booted with for this step (seconds). */
export const CHAT_TURN_SECS = 5;
/** How long the slow prompt makes the shim sleep — comfortably past the budget on a loaded host. */
const SLOW_TURN_SLEEP_MS = 20_000;
/** Grace over the budget before a missing budget cut is a failure (spawn + eviction on a slow host). */
const BUDGET_GRACE_MS = 15_000;

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  // The budget is read from the daemon's environment at turn time — a boot with the knob set is the
  // only way to make a 5 s budget observable; the same daemon then serves every case below.
  await ctx.daemon.restart({ extraEnv: { WICKED_CHAT_TURN_SECS: String(CHAT_TURN_SECS) } });
  t.info('daemon', `restarted with WICKED_CHAT_TURN_SECS=${CHAT_TURN_SECS} (start #${ctx.daemon.starts}, ${ctx.daemon.bootMs} ms to healthy)`);
  const api = ctx.api();
  const enc = encodeURIComponent;
  const ws = await openFrames(ctx.daemon.origin);
  try {
    // ── 1. F-2R2-009: a seat that cannot take a turn is refused by name, honestly ──
    {
      const chatId = `smoke-chat-refused-${Date.now().toString(36)}`;
      const t0 = Date.now();
      const open = await api.post('/chats', { chatId, clis: ['codex'] });
      const ev = t.evidence('chat-open-signed-out', { status: open.status, ms: Date.now() - t0, body: open.json ?? open.text?.slice(0, 500) });
      t.check('POST /chats {clis:[codex]} answered (no hang)', open.status !== 0 && Date.now() - t0 < 60_000, `status ${open.status} in ${Date.now() - t0} ms`, { evidence: ev });
      const refusals = JSON.stringify(open.json ?? {});
      t.check('a seat that cannot take a turn (codex) is refused BY NAME or the open is an honest error (F-2R2-009 class)', /codex/.test(refusals) && (/refus|signed out|not logged|unauthori|no ACP config/i.test(refusals) || open.status >= 400), refusals.slice(0, 300), { evidence: ev });
      if (open.status >= 200 && open.status < 300) await api.del(`/chats/${enc(chatId)}`);
    }

    // ── 2. Open on the ACP seat ──
    const chatId = `smoke-chat-${Date.now().toString(36)}`;
    const logBefore = ctx.daemon.logOffset();
    const t0 = Date.now();
    const open = await api.post('/chats', { chatId, clis: [ACP_SEAT_KEY] });
    const openMs = Date.now() - t0;
    const seats = Array.isArray(open.json?.seats) ? open.json.seats : [];
    const evOpen = t.evidence('chat-open-acp', { status: open.status, ms: openMs, body: open.json ?? open.text?.slice(0, 800) });
    t.check(`POST /chats {clis:[${ACP_SEAT_KEY}]} → 201`, open.status === 201, `status ${open.status} in ${openMs} ms: ${JSON.stringify(open.json ?? open.text).slice(0, 300)}`, { evidence: evOpen });
    const warm = seats.find((s) => s.cliKey === ACP_SEAT_KEY);
    t.check(`${ACP_SEAT_KEY} warmed over ACP (seats[].ok == true, refused: [])`, warm?.ok === true && (open.json?.refused ?? []).length === 0, `seats ${JSON.stringify(seats).slice(0, 300)}; refused ${JSON.stringify(open.json?.refused ?? null).slice(0, 300)}`, { evidence: evOpen });
    const acpCalls = () => ctx.shimCalls().filter((c) => c.shim === 'acp-agent');
    const handshake = acpCalls().filter((c) => c.acp === 'initialize' || c.acp === 'session/new');
    t.check('the shim saw the ACP handshake (initialize + session/new recorded in shim-calls.ndjson)', handshake.some((c) => c.acp === 'initialize') && handshake.some((c) => c.acp === 'session/new'), `${handshake.length} handshake record(s): ${handshake.map((c) => c.acp).join(', ') || 'none'}`);
    // DES-L5 §4: `chat <id> seat <cli> handed skills gen <gen> <hash>` — the seat receives the
    // published snapshot like a work unit does (today: SkillsDelivery::None, wicked-core #487).
    const handed = ctx.daemon.grepLog(/handed skills gen/, logBefore, 5);
    t.check(`daemon log: chat seat handed the published skills snapshot ("handed skills gen", F-RC1-113)`, handed.length >= 1, handed[0] ?? 'no "handed skills gen" line since the open', { finding: 'F-RC1-113', evidence: evOpen });
    if (open.status !== 201 || warm?.ok !== true) {
      t.info('skipped', 'the turn / budget / re-seat / close cases need a warm ACP seat — see the open above');
      return;
    }

    // ── 3. One turn: 202, deltas, an ok reply with usage; the transcript on GET ──
    const isReply = (f) => f?.type === 'chatReply' && f.chat === chatId && f.cliKey === ACP_SEAT_KEY;
    const isDelta = (f) => f?.type === 'chatDelta' && f.chat === chatId && f.cliKey === ACP_SEAT_KEY;
    {
      const sent = Date.now();
      const send = await api.post(`/chats/${enc(chatId)}/messages`, { text: 'wicked-smoke: say hello (turn 1)' });
      t.check('POST /chats/:id/messages → 202 with seats naming the seat', send.status === 202 && Array.isArray(send.json?.seats) && send.json.seats.includes(ACP_SEAT_KEY), `status ${send.status}: ${JSON.stringify(send.json ?? send.text).slice(0, 200)}`);
      const reply = await ws.waitFor(isReply, { ms: 60_000, signal: ctx.signal });
      const replyMs = Date.now() - sent;
      const deltas = ws.frames.filter(isDelta);
      const prompts = acpCalls().filter((c) => c.acp === 'session/prompt');
      const ev = t.evidence('chat-turn-1', { send: send.json ?? send.text, replyMs, reply, deltaCount: deltas.length, shimPrompts: prompts });
      t.check('a chatReply for the seat arrived on /ws', reply !== null, reply ? `in ${replyMs} ms` : `no chatReply within 60 s (${ws.frames.length} frames seen)`, { evidence: ev });
      t.check('chatReply.ok == true with a non-empty text', reply?.ok === true && typeof reply?.text === 'string' && reply.text.trim().length > 0, `ok ${reply?.ok}; text ${JSON.stringify(reply?.text ?? null).slice(0, 200)}`, { evidence: ev });
      t.check('at least one chatDelta streamed before the reply', deltas.length >= 1, `${deltas.length} delta frame(s)`, { evidence: ev });
      t.check('the turn reached the shim over ACP (session/prompt recorded)', prompts.length >= 1, `${prompts.length} session/prompt record(s)`, { evidence: ev });
      // DES-L5 §4: `chatReply.usage: {inputTokens, outputTokens, …} | null` — the shim reports usage
      // on the prompt result, so a wired daemon carries numbers here (today: no field, F-RC1-116).
      const usage = reply?.usage;
      t.check('chatReply carries usage {inputTokens, outputTokens} (F-RC1-116)', usage !== null && typeof usage === 'object' && Number.isFinite(usage?.inputTokens) && Number.isFinite(usage?.outputTokens), `usage ${JSON.stringify(usage ?? null).slice(0, 200)}`, { finding: 'F-RC1-116', evidence: ev });
      const detail = await api.get(`/chats/${enc(chatId)}`);
      const messages = detail.json?.messages;
      const ev2 = t.evidence('chat-detail-after-turn-1', { status: detail.status, body: detail.json ?? detail.text?.slice(0, 800) });
      t.check('GET /chats/:id → 200 with the seat warm', detail.status === 200 && Array.isArray(detail.json?.seats) && detail.json.seats.includes(ACP_SEAT_KEY), `status ${detail.status}; seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev2 });
      t.check('GET /chats/:id.messages holds the user message + the seat reply (2 records, F-RC1-112)', Array.isArray(messages) && messages.length === 2 && messages.some((m) => m.kind === 'user') && messages.some((m) => m.kind === 'seat' && m.cliKey === ACP_SEAT_KEY), Array.isArray(messages) ? `${messages.length} record(s): ${messages.map((m) => m.kind).join(', ')}` : `messages ${JSON.stringify(messages ?? null)} (absent on a daemon without the transcript)`, { finding: 'F-RC1-112', evidence: ev2 });
    }

    // ── 4. The turn budget: a slow seat is cut at WICKED_CHAT_TURN_SECS and released ──
    const repliesBefore = ws.frames.filter(isReply).length;
    {
      const sent = Date.now();
      const send = await api.post(`/chats/${enc(chatId)}/messages`, { text: `wicked-smoke: take your time — smoke-acp-sleep-ms=${SLOW_TURN_SLEEP_MS} — then answer (turn 2)` });
      t.check('slow turn: POST /chats/:id/messages → 202', send.status === 202, `status ${send.status}: ${JSON.stringify(send.json ?? send.text).slice(0, 200)}`);
      const reply = await ws.waitFor((f) => isReply(f) && ws.frames.filter(isReply).length > repliesBefore, { ms: SLOW_TURN_SLEEP_MS + 30_000, signal: ctx.signal });
      const replyMs = Date.now() - sent;
      const ev = t.evidence('chat-turn-budget', { budgetSecs: CHAT_TURN_SECS, shimSleepMs: SLOW_TURN_SLEEP_MS, send: send.json ?? send.text, replyMs, reply });
      t.check(`the ${CHAT_TURN_SECS} s turn budget cut the slow turn: chatReply {ok:false} before the shim's ${SLOW_TURN_SLEEP_MS / 1000} s answer`, reply !== null && reply.ok === false && replyMs < SLOW_TURN_SLEEP_MS, reply ? `ok ${reply.ok} in ${replyMs} ms` : `no chatReply within ${(SLOW_TURN_SLEEP_MS + 30_000) / 1000} s`, { evidence: ev });
      t.check(`the cut arrived within budget + grace (≤ ${(CHAT_TURN_SECS * 1000 + BUDGET_GRACE_MS) / 1000} s)`, reply !== null && replyMs <= CHAT_TURN_SECS * 1000 + BUDGET_GRACE_MS, `${replyMs} ms`, { evidence: ev });
      t.check('the failure names the seat', typeof reply?.text === 'string' && reply.text.includes(ACP_SEAT_KEY), JSON.stringify(reply?.text ?? null).slice(0, 300), { evidence: ev });
      // DES-L5 §4: "seat '<cli>' exceeded the <N> s turn budget (WICKED_CHAT_TURN_SECS) and was
      // released — target it on your next message to re-seat it. …" (today: "turn ended TimedOut").
      t.check('the failure names the budget (WICKED_CHAT_TURN_SECS) and the re-seat remedy (F-RC1-110)', typeof reply?.text === 'string' && /turn budget \(WICKED_CHAT_TURN_SECS\)/.test(reply.text) && /re-seat/i.test(reply.text), JSON.stringify(reply?.text ?? null).slice(0, 300), { finding: 'F-RC1-110', evidence: ev });
      const detail = await api.get(`/chats/${enc(chatId)}`);
      t.check('the cut seat was released: GET /chats/:id.seats no longer lists it', detail.status === 200 && Array.isArray(detail.json?.seats) && !detail.json.seats.includes(ACP_SEAT_KEY), `status ${detail.status}; seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev });
    }

    // ── 5. Re-seat by targeting the released seat on the next send ──
    {
      const before = ws.frames.filter(isReply).length;
      const sent = Date.now();
      const send = await api.post(`/chats/${enc(chatId)}/messages`, { text: 'wicked-smoke: hello again (turn 3, re-seat)', targets: [ACP_SEAT_KEY] });
      const ev0 = t.evidence('chat-turn-reseat-send', { status: send.status, body: send.json ?? send.text?.slice(0, 500) });
      t.check('re-seat: POST /chats/:id/messages {targets:[seat]} → 202 with seats including the released seat', send.status === 202 && Array.isArray(send.json?.seats) && send.json.seats.includes(ACP_SEAT_KEY), `status ${send.status}: ${JSON.stringify(send.json ?? send.text).slice(0, 200)}`, { evidence: ev0 });
      const reply = await ws.waitFor((f) => isReply(f) && ws.frames.filter(isReply).length > before, { ms: 60_000, signal: ctx.signal });
      const replyMs = Date.now() - sent;
      const ev = t.evidence('chat-turn-reseat', { replyMs, reply });
      t.check('re-seat: an ok chatReply follows (the seat re-warmed on the next ensure)', reply?.ok === true, reply ? `ok ${reply.ok} in ${replyMs} ms: ${JSON.stringify(reply.text).slice(0, 160)}` : 'no chatReply within 60 s', { evidence: ev });
      const detail = await api.get(`/chats/${enc(chatId)}`);
      t.check('re-seat: GET /chats/:id.seats lists the seat again', detail.status === 200 && Array.isArray(detail.json?.seats) && detail.json.seats.includes(ACP_SEAT_KEY), `seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev });
    }

    // ── 6. Close: chatClosed on /ws, seats and transcript gone ──
    {
      const t1 = Date.now();
      const close = await api.del(`/chats/${enc(chatId)}`);
      t.check('DELETE /chats/:id → 2xx', close.status >= 200 && close.status < 300, `status ${close.status}`);
      const closed = await ws.waitFor((f) => f?.type === 'chatClosed' && f.chat === chatId, { ms: 20_000, signal: ctx.signal });
      const ev = t.evidence('chat-close', { status: close.status, ms: Date.now() - t1, closed });
      t.check('chatClosed {reason: "requested"} on /ws', closed !== null && closed.reason === 'requested', closed ? `reason ${closed.reason} in ${Date.now() - t1} ms` : 'no chatClosed within 20 s', { evidence: ev });
      const detail = await api.get(`/chats/${enc(chatId)}`);
      const ev2 = t.evidence('chat-detail-after-close', { status: detail.status, body: detail.json ?? detail.text?.slice(0, 500) });
      t.check('after close: GET /chats/:id.seats == []', detail.status === 200 && Array.isArray(detail.json?.seats) && detail.json.seats.length === 0, `status ${detail.status}; seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev2 });
      t.check('after close: GET /chats/:id.messages == [] (the transcript goes with the chat, F-RC1-112)', Array.isArray(detail.json?.messages) && detail.json.messages.length === 0, `messages ${JSON.stringify(detail.json?.messages ?? null).slice(0, 200)}`, { finding: 'F-RC1-112', evidence: ev2 });
    }
    t.evidence('ws-chat-frames', ws.frames.filter((f) => typeof f?.type === 'string' && f.type.startsWith('chat')).slice(0, 400));
    t.info('turn timings', `see evidence chat-turn-1 / chat-turn-budget / chat-turn-reseat (replyMs) — DES-L5 §8 re-derives the budget from per-turn totals`);
  } finally {
    ws.close();
  }
}
