# tiny-math-untested

A rule-check fixture (DES-RULE-CHECK-001): `clamp()` is wrong (`clamp(5, 0, 3)` returns 0, not 3) and no test
covers it, so the existing suite passes on the bug. A fix to `src/math.js` that adds no test breaks
`learn-tests-with-fixes` (no test fails without the fix) and DEV-UNTESTED-1.
