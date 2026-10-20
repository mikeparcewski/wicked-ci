"""`e2e run`: selection -> capabilities -> scenarios -> a de-duplicated plan -> execution -> evidence.

1. SELECT the capabilities (the selection language, or a profile).
2. PLAN. For each capability, its scenarios are ranked by fidelity for the target (fixture:
   e2e-hermetic, e2e-fixture, integration, unit; live: e2e-live), and a scenario some earlier
   capability already planned wins a tie, so one scenario run proves several capabilities. The
   first candidate that (a) has an adapter on this target, (b) can run on this host (checkout,
   toolchain), (c) can capture every required evidence kind, and (d) has every dep met (deps.py)
   is chosen. When none qualifies the capability is `skipped` with the best candidate's unmet
   requirement as `skip.dep`. It is never a pass.
3. EXECUTE every unit once (one smoke harness run, one run_journeys call, one vitest file, one
   cargo target, one batch of direct reads), in plan order, one at a time.
4. JUDGE each capability on what its scenario recorded (observe.evaluate), with THE verdict rule
   (verdict.derive), and write `<run-dir>/<cap-id>/result.json` and its evidence files.
5. SEAL: hash every evidence file into `<cap-id>/evidence-manifest.json` and record each manifest
   (and the run) in the run's own wicked-vault; then write report.md/.html/.json.
"""
import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

from . import deps as depsmod
from . import evidence as evm
from . import plansum
from . import report as reportmod
from . import verdict as vd
from .adapters import Unit, all_adapters, rmtree, scenario_key, write_json
from .adapters.direct import DirectAdapter, DirectClient, LiveClient, direct_checkable
from .observe import evaluate, request_matches, sha256_file
from .select import select
from .validate import _checks, catalog_digest

HERE = os.path.dirname(os.path.abspath(__file__))
OPERATOR_PORTS = (7701, 7721)
RANK = {"fixture": {"e2e-hermetic": 0, "e2e-fixture": 1, "integration": 2, "unit": 3},
        "live": {"e2e-live": 0}}
DIRECT_FIRST, DIRECT_LAST = -1, 50
# A lower-fidelity test cannot record these natively; its test report stands in, labelled.
SUBSTITUTABLE = ("api-transcript", "event-log", "cli-transcript")


class RunError(Exception):
    pass


