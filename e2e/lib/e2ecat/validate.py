"""`e2e validate`: the catalog, surface-coverage and run-report checks (deterministic, offline).

(a) every catalog file is schema-valid, ids and aliases are unique, oracles are well-formed, a UI
    capability requires video + screenshot + trace, every `covers` key names a real surface element,
    and every scenario reference names a test file that exists at the pinned SHA;
(b) every surface element is covered by at least one capability (unmapped elements FAIL, by repo;
    `--baseline` tolerates the listed known gaps and fails on new ones and on stale entries);
(c) every capability has a scenario reference; `planned` is reported as uncovered;
(d) `--report RUN_DIR`: every selected capability has a verdict, observed oracle values and every
    required evidence file present and non-empty.
"""
import json
import os
import re

from .util import read_json
from . import schema as js
from .select import select

E2E = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(E2E)
AREAS = ["studio-ui", "crew-api", "core-engine", "estate", "garden", "plugins-and-installs",
         "interactive-and-docs", "foundation", "seats-and-clis"]
UI_EVIDENCE = {"video", "screenshot", "trace"}
EVIDENCE_EXT = {"video": (".webm",), "screenshot": (".png",), "trace": (".zip",)}
VALUE_ASSERTS = {"text-equals", "text-matches", "count", "attr"}
VERDICTS = {"pass", "fail", "partial", "manual", "error", "skipped"}
FIDELITY_ORDER = ["e2e-live", "e2e-hermetic", "e2e-fixture", "integration", "unit"]


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_catalog(e2e_dir=E2E):
    """Return (schema, {area: doc}, [capability with _area]) — no validation."""
    cat = os.path.join(e2e_dir, "catalog")
    sch = _load(os.path.join(cat, "SCHEMA.json"))
    docs, caps = {}, []
    for area in AREAS:
        p = os.path.join(cat, area + ".json")
        if os.path.isfile(p):
            docs[area] = _load(p)
            for c in docs[area].get("capabilities", []):
                if isinstance(c, dict):
                    c = dict(c)
                    c["_area"] = area
                    caps.append(c)
    return sch, docs, caps


def load_surfaces(e2e_dir=E2E, surfaces_dir=None):
    d = surfaces_dir or os.path.join(e2e_dir, "surfaces")
    out = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".json") and f != "pins.json":
            m = _load(os.path.join(d, f))
            out[m["repo"]] = m
    return out


def _checks(oracle):
    if oracle["kind"] == "all":
        return oracle["of"]
    if oracle["kind"] == "manual":
        return []
    return [oracle]


def local_test_index(repo_root):
    """This checkout's test files, by the same rule the surface manifests use for every other repo."""
    from .surfaces import test_index
    files = []
    for dp, dn, fn in os.walk(repo_root):
        dn[:] = [d for d in dn if d not in (".git", "node_modules", "__pycache__")]
        for f in fn:
            files.append(os.path.relpath(os.path.join(dp, f), repo_root).replace(os.sep, "/"))
    return test_index(repo_root, sorted(files))


