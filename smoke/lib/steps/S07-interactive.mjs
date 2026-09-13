// S07 interactive — OPT-IN in v1 (`--steps S07`). Crew spawns the wicked-interactive bridge with
// `npx wicked-interactive@<range> serve --root …` on first use: a cold npx fetch over the network,
// outside the ≤ 8 min budget and the offline posture of the other steps. What runs here is the proxy
// seam the studio uses: the doc-create path under `/projects/:id/interactive/api/docs` must answer
// (201 with a doc id, or an HONEST bridge-unavailable error — never a hang or a 500 with no body).
// TODO(v2): pre-warm the npx cache at install time (WICKED_INTERACTIVE_SPEC pinned to the installed
// version), then assert create → edit → export HTML non-empty → bridge pid reused across calls.
export const id = 'S07';
export const name = 'interactive (opt-in)';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const project = await api.post('/projects', { name: 'smoke-interactive' });
  const projectId = project.json?.project?.id;
  t.check('POST /projects 201', project.status === 201 && typeof projectId === 'string', `status ${project.status}`);
  if (!projectId) return;
  const t0 = Date.now();
  const create = await api.post(`/projects/${encodeURIComponent(projectId)}/interactive/api/docs`, { title: 'wicked-smoke doc', kind: 'source', content: '# smoke\n\nhello' });
  const ev = t.evidence('doc-create', { status: create.status, ms: Date.now() - t0, body: create.json ?? create.text?.slice(0, 500) });
  t.check('doc-create answered (no hang)', create.status !== 0, `status ${create.status} in ${Date.now() - t0} ms`, { evidence: ev });
  t.check('doc-create is a 2xx with an id OR an honest error body', (create.status >= 200 && create.status < 300 && (create.json?.id || create.json?.doc?.id)) || (create.status >= 400 && typeof (create.json?.error ?? create.json?.message) === 'string'), `status ${create.status}`, { evidence: ev });
  if (create.status >= 200 && create.status < 300) {
    const docId = create.json?.id ?? create.json?.doc?.id;
    const read = await api.get(`/projects/${encodeURIComponent(projectId)}/interactive/api/docs/${encodeURIComponent(docId)}`);
    t.check('doc readable through the proxy', read.status === 200, `status ${read.status}`);
    const read2 = await api.get(`/projects/${encodeURIComponent(projectId)}/interactive/api/docs/${encodeURIComponent(docId)}`);
    t.check('second proxy call answers (bridge reused, not respawned)', read2.status === 200 && read2.ms < 5000, `status ${read2.status} in ${read2.ms} ms`);
  } else {
    t.info('TODO', 'bridge spawn is a cold npx fetch in v1 — export/edit assertions land with the pre-warmed cache (v2)');
  }
}
