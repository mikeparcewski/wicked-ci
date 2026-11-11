# Releasing wicked-selftest

`selftest/` publishes to npm as `wicked-selftest` through `.github/workflows/selftest-release.yml`. The trigger is a
tag `selftest-v<X.Y.Z>` that equals `selftest/package.json`'s version. The workflow runs the offline selfchecks,
checks what the tarball holds, and publishes from `selftest/` with provenance, using npm trusted publishing (OIDC, no
token).

## A release

1. In a PR, bump `selftest/package.json` `version` and add a `CHANGELOG.md` entry. Merge it.
2. Tag the merge commit and push only that tag:

   ```bash
   git tag selftest-vX.Y.Z <merge sha> && git push origin selftest-vX.Y.Z
   ```

3. Check that `npm view wicked-selftest@X.Y.Z dist.attestations` shows a provenance attestation.

A product repo pins the suite by version (`wicked-selftest@X.Y.Z`); `latest` never decides a verdict. PR CI pins the
reusable workflow by wicked-ci SHA instead, so it does not wait for a publish.

## The first publish (operator, once)

npm can only register a trusted publisher on a package that already exists, so the first version is published by
hand:

1. On a checkout of the merge commit, sign in to npm as the account that will own the package:
   `npm login` (2FA as your account requires).
2. Check the tarball first: `cd selftest && npm pack --dry-run`. You should see bin/, lib/, journeys/, shims/,
   fixtures/, README.md and package.json, and no node_modules or .pyc files.
3. Publish: `cd selftest && npm publish --access public`. Provenance needs CI, so this first version has none.
4. On npmjs.com, open wicked-selftest → Settings → Trusted publishing → GitHub Actions, and enter:
   - Organization or user: `mikeparcewski`
   - Repository: `wicked-ci`
   - Workflow filename: `selftest-release.yml`
   - Environment: leave it empty
5. Optionally, on the same page set "Publishing access" to "Require two-factor authentication and disallow tokens".
   After that, only the workflow can publish.
6. Every later version: the tag steps above.
