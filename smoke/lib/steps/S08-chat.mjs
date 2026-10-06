// S08 chat — the chat wire end to end on a REAL daemon + REAL engine addon + REAL garden snapshot,
// with only the agent shimmed (shims/acp-agent.mjs speaks ACP over stdio; DES-L5 S-CHAT-01). v1 could
// only open/list/close: every seat shim spoke the headless one-shot contract, so `POST /chats` on a
// v1 seat refused at warm-up and a turn could never complete here — which is exactly why
// F-RC1-110 (the unnamed 300 s budget), F-RC1-111 (an evicted seat cannot be re-seated) and
// F-RC1-112 (no transcript) were found live and not by this harness.
//
// TWO WIRES. From crew 0.8.2 an ask is a team PATH (DES-ASK-TEAM-CHAT-001, DES-STUDIO-REBUILD-001
// Amendment 6): `POST /chats` warms nothing and admits the default roster and the seats NAMED in
// `clis` by ONE rule (`chatSeatAdmission` — a council-disabled seat takes no turn, and the engine's
// roster does not even list one), the FIRST message launches a run whose `understand` step
// `answer-1` the engine dispatches to the primary agent over ACP (a step that `executes_code:false`
// needs `acp_input_governance = true` on the seat's `[cli.acp]`, or the engine refuses the unit),
// every later message is `answer-N`, the reply is ONE stamped `chatReply{run_id, ord}` folded from the
// unit's output by the ask relay, a send during a turn is 409 `turn_in_flight`, and End (`DELETE`)
// cancels the path (`chatClosed{reason:"closed"}`, the run `cancelled`). The per-turn budget is the
// step's `budget_secs` (crew's ASK_TURN_BUDGET_SECS, 600 s) — `WICKED_CHAT_TURN_SECS` cuts a POOL
// turn, not a path step, so the 5 s budget / eviction / re-seat cases below are the < 0.8.2 wire's
// and the ≥ 0.8.2 wire asserts what replaced them. The pool wire's daemon is restarted with
// `WICKED_CHAT_TURN_SECS=5` (the product reads the variable at call time, so it needs a boot); the
// path wire's is restarted with the defaults — crew's turn index still derives a turn's STALENESS
// from that knob (crew #826), so a 5 s boot would un-stamp the 20 s step below — and the restart
// picks up the council-enabled overlay either way.
//
// < 0.8.2 (the pool wire):
//   1. F-2R2-009 (kept from v1): a seat that cannot take a chat turn (codex — signed out, and
//      overlaid without `[cli.acp]`) is refused BY NAME, the open answers honestly (no hang).
//   2. `POST /chats {clis: [acp-smoke]}` → 201, the seat warm; the daemon log carries the
//      "handed skills gen" line (the seat received the published skills snapshot) — F-RC1-113.
//   3. A turn: `POST /chats/:id/messages` → 202 `seats` names the seat; on /ws at least one
//      `chatDelta` then a `chatReply {ok: true}` for it; the shim log shows the turn reached it over
//      ACP (`session/prompt`); the reply carries `usage` — F-RC1-116; `GET /chats/:id.messages` has
//      the user message + the seat reply, one each (derived records — `citations`, `decisions`,
//      `system` — may sit beside them) — F-RC1-112.
//   4. Budget: a turn whose prompt makes the shim sleep 20 s → `chatReply {ok: false}` within the
//      5 s budget (+ grace), naming the seat; the text names the budget variable and the re-seat
//      remedy — F-RC1-110; the seat is gone from `GET /chats/:id.seats` (evicted).
//   5. Re-seat: the next send with `targets: [acp-smoke]` → 202 `seats` includes it again and an
//      `ok: true` `chatReply` follows (the engine re-warms on the next ensure; F-RC1-111 is the
//      studio never sending `targets` — asserted at the wire it must send).
//   6. `DELETE /chats/:id` → 2xx, `chatClosed {reason: "requested"}` on /ws, `GET /chats/:id` reads
//      `seats: []` and `messages: []` (the transcript goes with the chat) — F-RC1-112.
// ≥ 0.8.2 (the path wire):
//   1. as above (the admission rule now refuses or admits by name; the open still answers).
//   2. `POST /chats {clis: [acp-smoke]}` → 201 `seats[].ok`, nothing refused, `singleSeat` disclosed
//      (one eligible seat), `path: null` — and NO ACP traffic yet (nothing warms at open).
//   3. The first message → 202 `{seats, turnId, runId, stepId: "answer-1"}`; `GET /chats/:id.path`
//      names that run with `pa: acp-smoke`; on /ws ≥ 1 `chatDelta` then ONE `chatReply{ok: true,
//      run_id, ord, turn_id}` for the PA; the shim saw the ACP handshake AND `session/prompt`; the
//      run's events show the step on the ACP carrier for the seat (`acpSessionStarted`) and its
//      answer captured (the skills snapshot is handed per seat LEVER — a synthetic seat has none, so
//      `skillsSnapshotHanded` is disclosed, not asserted); the transcript has the user message + the
//      PA's reply, one each; `usage` on the path reply is a tracked finding (F-A6-USAGE, below).
//   4. In flight: a slow turn (the shim sleeps 20 s) → 202 `answer-2`; a send DURING it → 409
//      `turn_in_flight` naming the seat and the turn; the slow reply then lands `ok: true` AFTER the
//      sleep (the 5 s pool budget did not cut a path step — disclosed as info); the seat stays.
//   5. Follow-up: the next send → 202 `stepId: "answer-3"`, an `ok: true` reply, and the path's
//      `stepId` moved with it.
//   6. End: `DELETE /chats/:id` → 2xx, `chatClosed {reason: "closed"}`, `seats: []`, `messages: []`,
//      and the run reads `cancelled` (End cancels the path).
// Labels (`lib/expect.mjs`) carry the checks the PUBLISHED set is known to fail; everything else must
// pass today. Real crew, real core-ts napi, real garden snapshot (S02) — only the agent is a shim.
import { gte } from '../semver.mjs';
import { ACP_SEAT_KEY, writeCouncilOverlay } from '../shims.mjs';
import { openFrames } from '../ws.mjs';

