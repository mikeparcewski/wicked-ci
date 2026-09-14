#!/usr/bin/env node
// `acp-agent` — the ACP-speaking seat shim (wicked-smoke v2; DES-L5 S-CHAT-01). The chat path warms
// its seats over the Agent Client Protocol (JSON-RPC 2.0 ndjson on stdin/stdout — the transport the
// engine uses for `claude-agent-acp`, `opencode acp`, `codex-acp`), so a chat turn can only complete
// against a shim that speaks it. This one does exactly what the wire needs and nothing more:
//
//   initialize        → {protocolVersion, agentCapabilities, agentInfo, authMethods: []} (no auth step)
//   session/new       → {sessionId}
//   session/prompt    → sleep (see below) → two `session/update` `agent_message_chunk` notifications
//                       → the prompt RESULT {stopReason: "end_turn", usage: {inputTokens, outputTokens}}
//   session/cancel    → the pending prompt answers {stopReason: "cancelled"}
//   anything else     → a request gets JSON-RPC -32601; a notification is recorded and ignored
//
// The sleep before answering makes the turn budget observable (`WICKED_CHAT_TURN_SECS`): the
// baseline is `WICKED_SMOKE_ACP_SLEEP_MS` (env, default 0); a prompt carrying the token
// `smoke-acp-sleep-ms=<n>` overrides it for THAT turn, so one daemon can serve a fast turn, a
// budget-cut turn and a fast re-seat without a restart per case. Every JSON-RPC call is recorded in
// `<root>/shim-calls.ndjson` (`acp: <method>`) like every other shim invocation. Never calls a
// model, never touches the network. Invoked WITH arguments (a council ballot, a judge or worker turn
// routed through its `headless_invocation`) it answers like the claude shim — the seat is
// council-disabled in the overlay, so that path is a safety net, not a plan.
import { createInterface } from 'node:readline';
import { BALLOT, JUDGE_PASS, TRIAGE_ESCALATE, appendRecord, isVersionProbe, record, workerTurn } from './_lib.mjs';

const SHIM = 'acp-agent';
const VERSION = '0.1.0-smoke';
const SLEEP_ENV = 'WICKED_SMOKE_ACP_SLEEP_MS';
const SLEEP_TOKEN = /smoke-acp-sleep-ms=(\d{1,7})/;

const { argv, prompt, kind } = record(SHIM, { mode: process.argv.length > 2 ? 'headless' : 'acp' });
if (isVersionProbe(argv)) {
  console.log(`${VERSION} (wicked-smoke ACP seat shim)`);
  process.exit(0);
}
if (argv.length > 0) {
  // The one-shot contract, in case a turn is ever routed here headlessly.
  if (!prompt) console.log(`${SHIM} shim: no prompt`);
  else if (kind === 'ballot') console.log(BALLOT);
  else if (kind === 'judge') console.log(JUDGE_PASS);
  else if (kind === 'triage') console.log(TRIAGE_ESCALATE);
  else console.log(workerTurn(prompt));
  process.exit(0);
}

// ── ACP over stdio ──
const baseSleepMs = Math.max(0, Number.parseInt(process.env[SLEEP_ENV] ?? '0', 10) || 0);
let sessionSeq = 0;
/** sessionId → { promptId, timer } for the turn in flight (one per session; the engine sends one). */
const pending = new Map();

process.stdout.on('error', () => process.exit(0)); // the engine closed the pipe (eviction) — leave quietly

