// S06 campaign fan-out — F-086 class: `POST /testing/recon` over two repos builds an ENGINE campaign
// whose def carries crew's standing-decorated roster; on core-ts ≥ 0.7.22 a `health` object without
// `usable` fails the engine's deserializer → 500. The fan must register (201, campaignRegistered) and
// every sibling must pause at its intake gate before any unit runs. The siblings are cancelled
// afterwards — no council convenes in this step.
import { cloneCorpus } from '../corpus.mjs';
import { sleep, until } from '../proc.mjs';
import { waitTerminal } from '../runs.mjs';

export const id = 'S06';
export const name = 'campaign fan-out';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const env = ctx.env;
  if (!ctx.state.corpus) throw new Error('S06 needs S03 (the corpus) — run --steps S03,S06');

  const refs = [];
  for (const name of ['recon-a', 'recon-b']) {
    const repo = cloneCorpus(ctx.L, env, ctx.state.corpus, name);
    const reg = await api.post('/repos', { name, rootPath: repo });
    t.check(`POST /repos ${name} 201`, reg.status === 201, `status ${reg.status}`);
    if (reg.json?.onboardRunId) await waitTerminal(api, reg.json.onboardRunId, { ms: 60_000 });
    refs.push(reg.json?.repo?.id ?? name);
  }

  const body = { problem: 'Survey the public API surface of this repository and list its entry points (smoke recon).', repoRefs: refs };
  const recon = await api.post('/testing/recon', body);
  const ev = t.evidence('recon', { request: body, status: recon.status, response: recon.json ?? recon.text });
  t.check('POST /testing/recon 201 (F-086: not a 500 "missing field usable")', recon.status === 201, `status ${recon.status} ${recon.text?.slice(0, 300)}`, { evidence: ev });
  const campaign = recon.json?.campaign ?? recon.json?.campaignId ?? null;
  const registered = recon.json?.campaignRegistered;
  t.check('campaign registered with the engine (campaignRegistered: true)', registered === true, `campaignRegistered=${registered} campaign=${campaign}`, { evidence: ev });
  const runIds = Array.isArray(recon.json?.runs) ? recon.json.runs.map((r) => (typeof r === 'string' ? r : r.runId ?? r.id)).filter(Boolean) : Array.isArray(recon.json?.runIds) ? recon.json.runIds : [];
  t.check('two sibling runs launched', runIds.length === 2, `${runIds.length} run id(s): ${runIds.join(',')}`, { evidence: ev });

  let nodeStatus = null;
  if (campaign) {
    const done = await until(async () => {
      const c = await api.get(`/campaigns/${encodeURIComponent(campaign)}`);
      const ns = c.json?.campaign?.node_status ?? null;
      if (ns && Object.keys(ns).length === 2 && Object.values(ns).every((s) => s === 'awaiting_human')) return c.json.campaign;
      nodeStatus = ns;
      return null;
    }, { ms: 60_000, every: 1000 });
    const evC = t.evidence('campaign', done ?? { lastNodeStatus: nodeStatus });
    t.check('GET /campaigns/:id lists both nodes awaiting intake', done !== null, `node_status ${JSON.stringify(done?.node_status ?? nodeStatus)}`, { evidence: evC });
    const list = await api.get('/campaigns');
    t.check('GET /campaigns carries the recon fan', (list.json?.campaigns ?? []).some((c) => c.id === campaign), `${(list.json?.campaigns ?? []).length} campaign(s)`);
    const ids = runIds.length ? runIds : Object.values(done?.node_run_id ?? {});
    for (const rid of ids) {
      const c = await api.post(`/runs/${encodeURIComponent(rid)}/cancel`);
      t.info(`cancel ${rid.slice(0, 12)}`, `status ${c.status}`);
    }
    await sleep(1500);
  }
}
