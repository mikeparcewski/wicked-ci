// U08 (PRODUCT-WORKS J6, hermetic): the studio workflow builds an MCP server; the person consents to its install,
// sees it in MCP and calls it through the inspector. No registry/setup POST can stand in for that path.
import { readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { journeyPython, runJourney } from '../journey.mjs';

export const id = 'U08';
export const name = 'an MCP server is built, installed on consent and callable';

const TAG = 'U08: build and install an MCP server';
const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export async function run(ctx, t) {
  const { python, why } = journeyPython(ctx);
  if (!python) { t.skip(why); return; }
  await ctx.ensureDaemon();
  const api = ctx.api();
  const scenario = join(ctx.L.root, 'scenario.json');
  writeFileSync(scenario, JSON.stringify({ build: 'mcp-server' }));
  try {
    await runJourney(ctx, t, 'u08_mcp_server_installed', { state: { tag: TAG } });
  } finally {
    // As in U06/U07: find our run even if the browser crashed before writing its id. Cleanup can cancel; it can
    // never consent, install or call on the person's behalf. The installed copy stays in the hermetic run root.
    try {
      let launched = null;
      try { launched = JSON.parse(readFileSync(join(t.dir, 'result.json'), 'utf8')).state?.runId ?? null; } catch { /* no result */ }
      const listed = await api.get('/runs?limit=100');
      if (listed.status !== 200) t.check('cleanup: the runs list answers (to find the MCP run)', false, `GET /runs ${listed.status}`);
      const runs = listed.json?.runs ?? [];
      const ids = new Set([launched, ...runs.filter((r) => String(r.session?.problem ?? '').includes(TAG)).map((r) => r.session.id)].filter(Boolean));
      for (const rid of ids) {
        if (TERMINAL.has(runs.find((r) => r.session?.id === rid)?.session?.status)) continue;
        const c = await api.post(`/runs/${rid}/cancel`, {});
        let status = null;
        for (let i = 0; i < 30 && !TERMINAL.has(status); i++) {
          status = ((await api.get('/runs?limit=100')).json?.runs ?? []).find((r) => r.session?.id === rid)?.session?.status ?? null;
          if (!TERMINAL.has(status)) await new Promise((res) => setTimeout(res, 1000));
        }
        t.check(`cleanup: the MCP run ${rid.slice(0, 8)} is cancelled`, c.status >= 200 && c.status < 300 && TERMINAL.has(status), `cancel ${c.status}; status ${status}`);
      }
    } finally {
      rmSync(scenario, { force: true });
    }
  }
}