function send(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function respond(id, result) {
  send({ jsonrpc: '2.0', id, result });
}

function refuse(id, code, message) {
  send({ jsonrpc: '2.0', id, error: { code, message } });
}

function notify(method, params) {
  send({ jsonrpc: '2.0', method, params });
}

function promptText(blocks) {
  if (!Array.isArray(blocks)) return typeof blocks === 'string' ? blocks : '';
  return blocks.filter((b) => b && b.type === 'text' && typeof b.text === 'string').map((b) => b.text).join('\n');
}

function answer(sessionId, promptId, text, sleptMs) {
  pending.delete(sessionId);
  const head = '## Answer\n\n';
  const body = `wicked-smoke ACP seat: received your message (${text.length} chars) over ACP session ${sessionId}`
    + `${sleptMs > 0 ? ` after sleeping ${sleptMs} ms` : ''}. No model was called — this deterministic stand-in proves the `
    + 'chat wire (open → prompt → streamed deltas → reply), not an answer\'s quality.';
  notify('session/update', { sessionId, update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: head } } });
  notify('session/update', { sessionId, update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: body } } });
  const usage = { inputTokens: Math.max(1, Math.ceil(text.length / 4)), outputTokens: Math.max(1, Math.ceil((head.length + body.length) / 4)) };
  respond(promptId, { stopReason: 'end_turn', usage });
  appendRecord({ shim: SHIM, acp: 'session/prompt:answered', sessionId, sleptMs, usage });
}

function dispatch(msg) {
  const { id, method, params } = msg;
  const isRequest = Object.prototype.hasOwnProperty.call(msg, 'id');
  if (typeof method !== 'string') return; // a response to something we sent — we send no requests
  switch (method) {
    case 'initialize': {
      appendRecord({ shim: SHIM, acp: method, clientProtocolVersion: params?.protocolVersion ?? null, clientCapabilities: Object.keys(params?.clientCapabilities ?? {}) });
      respond(id, {
        protocolVersion: params?.protocolVersion ?? 1,
        agentCapabilities: { loadSession: false },
        agentInfo: { name: 'wicked-smoke-acp-agent', version: VERSION },
        authMethods: [],
      });
      return;
    }
    case 'authenticate': {
      appendRecord({ shim: SHIM, acp: method, methodId: params?.methodId ?? null });
      respond(id, {});
      return;
    }
    case 'session/new': {
      sessionSeq += 1;
      const sessionId = `smoke-acp-${process.pid}-${sessionSeq}`;
      appendRecord({ shim: SHIM, acp: method, sessionId, cwd: params?.cwd ?? null, mcpServers: Array.isArray(params?.mcpServers) ? params.mcpServers.map((s) => s?.name ?? '?') : null, hasMeta: params?._meta !== undefined });
      respond(id, { sessionId });
      return;
    }
    case 'session/prompt': {
      const sessionId = String(params?.sessionId ?? '');
      const text = promptText(params?.prompt);
      const token = text.match(SLEEP_TOKEN);
      const sleepMs = token ? Number.parseInt(token[1], 10) : baseSleepMs;
      appendRecord({ shim: SHIM, acp: method, sessionId, chars: text.length, sleepMs, promptHead: text.slice(0, 300) });
      const timer = setTimeout(() => answer(sessionId, id, text, sleepMs), sleepMs);
      pending.set(sessionId, { promptId: id, timer });
      return;
    }
    case 'session/cancel': {
      const sessionId = String(params?.sessionId ?? '');
      const p = pending.get(sessionId);
      appendRecord({ shim: SHIM, acp: method, sessionId, hadPending: p !== undefined });
      if (p) {
        clearTimeout(p.timer);
        pending.delete(sessionId);
        respond(p.promptId, { stopReason: 'cancelled' });
      }
      return;
    }
    default: {
      appendRecord({ shim: SHIM, acp: method, unhandled: true, isRequest });
      if (isRequest) refuse(id, -32601, `${SHIM} shim does not implement \`${method}\``);
    }
  }
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on('line', (line) => {
  const s = line.trim();
  if (!s) return;
  let msg;
  try { msg = JSON.parse(s); } catch { appendRecord({ shim: SHIM, acp: 'invalid-line', head: s.slice(0, 120) }); return; }
  if (msg && typeof msg === 'object') dispatch(msg);
});
rl.on('close', () => {
  // stdin closed: the engine tore the session down (turn budget eviction, chat close, daemon stop).
  for (const { timer } of pending.values()) clearTimeout(timer);
  appendRecord({ shim: SHIM, acp: 'stdin-closed', pendingTurns: pending.size });
  process.exit(0);
});
