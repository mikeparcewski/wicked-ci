"""Run reports: `<run-dir>/report.json` (for CI and a future studio view), `report.md` and
`report.html` (a coverage matrix by area x verdict, summary counts, every capability with links to
its video, screenshots, trace and transcripts; failures and partials first).

The report states what the results say and nothing more: it reads each `result.json` as written
(and `e2e validate --report` is what checks them). Paths are run-relative; the home directory and
the run directory's absolute path are redacted from every string.
"""
import html
import json
import os

from .validate import AREAS, oracle_complete
from . import verdict as vd

ORDER = ["fail", "error", "partial", "skipped", "manual", "pass"]
COLORS = {"pass": "#1a7f37", "fail": "#cf222e", "error": "#9a6700", "partial": "#bc4c00", "skipped": "#6e7781",
          "manual": "#8250df"}


def _redactor(run_dir):
    home = os.path.expanduser("~")
    absrun = os.path.abspath(run_dir)

    def red(v):
        if isinstance(v, str):
            v = v.replace(absrun, "<run-dir>")
            if home and len(home) > 1:
                v = v.replace(home, "~")
            return v
        if isinstance(v, list):
            return [red(x) for x in v]
        if isinstance(v, dict):
            return {k: red(x) for k, x in v.items()}
        return v
    return red


def build(run_dir, caps_by_id, validation=None):
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    red = _redactor(run_dir)
    rows, counts, matrix = [], {}, {}
    for cid in run.get("capabilities", []):
        cap = caps_by_id.get(cid, {})
        rp = os.path.join(run_dir, cid, "result.json")
        res = {}
        if os.path.isfile(rp):
            with open(rp, encoding="utf-8") as fh:
                res = json.load(fh)
        v = res.get("verdict") or "missing"
        counts[v] = counts.get(v, 0) + 1
        area = cap.get("_area", cid.split(".")[0])
        matrix.setdefault(area, {})
        matrix[area][v] = matrix[area].get(v, 0) + 1
        obs = res.get("observed") or []
        held = sum(1 for o in obs if o.get("ok") is True)
        rows.append({
            "id": cid, "area": area, "title": cap.get("title"), "surface": cap.get("surface"), "cost": cap.get("cost"),
            "verdict": v, "reason": red(res.get("reason")), "skip": red(res.get("skip")),
            "scenario": red({k: (res.get("scenario") or {}).get(k) for k in ("ref", "name", "fidelity", "adapter", "status", "detail")})
            if res.get("scenario") else None,
            "checks": {"total": len(obs), "held": held, "contradicted": sum(1 for o in obs if o.get("ok") is False),
                       "unsatisfied": sum(1 for o in obs if o.get("ok") is None and "unsatisfied" in str(o.get("how"))),
                       "not_observed": sum(1 for o in obs if o.get("ok") is None and "unsatisfied" not in str(o.get("how")))},
            "evidence": red(res.get("evidence") or {}), "evidence_substitutes": res.get("evidence_substitutes") or {},
            "result": "%s/result.json" % cid,
        })
    blockers = {}
    for x in rows:
        res = {}
        rp = os.path.join(run_dir, x["id"], "result.json")
        if os.path.isfile(rp):
            with open(rp, encoding="utf-8") as fh:
                res = json.load(fh)
        for b in blocks(caps_by_id.get(x["id"], {}), res):
            g = blockers.setdefault(b, {"count": 0, "capabilities": []})
            g["count"] += 1
            if len(g["capabilities"]) < 10:
                g["capabilities"].append(x["id"])
    rank = {v: i for i, v in enumerate(ORDER)}
    rows.sort(key=lambda r: (rank.get(r["verdict"], -1), r["area"], r["id"]))
    return {"version": 1,
            "run": red({k: run.get(k) for k in ("run_id", "target", "studio", "profile", "selection", "started", "finished",
                                                "checkouts", "catalog_sha256")}),
            "vault": red(run.get("vault")), "total": len(rows), "counts": counts,
            "matrix": {a: matrix[a] for a in AREAS if a in matrix} | {a: m for a, m in matrix.items() if a not in AREAS},
            "plan": red(run.get("plan") or []), "capabilities": rows,
            "blockers": dict(sorted(blockers.items(), key=lambda kv: (-kv[1]["count"], kv[0]))),
            "validation": red(validation) if validation is not None else None}


