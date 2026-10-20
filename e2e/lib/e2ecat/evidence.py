"""Evidence integrity: hash every evidence file, freeze the hashes in wicked-vault, re-check them.

Per capability the runner writes `<cap>/evidence-manifest.json`:

    {"id", "run_id", "verdict", "result_sha256", "files": {"<run-relative path>": "<sha256>"}}

and records it with `wicked-vault record --artifact <manifest>` (the vault CLI garden's `prove`
uses; scope `e2e:<run_id>`, phase `certify`, claim = the capability id). The vault copies the
manifest into `.wicked-vault/payloads/<sha256>` and binds it into a hashed entry, so the frozen
copy is what `validate --report` trusts: it re-hashes `result.json` and every evidence file against
the FROZEN manifest. Editing an evidence file, the result (a verdict flipped after recording), or
the manifest itself is detected. As wicked-vault documents, unkeyed hashes catch mutation, not a
determined local writer who also rewrites the vault; the vault's committed history is the audit
trail.
"""
import hashlib
import json
import os
import shutil
import subprocess

VAULT_ENV = {"WICKED_VAULT_NO_BUS": "1"}  # never emit onto a shared bus from a certification run
PHASE = "certify"
KIND = "e2e-evidence"
ACTOR = "e2e-runner"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(run_dir, path):
    return os.path.relpath(path, run_dir).replace(os.sep, "/")


def evidence_paths(result):
    out = []
    for paths in (result.get("evidence") or {}).values():
        out.extend(paths if isinstance(paths, list) else [paths])
    return sorted(set(out))


