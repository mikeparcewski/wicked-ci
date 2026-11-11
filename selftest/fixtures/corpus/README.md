# wicked-smoke corpus

A fixed, dependency-free repository the smoke harness registers, onboards and runs the seeded `bug`
workflow against. `src/add.js` ships with a sign error so `npm test` fails until the run's `fix`
phase corrects it; the repository's own check (`npm test` → `node test/run.mjs` → `node --test
test/add.test.js` with node's compile cache off) is what the engine's repo-checks floor re-runs in
the worktree.
