"""wicked-studio Playwright journeys (e2e/*_test.py) through the studio's own e2e/run_journeys.py.

Nothing in a journey changes. The runner puts e2e/lib/e2ecat/pwhook on PYTHONPATH and sets
E2E_PW_DIR, so every browser context the journey opens records a video, a trace and a HAR, every
screenshot is kept, the in-process fixture's request log is written, and the capabilities' DOM
checks are sampled (see pwhook/e2e_pw.py).

- `--target fixture` runs the fixture journeys (`e2e-fixture`: the built UI against the in-process
  uxfix stub; evidence, not certification). A LIVE journey never runs on the fixture target.
- `--target live` runs the `e2e-live` journeys with STUDIO_URL / CREW_ORIGIN pointed at the
  target (never their :7701 default).
"""
import glob
import json
import os
import re
import socket

from . import DOUBLED, Adapter, Outcome, run_logged, write_json

JOURNEY_RE = re.compile(r"^e2e/(\w+)_test\.py$")
LINE_RE = re.compile(r"^(PASS|FAIL)\s+(\w+)\s+\(")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def live_journeys(studio):
    """The LIVE list from run_journeys.py (journeys that need a real daemon or bridge)."""
    p = os.path.join(studio, "e2e", "run_journeys.py")
    try:
        with open(p, encoding="utf-8") as fh:
            m = re.search(r"^LIVE\s*=\s*\[([^\]]*)\]", fh.read(), re.M)
    except OSError:
        return set()
    return set(re.findall(r"\"(\w+)\"", m.group(1))) if m else set()


def parse_har(path):
    """HAR -> [{method, url, status, req, res}] (bodies parsed when JSON)."""
    try:
        with open(path, encoding="utf-8") as fh:
            har = json.load(fh)
    except (OSError, ValueError):
        return []
    out = []
    for e in (har.get("log") or {}).get("entries", []):
        rq, rs = e.get("request") or {}, e.get("response") or {}
        req = (rq.get("postData") or {}).get("text")
        try:
            req = json.loads(req) if req else None
        except ValueError:
            pass
        body = (rs.get("content") or {}).get("text")
        if (rs.get("content") or {}).get("encoding") == "base64":
            body = None
        try:
            body = json.loads(body) if body else None
        except ValueError:
            body = body[:4096] if isinstance(body, str) else None
        out.append({"method": rq.get("method"), "url": rq.get("url"), "status": rs.get("status"), "req": req,
                    "res": body, "started": e.get("startedDateTime")})
    return out