class Ctx:
    """Everything an adapter needs: target, paths, tools, probes, clients."""

    def __init__(self, a, e2e_dir, caps_by_id):
        self.target = a.target
        self.studio_url = (a.studio or "").rstrip("/") or None
        self.run_dir = os.path.abspath(a.out)
        self.work_dir = os.path.join(self.run_dir, ".work")
        self.e2e_dir = e2e_dir
        self.repo_root = os.path.dirname(e2e_dir)
        self.checkouts = {"wicked-ci": self.repo_root}
        for repo in ("wicked-studio", "wicked-crew", "wicked-core"):
            if a.src and os.path.isdir(os.path.join(a.src, repo)):
                self.checkouts[repo] = os.path.abspath(os.path.join(a.src, repo))
        for spec in a.checkout or []:
            repo, _, path = spec.partition("=")
            self.checkouts[repo] = os.path.abspath(path)
        self.python = a.python or sys.executable
        self.playwright_browsers = a.playwright_browsers or os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        self.node = shutil.which("node") or "node"
        self.npx = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
        self.build_slot = a.build_slot.split() if a.build_slot else []
        self.step_timeout = a.step_timeout
        self.unit_timeout = a.unit_timeout
        self.smoke_args = a.smoke_arg or []
        self.keep_work = a.keep_work
        self.studio_rebuild = a.studio_rebuild
        self.live_journeys = getattr(a, "live_journeys", False)
        self.cargo_target = a.cargo_target_dir
        self.pwhook_dir = os.path.join(HERE, "pwhook")
        self.taps_dir = os.path.join(HERE, "taps")
        self.caps = caps_by_id
        self.live = LiveClient(self.studio_url) if self.target == "live" and self.studio_url else None
        self.probe = depsmod.Probe(self.target, self.live)
        self.direct = DirectClient(self.target, self.live)
        self.bindings = {}
        if self.studio_url:
            u = urlparse(self.studio_url)
            self.bindings["port"] = u.port or (443 if u.scheme == "https" else 80)
        self._pw = None
        self.log_lines = []

    def log(self, msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        self.log_lines.append(line)
        print(line, flush=True)

    def checks_of(self, cid):
        return _checks(self.caps[cid]["oracle"])

    def dom_checks(self, unit):
        out = []
        for cid in unit.caps:
            for i, c in enumerate(self.checks_of(cid)):
                if c.get("kind") == "dom":
                    out.append({"id": "%s#%d" % (cid, i), "selector": c["selector"], "assert": c.get("assert"),
                                "value": c.get("value"), "attr": c.get("attr")})
        return out

    def playwright_ok(self):
        """Can this runner's Python launch Playwright's chromium? (checked once)"""
        if self._pw is None:
            code = ("from playwright.sync_api import sync_playwright\n"
                    "with sync_playwright() as p:\n b = p.chromium.launch(); b.close()\n")
            env = dict(os.environ)
            if self.playwright_browsers:
                env["PLAYWRIGHT_BROWSERS_PATH"] = self.playwright_browsers
            try:
                r = subprocess.run([self.python, "-c", code], capture_output=True, text=True, timeout=120, env=env)
                self._pw = (r.returncode == 0, "ok" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["?"])[-1][:200])
            except (OSError, subprocess.TimeoutExpired) as e:
                self._pw = (False, str(e))
        return self._pw

    def cargo_target_dir(self, core):
        return self.cargo_target or os.path.join(core, "target")


# ── planning ──────────────────────────────────────────────────────────────────────────────────

def _skip(dep, detail, cls=None, candidates=None):
    return {"dep": dep, "class": cls, "detail": detail, "candidates": candidates or []}


def plan(caps, ctx, adapters=None, catalog_ids=frozenset()):
    """Return (units in plan order, {cid: assignment}). An assignment is {"unit", "scenario"(key),
    "deps"} or {"skip": {...}}."""
    adapters = adapters if adapters is not None else all_adapters()
    direct = DirectAdapter()
    units, assign = {}, {}
    for cap in caps:
        cid = cap["id"]
        checks = _checks(cap["oracle"])
        cands = []
        for idx, s in enumerate(cap.get("scenarios", [])):
            if not isinstance(s, dict):
                continue
            for ad in adapters:
                c = ad.claim(s, ctx)
                if c:
                    rank = RANK.get(ctx.target, {}).get(s.get("fidelity"), 9)
                    cands.append({"rank": rank, "idx": idx, "ad": ad, "key": c[0], "params": c[1], "s": s})
                    break
        if direct.applicable(cap, ctx, checks):
            first = vd.read_only(cap) and all(direct_checkable(c, ctx) for c in checks)
            cands.append({"rank": DIRECT_FIRST if first else DIRECT_LAST, "idx": 99, "ad": direct,
                          "key": "direct", "params": {}, "s": direct.scenario(ctx)})
        if not cands:
            real = [s for s in cap.get("scenarios", []) if isinstance(s, dict)]
            if not real:
                assign[cid] = {"skip": _skip("scenario:planned", "no scenario exists yet (`planned`)")}
            else:
                fids = sorted({s.get("fidelity") for s in real})
                if ctx.target == "live" and "e2e-live" not in fids:
                    assign[cid] = {"skip": _skip("target:fixture", "no e2e-live scenario (fidelities: %s); run --target fixture" % ", ".join(fids))}
                else:
                    assign[cid] = {"skip": _skip("adapter:none", "no adapter runs its scenarios (%s) on the %s target" % (
                        ", ".join(sorted({"%s %s" % (s["ref"].split(":")[0], s.get("fidelity")) for s in real})), ctx.target))}
            continue
        cands.sort(key=lambda c: (c["rank"], 0 if c["key"] in units else 1, c["idx"]))
        reasons = []
        chosen = None
        for c in cands:
            ad, s = c["ad"], c["s"]
            una = ad.available(ctx, c["params"])
            if una:
                reasons.append({"scenario": s["ref"], "dep": una[0], "detail": una[1]})
                continue
            kinds = ad.evidence_kinds(ctx, s, cap)
            missing = [k for k in cap["required_evidence"] if k not in kinds]
            if s.get("fidelity") not in vd.CERTIFYING and "test-report" in kinds:
                missing = [k for k in missing if k not in SUBSTITUTABLE]
            if missing:
                reasons.append({"scenario": s["ref"], "dep": "evidence:" + ",".join(missing),
                                "detail": "%s cannot capture %s" % (ad.name, ", ".join(missing))})
                continue
            res = depsmod.resolve(cap, ad.provides(ctx, s), ctx.probe, catalog_ids)
            if res["unmet"]:
                dep, cls, detail = res["unmet"][0]
                reasons.append({"scenario": s["ref"], "dep": dep, "class": cls, "detail": detail})
                continue
            chosen = (c, res)
            break
        if chosen is None:
            r = reasons[0]
            assign[cid] = {"skip": _skip(r["dep"], r["detail"], r.get("class"), reasons)}
            continue
        c, res = chosen
        u = units.get(c["key"])
        if u is None:
            u = units[c["key"]] = Unit(c["key"], c["ad"])
        skey = scenario_key(c["s"])
        u.scenarios.setdefault(skey, dict(c["s"], params=c["params"]))
        u.caps.append(cid)
        assign[cid] = {"unit": c["key"], "scenario": skey, "deps": res, "passed_over": reasons}
    return list(units.values()), assign


