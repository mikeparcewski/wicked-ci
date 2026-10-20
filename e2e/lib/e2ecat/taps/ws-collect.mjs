// ws-collect.mjs <ws-url> <out.jsonl> <max-seconds>: subscribe READ-ONLY to a daemon's /ws event stream
// and append every JSON frame, one per line, until SIGTERM or the time limit. It never sends a frame.
// node >= 22 (the WebSocket client global). Used by the e2e runner's direct adapter on the live target.
import { appendFileSync, writeFileSync } from 'node:fs';

const [url, out, secs] = process.argv.slice(2);
writeFileSync(out, '');
const ws = new globalThis.WebSocket(url);
const stop = () => { try { ws.close(); } catch { /* gone */ } process.exit(0); };
ws.addEventListener('open', () => appendFileSync(out, JSON.stringify({ open: url, t: Date.now() }) + '\n'));
ws.addEventListener('message', (ev) => {
  const data = typeof ev.data === 'string' ? ev.data : Buffer.from(ev.data).toString('utf8');
  try { appendFileSync(out, JSON.stringify({ t: Date.now(), frame: JSON.parse(data) }) + '\n'); } catch { /* not JSON */ }
});
ws.addEventListener('error', () => { appendFileSync(out, JSON.stringify({ error: url, t: Date.now() }) + '\n'); process.exit(1); });
process.on('SIGTERM', stop);
process.on('SIGINT', stop);
setTimeout(stop, Number(secs || 120) * 1000);