def write_manifest(run_dir, run_id, cid, result_path, result):
    files = {}
    for p in evidence_paths(result):
        full = os.path.join(run_dir, p)
        if os.path.isfile(full):
            files[p] = sha256_file(full)
    man = {"id": cid, "run_id": run_id, "verdict": result.get("verdict"),
           "result_sha256": sha256_file(result_path), "files": files}
    mp = os.path.join(os.path.dirname(result_path), "evidence-manifest.json")
    with open(mp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return mp


def vault_cli():
    """argv prefix of the wicked-vault CLI, or None. `E2E_VAULT` overrides (e.g. `npx -y wicked-vault`)."""
    env = os.environ.get("E2E_VAULT")
    if env:
        return json.loads(env) if env.lstrip().startswith("[") else env.split()
    p = shutil.which("wicked-vault") or shutil.which("wicked-vault.cmd")
    return [p] if p else None


def _ancestor_vault(run_dir):
    d = os.path.dirname(os.path.realpath(run_dir))
    while True:
        if os.path.isdir(os.path.join(d, ".wicked-vault")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            return None
        d = nd


class Vault:
    """The run's own vault at `<run-dir>/.wicked-vault` (a nested vault always wins over an ancestor)."""

    def __init__(self, run_dir, argv=None, runner=subprocess.run):
        self.run_dir = os.path.abspath(run_dir)
        self.argv = argv if argv is not None else vault_cli()
        self.run = runner

    def _call(self, *args):
        env = dict(os.environ, **VAULT_ENV)
        r = self.run(self.argv + list(args), cwd=self.run_dir, capture_output=True, text=True, timeout=120, env=env)
        try:
            doc = json.loads(r.stdout) if r.stdout.strip() else {}
        except ValueError:
            doc = {"raw": r.stdout[-2000:]}
        return r.returncode, doc, r.stderr[-2000:]

    def version(self):
        try:
            r = self.run(self.argv + ["--version"], capture_output=True, text=True, timeout=60)
            return (r.stdout or "").strip()
        except OSError:
            return None

    def init(self):
        if not self.argv:
            raise RuntimeError("wicked-vault CLI not found (install wicked-vault, or set E2E_VAULT)")
        # `init` creates the vault at the start dir; we init first so no ancestor vault is ever used.
        rc, doc, err = self._call("init", "--cwd", self.run_dir)
        if not os.path.isdir(os.path.join(self.run_dir, ".wicked-vault")):
            # Never record into an ancestor's vault (the walk-up footgun): the run's own vault or none.
            raise RuntimeError("wicked-vault init did not create %s/.wicked-vault (exit %s; ancestor vault: %s): %s %s" % (
                self.run_dir, rc, _ancestor_vault(self.run_dir), doc, err))
        return doc

    def record(self, scope, claim, manifest_path, criteria):
        relp = rel(self.run_dir, manifest_path)
        rc, doc, err = self._call("record", "--cwd", self.run_dir, "--scope", scope, "--phase", PHASE,
                                  "--claim", claim, "--kind", KIND, "--source", relp, "--criteria", criteria,
                                  "--artifact", relp, "--actor", ACTOR)
        if rc != 0 or not doc.get("id"):
            raise RuntimeError("wicked-vault record %s failed (exit %s): %s %s" % (claim, rc, doc, err))
        return doc

    def verify(self, artifact_id):
        rc, doc, _ = self._call("verify", artifact_id, "--cwd", self.run_dir)
        return rc == 0 and doc.get("hash_ok") is True, doc


RUN_CLAIM = "e2e-run"


def _frozen(vdir, scope, claim, aid):
    """(manifest, failure) from a vault entry: the entry must exist, name `claim` in `scope`, and its
    payload must hash to the entry."""
    if not aid:
        return None, "no vault entry"
    ep = os.path.join(vdir, "entries", aid + ".json")
    if not os.path.isfile(ep):
        return None, "vault entry %s missing" % aid
    with open(ep, encoding="utf-8") as fh:
        entry = json.load(fh)
    if entry.get("claim_id") != claim or entry.get("scope") != scope:
        return None, "vault entry %s records claim %r in scope %r" % (aid, entry.get("claim_id"), entry.get("scope"))
    pp = os.path.join(vdir, entry.get("payload_ref") or ("payloads/" + str(entry.get("payload_sha256"))))
    if not os.path.isfile(pp):
        return None, "the frozen manifest (vault payload) is missing"
    with open(pp, "rb") as fh:
        raw = fh.read()
    if sha256_bytes(raw) != entry.get("payload_sha256"):
        return None, "the vault payload does not hash to its entry (vault tampered)"
    try:
        return json.loads(raw.decode("utf-8")), None
    except ValueError:
        return None, "the frozen manifest is not JSON"


def _check_frozen(vdir, scope, claim, aid, label, fn):
    man, err = _frozen(vdir, scope, claim, aid)
    if err:
        return ["%s: %s" % (label, err)]
    return ["%s: %s" % (label, f) for f in fn(man)]


def check_bundle(run_dir, run, selected, results, vault_argv=None, use_cli=True):
    """Re-derive every capability's hashes from the frozen vault copy. Returns failure strings."""
    fails = []
    vinfo = run.get("vault") or {}
    if not vinfo or vinfo.get("disabled"):
        return ["run.json: the evidence bundle is not recorded in wicked-vault (%s); hashes cannot be verified"
                % (vinfo.get("disabled") if vinfo else "no `vault` entry")]
    vdir = os.path.join(run_dir, ".wicked-vault")
    idx_p = os.path.join(run_dir, vinfo.get("index", "vault-index.json"))
    if not os.path.isdir(vdir) or not os.path.isfile(idx_p):
        return ["the run's vault (.wicked-vault/ and %s) is missing" % vinfo.get("index", "vault-index.json")]
    with open(idx_p, encoding="utf-8") as fh:
        index = json.load(fh)
    scope = vinfo.get("scope")
    if index.get("scope") != scope:
        fails.append("vault index scope %r != run.json vault scope %r" % (index.get("scope"), scope))
    cli = Vault(run_dir, argv=vault_argv) if use_cli else None
    if cli is not None and not cli.argv:
        cli = None
    fails += _check_frozen(vdir, scope, RUN_CLAIM, index.get("run"), "run.json",
                           lambda man: [] if man.get("run_json_sha256") == sha256_file(os.path.join(run_dir, "run.json"))
                           else ["run.json changed after it was recorded (hash differs from the vault)"])
    if cli is not None and index.get("run"):
        ok, doc = cli.verify(index["run"])
        if not ok:
            fails.append("run.json: wicked-vault verify %s did not pass: %s" % (index["run"], doc.get("detail") or doc))
    for cid in selected:
        res = results.get(cid)
        if res is None:
            continue
        aid = (index.get("entries") or {}).get(cid)
        man, err = _frozen(vdir, scope, cid, aid)
        if err:
            fails.append("%s: %s" % (cid, err))
            continue
        if man.get("id") != cid:
            fails.append("%s: the frozen manifest names %r" % (cid, man.get("id")))
        rp = os.path.join(run_dir, cid, "result.json")
        if sha256_file(rp) != man.get("result_sha256"):
            fails.append("%s: result.json changed after it was recorded (hash differs from the vault)" % cid)
        files = man.get("files") or {}
        for p in evidence_paths(res):
            if p not in files:
                fails.append("%s: evidence %s was not hash-recorded" % (cid, p))
        for p, h in sorted(files.items()):
            full = os.path.join(run_dir, p)
            if not os.path.isfile(full):
                fails.append("%s: recorded evidence %s is gone" % (cid, p))
            elif sha256_file(full) != h:
                fails.append("%s: evidence %s changed after it was recorded (sha256 differs)" % (cid, p))
        if cli is not None:
            ok, doc = cli.verify(aid)
            if not ok:
                fails.append("%s: wicked-vault verify %s did not pass: %s" % (cid, aid, doc.get("detail") or doc))
    return fails


def inspect(run_dir, cid, use_cli=True, vault_argv=None):
    """One capability's evidence, file by file, with its integrity against the vault's frozen manifest.

    Returns {"id", "verdict", "scenario", "evidence": [{"kind", "path", "abs", "sha256", "status"}],
    "result": {...}, "vault": {...}, "intact": bool, "problems": [...]}. A file's status is `ok` (its hash
    matches the frozen copy), `changed`, `gone`, `not-recorded` or `outside` (the path escapes the run
    directory, so it is not read); `intact` is true only when the run is
    sealed, the frozen manifest is well formed, every file and result.json match, and (when the CLI is on
    PATH, as `validate --report` does) `wicked-vault verify` passes."""
    run_dir = os.path.abspath(run_dir)
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    rp = os.path.join(run_dir, cid, "result.json")
    if cid not in run.get("capabilities", []):
        raise KeyError("%s is not a capability of this run" % cid)
    if not os.path.isfile(rp):
        raise KeyError("%s has no result.json in this run" % cid)
    with open(rp, encoding="utf-8") as fh:
        res = json.load(fh)
    problems, man = [], None
    vinfo = run.get("vault") or {}
    vault = {"scope": vinfo.get("scope"), "entry": None, "sealed": bool(vinfo.get("scope")) and not vinfo.get("disabled")}
    if not vault["sealed"]:
        problems.append("the run is not sealed in wicked-vault (%s): nothing can be verified" % (
            vinfo.get("disabled") or "no vault entry"))
    else:
        idx_p = os.path.join(run_dir, vinfo.get("index", "vault-index.json"))
        index = {}
        if os.path.isfile(idx_p):
            with open(idx_p, encoding="utf-8") as fh:
                index = json.load(fh)
        aid = (index.get("entries") or {}).get(cid)
        vault["entry"] = aid
        man, err = _frozen(os.path.join(run_dir, ".wicked-vault"), vinfo.get("scope"), cid, aid)
        if err:
            problems.append(err)
    if man is not None and not (isinstance(man, dict) and man.get("result_sha256") and isinstance(man.get("files"), dict)):
        problems.append("the frozen manifest is malformed (no result_sha256 or files)")
        man = None
    files = (man or {}).get("files") or {}
    result_ok = bool(man) and sha256_file(rp) == man.get("result_sha256")
    if man and not result_ok:
        problems.append("result.json changed after it was recorded (the verdict may have been edited)")
    rows = []
    for kind, paths in sorted((res.get("evidence") or {}).items()):
        for p in (paths if isinstance(paths, list) else [paths]):
            full = os.path.join(run_dir, p)
            real, base = os.path.realpath(full), os.path.realpath(run_dir)
            try:
                inside = os.path.commonpath([base, real]) == base and real != base
            except ValueError:  # another drive on Windows
                inside = False
            h = sha256_file(full) if inside and os.path.isfile(full) else None
            if not inside:
                st = "outside"
            elif h is None:
                st = "gone"
            elif not man:
                st = "unverified"
            elif p not in files:
                st = "not-recorded"
            elif files[p] != h:
                st = "changed"
            else:
                st = "ok"
            if st in ("gone", "not-recorded", "changed", "outside"):
                problems.append("%s %s: %s" % (kind, p, st))
            rows.append({"kind": kind, "path": p, "abs": full, "sha256": h, "status": st})
    for p in sorted(set(files) - {r["path"] for r in rows}):
        problems.append("recorded evidence %s is no longer listed in result.json" % p)
    if use_cli and vault["entry"]:
        cli = Vault(run_dir, argv=vault_argv)
        if cli.argv:
            ok, doc = cli.verify(vault["entry"])
            vault["verify"] = "pass" if ok else "fail"
            if not ok:
                problems.append("wicked-vault verify %s did not pass: %s" % (vault["entry"], doc.get("detail") or doc))
        else:
            vault["verify"] = "skipped (wicked-vault CLI not found)"
    return {"id": cid, "verdict": res.get("verdict"), "reason": res.get("reason"), "scenario": res.get("scenario"),
            "evidence": rows, "result": {"path": "%s/result.json" % cid, "abs": rp, "status": "ok" if result_ok else
                                         ("changed" if man else "unverified")},
            "vault": vault, "problems": problems,
            "intact": bool(vault["sealed"] and man and result_ok and not problems and all(r["status"] == "ok" for r in rows))}