# ── judging one capability ────────────────────────────────────────────────────────────────────

def _rel(ctx, p):
    return evm.rel(ctx.run_dir, p)


def _write_cap_file(ctx, cid, name, obj):
    return write_json(os.path.join(ctx.run_dir, cid, name), obj)


BROWSER = ("video", "screenshot", "trace")


def assemble_evidence(ctx, cap, outcome, observed, examined, direct=False):
    """{kind: [run-relative paths]}: scenario files plus this capability's own extracts. A direct unit's
    studio visit is evidence only for the capabilities that have a DOM check."""
    cid = cap["id"]
    checks = _checks(cap["oracle"])
    ev = {}
    for kind, paths in outcome.evidence.items():
        if direct and kind in BROWSER and not any(c.get("kind") == "dom" for c in checks):
            continue
        ev[kind] = [_rel(ctx, p) for p in paths]
    obs = outcome.obs
    # The capability's own slice of the API transcript: the exchanges its checks are about.
    api_ts = [c for c in checks if c.get("kind") == "api"]
    mine = [h for h in obs.http if any(h["method"] == (c.get("method") or "GET").upper()
                                        and request_matches(c.get("path", ""), h["url"] or "") for c in api_ts)]
    if mine:
        ev["api-transcript"] = [_rel(ctx, _write_cap_file(ctx, cid, "api-transcript.json", mine))] + ev.get("api-transcript", [])
    types = {c.get("type") for c in checks if c.get("kind") == "event"}
    mine_ev = [e for e in obs.events if e["type"] in types]
    if mine_ev:
        ev["event-log"] = [_rel(ctx, _write_cap_file(ctx, cid, "event-log.json", mine_ev))] + ev.get("event-log", [])
    if obs.cli and "cli-transcript" not in ev:
        ev["cli-transcript"] = [_rel(ctx, _write_cap_file(ctx, cid, "cli-transcript.json", obs.cli))]
    if obs.http and "api-transcript" not in ev:
        ev["api-transcript"] = [_rel(ctx, _write_cap_file(ctx, cid, "api-transcript.json", obs.http))]
    files = {}
    for p in examined:
        files[_redact_path(p)] = sha256_file(p)
    basis = "the files this capability's checks read"
    if not files:
        for p in outcome.evidence.get("scenario-evidence", []):
            files[_rel(ctx, p)] = sha256_file(p)
        basis = "the scenario's evidence files"
    if files:
        ev["file-hash"] = [_rel(ctx, _write_cap_file(ctx, cid, "file-hash.json", {"basis": basis, "sha256": files}))]
    return {k: v for k, v in ev.items() if v}


