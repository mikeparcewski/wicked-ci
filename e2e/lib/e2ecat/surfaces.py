"""Surface manifests: the user-facing elements of each wicked-* repo, read from source.

Every extractor reads a checkout (never a running product) and returns a list of elements
``{key, kind, name, files}``. ``key`` is the stable surface key a capability lists in ``covers``
(``<repo-short>:<kind>:<name>``). The manifest also carries the repo's test index (the tracked
files that hold tests) so a scenario reference can be checked offline.

Nothing here executes a product binary. The one network read is ``npm pack`` of the published
wicked-crew tarball, whose compiled CLI text is parsed for the command list.
"""
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from .util import read_text

# repo name -> surface key prefix
REPOS = {
    "wicked-studio": "studio",
    "wicked-crew": "crew",
    "wicked-estate": "estate",
    "wicked-garden": "garden",
    "wicked-core": "core",
    "wicked-interactive": "interactive",
    "wicked-bus": "bus",
    "wicked-vault": "vault",
    "wicked-ledger": "ledger",
    "wicked-installer": "installer",
}
SHORT_TO_REPO = {v: k for k, v in REPOS.items()}


class ExtractError(Exception):
    pass


def _read(root, rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        raise ExtractError("%s: expected file missing: %s" % (os.path.basename(root), rel))
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _el(prefix, kind, name, files=(), **extra):
    e = {"key": "%s:%s:%s" % (prefix, kind, name), "kind": kind, "name": name,
         "files": sorted(set(files))}
    e.update(extra)
    return e


def git_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True).stdout
    return sorted(p for p in out.decode("utf-8").split("\0") if p)


def git_sha(root):
    return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


