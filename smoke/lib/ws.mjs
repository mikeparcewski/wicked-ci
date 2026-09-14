// A minimal `/ws` frame collector over the daemon's event stream (node ≥ 22 ships the WebSocket
// client global; the harness has no dependencies). Chat replies (`chatDelta` / `chatReply` /
// `chatClosed`) travel ONLY on /ws — `GET /chats/:id` carries no transcript on the published
// daemon — so a step that asserts a chat turn reads them here, the way the studio does. Late-join
// gets no replay: open the socket BEFORE the action whose frames you want.
import { sleep } from './proc.mjs';

/**
 * Open `/ws` on `origin` and collect every JSON frame. Returns {frames, waitFor, close}.
 * `waitFor(pred, {ms, signal})` resolves with the first frame matching `pred` (already received or
 * arriving within `ms`), else `null`. `frames` is the live array (bounded by `max`).
 */
export async function openFrames(origin, { openTimeoutMs = 10_000, max = 5000 } = {}) {
  if (typeof globalThis.WebSocket !== 'function') {
    throw new Error(`wicked-smoke needs the WebSocket client global (node >= 22); running ${process.version}`);
  }
  const url = `${origin.replace(/^http/, 'ws')}/ws`;
  const ws = new globalThis.WebSocket(url);
  const frames = [];
  let closed = false;
  ws.addEventListener('message', (ev) => {
    const data = typeof ev.data === 'string' ? ev.data : Buffer.from(ev.data).toString('utf8');
    try {
      const frame = JSON.parse(data);
      if (frames.length < max) frames.push(frame);
    } catch { /* not JSON — not ours */ }
  });
  ws.addEventListener('close', () => { closed = true; });
  ws.addEventListener('error', () => { closed = true; });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`/ws did not open within ${openTimeoutMs} ms (${url})`)), openTimeoutMs);
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
    ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error(`/ws connection error (${url})`)); }, { once: true });
  });
  return {
    frames,
    get closed() { return closed; },
    async waitFor(pred, { ms = 30_000, every = 100, signal = null } = {}) {
      const deadline = Date.now() + ms;
      let seen = 0;
      while (Date.now() < deadline) {
        if (signal?.aborted) return null;
        for (; seen < frames.length; seen += 1) if (pred(frames[seen])) return frames[seen];
        if (closed) return null;
        await sleep(every);
      }
      for (; seen < frames.length; seen += 1) if (pred(frames[seen])) return frames[seen];
      return null;
    },
    close() {
      try { ws.close(); } catch { /* already gone */ }
    },
  };
}
