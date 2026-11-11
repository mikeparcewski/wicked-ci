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

npm can register a trusted publisher only on a package that already exists, so the first version is published by
hand. A trusted publisher that is not used within two days of its creation expires, so set it up only when the first
automated release is ready.

1. On a checkout of the merge commit, sign in to npm as the account that will own the package: `npm login` (with
   2FA, as your account requires).
2. Check the tarball, then publish it without provenance (provenance needs a CI provider, and `publishConfig` asks
   for it):

   ```bash
   cd selftest
   npm pack --dry-run          # bin/, lib/, journeys/, shims/, fixtures/, README.md, RELEASING.md, package.json
   npm publish --access public --provenance=false
   ```

3. On npmjs.com, open wicked-selftest, then Settings → Publishing access. Choose "Require two-factor authentication
   and disallow tokens", and revoke any automation or granular token that can publish it. Maintainers can still
   publish by hand with 2FA. No token can.
4. In GitHub, open wicked-ci → Settings → Environments → New environment `npm-release`:
   - Required reviewers: the operator.
   - Deployment branches and tags: selected tags matching `selftest-v*`.
5. When the next version is ready to tag, go to npmjs.com, wicked-selftest → Settings → Trusted publishing →
   GitHub Actions, and enter:
   - Organization or user: `mikeparcewski`
   - Repository: `wicked-ci`
   - Workflow filename: `selftest-release.yml`
   - Environment: `npm-release`
6. Within two days, tag that version (the release steps above) and approve the `npm-release` deployment. If the
   trusted publisher expired first, delete it and create it again.

Only admins can create tags here (the `release-tags` ruleset). The workflow publishes only a tag whose commit is on
`main`, and only after the environment's reviewer approves.
