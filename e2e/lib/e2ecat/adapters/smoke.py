"""wicked-ci self-test steps (S01-S12, U01-U07) as scenarios: one harness run for every step the plan needs.

The harness installs the PUBLISHED crew/core-ts/bus/garden into a hermetic temp root and boots the
daemon with shimmed seats (e2e-hermetic fidelity: certification-grade). The runner sets
WICKED_SMOKE_TAP_DIR, so the harness's own API calls, /ws frames and child-process runs are
recorded per step (selftest/lib/tap.mjs); the steps themselves are unchanged. Evidence: the step's
API transcript, its event log (/ws frames and the events it read back from GET /runs/:id/events),
its CLI transcript, and the harness's evidence directory for the step (hashed).

A U step is a studio journey the harness drives in Chromium against the same daemon. The runner hands the harness its
Python (`--python`) and the e2e Playwright hook (E2E_PW_HOOK_DIR, E2E_DOM_CHECKS); the journey's driver loads the hook,
which writes the UI's /api/ HAR, the catalog's DOM samples and copies of its screenshots under `<tap>/pw/<step>/driver/`.
Those become the step's browser HTTP observations, its DOM samples and its screenshot/video/trace evidence.
"""
import glob
import json
import os
import pathlib
import re

from . import DOUBLED, Adapter, Outcome, read_jsonl, rmtree, run_logged, write_json
from ..observe import event_type
from .studio import parse_har

HARNESS = ("selftest", "bin", "wicked-smoke.mjs")


def harness_path(ctx):
    """The harness entry point in this wicked-ci checkout (the smoke harness lives under selftest/ since the move)."""
    return os.path.join(ctx.repo_root, *HARNESS)


STEP_RE = re.compile(r"^selftest/lib/steps/([SU]\d\d)-[\w-]+\.mjs$")
# Steps that read what S03 left (the onboarded corpus, its bare origin): the harness refuses them alone, so a plan that
# needs one of them runs S03 first (its own outcome is not a scenario of this plan).
NEEDS_S03 = {"S04", "S05", "S06", "S11", "S12", "U04", "U05", "U06", "U07"}


def harness_steps(steps):
    """The steps one harness run takes for `steps`: S03 joins when a step needs it."""
    out = set(steps)
    if out & NEEDS_S03:
        out.add("S03")
    return sorted(out)


STATUS = {"PASS": "passed", "EXPECTED-FAIL": "failed", "UNEXPECTED-PASS": "passed", "FAIL": "failed",
          "ERROR": "error", "SKIPPED": "error"}


def step_windows(starts):
    """{step: (start ms, next step's start ms)} from the tap's steps.jsonl."""
    seq = [(r["start"], r["t"]) for r in starts if r.get("start") and isinstance(r.get("t"), (int, float))]
    out = {}
    for i, (step, t) in enumerate(seq):
        out[step] = (t, seq[i + 1][1] if i + 1 < len(seq) else float("inf"))
    return out


def read_bus(bus_dir):
    """Every event in the hermetic wicked-bus database (read-only), or None when there is none."""
    import sqlite3
    dbs = sorted(glob.glob(os.path.join(bus_dir, "*.db")))
    if not dbs:
        return None
    out = []
    for db in dbs:
        try:
            con = sqlite3.connect(pathlib.Path(os.path.abspath(db)).as_uri() + "?mode=ro", uri=True, timeout=10)
            try:
                rows = con.execute("SELECT event_id, event_type, domain, subdomain, payload, emitted_at, correlation_id "
                                   "FROM events ORDER BY event_id").fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            continue
        for eid, typ, dom, sub, payload, at, corr in rows:
            try:
                body = json.loads(payload)
            except (TypeError, ValueError):
                body = payload
            out.append({"event_id": eid, "event_type": typ, "domain": dom, "subdomain": sub, "payload": body,
                        "emitted_at": at, "correlation_id": corr})
    return out


