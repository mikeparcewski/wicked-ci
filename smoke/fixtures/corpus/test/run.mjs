// The repository's check runner. Node ≥ 24 writes an on-disk compile cache under the temp dir by
// default; inside the engine's checks sandbox that temp dir is the worktree's own scratch, and every
// cache file becomes one "EXCLUDED (scratch-dir)" line in the deliver phase's output — hundreds of
// them, enough to push the PR URL past the daemon's unit-output cap (observed: `delivery: stranded`
// on a run whose branch was pushed and whose PR was opened). The corpus keeps its check output small
// and deterministic by switching the cache off for the test process (cross-platform: no shell `VAR=`).
import { spawnSync } from 'node:child_process';

const r = spawnSync(process.execPath, ['--test', 'test/add.test.js'], {
  stdio: 'inherit',
  env: { ...process.env, NODE_DISABLE_COMPILE_CACHE: '1' },
});
process.exit(r.status ?? 1);