def check_catalog(sch, docs, caps, surfaces, repo_root=REPO_ROOT):
    """(a): returns a list of failure strings."""
    fails = []
    try:
        js.check_schema(sch)
    except js.SchemaError as e:
        return ["SCHEMA.json: %s" % e]
    missing = [a for a in AREAS if a not in docs]
    fails += ["catalog/%s.json: missing area file" % a for a in missing]
    for area, doc in docs.items():
        for err in js.validate(doc, sch):
            fails.append("catalog/%s.json: %s" % (area, err))
        if doc.get("area") != area:
            fails.append("catalog/%s.json: area field is %r" % (area, doc.get("area")))
    ids = {}
    for c in caps:
        if c["id"] in ids:
            fails.append("duplicate id %s (in %s and %s)" % (c["id"], ids[c["id"]], c["_area"]))
        ids[c["id"]] = c["_area"]
    aliases = {}
    for c in caps:
        for a in c.get("aliases", []):
            if a in ids:
                fails.append("%s: alias %s is also a live id" % (c["id"], a))
            if a in aliases:
                fails.append("%s: alias %s already belongs to %s" % (c["id"], a, aliases[a]))
            aliases[a] = c["id"]
    elements = {e["key"] for m in surfaces.values() for e in m["elements"]}
    tests = {m["repo"]: set(m["tests"]) for m in surfaces.values()}
    tests["wicked-ci"] = set(local_test_index(repo_root))
    for c in caps:
        cid = c["id"]
        for r in c.get("related", []):
            if r not in ids:
                fails.append("%s: related %s is not a catalog id" % (cid, r))
        if c.get("surface") == "ui" and not UI_EVIDENCE <= set(c.get("required_evidence", [])):
            fails.append("%s: a UI capability must require video, screenshot and trace" % cid)
        o = c.get("oracle")
        if isinstance(o, dict) and o.get("kind") in TYPED:
            fails += ["%s: %s" % (cid, f) for f in check_semantics(_checks(o))]
            if "complete" not in o:
                fails.append("%s: a typed oracle must say whether it is complete" % cid)
            elif o["complete"] and o.get("untyped"):
                fails.append("%s: oracle is marked complete but lists untyped clauses" % cid)
            elif not o["complete"] and not o.get("untyped"):
                fails.append("%s: a partial oracle must list its untyped clauses" % cid)
            if o.get("complete") and c.get("surface") == "ui" and not any(ch.get("kind") == "dom" for ch in _checks(o)):
                fails.append("%s: a UI oracle without a dom check cannot be complete" % cid)
        elif isinstance(o, dict) and o.get("kind") == "manual" and isinstance(o.get("precheck"), dict):
            fails += ["%s: precheck: %s" % (cid, f) for f in check_semantics(_checks(o["precheck"]))]
        for k in c.get("covers", []):
            if k not in elements:
                fails.append("%s: covers %s, which no surface manifest lists" % (cid, k))
        for s in c.get("scenarios", []):
            if s == "planned" or not isinstance(s, dict):
                continue
            repo, _, path = s["ref"].partition(":")
            if repo == "wicked-ci":
                if path not in tests["wicked-ci"]:
                    fails.append("%s: scenario %s is not a test file in this checkout" % (cid, s["ref"]))
            elif repo not in tests:
                fails.append("%s: scenario %s names a repo with no surface manifest" % (cid, s["ref"]))
            elif path not in tests[repo]:
                fails.append("%s: scenario %s is not a test file at %s@%s" % (cid, s["ref"], repo, surfaces[repo]["sha"][:12]))
        if len(c.get("scenarios", [])) > 1 and "planned" in c.get("scenarios", []):
            fails.append("%s: `planned` cannot sit beside a real scenario" % cid)
    return fails


TYPED = ("dom", "api", "event", "file", "exit", "npm", "gh", "all")
NO_VALUE_OPS = ("exists", "absent")


def _comparison(cmp_, where):
    if isinstance(cmp_, dict) and cmp_.get("op") not in NO_VALUE_OPS and "value" not in cmp_:
        return ["%s: comparison %s %s needs a value" % (where, cmp_.get("path"), cmp_.get("op"))]
    return []


SHORTHAND = re.compile(r"[\[\]|<>…]")
ATTR = re.compile(r"\[\s*[\w-]+\s*([~|^$*]?=)\s*([^\]]*?)\s*\]")
CSS_IDENT = re.compile(r"^-?[_a-zA-Z][\w-]*$")


def selector_problem(sel):
    """A cheap CSS check for what the catalog writes: every unquoted attribute value must be an identifier."""
    if sel.count("[") != sel.count("]"):
        return "unbalanced brackets"
    for m in ATTR.finditer(sel):
        v = m.group(2)
        if not (v[:1] in "'\"" and v[-1:] == v[:1]) and not CSS_IDENT.match(v):
            return "unquoted attribute value %r is not a CSS identifier (quote it, or use ^= for a prefix)" % v
    return None


def check_semantics(checks):
    """What JSON Schema (as subset here) cannot say: value-taking asserts carry values, nothing is vacuous,
    and no documentation shorthand ([optional], a|b, <name>, ...) is left where something runs it."""
    out = []
    for i, ch in enumerate(checks):
        k, w = ch.get("kind"), "oracle check %d (%s)" % (i, ch.get("kind"))
        if k == "api" and ch.get("method") != "JSONRPC" and SHORTHAND.search(ch.get("path", "")):
            out.append("%s path %r carries documentation shorthand" % (w, ch.get("path")))
        if k == "event" and ch.get("source") == "network" and SHORTHAND.search(ch.get("type", "")):
            out.append("%s network request %r carries documentation shorthand" % (w, ch.get("type")))
        if k == "dom" and isinstance(ch.get("selector"), str):
            prob = selector_problem(ch["selector"])
            if prob:
                out.append("%s selector %r: %s" % (w, ch["selector"], prob))
        if k == "dom" and ch.get("assert") in VALUE_ASSERTS and "value" not in ch:
            out.append("%s %s needs a value" % (w, ch["assert"]))
        if k == "dom" and ch.get("assert") == "attr" and "attr" not in ch:
            out.append("%s attr needs the attribute name" % w)
        if k == "file" and ch.get("assert") in ("sha256", "json-path", "matches") and "value" not in ch:
            out.append("%s %s needs a value" % (w, ch["assert"]))
        if k == "file" and ch.get("assert") == "json-path" and "json_path" not in ch:
            out.append("%s json-path needs json_path" % w)
        if k == "api":
            exp = ch.get("expect") or {}
            if not any(x in exp for x in ("status", "json", "error_code")):
                out.append("%s expects nothing" % w)
            if "json" in exp and not exp["json"]:
                out.append("%s has an empty json expectation" % w)
            for cmp_ in exp.get("json", []):
                out += _comparison(cmp_, w)
        if k == "gh":
            out += _comparison(ch.get("assert"), w)
        if k == "event" and isinstance(ch.get("count"), dict):
            cnt = ch["count"]
            if cnt.get("min", 0) < 1 and "max" not in cnt:
                out.append("%s count %s is vacuous (no min >= 1 and no max)" % (w, cnt))
    return out