def _redact_path(p):
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if home and p.startswith(home) else p


def judge(ctx, cap, unit, skey, outcome, assignment):
    cid = cap["id"]
    s = unit.scenarios[skey]
    obs = outcome.obs
    bindings = dict(ctx.bindings, **obs.bindings)
    examined = []
    o = cap["oracle"]
    observed = []
    n0, h0 = len(ctx.direct.cli), len(ctx.direct.http)
    definitive = vd.read_only(cap)
    for i, ch in enumerate(_checks(o)):
        r = evaluate(ch, obs, bindings, "%s#%d" % (cid, i), ctx.direct, examined, definitive)
        observed.append(dict({"check": i, "kind": ch.get("kind"), "value": r["value"], "ok": r["ok"], "how": r["how"]},
                             **({"wildcard": True} if r.get("wildcard") else {})))
    precheck = None
    if o["kind"] == "manual" and o.get("precheck"):
        r = evaluate(o["precheck"], obs, bindings, "%s#precheck" % cid, ctx.direct, examined)
        precheck = {"value": r["value"], "ok": r["ok"], "how": r["how"]}
    obs.cli.extend(dict(e, source="direct") for e in ctx.direct.cli[n0:])  # the reads made for this capability
    obs.http.extend(ctx.direct.http[h0:])
    fidelity = outcome.fidelity or s.get("fidelity")
    verdict, reasons = vd.derive(cap, outcome.status, observed, fidelity, driven=unit.adapter.name != "direct")
    if outcome.detail and outcome.status != "passed":
        reasons = reasons + [outcome.detail]
    ev = assemble_evidence(ctx, cap, outcome, observed, examined, direct=unit.adapter.name == "direct")
    substitutes = {}
    for k in cap["required_evidence"]:
        if k not in ev and k in SUBSTITUTABLE and fidelity not in vd.CERTIFYING and ev.get("test-report"):
            ev[k] = list(ev["test-report"])
            substitutes[k] = "test-report"
    missing = [k for k in cap["required_evidence"] if k not in ev]
    derived = None
    if missing and verdict != "error":
        derived = verdict
        reasons = ["required evidence not captured: %s (the run cannot show it)" % ", ".join(missing)] + reasons
        verdict = "error"
    res = {
        "id": cid, "verdict": verdict, "reason": "; ".join(reasons) if reasons else None,
        "partial_reasons": reasons if verdict == "partial" else [],
        "observed": observed if o["kind"] != "manual" else [],
        "evidence": ev,
        "scenario": {"ref": s["ref"], "name": s.get("name"), "fidelity": fidelity, "adapter": unit.adapter.name,
                     "unit": unit.key, "status": outcome.status, "detail": outcome.detail},
        "deps": assignment.get("deps"), "passed_over": assignment.get("passed_over") or [],
        "timings": {"scenario_seconds": round(outcome.seconds, 1)},
    }
    if precheck:
        res["precheck"] = precheck
    if substitutes:
        res["evidence_substitutes"] = substitutes
    if derived:
        res["derived_verdict"] = derived
    if outcome.extra:
        res["scenario"]["facts"] = outcome.extra
    return res


def skipped_result(cap, assignment):
    sk = assignment["skip"]
    return {"id": cap["id"], "verdict": "skipped", "reason": "skipped: %s (%s)" % (sk["dep"], sk["detail"]),
            "skip": sk, "observed": [], "evidence": {}, "scenario": None}


