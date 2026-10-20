// vitest setup file the e2e runner APPENDS to a package's own setupFiles (its hermetic setup still
// runs first). With E2E_HTTP_TAP set it records, one JSON line each, every HTTP exchange a test
// drives: Fastify `inject()` (light-my-request) and global `fetch` to an /api/ URL. Each line names
// the test that made it. It records; it never changes a request or an answer.
import { appendFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const OUT = process.env.E2E_HTTP_TAP;
const CAP = 256 * 1024;

function currentTest() {
  try {
    const w = globalThis.__vitest_worker__;
    const t = w?.current;
    if (t) {
      const names = [];
      for (let n = t; n && n.name; n = n.suite) names.unshift(n.name);
      return names.filter(Boolean).join(' > ');
    }
  } catch { /* not in a test */ }
  return null;
}

function parse(text) {
  if (typeof text !== 'string') return text ?? null;
  try { return JSON.parse(text); } catch { return text.length <= 4096 ? text : text.slice(0, 4096); }
}

function rec(r) {
  if (!OUT) return;
  try {
    let line = JSON.stringify({ test: currentTest(), t: Date.now(), ...r });
    if (line.length > CAP) line = JSON.stringify({ test: currentTest(), t: Date.now(), ...r, res: { truncated: true } });
    appendFileSync(OUT, line + '\n');
  } catch { /* a tap never fails a test */ }
}

if (OUT && !globalThis.__e2eTapInstalled) {
  globalThis.__e2eTapInstalled = true;

  const origFetch = globalThis.fetch;
  if (typeof origFetch === 'function') {
    globalThis.fetch = async function tappedFetch(input, init = {}) {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input?.url;
      const method = String(init?.method || input?.method || 'GET').toUpperCase();
      const res = await origFetch(input, init);
      if (typeof url === 'string' && /\/api\//.test(url)) {
        try {
          const text = await res.clone().text();
          rec({ via: 'fetch', method, url, status: res.status, req: parse(typeof init?.body === 'string' ? init.body : null), res: parse(text) });
        } catch { /* body not readable */ }
      }
      return res;
    };
  }

  try {
    const req = createRequire(join(process.cwd(), 'package.json'));
    const fastifyDir = dirname(req.resolve('fastify'));
    const id = req.resolve('light-my-request', { paths: [fastifyDir] });
    const orig = req(id);
    const log = (opts, res) => {
      if (!res) return;
      const o = typeof opts === 'string' ? { url: opts } : (opts || {});
      rec({ via: 'inject', method: String(o.method || 'GET').toUpperCase(), url: o.url || o.path || null,
        status: res.statusCode, req: o.payload ?? o.body ?? null, res: parse(res.payload) });
    };
    const wrapped = function tappedInject(dispatch, options, callback) {
      if (typeof callback === 'function') {
        return orig(dispatch, options, (err, res) => { log(options, res); callback(err, res); });
      }
      const r = orig(dispatch, options);
      if (r && typeof r.then === 'function') {
        const then = r.then.bind(r);
        r.then = (ok, bad) => then((res) => { log(r.option ?? options, res); return ok ? ok(res) : res; }, bad);
      }
      return r;
    };
    Object.assign(wrapped, orig);
    req.cache[id].exports = wrapped;
  } catch { /* no fastify here: fetch is still tapped */ }
}