def unmapped_elements(caps, surfaces):
    """(b): {repo: [element keys no capability covers]}."""
    covered = {k for c in caps for k in c.get("covers", [])}
    out = {}
    for repo, m in sorted(surfaces.items()):
        miss = [e["key"] for e in m["elements"] if e["key"] not in covered]
        if miss:
            out[repo] = miss
    return out


def apply_baseline(unmapped, baseline):
    """Ratchet: (new unmapped keys, stale baseline keys). Both are failures."""
    known = {k for keys in baseline.get("unmapped", {}).values() for k in keys}
    now = {k for keys in unmapped.values() for k in keys}
    return sorted(now - known), sorted(known - now)


def best_fidelity(c):
    fs = [s["fidelity"] for s in c.get("scenarios", []) if isinstance(s, dict)]
    for f in FIDELITY_ORDER:
        if f in fs:
            return f
    return None


def summary(caps, surfaces, unmapped):
    areas = {}
    for c in caps:
        a = areas.setdefault(c["_area"], {"capabilities": 0, "with_scenario": 0, "planned": 0,
                                          "manual": 0, "untyped": 0, "typed_complete": 0, "typed_partial": 0,
                                          "best_fidelity": {f: 0 for f in FIDELITY_ORDER}})
        a["capabilities"] += 1
        bf = best_fidelity(c)
        if bf:
            a["with_scenario"] += 1
            a["best_fidelity"][bf] += 1
        else:
            a["planned"] += 1
        k = c["oracle"]["kind"]
        if k == "manual" and c["oracle"].get("category") == "untyped":
            a["untyped"] += 1
        elif k == "manual":
            a["manual"] += 1
        elif c["oracle"].get("complete"):
            a["typed_complete"] += 1
        else:
            a["typed_partial"] += 1
    surf = {}
    for repo, m in sorted(surfaces.items()):
        miss = set(unmapped.get(repo, []))
        by_kind = {}
        for e in m["elements"]:
            bk = by_kind.setdefault(e["kind"], {"elements": 0, "unmapped": 0})
            bk["elements"] += 1
            bk["unmapped"] += e["key"] in miss
        surf[repo] = {"sha": m["sha"], "elements": len(m["elements"]), "unmapped": len(miss), "by_kind": by_kind}
    total = {k: sum(a[k] for a in areas.values()) for k in
             ("capabilities", "with_scenario", "planned", "manual", "untyped", "typed_complete", "typed_partial")}
    return {"areas": {a: areas[a] for a in AREAS if a in areas}, "total": total, "surfaces": surf}


def render_md(summ, fails, notes):
    L = ["# e2e coverage", ""]
    L.append("| area | capabilities | with scenario | planned | manual (not deterministic) | untyped (prose oracle) | typed (complete / partial) | best scenario: live / hermetic / fixture / integration / unit |")
    L.append("|---|---:|---:|---:|---:|---:|---|---|")
    rows = list(summ["areas"].items()) + [("**total**", None)]
    for a, s in rows:
        if s is None:
            t = summ["total"]
            L.append("| **total** | %d | %d | %d | %d | %d | %d / %d | |" % (
                t["capabilities"], t["with_scenario"], t["planned"], t["manual"], t["untyped"], t["typed_complete"], t["typed_partial"]))
            continue
        bf = s["best_fidelity"]
        L.append("| %s | %d | %d | %d | %d | %d | %d / %d | %s |" % (
            a, s["capabilities"], s["with_scenario"], s["planned"], s["manual"], s["untyped"], s["typed_complete"],
            s["typed_partial"], " / ".join(str(bf[f]) for f in FIDELITY_ORDER)))
    L += ["", "| repo | sha | surface elements | unmapped | unmapped by kind |", "|---|---|---:|---:|---|"]
    for repo, s in summ["surfaces"].items():
        bk = ", ".join("%s %d/%d" % (k, v["unmapped"], v["elements"]) for k, v in sorted(s["by_kind"].items()) if v["unmapped"])
        L.append("| %s | `%s` | %d | %d | %s |" % (repo, s["sha"][:12], s["elements"], s["unmapped"], bk or "-"))
    L.append("")
    for n in notes:
        L.append("- " + n)
    if fails:
        L += ["", "## Failures (%d)" % len(fails), ""]
        L += ["- %s" % f for f in fails[:400]]
        if len(fails) > 400:
            L.append("- ... %d more (see coverage.json)" % (len(fails) - 400))
    else:
        L += ["", "No failures."]
    return "\n".join(L) + "\n"