def _write_result(ctx, cid, res):
    p = os.path.join(ctx.run_dir, cid, "result.json")
    write_json(p, res)
    return p


# ── the run ───────────────────────────────────────────────────────────────────────────────────

def new_run_id():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-%04x" % random.randrange(1 << 16)


def check_target(a):
    if a.target == "live":
        if not a.studio:
            raise RunError("--target live needs --studio URL (the daemon that serves the studio)")
        port = urlparse(a.studio).port
        if port in OPERATOR_PORTS and not a.allow_daemon_port:
            raise RunError("--studio %s is an operator daemon port (%s); refusing without --allow-daemon-port "
                           "(certify a throwaway `wicked-crew serve --port <free>` instead)" % (a.studio, port))
    elif a.studio:
        raise RunError("--studio is the live target's URL; the fixture target serves its own")


def execute(a, e2e_dir, caps, profiles, select_expr, profile_name, adapters=None):
    check_target(a)
    by_id = {c["id"]: c for c in caps}
    catalog_ids = frozenset(by_id) | frozenset(x for c in caps for x in c.get("aliases", []))
    sel = select(caps, select_expr)
    if not sel:
        raise RunError("the selection selects no capability")
    run_dir = os.path.abspath(a.out)
    if os.path.exists(run_dir) and os.listdir(run_dir):
        raise RunError("--out %s is not empty (a previous run's?); choose a new run directory" % run_dir)
    os.makedirs(run_dir, exist_ok=True)
    ctx = Ctx(a, e2e_dir, by_id)
    run_id = new_run_id()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ctx.log("e2e run %s: %d capabilities selected (%s), target %s" % (run_id, len(sel), profile_name or select_expr or "*", a.target))
    units, assign = plan(sel, ctx, adapters=adapters, catalog_ids=catalog_ids)
    run = {"version": 2, "run_id": run_id, "target": a.target, "studio": ctx.studio_url,
           "profile": profile_name, "selection": select_expr, "capabilities": [c["id"] for c in sel],
           "catalog_sha256": catalog_digest(e2e_dir), "started": started, "finished": None,
           "checkouts": {k: _git_head(v) for k, v in ctx.checkouts.items()},
           "plan": [{"unit": u.key, "adapter": u.adapter.name, "scenarios": sorted(u.scenarios), "capabilities": u.caps}
                    for u in units],
           "host": {"platform": sys.platform, "python": sys.version.split()[0]}}
    summary = plansum.summarize(sel, units, assign, ctx, catalog_ids)
    write_json(os.path.join(run_dir, "plan.json"), {"run": run, "summary": summary, "assignments": {
        k: ({"skip": v["skip"]} if "skip" in v else {"unit": v["unit"], "scenario": v["scenario"]}) for k, v in assign.items()}})
    nskip = sum(1 for v in assign.values() if "skip" in v)
    ctx.log("plan: %d units for %d capabilities; %d skipped before running" % (len(units), len(sel) - nskip, nskip))
    for u in units:
        ctx.log("  unit %s (%s): %d scenario(s), %d capabilities" % (u.key, u.adapter.name, len(u.scenarios), len(u.caps)))
    write_json(os.path.join(run_dir, "run.json"), run)  # rewritten when the run is sealed
    if a.plan_only:
        sys.stdout.write(plansum.render(summary, a.target))
        return run_dir, 0
    for cap in sel:
        if "skip" in assign[cap["id"]]:
            _write_result(ctx, cap["id"], skipped_result(cap, assign[cap["id"]]))
    for u in units:
        ctx.log("running %s ..." % u.key)
        t0 = time.monotonic()
        try:
            u.outcomes = u.adapter.run(u, ctx)
        except Exception as e:  # an adapter crash is an error for its capabilities, never a pass
            from .adapters import Outcome
            u.outcomes = {k: Outcome("error", "adapter %s crashed: %s: %s" % (u.adapter.name, type(e).__name__, e))
                          for k in u.scenarios}
        ctx.log("  %s done in %.0fs: %s" % (u.key, time.monotonic() - t0,
                                            ", ".join("%s=%s" % (k.split("/")[-1], o.status) for k, o in u.outcomes.items())))
        for cid in u.caps:
            asg = assign[cid]
            out = u.outcomes.get(asg["scenario"])
            if out is None:
                from .adapters import Outcome
                out = Outcome("error", "the adapter returned no outcome for %s" % asg["scenario"])
            res = judge(ctx, by_id[cid], u, asg["scenario"], out, asg)
            _write_result(ctx, cid, res)
        try:
            u.adapter.cleanup(u, ctx)
        except Exception as e:
            ctx.log("  cleanup of %s failed: %s" % (u.key, e))
    run["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    try:
        seal(ctx, run, sel, a.no_vault)
    except (RuntimeError, OSError, ValueError) as e:
        # The results stand; the bundle is not sealed, so `validate --report` refuses it (and the run exits 1).
        run["vault"] = {"disabled": "sealing failed: %s" % e}
        write_json(os.path.join(run_dir, "run.json"), run)
        ctx.log("vault: %s" % run["vault"]["disabled"])
    val = reportmod.validation(run_dir, caps, profiles)
    reportmod.write(run_dir, by_id, val)
    ctx.log("validate --report: %s" % ("OK" if val["ok"] else "%d failures" % len(val["failures"])))
    if not ctx.keep_work:
        rmtree(ctx.work_dir)
    with open(os.path.join(run_dir, "runner.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(ctx.log_lines) + "\n")
    # 0: the run is complete and its own report validates (whatever the verdicts). 1: it does not.
    return run_dir, 0 if val["ok"] else 1


def seal(ctx, run, sel, no_vault):
    """Hash every capability's evidence and record the bundle in the run's own wicked-vault."""
    run_dir = ctx.run_dir
    scope = "e2e-%s" % run["run_id"]
    manifests = {}
    for cap in sel:
        cid = cap["id"]
        rp = os.path.join(run_dir, cid, "result.json")
        with open(rp, encoding="utf-8") as fh:
            res = json.load(fh)
        manifests[cid] = evm.write_manifest(run_dir, run["run_id"], cid, rp, res)
    if no_vault:
        run["vault"] = {"disabled": "--no-vault"}
        write_json(os.path.join(run_dir, "run.json"), run)
        ctx.log("vault: disabled (--no-vault); `validate --report` will refuse the bundle")
        return
    v = evm.Vault(run_dir)
    if not v.argv:
        run["vault"] = {"disabled": "wicked-vault CLI not found (install wicked-vault or set E2E_VAULT)"}
        write_json(os.path.join(run_dir, "run.json"), run)
        ctx.log("vault: %s" % run["vault"]["disabled"])
        return
    v.init()
    run["vault"] = {"scope": scope, "index": "vault-index.json", "cli": v.version()}
    write_json(os.path.join(run_dir, "run.json"), run)
    entries = {}
    for cap in sel:
        cid = cap["id"]
        with open(os.path.join(run_dir, cid, "result.json"), encoding="utf-8") as fh:
            verdict = json.load(fh).get("verdict")
        doc = v.record(scope, cid, manifests[cid],
                       "e2e %s: %s; result.json and every evidence file hash as listed" % (run["run_id"], verdict))
        entries[cid] = doc["id"]
    rm = write_json(os.path.join(run_dir, "run-manifest.json"),
                    {"run_id": run["run_id"], "run_json_sha256": sha256_file(os.path.join(run_dir, "run.json")),
                     "capabilities": run["capabilities"]})
    rdoc = v.record(scope, evm.RUN_CLAIM, rm, "e2e %s: run.json hashes as listed" % run["run_id"])
    write_json(os.path.join(run_dir, "vault-index.json"), {"scope": scope, "entries": entries, "run": rdoc["id"]})
    ctx.log("vault: %d capability entries + the run recorded in scope %s" % (len(entries), scope))


def _git_head(path):
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None