def blocks(cap, res):
    """What keeps one capability from `pass`, read from its result and its catalog record (never from the
    reason text). A pass has no blocker; every other verdict has at least one."""
    v = res.get("verdict") or "missing"
    if v == "pass":
        return []
    if v == "missing":
        return ["no result.json (the run did not record it)"]
    if v == "fail":
        return ["fail: the scenario failed or a check was contradicted (read its reason)"]
    if v == "manual":
        return ["manual oracle (never a pass)"]
    if v == "error":
        have = res.get("evidence") or {}
        if (res.get("scenario") or {}).get("status") == "passed" and any(
                k not in have for k in cap.get("required_evidence", [])):  # ran, but a required kind is absent
            return ["error: required evidence not captured by the adapter"]
        return ["error: the scenario could not run"]
    if v == "skipped":
        dep = str((res.get("skip") or {}).get("dep") or "?")
        if dep == "scenario:planned":
            return ["skipped: no scenario exists yet (planned)"]
        if dep == "adapter:none":
            return ["skipped: no adapter runs the scenario (adapter:none)"]
        if dep.startswith("adapter:"):
            # An adapter exists; a prerequisite or an explicit opt-in (live journeys) is missing.
            return ["skipped: the adapter needs %s" % dep[len("adapter:"):]]
        if dep.startswith("checkout:"):
            return ["skipped: missing checkout (%s; pass --src or --checkout)" % dep[len("checkout:"):]]
        if dep.startswith("evidence:"):
            return ["skipped: the adapter cannot capture %s" % dep[len("evidence:"):]]
        if dep.startswith("target:"):
            return ["skipped: wrong target (run %s)" % dep]
        cls = (res.get("skip") or {}).get("class")
        return ["skipped: unmet dependency %s" % (cls or dep)]
    out = []
    o = cap.get("oracle") or {}
    if o and o.get("kind") != "manual" and not oracle_complete(o):
        out.append("partial: incomplete oracle (untyped clauses)")
    obs = res.get("observed") or []
    if any(ob.get("ok") is None for ob in obs):
        out.append("partial: a check was not observed")
    if any(ob.get("ok") is True and ob.get("wildcard") for ob in obs):
        out.append("partial: a check held only on something not tied to this path (wildcard)")
    sc = res.get("scenario") or {}
    if sc.get("adapter") == "direct":
        if not (cap and vd.read_only(cap)):  # a read-only path is certified by the runner's own read
            out.append("partial: only the runner's direct reads (no scenario drove the path)")
    elif sc.get("fidelity") not in ("e2e-live", "e2e-hermetic"):
        out.append("partial: scenario fidelity %s is not certification" % sc.get("fidelity"))
    return out or ["%s: see the result's reason" % v]


def _verdicts(doc):
    return [v for v in ORDER if v in doc["counts"]] + sorted(v for v in doc["counts"] if v not in ORDER)


def render_md(doc):
    r = doc["run"]
    L = ["# e2e certification run %s" % r.get("run_id"), "",
         "Target **%s**%s, %s `%s`. Started %s, finished %s." % (
             r.get("target"), " (%s)" % r["studio"] if r.get("studio") else "",
             "profile" if r.get("profile") else "selection", r.get("profile") or r.get("selection") or "*",
             r.get("started"), r.get("finished")),
         "", "A `pass` means every typed check was observed to hold, on something tied to this path, on a complete "
         "oracle at e2e-live or e2e-hermetic fidelity, on a path a scenario drove. `partial` lists what is missing. `skipped` names "
         "the unmet dependency. This report restates the results; `e2e validate --report` checks them.", ""]
    vs = _verdicts(doc)
    L += ["## Summary", "", "| verdict | capabilities |", "|---|---:|"]
    L += ["| %s | %d |" % (v, doc["counts"][v]) for v in vs] + ["| **total** | **%d** |" % doc["total"], ""]
    L += ["## Coverage by area", "", "| area | " + " | ".join(vs) + " | total |", "|---|" + "---:|" * (len(vs) + 1)]
    for a, m in doc["matrix"].items():
        L.append("| %s | %s | %d |" % (a, " | ".join(str(m.get(v, 0)) for v in vs), sum(m.values())))
    L += [""]
    if doc.get("blockers"):
        L += ["## What blocks a pass", "", "| blocker | capabilities | e.g. |", "|---|---:|---|"]
        L += ["| %s | %d | %s |" % (b, g["count"], ", ".join("`%s`" % c for c in g["capabilities"][:3]))
              for b, g in doc["blockers"].items()]
        L += [""]
    vault = doc.get("vault") or {}
    L += ["Evidence: %s." % ("hashed and recorded in wicked-vault scope `%s`" % vault["scope"] if vault.get("scope")
                             else "NOT recorded in a vault (%s)" % vault.get("disabled")), ""]
    val = doc.get("validation")
    if val is not None:
        L += ["Validation (`e2e validate --report`, when this report was written): %s" % (
            "**OK**" if val["ok"] else "**%d FAILURES**" % len(val["failures"])), ""]
        L += ["- %s" % f for f in val["failures"][:30]] + ([""] if val["failures"] else [])
    for v in vs:
        rows = [x for x in doc["capabilities"] if x["verdict"] == v]
        L += ["## %s (%d)" % (v, len(rows)), ""]
        for x in rows:
            sc = x["scenario"] or {}
            head = "- **%s** (%s, %s)" % (x["id"], x["surface"], x["cost"])
            if sc:
                head += " via `%s`%s at %s" % (sc.get("ref"), " `%s`" % sc["name"] if sc.get("name") else "", sc.get("fidelity"))
            L.append(head)
            if x["checks"]["total"]:
                L.append("  - checks: %(held)d held, %(contradicted)d contradicted, %(unsatisfied)d unsatisfied on the transcript, %(not_observed)d not observed, of %(total)d" % x["checks"])
            if x["reason"]:
                L.append("  - %s" % x["reason"][:600])
            links = []
            for kind, paths in sorted(x["evidence"].items()):
                for i, p in enumerate(paths[:6]):
                    links.append("[%s%s](%s)" % (kind, "" if len(paths) == 1 else " %d" % (i + 1), p))
            if x["evidence_substitutes"]:
                links.append("(stand-ins: %s)" % ", ".join("%s = %s" % kv for kv in x["evidence_substitutes"].items()))
            links.append("[result](%s)" % x["result"])
            L.append("  - " + " · ".join(links))
        L.append("")
    return "\n".join(L) + "\n"


