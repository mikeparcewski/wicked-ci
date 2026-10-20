"""The plan summary `e2e run --plan-only` prints and writes into plan.json (`summary`).

It answers what the wicked-e2e-plan skill has to tell an operator before anything runs:

- what is selected (by cost, area, surface) and what will actually run (units, scenarios);
- what each will-run capability needs (requirement classes from deps.py: signed-in seats, a
  container runtime, registered repos, gh auth, tools) and how each is met (the scenario provides
  it, a host probe met it, or a prerequisite the scenario's setup performs);
- what is skipped before running, grouped by the unmet requirement (`skip.dep`);
- the best verdict each will-run capability can reach (its CEILING): a manual oracle is `manual`,
  a partial oracle, a lower-fidelity scenario or a direct read of a path that is not a read is at
  most `partial`. Only the rest can `pass`, and only if every check is then observed to hold;
- a time estimate per unit, low to high, with its basis (measured on the sample runs, or assumed);
- whether to ask before running (any selected capability at cost M or L, or the live target).

It reads the plan only. It never runs a scenario and never claims a verdict.
"""
from . import deps as depsmod
from . import verdict as vd
from .validate import oracle_complete

# Seconds per unit: (fixed low, fixed high, per-scenario low, per-scenario high, basis).
ESTIMATES = {
    "wicked-ci-smoke": (60, 180, 45, 120, "measured: S01-S09 in one harness run took 10 min on a loaded workstation "
                                          "(e2e/samples/smoke-fixture); installs the published artifacts first"),
    "wicked-studio-journeys": (20, 90, 5, 30, "measured: 7 fixture journeys took 59 s with a built studio "
                                              "(e2e/samples/ui-fixture); --studio-rebuild adds a build"),
    "wicked-crew-vitest": (20, 60, 10, 120, "assumed: one vitest file under crew's config; the first run installs nothing "
                                            "but compiles on demand"),
    "wicked-core-cargo": (30, 900, 5, 120, "assumed: a warm target dir builds in under a minute; a cold build of the "
                                           "engine takes many minutes and dominates"),
    "direct": (2, 20, 1, 5, "measured: 17 direct reads took 7 s against a local daemon (e2e/samples/live-throwaway)"),
}
LIVE_JOURNEY = (20, 120, 30, 900, "assumed: an e2e-live journey drives the daemon for real; one that launches a governed "
                                  "run takes minutes per phase")
DEFAULT = (30, 300, 10, 300, "assumed: an adapter with no measurement")


def _unit_estimate(u, target, live_journeys):
    est = ESTIMATES.get(u.adapter.name, DEFAULT)
    if u.adapter.name == "wicked-studio-journeys" and target == "live" and live_journeys:
        est = LIVE_JOURNEY
    n = len(u.scenarios)
    return est[0] + est[2] * n, est[1] + est[3] * n, est[4]


def ceiling(cap, unit, scenario):
    """(best verdict this capability can reach on this plan, [why])."""
    o = cap["oracle"]
    if o["kind"] == "manual":
        return "manual", ["the oracle is manual (%s)" % o.get("category")]
    why = []
    if not oracle_complete(o):
        why.append("the oracle is partial (%d untyped clause(s))" % len(o.get("untyped") or []) if o.get("untyped")
                   else "the oracle is partial")
    fid = (scenario or {}).get("fidelity")
    if unit.adapter.name == "direct":
        if not vd.read_only(cap):
            why.append("only the runner's direct reads: no scenario drives the path")
    elif fid not in vd.CERTIFYING:
        why.append("the scenario's fidelity %s is not certification" % fid)
    return ("partial", why) if why else ("pass", [])


def _count(d, k, n=1):
    d[k] = d.get(k, 0) + n