TEST_DIRS = {"test", "tests", "e2e", "__tests__", "spec", "smoke", "evidence"}
TEST_NAME = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|_spec\.|^tests?\.)")
RUST_TEST = re.compile(r"#\[(cfg\(test\)|test|tokio::test)\]")
# A scenario must be something that runs: data files, fixtures and markdown scenario write-ups are not tests.
EXECUTABLE = (".py", ".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".sh", ".bash", ".rs", ".yml", ".yaml")


def test_index(root, files):
    """Tracked, executable files that hold tests: test dirs/names, CI workflows, Rust files with test items."""
    idx = []
    for p in files:
        segs = p.split("/")
        if not p.endswith(EXECUTABLE) or "fixtures" in segs[:-1]:
            continue
        if p.startswith(".github/workflows/") or TEST_DIRS.intersection(segs[:-1]) or TEST_NAME.search(segs[-1]):
            idx.append(p)
        elif p.endswith(".rs"):
            try:
                with open(os.path.join(root, p), encoding="utf-8", errors="replace") as fh:
                    if RUST_TEST.search(fh.read()):
                        idx.append(p)
            except OSError:
                pass
    return idx


# ── studio ────────────────────────────────────────────────────────────────────────────────────

def studio(root, _ctx):
    inv = json.loads(_read(root, "testid-inventory.json"))
    els = []
    for t in inv["static"]:
        els.append(_el("studio", "testid", t["testId"], t["files"]))
    for t in inv["dynamic"]:
        els.append(_el("studio", "testid-pattern", t["pattern"], t["files"]))
    for t in inv["computed"]:
        els.append(_el("studio", "testid-computed", t["expression"], t["files"]))
    src = _read(root, "src/hooks/useRoute.ts")
    rf = ["src/hooks/useRoute.ts"]
    routes = route_shapes(src, lambda name: _predicate_values(root, name))
    m = re.search(r"const PANELS: Panel\[\] = \[([^\]]*)\]", src)
    if not m:
        raise ExtractError("wicked-studio: PANELS list not found in src/hooks/useRoute.ts")
    for p in re.findall(r"'([a-z-]+)'", m.group(1)):
        routes.add("/" + p)
    m = re.search(r"RETIRED_ADDRESSES: readonly string\[\] = \[(.*?)\];", src, re.S)
    if not m:
        raise ExtractError("wicked-studio: RETIRED_ADDRESSES not found")
    retired = re.findall(r"'([^']+)'", m.group(1))
    routes -= set(retired)
    if not {"/runs/new", "/runs/:id/events", "/testing/campaigns/:id", "/rules/:id"} <= routes:
        raise ExtractError("wicked-studio: route extraction lost a known nested route; the parse() shape changed")
    for r in sorted(routes):
        els.append(_el("studio", "route", r, rf))
    for r in retired:
        els.append(_el("studio", "retired-route", r, rf))
    return els, {"studioVersion": inv.get("studioVersion")}


def _predicate_values(root, name):
    """`isTestingSubPage` -> the values of the const array its body tests membership in."""
    for f in sorted(os.listdir(os.path.join(root, "src", "api"))):
        if not f.endswith(".ts"):
            continue
        txt = _read(root, "src/api/" + f)
        m = re.search(r"export function %s\([^)]*\)[^{]*\{(.*?)\n\}" % re.escape(name), txt, re.S)
        if not m:
            continue
        c = re.search(r"\(?([A-Z][A-Z_]+)\b", m.group(1))
        if c:
            arr = re.search(r"export const %s\b[^=]*=\s*\[([^\]]*)\]" % c.group(1), txt)
            if arr:
                return re.findall(r"'([a-z0-9-]+)'", arr.group(1))
    raise ExtractError("wicked-studio: cannot resolve the values of %s()" % name)


def route_shapes(src, predicate_values):
    """Address shapes from useRoute.ts parse(): each `if (first === ...)` block read whole."""
    body = src[src.index("function parse(pathname"):]
    body = body[:body.index("\n}\n")]
    lines = body.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"  if \(\(?first === '", ln)]
    routes = {"/"}
    for n, i in enumerate(starts):
        block = "\n".join(lines[i:starts[n + 1] if n + 1 < len(starts) else len(lines)])
        head = lines[i]
        for first in re.findall(r"first === '([a-z0-9-]*)'", head):
            if not first:
                continue
            base = "/" + first
            seconds = re.findall(r"second === '([a-z0-9-]+)'", head)
            if seconds:
                for sec in seconds:
                    routes.add("%s/%s" % (base, sec))
                continue
            if re.search(r"third === '([a-z]+)'", head):
                routes.add("%s/:id/%s" % (base, re.search(r"third === '([a-z]+)'", head).group(1)))
                continue
            if re.search(r"&& second(\)| &&)", head):
                routes.add(base + "/:id")
                if re.search(r"third === 'a' && fourth", block):
                    routes.add(base + "/:id/a/:key")
                continue
            routes.add(base)
            inner = block[len(head):]
            for sec, rest in re.findall(r"second === '([a-z0-9-]+)'( && third)?", inner):
                routes.add("%s/%s%s" % (base, sec, "/:id" if rest else ""))
            for third in re.findall(r"second && third === '([a-z0-9-]+)'", inner):
                routes.add("%s/:id/%s" % (base, third))
            for pred in re.findall(r"\b(is[A-Z]\w+)\(second\)", inner):
                for val in predicate_values(pred):
                    routes.add("%s/%s" % (base, val))
            if re.search(r"second \? safeDecode\(second\)", inner):
                routes.add(base + "/:id")
    return routes


# ── crew ──────────────────────────────────────────────────────────────────────────────────────

