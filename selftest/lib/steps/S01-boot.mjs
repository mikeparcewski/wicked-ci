// S01 boot — the PUBLISHED tarball boots hermetically and reports the versions it is made of.
// Packaging class: /health + /diagnostics component versions == the installed packages; the studio
// SPA is served same-origin and its bundle marker equals `components.studioBundle`.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export const id = 'S01';
export const name = 'boot';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  const api = ctx.api();
  const v = ctx.versions;

  const health = await api.get('/health');
  t.evidence('health', health.json ?? health.text);
  t.check('GET /health 200', health.status === 200, `status ${health.status}`);
  t.check('health.version == installed wicked-crew', health.json?.version === v.crew, `${health.json?.version} vs ${v.crew}`);
  t.check('health.ping ok', health.json?.ping === 'ok', String(health.json?.ping));

  const diag = await api.get('/diagnostics');
  const ev = t.evidence('diagnostics', diag.json ?? diag.text);
  t.check('GET /diagnostics 200', diag.status === 200, `status ${diag.status}`, { evidence: ev });
  const c = diag.json?.components ?? {};
  t.check('components.crew == installed', c.crew === v.crew, `${c.crew} vs ${v.crew}`, { evidence: ev });
  t.check('components.coreTs == installed wicked-core-ts', c.coreTs === v.coreTs, `${c.coreTs} vs ${v.coreTs}`, { evidence: ev });
  t.check('components.studioBundle present (not headless)', typeof c.studioBundle === 'string' && c.studioBundle !== '', String(c.studioBundle), { evidence: ev });
  t.check('components.studioBundle == bundled dist marker', c.studioBundle === v.studioBundle, `${c.studioBundle} vs dist/studio/testid-inventory.json ${v.studioBundle}`, { evidence: ev });
  t.check('recentErrors empty at boot', Array.isArray(diag.json?.recentErrors) && diag.json.recentErrors.length === 0, JSON.stringify(diag.json?.recentErrors ?? null).slice(0, 300), { evidence: ev });
  t.info('daemon boot', `${ctx.daemon.bootMs} ms to /health (skills seed included)`);

  // The studio index is served same-origin and IS the bundled dist (asset names match).
  const index = await api.raw('/');
  t.check('GET / serves the studio index', index.status === 200 && /<div id="root"|<script[^>]+type="module"/.test(index.text), `status ${index.status}, ${index.text.length} bytes`);
  const assets = [...index.text.matchAll(/(?:src|href)="\/?(assets\/[^"]+)"/g)].map((m) => m[1]);
  const distAssets = assets.filter((a) => existsSync(join(ctx.tree.crewDir, 'dist', 'studio', a)));
  t.check('served index references the bundled assets', assets.length > 0 && distAssets.length === assets.length, `${distAssets.length}/${assets.length} assets resolve under dist/studio`);
  const inv = await api.raw('/testid-inventory.json');
  let served = null;
  try { served = JSON.parse(inv.text).studioVersion ?? null; } catch { /* not served */ }
  if (inv.status === 200) t.check('served testid-inventory.json marker == studioBundle', served === c.studioBundle, `${served} vs ${c.studioBundle}`);
  else t.info('testid-inventory.json', `not served over HTTP (${inv.status}); marker read from disk: ${v.studioBundle}`);

  // Engine binary probes are honest: the shimmed estate answers, wicked-core is absent → null.
  t.info('engineBinaries', JSON.stringify(c.engineBinaries ?? null).slice(0, 200));
  ctx.state.bootDiagnostics = diag.json;
  void readFileSync; // (kept for parity with other steps' file reads)
}