CSS = """body{font:14px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#1f2328;max-width:1400px}
h1{font-size:20px}h2{font-size:16px;margin-top:28px}table{border-collapse:collapse;margin:8px 0}
td,th{border:1px solid #d0d7de;padding:4px 8px;vertical-align:top;text-align:left}th{background:#f6f8fa}
td.n{text-align:right}.v{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-weight:600;font-size:12px}
.cap{border:1px solid #d0d7de;border-radius:6px;padding:8px 12px;margin:8px 0}.cap .id{font-family:ui-monospace,monospace;font-weight:600}
.meta{color:#57606a;font-size:12px}.reason{margin:4px 0}.ev a{margin-right:10px}img.shot{max-width:240px;border:1px solid #d0d7de;margin:4px}
video{max-width:480px;display:block;margin:4px 0}"""


def render_html(doc):
    e = html.escape
    r = doc["run"]
    vs = _verdicts(doc)
    badge = lambda v: '<span class="v" style="background:%s">%s</span>' % (COLORS.get(v, "#57606a"), e(v))
    H = ["<!doctype html><html><head><meta charset='utf-8'><title>e2e run %s</title><style>%s</style></head><body>" % (
        e(str(r.get("run_id"))), CSS)]
    H.append("<h1>e2e certification run %s</h1>" % e(str(r.get("run_id"))))
    H.append("<p class='meta'>target <b>%s</b>%s · %s <code>%s</code> · %s → %s</p>" % (
        e(str(r.get("target"))), " (%s)" % e(r["studio"]) if r.get("studio") else "",
        "profile" if r.get("profile") else "selection", e(str(r.get("profile") or r.get("selection") or "*")),
        e(str(r.get("started"))), e(str(r.get("finished")))))
    H.append("<p>A <b>pass</b> means every typed check was observed to hold, on something tied to this path, on a "
             "complete oracle at e2e-live or e2e-hermetic fidelity, on a path a scenario drove. <b>partial</b> lists what is missing; <b>skipped</b> "
             "names the unmet dependency. <code>e2e validate --report</code> checks these results.</p>")
    H.append("<h2>Summary</h2><table><tr><th>verdict</th><th>capabilities</th></tr>")
    H += ["<tr><td>%s</td><td class='n'>%d</td></tr>" % (badge(v), doc["counts"][v]) for v in vs]
    H.append("<tr><td><b>total</b></td><td class='n'><b>%d</b></td></tr></table>" % doc["total"])
    H.append("<h2>Coverage by area</h2><table><tr><th>area</th>%s<th>total</th></tr>" % "".join("<th>%s</th>" % badge(v) for v in vs))
    for a, m in doc["matrix"].items():
        H.append("<tr><td>%s</td>%s<td class='n'>%d</td></tr>" % (
            e(a), "".join("<td class='n'>%s</td>" % (m.get(v, 0) or "") for v in vs), sum(m.values())))
    H.append("</table>")
    if doc.get("blockers"):
        H.append("<h2>What blocks a pass</h2><table><tr><th>blocker</th><th>capabilities</th><th>e.g.</th></tr>")
        H += ["<tr><td>%s</td><td class='n'>%d</td><td>%s</td></tr>" % (
            e(b), g["count"], e(", ".join(g["capabilities"][:3]))) for b, g in doc["blockers"].items()]
        H.append("</table>")
    vault = doc.get("vault") or {}
    H.append("<p class='meta'>Evidence %s</p>" % (
        "hashed and recorded in wicked-vault scope <code>%s</code>" % e(vault["scope"]) if vault.get("scope")
        else "<b>not</b> recorded in a vault (%s)" % e(str(vault.get("disabled")))))
    val = doc.get("validation")
    if val is not None:
        H.append("<p>Validation (<code>e2e validate --report</code>, when this report was written): %s</p>" % (
            "<b>OK</b>" if val["ok"] else "<b style='color:#cf222e'>%d FAILURES</b>" % len(val["failures"])))
        if val["failures"]:
            H.append("<ul>%s</ul>" % "".join("<li>%s</li>" % e(f) for f in val["failures"][:30]))
    for v in vs:
        rows = [x for x in doc["capabilities"] if x["verdict"] == v]
        H.append("<h2>%s %d</h2>" % (badge(v), len(rows)))
        for x in rows:
            sc = x["scenario"] or {}
            H.append("<div class='cap'><span class='id'>%s</span> %s <span class='meta'>%s · %s · %s</span>" % (
                e(x["id"]), badge(x["verdict"]), e(str(x["area"])), e(str(x["surface"])), e(str(x["cost"]))))
            if x.get("title"):
                H.append("<div>%s</div>" % e(x["title"]))
            if sc:
                H.append("<div class='meta'>scenario <code>%s</code>%s at %s via %s: %s</div>" % (
                    e(str(sc.get("ref"))), " <code>%s</code>" % e(sc["name"]) if sc.get("name") else "",
                    e(str(sc.get("fidelity"))), e(str(sc.get("adapter"))), e(str(sc.get("status")))))
            if x["checks"]["total"]:
                H.append("<div class='meta'>checks: %(held)d held, %(contradicted)d contradicted, %(unsatisfied)d unsatisfied on the transcript, %(not_observed)d not observed, of %(total)d</div>" % x["checks"])
            if x["reason"]:
                H.append("<div class='reason'>%s</div>" % e(x["reason"][:1200]))
            ev = x["evidence"]
            links = []
            for kind, paths in sorted(ev.items()):
                if kind in ("video", "screenshot"):
                    continue
                for i, p in enumerate(paths[:8]):
                    links.append("<a href='%s'>%s%s</a>" % (e(p, quote=True), e(kind), "" if len(paths) == 1 else " %d" % (i + 1)))
            links.append("<a href='%s'>result.json</a>" % e(x["result"], quote=True))
            H.append("<div class='ev'>%s</div>" % " ".join(links))
            if x["evidence_substitutes"]:
                H.append("<div class='meta'>stand-ins: %s</div>" % e(", ".join("%s = %s" % kv for kv in x["evidence_substitutes"].items())))
            for p in ev.get("video", [])[:3]:
                H.append("<details><summary>video %s</summary><video controls preload='none' src='%s'></video></details>" % (
                    e(os.path.basename(p)), e(p, quote=True)))
            shots = ev.get("screenshot", [])
            if shots:
                H.append("<details><summary>%d screenshot(s)</summary>%s</details>" % (len(shots), "".join(
                    "<a href='%s'><img class='shot' loading='lazy' src='%s'></a>" % (e(p, quote=True), e(p, quote=True))
                    for p in shots[:12])))
            H.append("</div>")
    H.append("</body></html>")
    return "\n".join(H) + "\n"


def validation(run_dir, caps, profiles):
    """The run's `validate --report` verdict, embedded so a report never reads cleaner than its run. The
    hashes are re-derived offline from the vault's frozen copies (`e2e validate --report` also runs
    `wicked-vault verify` on every entry)."""
    from .validate import check_report
    fails, _ = check_report(run_dir, caps, profiles, vault_cli=False)
    return {"ok": not fails, "failures": fails}


def write(run_dir, caps_by_id, validation=None):
    doc = build(run_dir, caps_by_id, validation)
    for name, text in (("report.json", json.dumps(doc, indent=1, ensure_ascii=False) + "\n"),
                       ("report.md", render_md(doc)), ("report.html", render_html(doc))):
        with open(os.path.join(run_dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return doc