def _npm_pack(pkg, version, workdir):
    spec = "%s@%s" % (pkg, version)
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise ExtractError("npm not found: needed to read the published %s CLI" % spec)
    r = subprocess.run([npm, "pack", spec, "--silent", "--pack-destination", workdir],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise ExtractError("npm pack %s failed: %s" % (spec, r.stderr.strip()[-400:]))
    tgz = os.path.join(workdir, r.stdout.strip().splitlines()[-1])
    with tarfile.open(tgz) as tf:
        members = {m.name: m for m in tf.getmembers()}
        out = {}
        for name in ("package/dist/cli/index.js", "package/dist/cli/governance.js", "package/package.json"):
            if name in members:
                out[name[len("package/"):]] = tf.extractfile(members[name]).read().decode("utf-8")
    return out


def crew_cli_from_text(index_js, governance_js):
    tops = [u for u in re.findall(r"Usage: wicked-crew ([a-z|-]+)", index_js) if "|" in u]
    if not tops:
        raise ExtractError("wicked-crew: top-level usage line (serve|start|...) not found in the CLI")
    cmds = [c for c in tops[0].split("|") if c]
    if "--install-service" in index_js:
        cmds += ["serve --install-service", "serve --uninstall-service"]
    for sub in sorted(set(re.findall(r"wicked-crew governance ([a-z]+)", governance_js or ""))):
        cmds.append("governance " + sub)
    return cmds


def crew(root, ctx):
    rel = "packages/crew/endpoint-manifest.json"
    man = json.loads(_read(root, rel))
    els = [_el("crew", "route", "%s %s" % (e["method"], e["path"]), [rel]) for e in man["endpoints"]]
    for f in git_files_cached(ctx, root):
        if f.startswith("packages/crew/src/") and f.endswith(".ts"):
            txt = read_text(os.path.join(root, f))
            for ws in re.findall(r"""['"`](/ws(?:/[a-z]+(?:/:[a-z]+)?)?)['"`]""", txt):
                els.append(_el("crew", "ws", ws, [f]))
    ws = sorted(e["name"] for e in els if e["kind"] == "ws")
    els = [e for e in els if e["kind"] != "ws" or not any(o != e["name"] and o.startswith(e["name"] + "/") for o in ws)
           or e["name"] == "/ws"]
    mcp_rel = "packages/crew/src/cli/mcp.ts"
    for name in re.findall(r"server\.tool\(\s*'([a-z_]+)'", _read(root, mcp_rel)):
        els.append(_el("crew", "mcp", name, [mcp_rel]))
    ask_rel = "packages/crew/src/mcp/ask-server.ts"
    for name in re.findall(r"registerTool\('([a-z_]+)'", _read(root, ask_rel)):
        els.append(_el("crew", "mcp", name, [ask_rel]))
    meta = {}
    pub = ctx.get("crew_npm")
    if pub:
        work = tempfile.mkdtemp(prefix="e2e-crew-pack-")
        try:
            files = _npm_pack("wicked-crew", pub, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if "dist/cli/index.js" not in files:
            raise ExtractError("wicked-crew@%s: dist/cli/index.js missing from the tarball" % pub)
        cmds = crew_cli_from_text(files["dist/cli/index.js"], files.get("dist/cli/governance.js", ""))
        src_files = ["npm:wicked-crew@%s/dist/cli/index.js" % pub]
        meta["cli_source"] = "npm:wicked-crew@%s" % pub
    else:
        cmds = crew_cli_from_text(_read(root, "packages/crew/src/cli/index.ts"),
                                  _read(root, "packages/crew/src/cli/governance.ts"))
        src_files = ["packages/crew/src/cli/index.ts"]
        meta["cli_source"] = "source"
    for c in cmds:
        els.append(_el("crew", "cli", c, src_files))
    meta["apiTypesVersion"] = man.get("apiTypesVersion")
    return els, meta


def git_files_cached(ctx, root):
    key = ("files", root)
    if key not in ctx:
        ctx[key] = git_files(root)
    return ctx[key]


# ── estate ────────────────────────────────────────────────────────────────────────────────────

def estate(root, _ctx):
    els = []
    lib_rel = "crates/wicked-estate-mcp/src/lib.rs"
    lib = _read(root, lib_rel)
    m = re.search(r"pub fn all_tools\(\)[^{]*\{\s*vec!\[(.*?)\]", lib, re.S)
    if not m:
        raise ExtractError("wicked-estate: all_tools() not found")
    structs = re.findall(r"Box::new\((\w+)\)", m.group(1)) + ["SemanticSearch"]
    names = {}
    retrieve = "crates/wicked-estate-retrieve/src"
    for f in sorted(os.listdir(os.path.join(root, retrieve))):
        if not f.endswith(".rs"):
            continue
        txt = _read(root, "%s/%s" % (retrieve, f))
        for im in re.finditer(r"impl\s+RetrievalTool\s+for\s+(\w+)\s*\{", txt):
            nm = re.search(r"fn name\(&self\)[^{]*\{\s*\"([^\"]+)\"", txt[im.end():im.end() + 4000])
            if nm:
                names[im.group(1)] = ("%s/%s" % (retrieve, f), nm.group(1))
    for s in structs:
        if s not in names:
            raise ExtractError("wicked-estate: tool struct %s has no RetrievalTool name" % s)
        f, n = names[s]
        extra = {"conditional": True} if s == "SemanticSearch" else {}
        els.append(_el("estate", "mcp", n, [lib_rel, f], **extra))
    tools = "crates/wicked-estate-mcp/src/tools"
    for f in ("memory.rs", "knowledge.rs", "proposals.rs"):
        rel = "%s/%s" % (tools, f)
        for n in re.findall(r"^\s+\"((?:memory|knowledge|proposal)\.[a-z_]+)\" =>", _read(root, rel), re.M):
            els.append(_el("estate", "mcp", n, [rel]))
    res_rel = "crates/wicked-estate-mcp/src/resources.rs"
    res = _read(root, res_rel)
    for u in sorted(set(re.findall(r"\"(skill://[a-z0-9_./-]+)\"", res))):
        els.append(_el("estate", "mcp-resource", u, [res_rel]))
    cf_rel = "crates/wicked-estate/src/cli_flags.rs"
    cmds = re.findall(r"Command \{\s*name:\s*\"([a-z][a-z-]*)\"", _read(root, cf_rel))
    for c in cmds:
        els.append(_el("estate", "cli", c, [cf_rel]))
    tb_rel = "crates/wicked-estate/src/tool_bridge.rs"
    tb = _read(root, tb_rel)
    for bm in re.finditer(r"BridgedCommand \{\s*name:\s*\"([a-z][a-z-]*)\",\s*aliases:\s*&\[([^\]]*)\]", tb):
        aliases = re.findall(r"\"([a-z-]+)\"", bm.group(2))
        els.append(_el("estate", "cli", bm.group(1), [tb_rel], aliases=aliases))
    if not cmds:
        raise ExtractError("wicked-estate: no CLI commands found")
    return els, {}


# ── garden ────────────────────────────────────────────────────────────────────────────────────

def garden(root, _ctx):
    rel = ".claude-plugin/components.json"
    comp = json.loads(_read(root, rel))
    els = []
    domain_of = {}
    for dom, members in comp["skills_by_domain"].items():
        for s in members:
            domain_of.setdefault(s, dom)
    for s in sorted(domain_of):
        d = "skills/%s/SKILL.md" % s
        els.append(_el("garden", "skill", s, [rel] + ([d] if os.path.isfile(os.path.join(root, d)) else []),
                       domain=domain_of[s]))
    for s in comp["fork_skills"]:
        els.append(_el("garden", "fork-skill", s, [rel]))
    hooks = json.loads(_read(root, "hooks/hooks.json"))
    for ev, entries in sorted(hooks.get("hooks", {}).items()):
        scripts = sorted(set(re.findall(r"hooks/scripts/[a-z_]+\.py", json.dumps(entries))))
        els.append(_el("garden", "hook", ev, ["hooks/hooks.json"] + scripts))
    inst = _read(root, "install.mjs")
    m = re.search(r"switch \(opts\.cmd\) \{(.*?)\n  \}", inst, re.S)
    verbs = re.findall(r"case \"([a-z-]+)\":", m.group(1)) if m else []
    if not verbs:
        raise ExtractError("wicked-garden: install.mjs verb switch not found")
    for v in verbs:
        els.append(_el("garden", "cli", v, ["install.mjs"]))
    pm = re.search(r"function cmdPack\(argv\) \{(.*?)\n\}", inst, re.S)
    for v in re.findall(r"case \"([a-z-]+)\":", pm.group(1)) if pm else []:
        els.append(_el("garden", "cli", "pack " + v, ["install.mjs"]))
    for p in sorted(os.listdir(os.path.join(root, "packs"))):
        if os.path.isdir(os.path.join(root, "packs", p)):
            els.append(_el("garden", "pack", p, ["packs/%s" % p]))
    return els, {"summary": comp.get("summary")}


# ── core ──────────────────────────────────────────────────────────────────────────────────────

def core(root, _ctx):
    rel = "src/bin/wicked-core.rs"
    src = _read(root, rel)
    cmds = set()
    m = re.search(r"const SUBCOMMAND_USAGE: &\[\(&str, &str\)\] = &\[(.*?)\n\];", src, re.S)
    if not m:
        raise ExtractError("wicked-core: SUBCOMMAND_USAGE not found")
    cmds.update(re.findall(r"\(\s*\"([a-z][a-z -]*)\",", m.group(1)))
    cmds.update(re.findall(r"args\.get\(1\)\.map\(String::as_str\) == Some\(\"([a-z-]+)\"\)", src))
    start = src.index("fn main()")
    end = src.find("\nfn ", start + 1)
    main = src[start:end if end > 0 else len(src)]
    for top, sub in re.findall(r"Some\(\"([a-z-]+)\"\) if args\.get\(2\)\.map\(String::as_str\) == Some\(\"([a-z-]+)\"\)", main):
        cmds.add("%s %s" % (top, sub))
        cmds.discard(top)
    for c in re.findall(r"^        Some\(\"([a-z-]+)\"\) =>", main, re.M):
        cmds.add(c)
    for arm in re.findall(r"^        ((?:Some\(\"[a-z-]+\"\)\s*\|\s*)+Some\(\"[a-z-]+\"\)) =>", src, re.M):
        cmds.update(re.findall(r"Some\(\"([a-z][a-z-]*)\"\)", arm))  # `Some("--help") | Some("-h") | Some("help")`
    return [_el("core", "cli", c, [rel]) for c in sorted(cmds)], {}


# ── interactive ───────────────────────────────────────────────────────────────────────────────

def interactive(root, ctx):
    els = []
    for f in git_files_cached(ctx, root):
        if f.startswith("src/") and f.endswith((".js", ".mjs")):
            txt = read_text(os.path.join(root, f))
            # `top` is the bridge root; `app` is one document's service, mounted at /d/:doc (top.use(`/d/${name}`, svc.app)).
            for recv, meth, path in re.findall(r"\b(top|app)\.(get|post|put|patch|delete|all)\(\s*[\"']([^\"']+)[\"']", txt):
                full = path if recv == "top" else "/d/:doc" + path
                els.append(_el("interactive", "route", "%s %s" % (meth.upper(), full), [f]))
    bin_rel = "bin/wicked-interactive.js"
    b = _read(root, bin_rel)
    for c in sorted(set(re.findall(r"cmd === \"([a-z-]+)\"", b)) | {"serve"}):
        els.append(_el("interactive", "cli", c, [bin_rel]))
    return els, {}


# ── bus / vault / ledger ──────────────────────────────────────────────────────────────────────

def bus(root, _ctx):
    els = []
    rel = "commands/cli.js"
    for c in re.findall(r"^\s+case '([a-z-]+)': \{", _read(root, rel), re.M):
        els.append(_el("bus", "cli", c, [rel, "commands/cmd-%s.js" % c]))
        sub_rel = "commands/cmd-%s.js" % c
        if os.path.isfile(os.path.join(root, sub_rel)):
            for s in re.findall(r"^\s+case '([a-z-]+)':", _read(root, sub_rel), re.M):
                els.append(_el("bus", "cli", "%s %s" % (c, s), [sub_rel]))
    els.append(_el("bus", "cli", "wicked-bus-install", ["install.mjs"]))
    return els, {}


def vault(root, _ctx):
    rel = "bin/wicked-vault.mjs"
    b = _read(root, rel)
    cmds = set(re.findall(r"case '([a-z-]+)':", b)) | set(re.findall(r"cmd === '([a-z-]+)'", b))
    cmds = {c for c in cmds if not c.startswith("-")} - {"help", "version"}
    els = [_el("vault", "cli", c, [rel]) for c in sorted(cmds)]
    els.append(_el("vault", "cli", "wicked-vault-install", ["install.mjs"]))
    return els, {}


def ledger(root, _ctx):
    rel = "lib/index.mjs"
    src = _read(root, rel)
    names = set()
    for block in re.findall(r"export \{([^}]*)\}", src):
        for part in block.split(","):
            part = part.strip()
            if part:
                names.add(part.split(" as ")[-1].strip())
    names.update(re.findall(r"export (?:async )?(?:function|const|class) (\w+)", src))
    # `default` re-exports DomainStore; `__*` are test hooks, not user-facing API.
    names = {n for n in names if n != "default" and not n.startswith("__")}
    return [_el("ledger", "export", n, [rel]) for n in sorted(names)], {}


# ── installer ─────────────────────────────────────────────────────────────────────────────────

def installer(root, ctx):
    els = []
    idx = _read(root, "src/index.ts")
    m = re.search(r"function printHelp\(\): void \{(.*?)\n\}", idx, re.S)
    if not m:
        raise ExtractError("wicked-installer: printHelp not found")
    for verb in re.findall(r"\"  wicked-installer ([a-z][a-z-]*)(?: ([a-z|]+))?", m.group(1)):
        v, sub = verb
        if v == "mcp" and sub:
            for s in sub.split("|"):
                els.append(_el("installer", "cli", "mcp " + s, ["src/index.ts", "src/mcp-verb.ts"]))
        else:
            els.append(_el("installer", "cli", v, ["src/index.ts"]))
    pack = _read(root, "src/pack.ts")
    for v in sorted(set(re.findall(r"case \"(add|remove|list|check)\"", pack))):
        els.append(_el("installer", "cli", "pack " + v, ["src/pack.ts"]))
    for f in git_files_cached(ctx, root):
        am = re.match(r"src/install-([a-z]+)\.ts$", f)
        if am:
            els.append(_el("installer", "agent", am.group(1), [f]))
    reg = json.loads(_read(root, "registry.json"))
    for p in reg["products"]:
        els.append(_el("installer", "product", p["id"], ["registry.json"]))
    for b in reg.get("bundles", []):
        els.append(_el("installer", "bundle", b["id"], ["registry.json"]))
    return els, {}


EXTRACTORS = {
    "wicked-studio": studio, "wicked-crew": crew, "wicked-estate": estate, "wicked-garden": garden,
    "wicked-core": core, "wicked-interactive": interactive, "wicked-bus": bus, "wicked-vault": vault,
    "wicked-ledger": ledger, "wicked-installer": installer,
}


def extract(repo, root, ctx=None):
    """Return the normalised manifest for one checkout."""
    ctx = {} if ctx is None else ctx
    els, meta = EXTRACTORS[repo](root, ctx)
    seen, uniq = {}, []
    for e in els:
        if e["key"] in seen:
            seen[e["key"]]["files"] = sorted(set(seen[e["key"]]["files"]) | set(e["files"]))
            continue
        seen[e["key"]] = e
        uniq.append(e)
    uniq.sort(key=lambda e: e["key"])
    files = git_files_cached(ctx, root)
    return {
        "version": 1,
        "repo": repo,
        "prefix": REPOS[repo],
        "sha": git_sha(root),
        "meta": meta,
        "counts": _counts(uniq),
        "elements": uniq,
        "tests": test_index(root, files),
    }


def _counts(els):
    c = {}
    for e in els:
        c[e["kind"]] = c.get(e["kind"], 0) + 1
    return dict(sorted(c.items()))


def clone(repo, sha, dest):
    """Shallow, blobless clone of mikeparcewski/<repo> at ``sha`` (or the default branch when None)."""
    url = "https://github.com/mikeparcewski/%s.git" % repo
    if sha is None:
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", url, dest], check=True)
        return
    subprocess.run(["git", "init", "-q", dest], check=True)
    subprocess.run(["git", "-C", dest, "remote", "add", "origin", url], check=True)
    subprocess.run(["git", "-C", dest, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha], check=True)
    subprocess.run(["git", "-C", dest, "checkout", "-q", "FETCH_HEAD"], check=True)