class SmokeAdapter(Adapter):
    name = "wicked-ci-smoke"
    targets = ("fixture",)

    def claim(self, scenario, ctx):
        repo, _, path = scenario["ref"].partition(":")
        m = STEP_RE.match(path)
        if repo != "wicked-ci" or not m or ctx.target not in self.targets:
            return None
        return "wicked-ci-smoke", {"step": m.group(1)}

    def available(self, ctx, params):
        harness = harness_path(ctx)
        if not os.path.isfile(harness):
            return "checkout:wicked-ci", "selftest/bin/wicked-smoke.mjs is not in this checkout"
        ok, detail = ctx.probe.check("tool-node", "node>=22")
        if not ok:
            return "adapter:node>=22", detail
        ok, detail = ctx.probe.check("network", "network")
        if not ok:
            return "adapter:network", detail + " (the harness installs the published packages)"
        if params["step"].startswith("U"):
            ok, why = self._playwright_isolated(ctx)
            if not ok:
                return "adapter:playwright-chromium", why
        return None

    def provides(self, ctx, scenario):
        d = "the smoke harness: published crew, shimmed seats, temp root"
        p = {"daemon": d, "real-engine": d, "signed-in-seats": d + " (shims)", "registered-repo": d,
             "projects-engine": d, "studio-dist": "crew's bundled studio", "bin-wicked-garden": "installed garden tag",
             "bin-wicked-bus": "installed wicked-bus", "bin-wicked-estate": "estate shim", "tool-git": "host git"}
        m = STEP_RE.match(scenario["ref"].partition(":")[2])
        if m and m.group(1).startswith("U"):
            # A journey drives the daemon's own studio in the runner's Playwright (checked in available()).
            p["playwright"] = "the runner's Playwright, driving the daemon's bundled studio"
        return p

    def evidence_kinds(self, ctx, scenario, cap):
        kinds = {"api-transcript", "event-log", "cli-transcript", "file-hash"}
        m = STEP_RE.match(scenario["ref"].partition(":")[2])
        if m and m.group(1).startswith("U"):
            kinds |= {"screenshot", "video", "trace"}
        return kinds

    def run(self, unit, ctx):
        steps = sorted({s["params"]["step"] for s in unit.scenarios.values()})
        out = os.path.join(ctx.run_dir, "scenarios", unit.slug)
        root = os.path.join(ctx.work_dir, "smoke-root")
        rmtree(root)
        tap = os.path.join(out, "tap")
        argv = [ctx.node, harness_path(ctx), "--steps", ",".join(harness_steps(steps)),
                "--root", root, "--keep", "--report-dir", os.path.join(out, "harness"),
                "--step-timeout", str(ctx.step_timeout)] + list(ctx.smoke_args)
        env = dict(os.environ, WICKED_SMOKE_TAP_DIR=tap)
        if any(s.startswith("U") for s in steps):
            # The journeys run on this runner's Python with the e2e hook; its DOM checks are this unit's.
            argv += ["--python", ctx.python]
            env["E2E_PW_HOOK_DIR"] = ctx.pwhook_dir
            env["E2E_DOM_CHECKS"] = write_json(os.path.join(out, "dom-checks.json"), ctx.dom_checks(unit))
            if ctx.playwright_browsers:
                env["PLAYWRIGHT_BROWSERS_PATH"] = ctx.playwright_browsers
        rc, secs = run_logged(argv, ctx.repo_root, env, os.path.join(out, "harness.log"), ctx.unit_timeout)
        unit.params["root"] = root
        report_p = os.path.join(out, "harness", "report.json")
        report = None
        if os.path.isfile(report_p):
            with open(report_p, encoding="utf-8") as fh:
                report = json.load(fh)
        by_step = {s["id"]: s for s in (report or {}).get("steps", [])}
        http, ws, cli, starts = (read_jsonl(os.path.join(tap, n + ".jsonl")) for n in ("http", "ws", "cli", "steps"))
        bus = read_bus(os.path.join(root, "bus"))
        windows = step_windows(starts)
        crew_dirs = [p for p in glob.glob(os.path.join(root, "npm", "**", "node_modules", "wicked-crew"), recursive=True)
                     if os.path.isdir(p)]
        port = ((report or {}).get("daemon") or {}).get("port")
        outcomes = {}
        for key, s in unit.scenarios.items():
            step = s["params"]["step"]
            r = by_step.get(step)
            if r is None:
                o = Outcome("error", "the harness wrote no result for %s (exit %s; see harness.log)" % (step, rc),
                            s.get("fidelity"))
            else:
                st = STATUS.get(r["status"], "error")
                bad = [c["name"] for c in r.get("checks", []) if not c.get("ok")]
                detail = "%s %s" % (step, r["status"])
                if r.get("error"):
                    detail += ": " + str(r["error"])[:300]
                elif bad:
                    detail += ": failing checks " + "; ".join(bad[:5])
                o = Outcome(st, detail, s.get("fidelity"))
                o.seconds = (r.get("ms") or 0) / 1000.0
                o.extra = {"step": step, "harness_status": r["status"], "checks": len(r.get("checks", [])),
                           "failing_checks": bad[:20], "versions": (report or {}).get("versions")}
            self._observe(o, step, http, ws, cli, crew_dirs + [root], port)
            if step.startswith("U"):
                self._browser(o, os.path.join(tap, "pw", step, "driver"), os.path.join(out, "harness", "evidence", step))
            lo, hi = windows.get(step, (None, None))
            if lo is not None and bus is not None:
                for ev in bus:
                    at = ev["emitted_at"]
                    if isinstance(at, (int, float)) and lo <= at < hi:
                        o.obs.add_event("bus", ev["event_type"], ev)
                o.obs.stream("bus", False, "the hermetic bus.db, by step window (an async emit can land in the next step)")
            sd = os.path.join(out, step)
            if o.obs.http:
                o.add("api-transcript", write_json(os.path.join(sd, "api-transcript.json"), o.obs.http))
            if o.obs.events:
                o.add("event-log", write_json(os.path.join(sd, "event-log.json"), o.obs.events))
            if o.obs.cli:
                o.add("cli-transcript", write_json(os.path.join(sd, "cli-transcript.json"), o.obs.cli))
            ev = os.path.join(out, "harness", "evidence", step)
            for p in sorted(glob.glob(os.path.join(ev, "*"))):
                o.add("scenario-evidence", p)
            outcomes[key] = o
        return outcomes

    @staticmethod
    def _playwright_isolated(ctx):
        """Can the runner's Python launch Chromium the way the harness runs a journey (`python -I`: no user site, no
        PYTHONPATH)? The studio adapter's probe runs without -I, so it can accept a Python the journey cannot use."""
        cached = getattr(ctx, "_smoke_pw", None)
        if cached is None:
            import subprocess
            code = ("from playwright.sync_api import sync_playwright\n"
                    "with sync_playwright() as p:\n b = p.chromium.launch(); b.close()\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
            if ctx.playwright_browsers:
                env["PLAYWRIGHT_BROWSERS_PATH"] = ctx.playwright_browsers
            try:
                r = subprocess.run([ctx.python, "-I", "-c", code], capture_output=True, text=True, timeout=120, env=env)
                cached = (r.returncode == 0, "ok" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["?"])[-1][:200])
            except (OSError, subprocess.TimeoutExpired) as e:
                cached = (False, str(e))
            ctx._smoke_pw = cached
        return cached

    @staticmethod
    def _browser(o, hook_dir, ev_dir):
        """A journey's browser-side observations: the hook's HAR (the UI's own /api/ calls), its DOM samples, and the
        journey's screenshots, video and trace (the driver keeps those under the step's evidence directory)."""
        obs = o.obs
        hook = {}
        try:
            with open(os.path.join(hook_dir, "hook.json"), encoding="utf-8") as fh:
                hook = json.load(fh)
        except (OSError, ValueError):
            hook = {}
        hars = sorted(glob.glob(os.path.join(hook_dir, "har", "*.har")))
        readable = 0
        for p in hars:
            # A HAR that does not parse is a recording that failed, never an empty one: the stream stays incomplete.
            try:
                with open(p, encoding="utf-8") as fh:
                    json.load(fh)
                readable += 1
            except (OSError, ValueError):
                o.extra.setdefault("unreadable_hars", []).append(os.path.basename(p))
                continue
            for h in parse_har(p):
                obs.add_http(h["method"], h["url"], h["status"], h["req"], h["res"], source="browser-har")
                path = re.sub(r"^https?://[^/]+", "", h["url"] or "")
                obs.add_event("network", "%s %s" % (h["method"], path), {"body": h["req"], "status": h["status"]})
        complete = bool(hars) and readable == len(hars) == hook.get("contexts", -1)
        obs.stream("network", complete, "the journey's browser HAR (/api/ requests)")
        for cid, s in (hook.get("dom") or {}).items():
            obs.dom[cid] = s
        obs.dom_sampled = bool(hook.get("sampled"))
        for p in sorted(glob.glob(os.path.join(ev_dir, "*.png"))):
            o.add("screenshot", p)
        for p in sorted(glob.glob(os.path.join(ev_dir, "video", "*.webm"))):
            o.add("video", p)
        o.add("trace", os.path.join(ev_dir, "trace.zip"))
        if hook.get("errors"):
            o.extra["hook_errors"] = hook["errors"][:10]

    @staticmethod
    def _observe(o, step, http, ws, cli, roots, port):
        obs = o.obs
        for h in http:
            if h.get("step") == step:
                obs.add_http(h.get("method"), h.get("url"), h.get("status"), h.get("req"), h.get("res"), source="smoke-tap")
        frames = [w for w in ws if w.get("step") == step and "frame" in w]
        for w in frames:
            f = w["frame"]
            obs.add_event("ws", event_type(f), f)
            inner = f.get("event") if isinstance(f, dict) and isinstance(f.get("event"), dict) else None
            if inner is not None:
                obs.add_event("core-event", event_type(inner), inner)
        if any(w.get("step") == step and "open" in w for w in ws):
            # The harness opens /ws only around the action it asserts: the stream is a window, not the run.
            obs.stream("ws", False, "smoke /ws window")
            obs.stream("core-event", False, "smoke /ws window")
        obs.events_from_http()
        for c in cli:
            if c.get("step") == step:
                obs.cli.append({"argv": c.get("argv") or [], "code": c.get("code"), "stdout": c.get("stdout", ""),
                                "stderr": c.get("stderr", "")})
        obs.file_roots = [r for r in roots if os.path.isdir(r)]
        if port:
            obs.bindings["port"] = port

    def cleanup(self, unit, ctx):
        if not ctx.keep_work:
            rmtree(unit.params.get("root"))