export const id = 'S08';
export const name = 'chat';

/** Every transcript record kind crew serves (`ChatTranscriptRecord`): the turn's own two, and the derived ones. */
const TRANSCRIPT_KINDS = new Set(['user', 'seat', 'citations', 'decisions', 'system']);
/** The per-turn budget the daemon is booted with for this step (seconds). */
export const CHAT_TURN_SECS = 5;
/** How long the slow prompt makes the shim sleep — comfortably past the budget on a loaded host. */
const SLOW_TURN_SLEEP_MS = 20_000;
/** Grace over the budget before a missing budget cut is a failure (spawn + eviction on a slow host). */
const BUDGET_GRACE_MS = 15_000;
/** The first crew whose ask is a team path (ASK-C1/C2); the chat wire changed shape with it. */
export const ASK_PATH_CREW = '0.8.2';
/** How long a path turn may take on a loaded host: the shim answers at once, the engine's dispatch,
 *  ACP session and fold ride the daemon's 2 s bus poll — generous, never a second clock. */
const PATH_TURN_MS = 120_000;

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const askWire = Boolean(ctx.versions.crew && gte(ctx.versions.crew, ASK_PATH_CREW));
  if (askWire) {
    // The admission rule of the path wire refuses a council-disabled seat, so the seat this step
    // speaks to is re-written council-enabled before the restart below (S04's roster is untouched:
    // S08 is the last step that convenes a seat).
    const overlay = writeCouncilOverlay(ctx.L, { acpSeatForCouncil: true });
    t.info('overlay', `crew ${ctx.versions.crew} ≥ ${ASK_PATH_CREW} (an ask is a team path): council overlay re-written with ${ACP_SEAT_KEY} enabled_for_council = true (${overlay})`);
  }
  // Pool wire: the budget is read from the daemon's environment at turn time — a boot with the knob
  // set is the only way to make a 5 s budget observable; the same daemon then serves every case
  // below. Path wire: the knob bounds no path step, but crew's turn index still derives its
  // STALENESS from it (3 × WICKED_CHAT_TURN_SECS; `chatTurnStaleAfterMs`) — booted with 5 s, a 20 s
  // step's reply arrives unstamped and is never persisted (crew #826) — so the path wire boots with
  // the daemon's defaults (the restart still picks up the council-enabled overlay above).
  await ctx.daemon.restart(askWire ? {} : { extraEnv: { WICKED_CHAT_TURN_SECS: String(CHAT_TURN_SECS) } });
  t.info('daemon', `restarted ${askWire ? 'with the daemon defaults (the path wire reads no WICKED_CHAT_TURN_SECS budget)' : `with WICKED_CHAT_TURN_SECS=${CHAT_TURN_SECS}`} (start #${ctx.daemon.starts}, ${ctx.daemon.bootMs} ms to healthy); wire: ${askWire ? 'path (crew ≥ 0.8.2)' : 'pool (crew < 0.8.2)'}`);
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
    const acpCalls = () => ctx.shimCalls().filter((c) => c.shim === 'acp-agent');
    const acpCallsBeforeOpen = acpCalls().length;
    const t0 = Date.now();
    const open = await api.post('/chats', { chatId, clis: [ACP_SEAT_KEY] });
    const openMs = Date.now() - t0;
    const seats = Array.isArray(open.json?.seats) ? open.json.seats : [];
    const evOpen = t.evidence('chat-open-acp', { status: open.status, ms: openMs, body: open.json ?? open.text?.slice(0, 800) });
    t.check(`POST /chats {clis:[${ACP_SEAT_KEY}]} → 201`, open.status === 201, `status ${open.status} in ${openMs} ms: ${JSON.stringify(open.json ?? open.text).slice(0, 300)}`, { evidence: evOpen });
    const warm = seats.find((s) => s.cliKey === ACP_SEAT_KEY);
    t.check(`${ACP_SEAT_KEY} ${askWire ? 'admitted' : 'warmed over ACP'} (seats[].ok == true, refused: [])`, warm?.ok === true && (open.json?.refused ?? []).length === 0, `seats ${JSON.stringify(seats).slice(0, 300)}; refused ${JSON.stringify(open.json?.refused ?? null).slice(0, 300)}`, { evidence: evOpen });
    if (askWire) {
      // Nothing warms at open on the path wire: the seat is spoken to by the run the first message
      // launches. Asserted here so a daemon that silently went back to warming pools is caught.
      // `path` is ABSENT until the first message launches the run (`ChatDetailResponse.path?`).
      const detail0 = await api.get(`/chats/${enc(chatId)}`);
      t.check('path wire: the open warmed nothing (no ACP call since the open; GET /chats/:id carries no path yet)', acpCalls().length === acpCallsBeforeOpen && detail0.status === 200 && (detail0.json?.path === undefined || detail0.json?.path === null), `${acpCalls().length - acpCallsBeforeOpen} ACP call(s) since the open; path ${JSON.stringify(detail0.json?.path ?? null)}`, { evidence: evOpen });
      t.check('path wire: a one-seat chat is disclosed (singleSeat.degraded == true, warmed == the seat)', open.json?.singleSeat?.degraded === true && open.json?.singleSeat?.warmed === ACP_SEAT_KEY, `singleSeat ${JSON.stringify(open.json?.singleSeat ?? null).slice(0, 300)}`, { evidence: evOpen });
    } else {
      const handshake = acpCalls().filter((c) => c.acp === 'initialize' || c.acp === 'session/new');
      t.check('the shim saw the ACP handshake (initialize + session/new recorded in shim-calls.ndjson)', handshake.some((c) => c.acp === 'initialize') && handshake.some((c) => c.acp === 'session/new'), `${handshake.length} handshake record(s): ${handshake.map((c) => c.acp).join(', ') || 'none'}`);
      // DES-L5 §4: `chat <id> seat <cli> handed skills gen <gen> <hash>` — the seat receives the
      // published snapshot like a work unit does (today: SkillsDelivery::None, wicked-core #487).
      const handed = ctx.daemon.grepLog(/handed skills gen/, logBefore, 5);
      t.check(`daemon log: chat seat handed the published skills snapshot ("handed skills gen", F-RC1-113)`, handed.length >= 1, handed[0] ?? 'no "handed skills gen" line since the open', { finding: 'F-RC1-113', evidence: evOpen });
    }
    if (open.status !== 201 || warm?.ok !== true) {
      t.info('skipped', `the turn / ${askWire ? 'in-flight / follow-up / end' : 'budget / re-seat / close'} cases need an admitted ACP seat — see the open above`);
      return;
    }

    // ── 3. One turn: 202, deltas, an ok reply; the transcript on GET ──
    const isReply = (f) => f?.type === 'chatReply' && f.chat === chatId && f.cliKey === ACP_SEAT_KEY;
    const isDelta = (f) => f?.type === 'chatDelta' && f.chat === chatId && f.cliKey === ACP_SEAT_KEY;
    let runId = null;
    {
      const sent = Date.now();
      const send = await api.post(`/chats/${enc(chatId)}/messages`, { text: 'wicked-smoke: say hello (turn 1)' });
      t.check('POST /chats/:id/messages → 202 with seats naming the seat', send.status === 202 && Array.isArray(send.json?.seats) && send.json.seats.includes(ACP_SEAT_KEY), `status ${send.status}: ${JSON.stringify(send.json ?? send.text).slice(0, 200)}`);
      if (askWire) {
        runId = typeof send.json?.runId === 'string' ? send.json.runId : null;
        t.check('path wire: the first message launched the path — 202 carries {turnId, runId, stepId: "answer-1"}', typeof send.json?.turnId === 'string' && runId !== null && send.json?.stepId === 'answer-1', JSON.stringify({ turnId: send.json?.turnId, runId, stepId: send.json?.stepId }), { evidence: t.evidence('chat-turn-1-send', send.json ?? send.text) });
        const path = (await api.get(`/chats/${enc(chatId)}`)).json?.path;
        t.check(`path wire: GET /chats/:id.path names the run with pa == ${ACP_SEAT_KEY}`, path?.runId === runId && path?.pa === ACP_SEAT_KEY && path?.stepId === 'answer-1', `path ${JSON.stringify(path ?? null).slice(0, 300)}`);
      }
      const reply = await ws.waitFor(isReply, { ms: askWire ? PATH_TURN_MS : 60_000, signal: ctx.signal });
      const replyMs = Date.now() - sent;
      const deltas = ws.frames.filter(isDelta);
      const prompts = acpCalls().filter((c) => c.acp === 'session/prompt');
      const ev = t.evidence('chat-turn-1', { send: send.json ?? send.text, replyMs, reply, deltaCount: deltas.length, shimPrompts: prompts });
      t.check('a chatReply for the seat arrived on /ws', reply !== null, reply ? `in ${replyMs} ms` : `no chatReply within ${(askWire ? PATH_TURN_MS : 60_000) / 1000} s (${ws.frames.length} frames seen)`, { evidence: ev });
      t.check('chatReply.ok == true with a non-empty text', reply?.ok === true && typeof reply?.text === 'string' && reply.text.trim().length > 0, `ok ${reply?.ok}; text ${JSON.stringify(reply?.text ?? null).slice(0, 200)}`, { evidence: ev });
      t.check('at least one chatDelta streamed before the reply', deltas.length >= 1, `${deltas.length} delta frame(s)`, { evidence: ev });
      t.check('the turn reached the shim over ACP (session/prompt recorded)', prompts.length >= 1, `${prompts.length} session/prompt record(s)`, { evidence: ev });
      if (askWire) {
        const handshake = acpCalls().filter((c) => c.acp === 'initialize' || c.acp === 'session/new');
        t.check('path wire: the run opened the ACP session (initialize + session/new recorded after the first message)', handshake.some((c) => c.acp === 'initialize') && handshake.some((c) => c.acp === 'session/new'), `${handshake.length} handshake record(s): ${handshake.map((c) => c.acp).join(', ') || 'none'}`, { evidence: ev });
        t.check('path wire: the reply is stamped with the run and the turn (run_id == runId, ord is a number, turn_id == turnId)', reply?.run_id === runId && Number.isInteger(reply?.ord) && reply?.turn_id === send.json?.turnId, JSON.stringify({ run_id: reply?.run_id, ord: reply?.ord, turn_id: reply?.turn_id }), { evidence: ev });
        t.check('path wire: the reply is the shim\'s answer, not an engine refusal (no "[wicked-core]" prefix)', typeof reply?.text === 'string' && !/^\[wicked-core\]/.test(reply.text.trim()), JSON.stringify(reply?.text ?? null).slice(0, 200), { evidence: ev });
        t.check('path wire: exactly ONE chatReply for the turn (one voice)', ws.frames.filter(isReply).length === 1, `${ws.frames.filter(isReply).length} chatReply frame(s)`, { evidence: ev });
        // The run's own record: the step ran on the ACP carrier for THIS seat (`acpSessionStarted`),
        // and the answer was captured (`unitOutputCaptured`). The skills snapshot is handed per
        // seat LEVER (`SkillsSnapshot::delivery(cli)` → `delivers_skills`): a synthetic seat the
        // engine knows no lever for (acp-smoke) is handed none and emits no `skillsSnapshotHanded`,
        // so the pool wire's F-RC1-113 check has no path-wire equivalent here — the count is
        // disclosed, not asserted (a real seat's handing is what the rig's runs show).
        const events = (await api.get(`/runs/${enc(runId)}/events`)).json?.events;
        const list = Array.isArray(events) ? events : [];
        const evRun = t.evidence('run-events-after-turn-1', { count: list.length, types: list.map((e) => e?.type) });
        t.check(`path wire: the run's events show the step on the ACP carrier for ${ACP_SEAT_KEY} (acpSessionStarted{cliKey}) and its answer captured (unitOutputCaptured)`, list.some((e) => e?.type === 'acpSessionStarted' && e.cliKey === ACP_SEAT_KEY) && list.some((e) => e?.type === 'unitOutputCaptured'), `${list.length} event(s): ${[...new Set(list.map((e) => e?.type))].join(', ')}`, { evidence: evRun });
        t.info('skills', `skillsSnapshotHanded × ${list.filter((e) => e?.type === 'skillsSnapshotHanded').length} for the ${ACP_SEAT_KEY} unit — the engine hands a snapshot per seat lever and knows none for a synthetic seat (SkillsDelivery::None → no event); not a F-RC1-113 verdict on the path wire`);
      }
      // DES-L5 §4: `chatReply.usage: {inputTokens, outputTokens, …} | null` — the shim reports usage
      // on the prompt result, so a wired daemon carries numbers here (pool wire: fixed on crew 0.7.35;
      // path wire: the relay folds a unit's output and carries none — F-A6-USAGE, crew#824).
      const usage = reply?.usage;
      t.check(`chatReply carries usage {inputTokens, outputTokens} (${askWire ? 'F-A6-USAGE' : 'F-RC1-116'})`, usage !== null && typeof usage === 'object' && Number.isFinite(usage?.inputTokens) && Number.isFinite(usage?.outputTokens), `usage ${JSON.stringify(usage ?? null).slice(0, 200)}`, { finding: askWire ? 'F-A6-USAGE' : 'F-RC1-116', evidence: ev });
      const detail = await api.get(`/chats/${enc(chatId)}`);
      const messages = detail.json?.messages;
      const ev2 = t.evidence('chat-detail-after-turn-1', { status: detail.status, body: detail.json ?? detail.text?.slice(0, 800) });
      t.check(`GET /chats/:id → 200 with the seat ${askWire ? 'eligible' : 'warm'}`, detail.status === 200 && Array.isArray(detail.json?.seats) && detail.json.seats.includes(ACP_SEAT_KEY), `status ${detail.status}; seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev2 });
      // The turn's own records are exactly ONE `user` and ONE `seat` reply. A daemon may append DERIVED
      // records beside them, each folded onto the turn by a reader (crew-api-types
      // `ChatTranscriptRecord`): `citations`, `system`, and — from crew 0.7.48, decision capture's
      // studio-chat host — one `decisions` record per turn. Any OTHER kind, or a second user/seat
      // record, fails: the transcript must not grow records nobody can name.
      const kinds = Array.isArray(messages) ? messages.map((m) => m?.kind) : [];
      const users = kinds.filter((k) => k === 'user').length;
      const seatReplies = Array.isArray(messages) ? messages.filter((m) => m?.kind === 'seat' && m.cliKey === ACP_SEAT_KEY).length : 0;
      const unknownKinds = kinds.filter((k) => !TRANSCRIPT_KINDS.has(k));
      t.check('GET /chats/:id.messages holds the user message + the seat reply (one each; only derived records beside them, F-RC1-112)', Array.isArray(messages) && users === 1 && seatReplies === 1 && kinds.filter((k) => k === 'seat').length === 1 && unknownKinds.length === 0, Array.isArray(messages) ? `${messages.length} record(s): ${kinds.join(', ')}${unknownKinds.length > 0 ? ` — unknown kind(s): ${unknownKinds.join(', ')}` : ''}` : `messages ${JSON.stringify(messages ?? null)} (absent on a daemon without the transcript)`, { finding: 'F-RC1-112', evidence: ev2 });
    }

    if (askWire) {
      // The Nth reply of this chat (0-based), waited for: `ws.waitFor` resolves with the FIRST frame
      // its predicate accepts, scanning from the start, so a "count grew" predicate could hand back
      // turn 1's reply once a later one exists — the reply is picked by its index instead.
      const nthReply = async (n, ms) => {
        const grown = await ws.waitFor(() => ws.frames.filter(isReply).length > n, { ms, signal: ctx.signal });
        return grown === null ? null : ws.frames.filter(isReply)[n] ?? null;
      };
      // ── 4 (path). In flight: a slow step, a send during it is 409, the slow reply lands uncut ──
      {
        const before = ws.frames.filter(isReply).length;
        const sent = Date.now();
        const send = await api.post(`/chats/${enc(chatId)}/messages`, { text: `wicked-smoke: take your time — smoke-acp-sleep-ms=${SLOW_TURN_SLEEP_MS} — then answer (turn 2)` });
        t.check('slow turn: POST /chats/:id/messages → 202 {stepId: "answer-2"}', send.status === 202 && send.json?.stepId === 'answer-2', `status ${send.status}: ${JSON.stringify(send.json ?? send.text).slice(0, 200)}`);
        const during = await api.post(`/chats/${enc(chatId)}/messages`, { text: 'wicked-smoke: are you there? (sent during turn 2)' });
        const evDuring = t.evidence('chat-send-during-turn', { status: during.status, body: during.json ?? during.text?.slice(0, 600) });
        t.check(`a send DURING the turn is refused: 409 turn_in_flight naming ${ACP_SEAT_KEY} and the turn (F-RECON-017)`, during.status === 409 && during.json?.code === 'turn_in_flight' && typeof during.json?.error === 'string' && during.json.error.includes(ACP_SEAT_KEY) && during.json?.turn?.turnId === send.json?.turnId, `status ${during.status}: ${JSON.stringify(during.json ?? during.text).slice(0, 240)}`, { evidence: evDuring });
        const reply = await nthReply(before, SLOW_TURN_SLEEP_MS + PATH_TURN_MS);
        const replyMs = Date.now() - sent;
        const ev = t.evidence('chat-turn-slow', { poolBudgetSecs: CHAT_TURN_SECS, shimSleepMs: SLOW_TURN_SLEEP_MS, send: send.json ?? send.text, replyMs, reply });
        t.check(`the slow step answered ok:true AFTER the shim's ${SLOW_TURN_SLEEP_MS / 1000} s sleep (the step's own budget is the ask's 600 s, not WICKED_CHAT_TURN_SECS)`, reply !== null && reply.ok === true && replyMs >= SLOW_TURN_SLEEP_MS && reply.run_id === runId, reply ? `ok ${reply.ok} in ${replyMs} ms` : `no chatReply within ${(SLOW_TURN_SLEEP_MS + PATH_TURN_MS) / 1000} s`, { evidence: ev });
        // The reply of a 20 s step is still STAMPED (turn_id) — the turn index did not drop it as
        // stale, so the transcript persists it (crew #826: with WICKED_CHAT_TURN_SECS=5 it would be).
        t.check('the slow reply is stamped with its turn (turn_id == the 202\'s turnId) and ord 2', reply?.turn_id === send.json?.turnId && reply?.ord === 2, JSON.stringify({ turn_id: reply?.turn_id, turnId: send.json?.turnId, ord: reply?.ord }), { evidence: ev });
        t.info('budget', `path wire: a ${SLOW_TURN_SLEEP_MS / 1000} s step answered uncut in ${replyMs} ms — a path step's budget is crew's ASK_TURN_BUDGET_SECS (600 s), not WICKED_CHAT_TURN_SECS; a step over it is re-picked or the path ends, which this harness does not wait for`);
        const detail = await api.get(`/chats/${enc(chatId)}`);
        t.check('the seat stays eligible after the slow step (GET /chats/:id.seats still lists it)', detail.status === 200 && Array.isArray(detail.json?.seats) && detail.json.seats.includes(ACP_SEAT_KEY), `status ${detail.status}; seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev });
        // The refused send must not have become a step: the transcript has two user records, no third.
        const kinds = Array.isArray(detail.json?.messages) ? detail.json.messages.map((m) => m?.kind) : [];
        t.check('the refused send left no record (two user messages, two seat replies)', kinds.filter((k) => k === 'user').length === 2 && kinds.filter((k) => k === 'seat').length === 2, `${kinds.length} record(s): ${kinds.join(', ')}`, { evidence: ev });
      }

      // ── 5 (path). Follow-up: the next message is answer-3 on the same run ──
      {
        const before = ws.frames.filter(isReply).length;
        const sent = Date.now();
        const send = await api.post(`/chats/${enc(chatId)}/messages`, { text: 'wicked-smoke: hello again (turn 3, follow-up)' });
        const ev0 = t.evidence('chat-turn-followup-send', { status: send.status, body: send.json ?? send.text?.slice(0, 500) });
        t.check('follow-up: POST /chats/:id/messages → 202 {stepId: "answer-3", runId: the same run}', send.status === 202 && send.json?.stepId === 'answer-3' && send.json?.runId === runId, `status ${send.status}: ${JSON.stringify(send.json ?? send.text).slice(0, 200)}`, { evidence: ev0 });
        const reply = await nthReply(before, PATH_TURN_MS);
        const replyMs = Date.now() - sent;
        const ev = t.evidence('chat-turn-followup', { replyMs, reply });
        t.check('follow-up: an ok chatReply follows on the same run', reply?.ok === true && reply?.run_id === runId, reply ? `ok ${reply.ok} in ${replyMs} ms: ${JSON.stringify(reply.text).slice(0, 160)}` : `no chatReply within ${PATH_TURN_MS / 1000} s`, { evidence: ev });
        const path = (await api.get(`/chats/${enc(chatId)}`)).json?.path;
        t.check('follow-up: GET /chats/:id.path.stepId moved to "answer-3"', path?.stepId === 'answer-3' && path?.runId === runId, `path ${JSON.stringify(path ?? null).slice(0, 200)}`, { evidence: ev });
      }

      // ── 6 (path). End: chatClosed on /ws, seats and transcript gone, the run cancelled ──
      {
        const t1 = Date.now();
        const close = await api.del(`/chats/${enc(chatId)}`);
        t.check('DELETE /chats/:id → 2xx', close.status >= 200 && close.status < 300, `status ${close.status}`);
        const closed = await ws.waitFor((f) => f?.type === 'chatClosed' && f.chat === chatId, { ms: 20_000, signal: ctx.signal });
        const ev = t.evidence('chat-close', { status: close.status, ms: Date.now() - t1, closed });
        t.check('chatClosed {reason: "closed"} on /ws (End, the daemon owns the close)', closed !== null && closed.reason === 'closed', closed ? `reason ${closed.reason} in ${Date.now() - t1} ms` : 'no chatClosed within 20 s', { evidence: ev });
        const detail = await api.get(`/chats/${enc(chatId)}`);
        const ev2 = t.evidence('chat-detail-after-close', { status: detail.status, body: detail.json ?? detail.text?.slice(0, 500) });
        t.check('after End: GET /chats/:id.seats == []', detail.status === 200 && Array.isArray(detail.json?.seats) && detail.json.seats.length === 0, `status ${detail.status}; seats ${JSON.stringify(detail.json?.seats ?? null)}`, { evidence: ev2 });
        t.check('after End: GET /chats/:id.messages == [] (the transcript goes with the chat, F-RC1-112)', Array.isArray(detail.json?.messages) && detail.json.messages.length === 0, `messages ${JSON.stringify(detail.json?.messages ?? null).slice(0, 200)}`, { finding: 'F-RC1-112', evidence: ev2 });
        // End cancels the path: the run reads `cancelled` (polled — the cancel is awaited by the
        // route, the view may lag a bus poll).
        let status = null;
        for (let i = 0; i < 20 && status !== 'cancelled'; i += 1) {
          if (i > 0) await new Promise((r) => setTimeout(r, 1000));
          const run = await api.get(`/runs/${enc(runId)}`);
          status = run.json?.run?.session?.status ?? run.json?.session?.status ?? null;
        }
        t.check('after End: the path\'s run reads cancelled (GET /runs/:id)', status === 'cancelled', `status ${status}`, { evidence: t.evidence('run-after-end', { runId, status }) });
      }
    } else {
      // ── 4 (pool). The turn budget: a slow seat is cut at WICKED_CHAT_TURN_SECS and released ──
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

      // ── 5 (pool). Re-seat by targeting the released seat on the next send ──
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

      // ── 6 (pool). Close: chatClosed on /ws, seats and transcript gone ──
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
    }
    t.evidence('ws-chat-frames', ws.frames.filter((f) => typeof f?.type === 'string' && f.type.startsWith('chat')).slice(0, 400));
    t.info('turn timings', `see evidence chat-turn-1 / ${askWire ? 'chat-turn-slow / chat-turn-followup' : 'chat-turn-budget / chat-turn-reseat'} (replyMs) — DES-L5 §8 re-derives the budget from per-turn totals`);
  } finally {
    ws.close();
  }
}
