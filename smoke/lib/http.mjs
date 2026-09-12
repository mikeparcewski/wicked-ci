// Tiny JSON client over the daemon's /api/v1 — records every call when verbose.

export function apiClient(origin, { log, verbose = false } = {}) {
  const base = `${origin}/api/v1`;
  async function call(method, path, body) {
    const t0 = Date.now();
    const init = { method, headers: {} };
    if (body !== undefined) {
      init.headers['content-type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(base + path, init);
    } catch (err) {
      // One retry after a transport failure (a socket reset while the daemon is saturated on a loaded
      // host): a smoke assertion must fail on what the daemon ANSWERED, not on a dropped connection.
      if (verbose && log) log(`  http ${method} ${path} -> network error ${err.message}; retrying once`);
      await new Promise((r) => setTimeout(r, 2000));
      try {
        res = await fetch(base + path, init);
      } catch (err2) {
        if (log) log(`  http ${method} ${path} -> network error twice: ${err2.message}`);
        return { status: 0, json: null, text: String(err2.message), ms: Date.now() - t0 };
      }
    }
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* not JSON */ }
    if (verbose && log) log(`  http ${method} ${path} -> ${res.status} (${Date.now() - t0} ms)`);
    return { status: res.status, json, text, ms: Date.now() - t0 };
  }
  return {
    origin,
    base,
    get: (p) => call('GET', p),
    post: (p, b) => call('POST', p, b ?? {}),
    put: (p, b) => call('PUT', p, b ?? {}),
    del: (p) => call('DELETE', p),
    /** Raw GET of a non-API path (the studio index). */
    async raw(path) {
      try {
        const res = await fetch(origin + path);
        return { status: res.status, text: await res.text(), headers: res.headers };
      } catch (err) {
        return { status: 0, text: String(err.message), headers: new Headers() };
      }
    },
  };
}