class StudioJourneyAdapter(Adapter):
    name = "wicked-studio-journeys"
    targets = ("fixture", "live")

    def claim(self, scenario, ctx):
        repo, _, path = scenario["ref"].partition(":")
        m = JOURNEY_RE.match(path)
        if repo != "wicked-studio" or not m:
            return None
        name = m.group(1)
        studio = ctx.checkouts.get("wicked-studio")
        live = name in live_journeys(studio) if studio else False
        fid = scenario.get("fidelity")
        if ctx.target == "fixture" and (live or fid == "e2e-live"):
            return None
        if ctx.target == "live" and not (live or fid == "e2e-live"):
            return None
        return "wicked-studio-journeys", {"journey": name}

    def available(self, ctx, params):
        studio = ctx.checkouts.get("wicked-studio")
        if not studio or not os.path.isfile(os.path.join(studio, "e2e", "run_journeys.py")):
            return "checkout:wicked-studio", "pass --src DIR or --checkout wicked-studio=PATH"
        if not os.path.isfile(os.path.join(studio, "e2e", params["journey"] + "_test.py")):
            return "checkout:wicked-studio", "e2e/%s_test.py is not in this checkout" % params["journey"]
        ok, why = ctx.playwright_ok()
        if not ok:
            return "adapter:playwright-chromium", why
        built = os.path.isfile(os.path.join(studio, "dist-sameorigin", "index.html"))
        if not built and not os.path.isdir(os.path.join(studio, "node_modules")):
            return "adapter:studio-build", "no dist-sameorigin/ and no node_modules to build it (npm ci)"
        if ctx.target == "live" and not ctx.studio_url:
            return "target:live", "--studio URL"
        if ctx.target == "live" and not ctx.live_journeys:
            # A live journey drives the target for real (some launch governed runs or approve a deliver),
            # whichever capability selected it: running one is an explicit choice.
            return "adapter:live-journeys", "a live journey can launch governed runs on the target; opt in with --live-journeys"
        return None

    def provides(self, ctx, scenario):
        p = {"playwright": "the runner's Playwright", "studio-dist": "the checkout's same-origin build"}
        if ctx.target == "fixture":
            for k in DOUBLED:
                p[k] = "uxfix fixture stub"
        return p

    def evidence_kinds(self, ctx, scenario, cap):
        return {"video", "screenshot", "trace", "api-transcript", "event-log"}

    def run(self, unit, ctx):
        studio = ctx.checkouts["wicked-studio"]
        out = os.path.join(ctx.run_dir, "scenarios", unit.slug)
        pw = os.path.join(out, "pw")
        os.makedirs(pw, exist_ok=True)
        names = sorted({s["params"]["journey"] for s in unit.scenarios.values()})
        checks = write_json(os.path.join(out, "dom-checks.json"), ctx.dom_checks(unit))
        built = os.path.isfile(os.path.join(studio, "dist-sameorigin", "index.html"))
        env = dict(os.environ)
        env.update({
            "E2E_PW_DIR": pw, "E2E_DOM_CHECKS": checks, "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(filter(None, [ctx.pwhook_dir, env.get("PYTHONPATH")])),
            # Build once (SKIP_STUDIO_BUILD=0) when there is no same-origin build yet; reuse it after.
            "SKIP_STUDIO_BUILD": "1" if built and not ctx.studio_rebuild else "0",
            "FEEDBACK_PORT": str(free_port()), "CREW_PORT": str(free_port()), "STUDIO_PORT": str(free_port()),
            "DOC_PORT": str(free_port()),
        })
        if ctx.playwright_browsers:
            env["PLAYWRIGHT_BROWSERS_PATH"] = ctx.playwright_browsers
        if ctx.target == "live":
            env.update({"STUDIO_URL": ctx.studio_url, "CREW_ORIGIN": ctx.studio_url})
        argv = [ctx.python, os.path.join(studio, "e2e", "run_journeys.py")] + names
        rc, secs = run_logged(argv, studio, env, os.path.join(out, "run_journeys.log"), ctx.unit_timeout)
        verdicts = {}
        with open(os.path.join(out, "run_journeys.log"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = LINE_RE.match(line.strip())
                if m:
                    verdicts[m.group(2)] = m.group(1)
        outcomes = {}
        for key, s in unit.scenarios.items():
            name = s["params"]["journey"]
            v = verdicts.get(name)
            if v is None:
                o = Outcome("error", "run_journeys printed no verdict for %s (exit %s%s)" % (
                    name, rc, ", timed out" if rc is None else ""), s.get("fidelity"))
            else:
                o = Outcome("passed" if v == "PASS" else "failed", "%s %s" % (v, name), s.get("fidelity"))
            self._collect(o, os.path.join(pw, name))
            outcomes[key] = o
        return outcomes

    @staticmethod
    def _collect(o, jd):
        hook = {}
        hp = os.path.join(jd, "hook.json")
        if os.path.isfile(hp):
            with open(hp, encoding="utf-8") as fh:
                hook = json.load(fh)
        for p in sorted(glob.glob(os.path.join(jd, "video", "*.webm"))):
            o.add("video", p)
        for p in sorted(glob.glob(os.path.join(jd, "shots", "*.png"))):
            o.add("screenshot", p)
        for p in sorted(glob.glob(os.path.join(jd, "trace", "*.zip"))):
            o.add("trace", p)
        obs = o.obs
        hars = sorted(glob.glob(os.path.join(jd, "har", "*.har")))
        for p in hars:
            for h in parse_har(p):
                obs.add_http(h["method"], h["url"], h["status"], h["req"], h["res"], source="browser-har")
                path = re.sub(r"^[a-z]+://[^/]+", "", h["url"] or "").split("?")[0]
                obs.add_event("network", "%s %s" % (h["method"], path), {"body": h["req"], "status": h["status"]})
        fl = os.path.join(jd, "fixture-requests.jsonl")
        if os.path.isfile(fl):
            with open(fl, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    obs.add_http(r.get("method"), r.get("path"), r.get("status"), None, None, source="fixture-log")
        # The HAR covers every /api/ request of every context the hook opened: complete for the network
        # source only when every context recorded one.
        obs.stream("network", bool(hars) and len(hars) == hook.get("contexts", -1), "browser HAR (/api/ requests)")
        for cid, s in (hook.get("dom") or {}).items():
            obs.dom[cid] = s
        obs.dom_sampled = bool(hook.get("sampled"))
        if obs.http:
            o.add("api-transcript", write_json(os.path.join(jd, "api-transcript.json"), obs.http))
        net = [e for e in obs.events if e["source"] == "network"]
        if net:
            o.add("event-log", write_json(os.path.join(jd, "network-events.json"), net))
        o.extra = {"hook": {k: hook.get(k) for k in ("contexts", "sampled", "checks", "errors")}}