# ── (d) run report ────────────────────────────────────────────────────────────────────────────

def check_report(run_dir, caps, profiles):
    """Return (fails, verdict counts)."""
    fails, counts = [], {}
    rp = os.path.join(run_dir, "run.json")
    if not os.path.isfile(rp):
        return ["%s: run.json missing" % run_dir], counts
    run = _load(rp)
    by_id = {c["id"]: c for c in caps}
    if "capabilities" in run:
        selected = run["capabilities"]
    else:
        expr = run.get("selection")
        if expr is None and run.get("profile"):
            prof = profiles.get(run["profile"])
            if prof is None:
                return ["run.json: unknown profile %r" % run["profile"]], counts
            expr = prof["select"]
        selected = [c["id"] for c in select(caps, expr or "")]
    if not selected:
        fails.append("run.json: the run selects no capability")
    for cid in selected:
        cap = by_id.get(cid)
        if cap is None:
            fails.append("%s: selected, but not a catalog id" % cid)
            continue
        res_p = os.path.join(run_dir, "results", cid + ".json")
        if not os.path.isfile(res_p):
            fails.append("%s: no verdict (results/%s.json missing)" % (cid, cid))
            continue
        try:
            res = _load(res_p)
        except ValueError as e:
            fails.append("%s: results file is not JSON (%s)" % (cid, e))
            continue
        v = res.get("verdict")
        counts[v] = counts.get(v, 0) + 1
        if res.get("id") != cid:
            fails.append("%s: results file names id %r" % (cid, res.get("id")))
        if v not in VERDICTS:
            fails.append("%s: verdict %r is not one of %s" % (cid, v, sorted(VERDICTS)))
            continue
        o = cap["oracle"]
        if o["kind"] == "manual" and v == "pass":
            fails.append("%s: a manual oracle can never be `pass` (report `manual`)" % cid)
        if o["kind"] != "manual" and not o.get("complete") and v == "pass":
            fails.append("%s: the oracle is partial (complete=false); report `partial`, not `pass`" % cid)
        if v != "skipped" and o["kind"] != "manual":
            n = len(_checks(o))
            obs = res.get("observed")
            if not isinstance(obs, list) or len(obs) != n:
                fails.append("%s: observed must list one entry per oracle check (%d), got %s" % (
                    cid, n, len(obs) if isinstance(obs, list) else type(obs).__name__))
            else:
                for i, ob in enumerate(obs):
                    if not isinstance(ob, dict) or "value" not in ob or "ok" not in ob:
                        fails.append("%s: observed[%d] needs `value` and `ok`" % (cid, i))
        if v == "skipped":
            fails.append("%s: skipped — a selected capability must run (or be deselected)" % cid)
            continue
        ev = res.get("evidence") or {}
        for kind in cap["required_evidence"]:
            paths = ev.get(kind)
            if not paths:
                fails.append("%s: required evidence %s missing" % (cid, kind))
                continue
            for p in paths if isinstance(paths, list) else [paths]:
                base = os.path.realpath(run_dir)
                full = os.path.realpath(os.path.join(base, p))  # symlinks resolved: a link out of the run dir escapes
                try:
                    inside = os.path.commonpath([base, full]) == base and full != base
                except ValueError:  # different drives on Windows
                    inside = False
                if not inside:
                    fails.append("%s: evidence %s escapes the run dir" % (cid, p))
                elif not os.path.isfile(full) or os.path.getsize(full) == 0:
                    fails.append("%s: evidence %s (%s) missing or empty" % (cid, p, kind))
                elif kind in EVIDENCE_EXT and not p.lower().endswith(EVIDENCE_EXT[kind]):
                    fails.append("%s: %s evidence must be %s, got %s" % (cid, kind, "/".join(EVIDENCE_EXT[kind]), p))
    return fails, counts


def check_profiles(profiles, caps):
    from .select import SelectError
    fails = []
    for name, p in sorted(profiles.items()):
        try:
            n = len(select(caps, p.get("select", "")))
        except SelectError as e:
            fails.append("profiles.json %s: %s" % (name, e))
            continue
        if n == 0:
            fails.append("profiles.json %s: selects no capability" % name)
    return fails
