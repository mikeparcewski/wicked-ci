// S02 skills — the garden plugin the daemon seeds from (marketplace-cache layout) publishes cleanly:
// state `published`, every skill portable, no findings. Then the F-083 class: a current generation
// published under OLDER portability rules must be ACCEPTED with exactly one `skills.stale-rules`
// warning, never refused into `config-error` (an upgrade must not brick the skills root).
import { chmodSync, existsSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

export const id = 'S02';
export const name = 'skills';

export async function run(ctx, t) {
  await ctx.ensureDaemon();
  let api = ctx.api();

  const diag = await api.get('/diagnostics');
  const skills = diag.json?.skills ?? null;
  const ev = t.evidence('diagnostics-skills', skills);
  t.check('skills.state == published', skills?.state === 'published', `state ${skills?.state}; findings ${JSON.stringify(skills?.findings ?? []).slice(0, 300)}`, { evidence: ev });
  t.check('skills.current.gen >= 1', Number(skills?.current?.gen) >= 1, `gen ${skills?.current?.gen}`);
  t.check('skills.engineInput points inside the temp root', typeof skills?.engineInput === 'string' && skills.engineInput.startsWith(ctx.L.root), String(skills?.engineInput));
  const findings = Array.isArray(skills?.findings) ? skills.findings : [];
  t.check('skills.findings == [] (garden class: the published plugin has no blocking/warning finding)', findings.length === 0, JSON.stringify(findings).slice(0, 400), { evidence: ev });

  const sk = await api.get('/skills');
  const manifest = sk.json?.manifest ?? {};
  const entries = manifest.skills && typeof manifest.skills === 'object' ? Object.entries(manifest.skills) : [];
  const portable = entries.filter(([, s]) => s.portable === true).length;
  const ev2 = t.evidence('skills-manifest-summary', { revision: sk.json?.revision, current: sk.json?.current, total: entries.length, portable, nonPortable: entries.filter(([, s]) => s.portable !== true).map(([n]) => n) });
  t.check('GET /skills 200', sk.status === 200, `status ${sk.status}`);
  t.check('manifest lists skills', entries.length > 0, `${entries.length} skills`, { evidence: ev2 });
  t.check('portable count == total', entries.length > 0 && portable === entries.length, `${portable}/${entries.length} portable`, { evidence: ev2 });
  t.check('current.rules.stale == false on a fresh publish', sk.json?.current?.rules?.stale === false, JSON.stringify(sk.json?.current?.rules ?? null).slice(0, 300));

  // F-E2E-002: the boot publish's warnings are only in the daemon log; /diagnostics says [].
  const landed = ctx.daemon.grepLog(/first publish landed with (\d+) warning/, 0, 1)[0] ?? null;
  const warnCount = landed ? Number(landed.match(/landed with (\d+) warning/)?.[1] ?? 0) : 0;
  t.info('boot publish log', landed ? landed.slice(0, 300) : 'no "first publish landed with N warning(s)" line');
  if (warnCount > 0) {
    t.check('publish warnings visible in /diagnostics.skills.findings (F-E2E-002)', findings.length >= warnCount, `daemon log: ${warnCount} warning(s); diagnostics findings: ${findings.length}`, { finding: 'F-E2E-002', evidence: ev });
  }

  // ── F-083: a generation published under OLDER rules must be accepted with ONE warning ──
  const snapDir = skills?.current?.path;
  const manifestPath = snapDir ? join(snapDir, 'snapshot.json') : null;
  t.check('current snapshot manifest exists', manifestPath !== null && existsSync(manifestPath), String(manifestPath));
  if (manifestPath && existsSync(manifestPath)) {
    const snap = JSON.parse(readFileSync(manifestPath, 'utf8'));
    const recorded = { rulesVersion: snap.rulesVersion, rulesSha256: snap.rulesSha256 };
    t.check('snapshot records the rules identity (rulesVersion + rulesSha256)', Number.isInteger(snap.rulesVersion) && typeof snap.rulesSha256 === 'string', JSON.stringify(recorded));
    // Republish under OLDER rules: rewrite the recorded identity, restart the daemon (verification of
    // `current` happens on load), read the verdict.
    snap.rulesVersion = Math.max(1, Number(snap.rulesVersion ?? 2) - 1);
    snap.rulesSha256 = '0'.repeat(64);
    // What an OLDER daemon would have left on disk: the generation's snapshot.json recording ITS rules
    // identity, and the root's manifest.json `published.snapshotHash` = sha256 of that file (the store
    // authenticates the metadata against it — a mismatch is tampering, refused; the same-authenticated
    // bytes under other rules is drift, accepted with the warning). The generation is LOCKED read-only
    // (immutable), so the lock is lifted for the rewrite and restored; the ORIGINAL bytes are kept so
    // the root can be put back if the product refuses — a refusal must never poison the later steps.
    const rootManifestPath = join(skills.root, 'manifest.json');
    const origSnapBytes = readFileSync(manifestPath);
    const origRootBytes = existsSync(rootManifestPath) ? readFileSync(rootManifestPath) : null;
    const newSnapBytes = Buffer.from(JSON.stringify(snap, null, 1));
    const rawSha = createHash('sha256').update(newSnapBytes).digest('hex');
    const dirMode = statSync(snapDir).mode & 0o777;
    const fileMode = statSync(manifestPath).mode & 0o777;
    const writeLocked = (bytes) => {
      chmodSync(snapDir, 0o755);
      chmodSync(manifestPath, 0o644);
      writeFileSync(manifestPath, bytes);
      chmodSync(manifestPath, fileMode);
      chmodSync(snapDir, dirMode);
    };
    writeLocked(newSnapBytes);
    let restamped = false;
    if (origRootBytes) {
      const rm = JSON.parse(origRootBytes.toString('utf8'));
      if (rm.published && rm.published.gen === snap.gen) { rm.published.snapshotHash = rawSha; restamped = true; }
      writeFileSync(rootManifestPath, JSON.stringify(rm, null, 2));
    }
    t.info('stale-rules injection', `snapshot.json rulesVersion -> ${snap.rulesVersion}, rulesSha256 -> zeros; manifest.json published.snapshotHash re-stamped=${restamped}; restarting daemon`);
    await ctx.daemon.restart();
    api = ctx.api();
    const diag2 = await api.get('/diagnostics');
    const s2 = diag2.json?.skills ?? null;
    const ev3 = t.evidence('diagnostics-skills-after-stale-rules', s2);
    const stale = (s2?.findings ?? []).filter((f) => f.kind === 'skills.stale-rules');
    const others = (s2?.findings ?? []).filter((f) => f.kind !== 'skills.stale-rules');
    t.check('stale-rules generation ACCEPTED (state still published, F-083)', s2?.state === 'published', `state ${s2?.state}: ${JSON.stringify(s2?.findings ?? []).slice(0, 300)}`, { evidence: ev3 });
    t.check('exactly ONE skills.stale-rules warning', stale.length === 1 && (stale[0].severity ?? 'warning') === 'warning', `${stale.length} stale-rules finding(s): ${JSON.stringify(stale).slice(0, 300)}`, { evidence: ev3 });
    t.check('no other new finding from the stale-rules republish', others.length === findings.length, `${others.length} other finding(s)`, { evidence: ev3 });
    const sk2 = await api.get('/skills');
    t.check('GET /skills current.rules.stale == true', sk2.json?.current?.rules?.stale === true, JSON.stringify(sk2.json?.current?.rules ?? null).slice(0, 300));
    t.check('engineInput still a real snapshot (not the refused/ path)', typeof s2?.engineInput === 'string' && !/refused/.test(s2.engineInput) && s2.engineInput.startsWith(ctx.L.root), String(s2?.engineInput));
    if (s2?.state !== 'published') {
      // Put the root back exactly as the daemon published it, so S03+ run on a healthy skills root.
      writeLocked(origSnapBytes);
      if (origRootBytes) writeFileSync(rootManifestPath, origRootBytes);
      await ctx.daemon.restart();
      api = ctx.api();
      const d3 = await api.get('/diagnostics');
      t.info('root restored', `after restoring the original bytes: skills.state ${d3.json?.skills?.state}`);
    }
  }
}
