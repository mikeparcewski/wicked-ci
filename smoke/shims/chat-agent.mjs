#!/usr/bin/env node
// `chat-agent` — the HEADLESS chat seat shim (seat key `chat-smoke`), S08's seat on a C5 crew
// (crew >= 0.13.0, wicked-crew#1018 / wicked-core#950). C5 removed ACP from the seats: every unit,
// a chat path's `answer-N` step included, runs the seat's headless one-shot invocation on the wrapped
// carrier, and on the interim HOST floor (`WICKED_SEAT_FLOOR=host`, what the harness boots a C5 crew
// on) the engine runs a governed unit only when the launch keeps a per-call check — a binary whose
// file stem is `claude` (its PreToolUse gate hook) or a bounded codex; any other seat is refused
// `needs_container_floor` (wicked-core src/execute_wrapped.rs `host_floor_keeps_a_check`). So the
// harness launches this script through a wrapper NAMED `claude` (`<root>/bin/chat-seat/claude`):
// the engine treats the seat as a claude carrier — the gate hook is armed through the `wicked-core`
// shim, the output is read by the claude stream-json adapter — and S08 still sees its own shim in
// the call log. The ACP stdio shim (acp-agent.mjs) is only for crews < 0.13.0.
//
// A worker turn (the answer step) sleeps first when the prompt carries `smoke-acp-sleep-ms=<n>` (the
// token S08 already sends for its in-flight case; `WICKED_SMOKE_ACP_SLEEP_MS` is the env baseline),
// then answers >= 200 chars (the engine's substance gate). With `--output-format stream-json` in
// argv (the claude carrier's headless JSON mode) the answer is claude's NDJSON: two `assistant` text
// messages (the deltas) and a terminal `result` carrying `usage` — the turn is metered the way a real
// claude seat's is; without it, plain text. Ballots, judges and triage answer like the claude shim.
// Every invocation is recorded in `<root>/shim-calls.ndjson`; the answered turn adds `chat: answered`.
import { BALLOT, JUDGE_PASS, TRIAGE_ESCALATE, appendRecord, isVersionProbe, record } from './_lib.mjs';

const SHIM = 'chat-agent';
const SLEEP_ENV = 'WICKED_SMOKE_ACP_SLEEP_MS';
const SLEEP_TOKEN = /smoke-acp-sleep-ms=(\d{1,7})/;

const { argv, prompt, kind } = record(SHIM, { mode: 'headless' });
if (isVersionProbe(argv)) {
  console.log('0.1.0-smoke (wicked-smoke headless chat seat shim)');
  process.exit(0);
}
if (!prompt) {
  console.log(`${SHIM} shim: no prompt`);
  process.exit(0);
}
if (kind === 'ballot') console.log(BALLOT);
else if (kind === 'judge') console.log(JUDGE_PASS);
else if (kind === 'triage') console.log(TRIAGE_ESCALATE);
else {
  const token = prompt.match(SLEEP_TOKEN);
  const sleptMs = token ? Number.parseInt(token[1], 10) : Math.max(0, Number.parseInt(process.env[SLEEP_ENV] ?? '0', 10) || 0);
  if (sleptMs > 0) await new Promise((r) => setTimeout(r, sleptMs));
  const head = '## Answer\n\n';
  const body = `wicked-smoke headless chat seat: received your message (${prompt.length} chars of prompt) on the wrapped carrier`
    + `${sleptMs > 0 ? ` after sleeping ${sleptMs} ms` : ''}. No model was called — this deterministic stand-in proves the `
    + 'chat wire (open → first message launches the path → the answer step runs the seat headlessly → one stamped reply), '
    + 'not an answer\'s quality.';
  const usage = { input_tokens: Math.max(1, Math.ceil(prompt.length / 4)), output_tokens: Math.max(1, Math.ceil((head.length + body.length) / 4)) };
  const fmt = argv.indexOf('--output-format');
  const streamJson = fmt >= 0 && argv[fmt + 1] === 'stream-json';
  appendRecord({ shim: SHIM, chat: 'answered', sleptMs, streamJson, cwd: process.cwd() });
  if (streamJson) {
    const sessionId = `smoke-chat-${process.pid}`;
    const line = (o) => process.stdout.write(`${JSON.stringify(o)}\n`);
    line({ type: 'system', subtype: 'init', session_id: sessionId });
    line({ type: 'assistant', session_id: sessionId, message: { role: 'assistant', content: [{ type: 'text', text: head }] } });
    line({ type: 'assistant', session_id: sessionId, message: { role: 'assistant', content: [{ type: 'text', text: body }] } });
    line({ type: 'result', subtype: 'success', is_error: false, session_id: sessionId, result: `${head}${body}`, usage });
  } else console.log(`${head}${body}`);
}
// No process.exit here: stdout to a pipe is asynchronous on macOS, and the NDJSON must drain first.
process.exitCode = 0;