def summarize(sel, units, assign, ctx, catalog_ids=frozenset()):
    by_unit = {u.key: u for u in units}
    out = {"selected": len(sel), "will_run": 0, "skipped": 0, "cost": {}, "areas": {}, "surfaces": {},
           "units": [], "requirements": {}, "skips": {}, "ceilings": {"pass": 0, "partial": 0, "manual": 0},
           "ceiling_reasons": {}, "estimate": {}, "ask_before_running": False, "ask_reasons": []}
    for cap in sel:
        _count(out["cost"], cap["cost"])
        _count(out["areas"], cap["_area"])
        _count(out["surfaces"], cap["surface"])
        a = assign[cap["id"]]
        if "skip" in a:
            out["skipped"] += 1
            sk = a["skip"]
            g = out["skips"].setdefault(sk["dep"], {"count": 0, "class": sk.get("class"), "detail": sk.get("detail"),
                                                   "capabilities": []})
            g["count"] += 1
            if len(g["capabilities"]) < 5:
                g["capabilities"].append(cap["id"])
            continue
        out["will_run"] += 1
        u = by_unit[a["unit"]]
        best, why = ceiling(cap, u, u.scenarios.get(a["scenario"]))
        _count(out["ceilings"], best)
        for w in why:
            _count(out["ceiling_reasons"], w.split(" (")[0])
        res = a.get("deps") or {}
        for dep in cap.get("deps", []):
            cls = depsmod.classify(dep, catalog_ids)
            kind = next((k for k in ("provided", "met", "prerequisite", "unchecked")
                         if any(e == dep or (isinstance(e, str) and e.startswith(dep + " (")) for e in res.get(k, []))),
                        None)
            if kind is None:
                continue
            r = out["requirements"].setdefault(cls, {"provided": 0, "met": 0, "prerequisite": 0, "unchecked": 0,
                                                     "examples": []})
            r[kind] += 1
            if dep not in r["examples"] and len(r["examples"]) < 4:
                r["examples"].append(dep)
    lo = hi = 0
    for u in units:
        ul, uh, basis = _unit_estimate(u, ctx.target, ctx.live_journeys)
        lo, hi = lo + ul, hi + uh
        out["units"].append({"unit": u.key, "adapter": u.adapter.name, "scenarios": len(u.scenarios),
                             "capabilities": len(u.caps), "estimate_s": [ul, uh], "basis": basis})
    out["estimate"] = {"low_s": lo, "high_s": hi, "low_min": round(lo / 60.0, 1), "high_min": round(hi / 60.0, 1),
                       "note": "units run one at a time; the range is per-unit low/high summed; host load and cold "
                               "builds move it"}
    costly = {k: n for k, n in out["cost"].items() if k in ("M", "L")}
    if costly:
        out["ask_reasons"].append("selected capabilities at cost %s (M = one live seat turn, L = a governed run)" % (
            ", ".join("%s x%d" % kv for kv in sorted(costly.items()))))
    if ctx.target == "live":
        out["ask_reasons"].append("the live target %s%s" % (ctx.studio_url, " with --live-journeys (they drive the daemon "
                                                            "for real)" if ctx.live_journeys else " (read-only GETs)"))
    out["ask_before_running"] = bool(out["ask_reasons"])
    return out


def _fmt_s(s):
    return "%d s" % s if s < 120 else "%.0f min" % (s / 60.0)


def render(summ, target):
    L = ["plan: %d selected on the %s target; %d will run in %d unit(s), %d skipped before running" % (
        summ["selected"], target, summ["will_run"], len(summ["units"]), summ["skipped"]),
        "  cost: %s" % ", ".join("%s %d" % kv for kv in sorted(summ["cost"].items())),
        "  areas: %s" % ", ".join("%s %d" % kv for kv in sorted(summ["areas"].items()))]
    if summ["units"]:
        L.append("units (run one at a time):")
        for u in summ["units"]:
            L.append("  %s: %d scenario(s), %d capabilities, ~%s to %s (%s)" % (
                u["unit"], u["scenarios"], u["capabilities"], _fmt_s(u["estimate_s"][0]), _fmt_s(u["estimate_s"][1]),
                u["basis"].split(":")[0]))
        e = summ["estimate"]
        L.append("estimate: %s to %s in total (%s)" % (_fmt_s(e["low_s"]), _fmt_s(e["high_s"]), e["note"]))
    if summ["requirements"]:
        L.append("needs (for what will run; provided = the scenario brings it, such as the smoke harness's real daemon "
                 "and shimmed seats or a test's doubles; met = probed on this host or the live target):")
        for cls, r in sorted(summ["requirements"].items()):
            how = ", ".join("%s %d" % (k, r[k]) for k in ("provided", "met", "prerequisite", "unchecked") if r[k])
            L.append("  %s: %s (e.g. %s)" % (cls, how, "; ".join(r["examples"][:2])))
    c = summ["ceilings"]
    L.append("best possible verdicts: pass %d, partial %d, manual %d (a pass still needs every check observed)" % (
        c["pass"], c["partial"], c["manual"]))
    for w, n in sorted(summ["ceiling_reasons"].items(), key=lambda kv: -kv[1]):
        L.append("  at most partial: %s (%d)" % (w, n))
    if summ["skips"]:
        L.append("skipped before running (never a pass):")
        for dep, g in sorted(summ["skips"].items(), key=lambda kv: -kv[1]["count"]):
            L.append("  %s: %d (%s) e.g. %s" % (dep, g["count"], g["detail"], ", ".join(g["capabilities"][:2])))
    if summ["ask_before_running"]:
        L.append("ask before running: %s" % "; ".join(summ["ask_reasons"]))
    return "\n".join(L) + "\n"
