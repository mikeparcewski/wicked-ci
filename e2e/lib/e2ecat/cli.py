"""Command dispatch for e2e/bin/e2e."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .util import read_json
from . import surfaces as sf
from . import validate as v
from .select import SelectError, select


def _write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _dump(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def dump_manifest(m):
    """One element / test path per line, so a surface drift diff reads element by element."""
    head = {k: m[k] for k in m if k not in ("elements", "tests")}
    lines = ["{"]
    for k, val in head.items():
        lines.append(" %s: %s," % (json.dumps(k), json.dumps(val, ensure_ascii=False, sort_keys=True)))
    lines.append(' "elements": [')
    lines.append(",\n".join("  " + json.dumps(e, ensure_ascii=False, sort_keys=True) for e in m["elements"]))
    lines.append(" ],")
    lines.append(' "tests": [')
    lines.append(",\n".join("  " + json.dumps(t, ensure_ascii=False) for t in m["tests"]))
    lines.append(" ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _profiles(e2e):
    p = os.path.join(e2e, "profiles.json")
    return read_json(p)["profiles"] if os.path.isfile(p) else {}


def cmd_validate(a):
    e2e = a.e2e
    sch, docs, caps = v.load_catalog(e2e)
    surfaces = v.load_surfaces(e2e, a.surfaces)
    profiles = _profiles(e2e)
    fails = v.check_catalog(sch, docs, caps, surfaces, repo_root=os.path.dirname(e2e))
    fails += v.check_profiles(profiles, caps)
    unmapped = v.unmapped_elements(caps, surfaces)
    notes = []
    if a.baseline:
        base = read_json(a.baseline)
        new, stale = v.apply_baseline(unmapped, base)
        fails += ["unmapped surface element (not in the baseline): %s" % k for k in new]
        fails += ["baseline entry is no longer unmapped, remove it: %s" % k for k in stale]
        notes.append("baseline %s tolerates %d known unmapped elements; %d new, %d stale" % (
            os.path.relpath(a.baseline), sum(len(x) for x in base.get("unmapped", {}).values()), len(new), len(stale)))
    else:
        for repo, keys in unmapped.items():
            fails += ["%s: unmapped surface element %s" % (repo, k) for k in keys]
    summ = v.summary(caps, surfaces, unmapped)
    report = None
    if a.report:
        rfails, counts = v.check_report(a.report, caps, profiles)
        fails += ["report: %s" % f for f in rfails]
        report = {"run_dir": a.report, "verdicts": counts, "failures": len(rfails)}
        notes.append("run report %s: verdicts %s; %d completeness failures" % (a.report, counts, len(rfails)))
    planned = summ["total"]["planned"]
    notes.append("%d capabilities have only a `planned` scenario (reported as uncovered, not a failure)" % planned)
    md = v.render_md(summ, fails, notes)
    out = {"ok": not fails, "summary": summ, "unmapped": unmapped, "failures": fails, "report": report}
    if a.out:
        _write(os.path.join(a.out, "coverage.md"), md)
        _write(os.path.join(a.out, "coverage.json"), _dump(out))
    sys.stdout.write(md if a.verbose or not a.out else "")
    t = summ["total"]
    print("e2e validate: %d capabilities (%d with scenario, %d planned; %d manual, %d untyped); %d unmapped surface elements; %s" % (
        t["capabilities"], t["with_scenario"], t["planned"], t["manual"], t["untyped"],
        sum(len(x) for x in unmapped.values()), "OK" if not fails else "%d FAILURES" % len(fails)))
    return 0 if not fails else 1


def cmd_select(a):
    _, _, caps = v.load_catalog(a.e2e)
    expr = a.expr
    if a.profile:
        prof = _profiles(a.e2e).get(a.profile)
        if prof is None:
            print("unknown profile %r" % a.profile, file=sys.stderr)
            return 2
        expr = prof["select"]
    try:
        sel = select(caps, expr or "")
    except SelectError as e:
        print("e2e select: %s" % e, file=sys.stderr)
        return 2
    for c in sel:
        print("%s\t%s\t%s\t%s" % (c["id"], c["cost"], c["surface"], c["oracle"]["kind"]))
    print("%d selected" % len(sel), file=sys.stderr)
    return 0


def cmd_surfaces(a):
    out = a.out or os.path.join(a.e2e, "surfaces")
    pins_p = os.path.join(out, "pins.json")
    pins = read_json(pins_p) if os.path.isfile(pins_p) else {"repos": {}, "npm": {}}
    crew_npm = a.crew_npm or pins.get("npm", {}).get("wicked-crew")
    if crew_npm == "latest":
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        crew_npm = subprocess.run([npm, "view", "wicked-crew", "version"], capture_output=True, text=True,
                                  check=True).stdout.strip()
    repos = a.repos.split(",") if a.repos else list(sf.REPOS)
    tmp = None
    rc = 0
    new_pins = {"repos": dict(pins.get("repos", {})), "npm": {"wicked-crew": crew_npm} if crew_npm else {}}
    try:
        if a.clone:
            tmp = tempfile.mkdtemp(prefix="e2e-surfaces-")
        for repo in repos:
            if a.clone:
                root = os.path.join(tmp, repo)
                sha = pins.get("repos", {}).get(repo) if a.clone == "pinned" else None
                if a.clone == "pinned" and not sha:
                    print("%s: no pinned sha in %s" % (repo, pins_p), file=sys.stderr)
                    rc = 1
                    continue
                sf.clone(repo, sha, root)
            else:
                root = os.path.join(a.src, repo)
            ctx = {"crew_npm": crew_npm}
            try:
                m = sf.extract(repo, root, ctx)
            except sf.ExtractError as e:
                print("%s: %s" % (repo, e), file=sys.stderr)
                rc = 1
                continue
            _write(os.path.join(out, repo + ".json"), dump_manifest(m))
            new_pins["repos"][repo] = m["sha"]
            print("%s @ %s: %s" % (repo, m["sha"][:12], m["counts"]))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if a.write_pins:
        new_pins["repos"] = dict(sorted(new_pins["repos"].items()))
        _write(pins_p, _dump(new_pins))
    return rc


def cmd_drift(a):
    """Compare the pinned manifests with freshly extracted ones (e.g. from current mains). Never fails."""
    pinned = v.load_surfaces(a.e2e)
    fresh = v.load_surfaces(a.e2e, a.against)
    _, _, caps = v.load_catalog(a.e2e)
    covered = {k for c in caps for k in c.get("covers", [])}
    L = ["# e2e surface drift", "", "| repo | pinned | current | added | removed | added and unmapped |", "|---|---|---|---:|---:|---:|"]
    detail, out = [], {}
    for repo in sorted(set(pinned) | set(fresh)):
        p = {e["key"] for e in pinned.get(repo, {}).get("elements", [])}
        f = {e["key"] for e in fresh.get(repo, {}).get("elements", [])}
        added, removed = sorted(f - p), sorted(p - f)
        unm = [k for k in added if k not in covered]
        out[repo] = {"pinned": pinned.get(repo, {}).get("sha"), "current": fresh.get(repo, {}).get("sha"),
                     "added": added, "removed": removed, "added_unmapped": unm}
        L.append("| %s | `%s` | `%s` | %d | %d | %d |" % (repo, (out[repo]["pinned"] or "-")[:12],
                                                        (out[repo]["current"] or "-")[:12], len(added), len(removed), len(unm)))
        for k in added:
            detail.append("- %s added%s: `%s`" % (repo, "" if k in covered else " (unmapped)", k))
        for k in removed:
            detail.append("- %s removed%s: `%s`" % (repo, " (a capability still covers it)" if k in covered else "", k))
    md = "\n".join(L + [""] + (detail or ["No drift."])) + "\n"
    if a.out:
        _write(os.path.join(a.out, "drift.md"), md)
        _write(os.path.join(a.out, "drift.json"), _dump(out))
    sys.stdout.write(md)
    return 0


def cmd_baseline(a):
    _, _, caps = v.load_catalog(a.e2e)
    unmapped = v.unmapped_elements(caps, v.load_surfaces(a.e2e))
    doc = {"version": 1,
           "$comment": "Known unmapped surface elements (the coverage ratchet). `e2e validate --baseline` fails on any "
                       "element missing from this list AND on any listed element that is now covered or gone, so the "
                       "list only shrinks. Regenerate with `e2e baseline --write` only to drop entries.",
           "unmapped": unmapped}
    if a.write:
        _write(a.path, _dump(doc))
    print("%d unmapped elements across %d repos%s" % (sum(len(x) for x in unmapped.values()), len(unmapped),
                                                       " -> " + a.path if a.write else ""))
    return 0


def main(argv):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = argparse.ArgumentParser(prog="e2e", description="wicked platform certification catalog tool")
    p.add_argument("--e2e", default=here, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("validate", help="catalog + coverage (+ run report) checks")
    pv.add_argument("--report", help="a run directory to check for completeness (phase 2 runner output)")
    pv.add_argument("--baseline", help="tolerate the known unmapped elements listed in this file (ratchet)")
    pv.add_argument("--out", help="write coverage.md + coverage.json here")
    pv.add_argument("-v", "--verbose", action="store_true", help="print the Markdown summary even with --out")
    pv.add_argument("--surfaces", help="read surface manifests from this directory instead of e2e/surfaces")
    pd = sub.add_parser("drift", help="compare the pinned manifests with freshly extracted ones (report only)")
    pd.add_argument("--against", required=True, help="a directory of freshly extracted manifests")
    pd.add_argument("--out", help="write drift.md + drift.json here")
    ps = sub.add_parser("select", help="print the capabilities an expression selects")
    ps.add_argument("expr", nargs="?", default="")
    ps.add_argument("--profile")
    pf = sub.add_parser("surfaces", help="extract surface manifests")
    g = pf.add_mutually_exclusive_group(required=True)
    g.add_argument("--src", help="a directory holding the repo checkouts")
    g.add_argument("--clone", choices=["pinned", "main"], help="shallow-clone each repo at its pin or at main")
    pf.add_argument("--repos", help="comma list (default: all)")
    pf.add_argument("--crew-npm", help="published wicked-crew version whose CLI is read (default: the pin; `latest`)")
    pf.add_argument("--out", help="manifest directory (default: e2e/surfaces)")
    pf.add_argument("--write-pins", action="store_true", help="record the extracted SHAs in pins.json")
    pb = sub.add_parser("baseline", help="print or write the known-unmapped baseline")
    pb.add_argument("--path", default=os.path.join(here, "coverage-baseline.json"))
    pb.add_argument("--write", action="store_true")
    a = p.parse_args(argv)
    return {"validate": cmd_validate, "select": cmd_select, "surfaces": cmd_surfaces, "baseline": cmd_baseline,
            "drift": cmd_drift}[a.cmd](a)
