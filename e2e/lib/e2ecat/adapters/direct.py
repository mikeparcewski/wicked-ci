"""Direct oracle checks: reads the runner makes itself, with no test.

- `api` GET on the live target (`--target live --studio URL`): read-only, `/api/v1/` paths only,
  every placeholder bound. The runner never sends a non-GET to a daemon.
- `exit` on the live target, only for the read-only invocation forms `<bin> --version|-v|--help|-h|
  help|version` of a binary on PATH.
- `npm` (`npm view <pkg> versions dist-tags`) and `gh` (`gh api`, read-only: a repo's latest
  workflow run, latest release, or a PR by a bound number), on any target.
- `dom` on the live target: one read-only visit of the studio root in Playwright (video, trace,
  HAR, screenshot, DOM samples). It never clicks, so a UI capability read this way is at most
  `partial`: the runner read the end state, nothing drove the user's path.

A direct read is `pass`-capable only for a capability whose every check is such a read (verdict.py
`read_only`): then the read IS the user's path.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import Adapter, Outcome, read_jsonl, run_logged, write_json
from ..observe import bind, event_type, unbound

SAFE_ARGS = {"--version", "-v", "-V", "--help", "-h", "help", "version"}
LIVE_PREFIXES = ("/api/v1/",)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is answered as what it is (3xx), never followed: a followed redirect could leave the
    allowed paths or the target (an operator port) and be recorded under the permitted path."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LiveClient:
    """Read-only HTTP against the live target: GET only, /api/v1/ (and the root page) only, no redirects."""

    def __init__(self, base, timeout=20, opener=None):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.open = opener or urllib.request.build_opener(_NoRedirect).open
        self.calls = []

    def get(self, path):
        if not (path == "/" or path.startswith(LIVE_PREFIXES)):
            return None
        req = urllib.request.Request(self.base + path, method="GET", headers={"Accept": "application/json"})
        try:
            with self.open(req, timeout=self.timeout) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            try:
                status, raw = e.code, e.read() if hasattr(e, "read") else b""
            finally:
                e.close()
        except (urllib.error.URLError, OSError) as e:
            self.calls.append({"method": "GET", "url": path, "status": 0, "error": str(e)})
            return None
        text = raw.decode("utf-8", errors="replace")
        try:
            doc = json.loads(text)
        except ValueError:
            doc = None
        self.calls.append({"method": "GET", "url": path, "status": status})
        return {"status": status, "json": doc, "text": text[:4096]}

    def probe(self, cls, dep):
        if cls == "daemon":
            h = self.get("/api/v1/health")
            return (h is not None and h["status"] == 200), "GET /api/v1/health -> %s" % (h and h["status"])
        if cls == "real-engine":
            d = self.get("/api/v1/diagnostics")
            core = ((d or {}).get("json") or {}).get("components", {}).get("coreTs") if d else None
            return bool(core), "diagnostics components.coreTs = %r" % core
        if cls == "signed-in-seats":
            r = self.get("/api/v1/roster")
            seats = ((r or {}).get("json") or {}).get("roster") if r else None
            n = sum(1 for s in seats or [] if isinstance(s, dict) and (s.get("auth") == "signed_in" or s.get("signed_in") is True))
            need = 2 if re.search(r"≥\s*2|>=\s*2|two|distinct", dep) else 1
            return n >= need, "%d signed-in seat(s) on the roster, need %d" % (n, need)
        if cls == "registered-repo":
            r = self.get("/api/v1/repos")
            doc = (r or {}).get("json")
            repos = doc.get("repos") if isinstance(doc, dict) else doc
            return bool(repos), "%d registered repo(s)" % len(repos or [])
        if cls == "projects-engine":
            r = self.get("/api/v1/projects")
            return (r is not None and r["status"] == 200), "GET /api/v1/projects -> %s" % (r and r["status"])
        if cls == "studio-dist":
            r = self.get("/")
            return (r is not None and r["status"] == 200 and "<html" in (r["text"] or "").lower()), "GET / serves the studio"
        return False, "no live probe for %s" % cls


class DirectClient:
    """The `direct` reads `observe.evaluate` may make. Live-only reads answer None off the live target."""

    def __init__(self, target, live=None, npm=None, gh=None, runner=subprocess.run):
        self.target = target
        self.live = live
        self.npm = npm or ("npm.cmd" if sys.platform.startswith("win") else "npm")
        self.gh_bin = gh or os.environ.get("E2E_GH") or "gh"
        self.run = runner
        self._npm = {}
        self.cli = []   # every command this client ran (the cli-transcript of direct reads)
        self.http = []  # every GitHub REST read (an API transcript of direct reads)

    def get(self, path):
        if self.target != "live" or self.live is None:
            return None
        return self.live.get(path)

    def _exec(self, argv, timeout=60):
        try:
            r = self.run(argv, capture_output=True, text=True, timeout=timeout)
            e = {"argv": argv, "code": r.returncode, "stdout": (r.stdout or "")[-16384:], "stderr": (r.stderr or "")[-4096:]}
        except (OSError, subprocess.TimeoutExpired) as ex:
            e = {"argv": argv, "code": None, "stdout": "", "stderr": str(ex)}
        self.cli.append(e)
        return e

    def run_safe(self, cmd):
        if self.target != "live":
            return None
        try:
            toks = shlex.split(cmd)
        except ValueError:
            return None
        if len(toks) != 2 or toks[1] not in SAFE_ARGS:
            return None
        import shutil
        exe = shutil.which(toks[0])
        if not exe:
            return None
        e = self._exec([exe, toks[1]], timeout=30)
        return dict(e, argv=[toks[0], toks[1]])

    def npm_view(self, pkg):
        if pkg in self._npm and self._npm[pkg + "#call"] is not None:
            self.cli.append(dict(self._npm[pkg + "#call"], cached=True))
        if pkg not in self._npm:
            e = self._exec([self.npm, "view", pkg, "versions", "dist-tags", "--json"], timeout=90)
            self._npm[pkg + "#call"] = e
            try:
                self._npm[pkg] = json.loads(e["stdout"]) if e["code"] == 0 else None
            except ValueError:
                self._npm[pkg] = None
        return self._npm[pkg]

    def gh(self, target, repo, ch, bindings):
        if target == "run":
            path = "repos/%s/actions/runs?per_page=1" % repo
        elif target == "release":
            path = "repos/%s/releases/latest" % repo
        elif target == "pr":
            n = bind(str(ch.get("number") or bindings.get("pr") or ""), bindings)
            if not n or unbound(n):
                return None
            path = "repos/%s/pulls/%s" % (repo, n)
        else:
            return None
        e = self._exec([self.gh_bin, "api", "-X", "GET", path], timeout=60)
        try:
            doc = json.loads(e["stdout"]) if e["code"] == 0 else None
        except ValueError:
            doc = None
        self.http.append({"method": "GET", "url": "https://api.github.com/" + path, "status": 200 if doc is not None else None,
                          "req": None, "res": doc, "source": "gh api"})
        if doc is None:
            return None
        if target == "run":
            runs = doc.get("workflow_runs") or []
            return runs[0] if runs else None
        return doc


def direct_checkable(ch, ctx):
    """Can a direct read observe this check on ctx.target (ignoring placeholders)?"""
    k = ch.get("kind")
    if k in ("npm", "gh"):
        return True
    if ctx.target != "live":
        return False
    if k == "api":
        return ch.get("method", "GET").upper() == "GET" and ch.get("path", "").startswith(LIVE_PREFIXES)
    if k == "exit":
        try:
            toks = shlex.split(ch.get("cmd", ""))
        except ValueError:
            return False
        return len(toks) == 2 and toks[1] in SAFE_ARGS
    if k == "dom":
        return True
    return False


class DirectAdapter(Adapter):
    name = "direct"
    targets = ("fixture", "live")

    def claim(self, scenario, ctx):
        return None  # the planner offers it explicitly (it is not a catalog scenario)

    def scenario(self, ctx):
        return {"ref": "direct", "fidelity": "e2e-live", "params": {}}

    def applicable(self, cap, ctx, checks):
        return any(direct_checkable(c, ctx) for c in checks)

    def available(self, ctx, params):
        if ctx.target == "live" and ctx.live is None:
            return "target:live", "--studio URL"
        return None

    def provides(self, ctx, scenario):
        if ctx.target == "live" and ctx.playwright_ok()[0]:
            return {"playwright": "the runner's Playwright (one read-only visit)"}
        return {}

    def evidence_kinds(self, ctx, scenario, cap):
        k = {"cli-transcript"}
        if any(c.get("kind") == "gh" for c in ctx.checks_of(cap["id"])):
            k |= {"api-transcript"}  # the GitHub REST reads
        if ctx.target == "live":
            k |= {"api-transcript", "event-log"}  # event-log: only when the daemon sends a frame (else error)
            if ctx.playwright_ok()[0]:
                k |= {"video", "screenshot", "trace"}
        return k

    def run(self, unit, ctx):
        out = os.path.join(ctx.run_dir, "scenarios", unit.slug)
        os.makedirs(out, exist_ok=True)
        o = Outcome("passed", "direct reads", "e2e-live")
        if ctx.target != "live":
            return {k: o for k in unit.scenarios}  # npm and gh reads happen as each capability is judged
        # Live: subscribe read-only to /ws for the whole unit (the event log), make every GET and
        # --version read the unit's checks name, and visit the studio root once when a check is DOM.
        wslog = os.path.join(out, "ws-frames.jsonl")
        ws = None
        try:
            ws = subprocess.Popen([ctx.node, os.path.join(ctx.taps_dir, "ws-collect.mjs"),
                                   re.sub(r"^http", "ws", ctx.studio_url) + "/ws", wslog, str(ctx.unit_timeout)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            ws = None
        if ws is not None:  # let the subscription open first, so the reads' frames are in the log
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not any("open" in r or "error" in r for r in read_jsonl(wslog)):
                time.sleep(0.1)
        try:
            for cid in unit.caps:
                for ch in ctx.checks_of(cid):
                    path = bind(ch.get("path", ""), ctx.bindings)
                    if ch.get("kind") == "api" and ch.get("method", "GET").upper() == "GET" and not unbound(path) \
                            and not any(h["url"] == path for h in o.obs.http):
                        h = ctx.live.get(path)
                        if h is not None:
                            o.obs.add_http("GET", path, h["status"], None, h.get("json"), source="direct")
                    if ch.get("kind") == "exit" and not unbound(ch.get("cmd", "")):
                        e = ctx.direct.run_safe(ch["cmd"])
                        if e is not None:
                            o.obs.cli.append(dict(e, source="direct"))
            if any(c.get("kind") == "dom" for cid in unit.caps for c in ctx.checks_of(cid)):
                if not self._visit(unit, ctx, out, o):
                    o.status, o.detail = "error", "the read-only studio visit failed (see visit.log)"
        finally:
            if ws is not None:
                time.sleep(1.0)
                ws.terminate()
                try:
                    ws.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    ws.kill()
        frames = [r for r in read_jsonl(wslog) if "frame" in r]
        for r in frames:
            f = r["frame"]
            o.obs.add_event("ws", event_type(f), f)
            if isinstance(f, dict) and isinstance(f.get("event"), dict):
                o.obs.add_event("core-event", event_type(f["event"]), f["event"])
        if any("open" in r for r in read_jsonl(wslog)):
            o.obs.stream("ws", False, "the runner's /ws subscription during its reads")
            o.obs.stream("core-event", False, "the runner's /ws subscription during its reads")
        if frames:
            o.add("event-log", write_json(os.path.join(out, "event-log.json"), [r["frame"] for r in frames]))
        if o.obs.http:
            o.add("api-transcript", write_json(os.path.join(out, "api-transcript.json"), o.obs.http))
        return {k: o for k in unit.scenarios}

    def _visit(self, unit, ctx, out, o):
        from .studio import StudioJourneyAdapter
        pw = os.path.join(out, "pw")
        checks = write_json(os.path.join(out, "dom-checks.json"), ctx.dom_checks(unit))
        env = dict(os.environ, E2E_PW_DIR=pw, E2E_DOM_CHECKS=checks,
                   PYTHONPATH=os.pathsep.join(filter(None, [ctx.pwhook_dir, os.environ.get("PYTHONPATH")])))
        if ctx.playwright_browsers:
            env["PLAYWRIGHT_BROWSERS_PATH"] = ctx.playwright_browsers
        rc, _ = run_logged([ctx.python, os.path.join(ctx.pwhook_dir, "visit.py"), ctx.studio_url + "/"],
                           out, env, os.path.join(out, "visit.log"), 180)
        StudioJourneyAdapter._collect(o, os.path.join(pw, "visit"))
        return rc == 0

