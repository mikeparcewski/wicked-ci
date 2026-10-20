"""Unit tests for the phase-2 runner (stdlib unittest; no network, no product binaries).

The end-to-end tests drive `run.execute` with a fake adapter and the stub vault (tests/stub_vault.py),
then check `validate --report` on the run directory the runner wrote: it passes as written, and it
fails when a video is deleted, an evidence file or a result is edited after recording, a partial
oracle claims `pass`, a check that was not observed claims `pass`, or a capability is dropped.
"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

E2E = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(E2E, "lib"))

from e2ecat import deps, evidence as evm, observe as ob, report, run as runmod, validate as v, verdict as vd  # noqa: E402
from e2ecat.adapters import Adapter, Outcome, write_json  # noqa: E402
from e2ecat.adapters.studio import parse_har  # noqa: E402
from e2ecat.adapters.smoke import SmokeAdapter  # noqa: E402
from e2ecat.adapters.direct import DirectClient  # noqa: E402
from e2ecat.util import read_json, read_text  # noqa: E402

STUB_VAULT = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "stub_vault.py")]


def cap(cid, **kw):
    c = {"id": cid, "title": "t", "surface": "api", "user_path": "GET /api/v1/health", "deps": [], "cost": "S",
         "tags": [cid.split(".")[0]], "required_evidence": ["api-transcript"],
         "oracle": {"kind": "api", "method": "GET", "path": "/api/v1/health", "expect": {"status": 200}, "complete": True},
         "covers": [], "scenarios": [{"ref": "fake:hermetic/one", "fidelity": "e2e-hermetic"}], "origin": "test"}
    c.update(kw)
    c["_area"] = c.get("_area", cid.split(".")[0])
    return c


# ── observe ───────────────────────────────────────────────────────────────────────────────────

class JsonPathAndCompare(unittest.TestCase):
    DOC = {"run": {"session": {"status": "completed"}, "units": [{"id": "a", "ok": True}, {"id": "b", "ok": False}]},
           "list": [1, 2, 3], "empty": []}

    def test_paths(self):
        self.assertEqual(ob.jsonpath(self.DOC, "$.run.session.status"), ["completed"])
        self.assertEqual(ob.jsonpath(self.DOC, "$.run.units[1].id"), ["b"])
        self.assertEqual(ob.jsonpath(self.DOC, "$.run.units[?(@.id=='b')].ok"), [False])
        self.assertEqual(ob.jsonpath(self.DOC, "$.nope"), [])
        with self.assertRaises(ob.PathError):
            ob.jsonpath(self.DOC, "run.session")

    def test_ops(self):
        c = lambda **k: ob.compare(self.DOC, k)[0]
        self.assertTrue(c(path="$.run.session.status", op="eq", value="completed"))
        self.assertFalse(c(path="$.run.session.status", op="eq", value="failed"))
        self.assertTrue(c(path="$.empty", op="eq", value=[]))
        self.assertTrue(c(path="$.list", op="length", value=3))
        self.assertTrue(c(path="$.list", op="contains", value=2))
        self.assertTrue(c(path="$.nope", op="absent"))
        self.assertFalse(c(path="$.nope", op="eq", value=None))  # absent is not equal to anything
        self.assertTrue(c(path="$.list[0]", op="lt", value=2))
        self.assertTrue(c(path="$.run.session.status", op="matches", value="^comp"))


class Evaluate(unittest.TestCase):
    def obs(self):
        o = ob.Observations()
        o.add_http("GET", "/api/v1/runs/r-1", 200, None, {"run": {"session": {"status": "running"}}})
        o.add_http("GET", "/api/v1/runs/r-1", 200, None, {"run": {"session": {"status": "completed"}}})
        o.add_http("GET", "/api/v1/health", 503, None, {"ok": False})
        return o

    def test_api_any_matching_exchange_holds_a_wildcard_is_marked(self):
        ch = {"kind": "api", "method": "GET", "path": "/api/v1/runs/{runId}",
              "expect": {"status": 200, "json": [{"path": "$.run.session.status", "op": "eq", "value": "completed"}]}}
        r = ob.evaluate(ch, self.obs(), {}, "c#0")
        self.assertIs(r["ok"], True)
        self.assertTrue(r["wildcard"], "{runId} unbound: it held on SOME run")
        r = ob.evaluate(ch, self.obs(), {"runId": "r-1"}, "c#0")
        self.assertIs(r["ok"], True)
        self.assertNotIn("wildcard", r)

    def test_an_unsatisfied_transcript_is_not_a_contradiction_a_direct_read_is(self):
        lit = {"kind": "api", "method": "GET", "path": "/api/v1/health", "expect": {"status": 200}}
        r = ob.evaluate(lit, self.obs(), {}, "c#0")
        self.assertIsNone(r["ok"])
        self.assertEqual(r["how"], "transcript: unsatisfied")
        wild = {"kind": "api", "method": "GET", "path": "/api/v1/runs/{runId}",
                "expect": {"json": [{"path": "$.run.session.status", "op": "eq", "value": "cancelled"}]}}
        self.assertIsNone(ob.evaluate(wild, self.obs(), {}, "c#0")["ok"])

        class Live:
            def get(self, path):
                return {"status": 503, "json": {"ok": False}}
        self.assertIs(ob.evaluate(lit, ob.Observations(), {}, "c#0", direct=Live(), direct_definitive=True)["ok"], False)

    def test_unrecorded_request_is_not_observed(self):
        ch = {"kind": "api", "method": "POST", "path": "/api/v1/chats", "expect": {"status": 201}, "body": "{request_body}"}
        r = ob.evaluate(ch, self.obs(), {}, "c#0")
        self.assertIsNone(r["ok"])
        self.assertEqual(r["how"], "not observed")

    def test_capture_binds(self):
        o = ob.Observations()
        o.add_http("POST", "/api/v1/runs", 201, {"x": 1}, {"runId": "r-9"})
        o.add_http("GET", "/api/v1/runs/r-9", 200, None, {"ok": 1})
        b = {}
        ob.evaluate({"kind": "api", "method": "POST", "path": "/api/v1/runs", "expect": {"status": 201},
                     "capture": {"runId": "$.runId"}}, o, b, "c#0")
        self.assertEqual(b, {"runId": "r-9"})

    def test_direct_get_only(self):
        class Live:
            def get(self, path):
                return {"status": 200, "json": {"ok": True}} if path == "/api/v1/health" else None
        o = ob.Observations()
        ch = {"kind": "api", "method": "GET", "path": "/api/v1/health", "expect": {"status": 200}}
        self.assertIs(ob.evaluate(ch, o, {}, "c#0", direct=Live())["ok"], True)
        self.assertEqual(o.http[0]["source"], "direct")
        post = {"kind": "api", "method": "POST", "path": "/api/v1/health", "expect": {"status": 200}, "body": "{}"}
        self.assertIsNone(ob.evaluate(post, ob.Observations(), {}, "c#0", direct=Live())["ok"])

    def test_events_complete_vs_partial(self):
        o = ob.Observations()
        o.add_event("core-event", "sessionCompleted", {"x": 1})
        ch = {"kind": "event", "source": "core-event", "type": "sessionCompleted", "count": 1}
        self.assertIsNone(ob.evaluate(ch, o, {}, "c#0")["ok"], "no stream recorded -> not observed")
        o.stream("core-event", False)
        self.assertIs(ob.evaluate(ch, o, {}, "c#0")["ok"], None, "an exact count on a partial stream is undecidable")
        mn = dict(ch, count={"min": 1})
        self.assertIs(ob.evaluate(mn, o, {}, "c#0")["ok"], True)
        o.add_event("core-event", "sessionCompleted", {"x": 2})
        self.assertIsNone(ob.evaluate(ch, o, {}, "c#0")["ok"], "more than max on a partial stream: another run's, maybe")
        o2 = ob.Observations()
        o2.stream("network", True)
        never = {"kind": "event", "source": "network", "type": "POST /api/v1/runs", "count": 0}
        self.assertIs(ob.evaluate(never, o2, {}, "c#0")["ok"], True)
        o2.add_event("network", "POST /api/v1/runs", {"body": {"workflow": "bug"}})
        self.assertIs(ob.evaluate(never, o2, {}, "c#0")["ok"], False)
        where = {"kind": "event", "source": "network", "type": "POST /api/v1/runs", "where": {"body.workflow": "bug"}}
        self.assertIs(ob.evaluate(where, o2, {}, "c#0")["ok"], True)

    def test_events_from_run_events_reads(self):
        o = ob.Observations()
        o.add_http("GET", "/api/v1/runs/r/events", 200, None, {"events": [{"type": "sessionCompleted"}, {"type": "x"}]})
        o.add_http("GET", "/api/v1/runs/r/events", 200, None, {"events": [{"type": "sessionCompleted"}]})
        o.events_from_http()
        self.assertEqual([e["type"] for e in o.events], ["sessionCompleted", "x"])  # de-duplicated
        self.assertFalse(o.streams["core-event"]["complete"])

    def test_exit_and_file(self):
        o = ob.Observations()
        o.cli.append({"argv": ["/tmp/x/bin/wicked-crew", "--version"], "code": 0, "stdout": "wicked-crew 1.0", "stderr": ""})
        self.assertIs(ob.evaluate({"kind": "exit", "cmd": "wicked-crew --version", "code": 0}, o, {}, "c#0")["ok"], True)
        self.assertIsNone(ob.evaluate({"kind": "exit", "cmd": "wicked-crew --version", "code": 0, "stdout_matches": "^nope"},
                                      o, {}, "c#0")["ok"])
        o.cli.append({"argv": ["/usr/bin/node", "/r/npm/lib/node_modules/wicked-crew/dist/cli/index.js", "status"],
                      "code": 1, "stdout": "", "stderr": ""})
        self.assertIsNone(ob.evaluate({"kind": "exit", "cmd": "wicked-crew status", "code": 0}, o, {}, "c#0")["ok"])
        self.assertIs(ob.evaluate({"kind": "exit", "cmd": "wicked-crew status", "code": "nonzero"}, o, {}, "c#0")["ok"], True,
                      "node <pkg>/dist/cli/index.js reads as the package's command")
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "dist"))
            with open(os.path.join(d, "dist", "a.json"), "w") as fh:
                json.dump({"head": 3}, fh)
            o.file_roots = [d]
            self.assertIs(ob.evaluate({"kind": "file", "path": "dist/a.json", "assert": "exists"}, o, {}, "c#0")["ok"], True)
            self.assertIs(ob.evaluate({"kind": "file", "path": "dist/a.json", "assert": "json-path", "json_path": "$.head",
                                       "value": 3}, o, {}, "c#0")["ok"], True)
            self.assertIsNone(ob.evaluate({"kind": "file", "path": "../../etc/hosts", "assert": "exists"}, o, {}, "c#0")["ok"],
                              "never reads outside the scenario's roots")
            self.assertIsNone(ob.evaluate({"kind": "file", "path": "dist/missing", "assert": "exists"}, o, {}, "c#0")["ok"])
        finally:
            shutil.rmtree(d)

    def test_dom_sample_never_false(self):
        o = ob.Observations()
        o.dom_sampled = True
        o.dom["c#0"] = {"ok": True, "value": True}
        self.assertIs(ob.evaluate({"kind": "dom", "selector": "[data-testid=x]", "assert": "visible"}, o, {}, "c#0")["ok"], True)
        self.assertIsNone(ob.evaluate({"kind": "dom", "selector": "[data-testid=y]", "assert": "visible"}, o, {}, "c#1")["ok"])


# ── the verdict rule ──────────────────────────────────────────────────────────────────────────

class Verdicts(unittest.TestCase):
    def test_derive(self):
        c = cap("crew-api.a.b")
        ok = [{"value": 200, "ok": True}]
        self.assertEqual(vd.derive(c, "passed", ok, "e2e-hermetic", True)[0], "pass")
        self.assertEqual(vd.derive(c, "passed", ok, "integration", True)[0], "partial")
        self.assertEqual(vd.derive(c, "passed", ok, "e2e-fixture", True)[0], "partial")
        self.assertEqual(vd.derive(c, "passed", [{"value": None, "ok": None}], "e2e-hermetic", True)[0], "partial")
        self.assertEqual(vd.derive(c, "passed", [{"value": 500, "ok": False}], "e2e-hermetic", True)[0], "fail")
        self.assertEqual(vd.derive(c, "failed", ok, "e2e-hermetic", True)[0], "fail")
        self.assertEqual(vd.derive(c, "error", ok, "e2e-hermetic", True)[0], "error")
        partial = cap("crew-api.a.c", oracle=dict(c["oracle"], complete=False, untyped=["x"]))
        self.assertEqual(vd.derive(partial, "passed", ok, "e2e-hermetic", True)[0], "partial")
        manual = cap("crew-api.a.d", oracle={"kind": "manual", "category": "model-output", "reason": "r"})
        self.assertEqual(vd.derive(manual, "passed", [], "e2e-hermetic", True)[0], "manual")

    def test_a_wildcard_hold_is_never_a_pass(self):
        c = cap("crew-api.a.b")
        obs = [{"value": 200, "ok": True, "wildcard": True}]
        v_, why = vd.derive(c, "passed", obs, "e2e-hermetic", True)
        self.assertEqual(v_, "partial")
        self.assertIn("not tied to this path", why[0])
        bad = {"verdict": "pass", "observed": obs,
               "scenario": {"ref": "fake:hermetic/one", "fidelity": "e2e-hermetic", "status": "passed"}}
        self.assertTrue(any("wildcard" in p for p in vd.problems(c, bad)))
        o = ob.Observations()
        o.stream("core-event", False)
        o.add_event("core-event", "sessionCompleted", {})
        r = ob.evaluate({"kind": "event", "source": "core-event", "type": "sessionCompleted", "count": {"min": 1}}, o, {}, "c#0")
        self.assertTrue(r["ok"] and r["wildcard"], "an event in a shared window may be another run's")

    def test_direct_reads_pass_only_read_only_paths(self):
        c = cap("crew-api.a.b")
        self.assertTrue(vd.read_only(c))
        self.assertEqual(vd.derive(c, "passed", [{"value": 200, "ok": True}], "e2e-live", False)[0], "pass")
        ui = cap("studio-ui.a.b", surface="ui", oracle={"kind": "dom", "selector": "[data-testid=x]", "assert": "visible",
                                                     "complete": True})
        self.assertFalse(vd.read_only(ui))
        self.assertEqual(vd.derive(ui, "passed", [{"value": True, "ok": True}], "e2e-live", False)[0], "partial")

    def test_a_path_with_setup_is_not_a_read(self):
        c = cap("crew-api.a.e", user_path="Trigger a bus error (S05 sequence); GET /api/v1/diagnostics. Terminal: x")
        self.assertFalse(vd.read_only(c), "the runner's read is not the end of a path it did not drive")
        self.assertTrue(vd.read_only(cap("crew-api.a.f", user_path="GET /api/v1/roster. Terminal: roster[]")))
        self.assertFalse(vd.read_only(cap("crew-api.a.g", user_path="POST /api/v1/runs {x}. Terminal: done")))

        class Live:
            def get(self, path):
                return {"status": 503, "json": {}}
        ch = c["oracle"]
        self.assertIsNone(ob.evaluate(ch, ob.Observations(), {}, "c#0", direct=Live(), direct_definitive=False)["ok"])
        self.assertIs(ob.evaluate(ch, ob.Observations(), {}, "c#0", direct=Live(), direct_definitive=True)["ok"], False)

    def test_problems(self):
        c = cap("crew-api.a.b")
        good = {"verdict": "pass", "observed": [{"value": 200, "ok": True}],
                "scenario": {"ref": "fake:hermetic/one", "fidelity": "e2e-hermetic", "status": "passed"}}
        self.assertEqual(vd.problems(c, good), [])
        self.assertTrue(vd.problems(c, dict(good, observed=[{"value": None, "ok": None}])))
        self.assertTrue(vd.problems(c, dict(good, scenario=dict(good["scenario"], fidelity="integration"))))
        self.assertTrue(vd.problems(c, dict(good, scenario=dict(good["scenario"], ref="fake:other"))))
        self.assertTrue(vd.problems(c, dict(good, scenario=dict(good["scenario"], status="failed"))))
        self.assertTrue(vd.problems(c, dict(good, verdict="partial", observed=[{"value": 500, "ok": False}])))
        self.assertTrue(vd.problems(c, {"verdict": "skipped", "skip": {"dep": "anything at all"}}))
        self.assertEqual(vd.problems(cap("x.y.z", deps=["container runtime"]),
                                     {"verdict": "skipped", "skip": {"dep": "container runtime"}}), [])
        self.assertEqual(vd.problems(c, {"verdict": "skipped", "skip": {"dep": "evidence:video"}}), [])


# ── deps ──────────────────────────────────────────────────────────────────────────────────────

class Deps(unittest.TestCase):
    def test_classify(self):
        cases = {"signed-in-seats": "signed-in-seats", "≥2 seats": "signed-in-seats", "container runtime": "container",
                 "crew:daemon-hermetic": "daemon", "crew daemon :7721": "daemon", "real-engine": "real-engine",
                 "playwright-chromium": "playwright", "studio:bundled-dist": "studio-dist", "gh-auth": "gh-auth",
                 "network (npm)": "network", "node>=22": "tool-node", "python>=3.10": "tool-python",
                 "wicked-vault CLI": "bin-wicked-vault", "claude subscription": "credential",
                 "registered-repo": "registered-repo", "open chat": "unchecked", "rust toolchain": "tool-cargo"}
        for dep, want in cases.items():
            self.assertEqual(deps.classify(dep), want, dep)
        self.assertEqual(deps.classify("foundation.bus.init", {"foundation.bus.init"}), "prerequisite")

    def test_resolve_provided_probed_unmet(self):
        class P(deps.Probe):
            def check(self, cls, dep):
                return (False, "no runtime") if cls == "container" else (True, "ok")
        c = cap("x.y.z", deps=["daemon", "container runtime", "open chat", "foundation.bus.init"])
        r = deps.resolve(c, {"daemon": "fixture"}, P(), {"foundation.bus.init"})
        self.assertEqual(r["unmet"][0][0], "container runtime")
        self.assertEqual(r["prerequisite"], ["foundation.bus.init"])
        self.assertEqual(r["unchecked"], ["open chat"])
        self.assertTrue(r["provided"][0].startswith("daemon"))
        self.assertFalse(deps.Probe().check("credential", "claude subscription")[0], "the runner reads no credential")
        self.assertFalse(deps.Probe(target="fixture").check("signed-in-seats", "seats")[0])


# ── the runner end to end (fake adapter, stub vault) ───────────────────────────────────────────

class FakeAdapter(Adapter):
    """Claims `fake:<fidelity>/<name>`: writes a webm/png/zip/transcript and records what `behaviour` says."""
    name = "fake"
    targets = ("fixture",)

    def __init__(self, behaviour=None, kinds=None):
        self.behaviour = behaviour or {}
        self.kinds = kinds
        self.runs = []

    def claim(self, scenario, ctx):
        repo, _, path = scenario["ref"].partition(":")
        if repo != "fake":
            return None
        return "fake:" + path.split("/")[0], {"name": path}

    def provides(self, ctx, scenario):
        return {"daemon": "fake"}

    def evidence_kinds(self, ctx, scenario, cap):
        return self.kinds or {"video", "screenshot", "trace", "api-transcript", "event-log", "test-report"}

    def run(self, unit, ctx):
        self.runs.append(unit.key)
        out = os.path.join(ctx.run_dir, "scenarios", unit.slug)
        os.makedirs(out, exist_ok=True)
        res = {}
        for key, s in unit.scenarios.items():
            b = self.behaviour.get(s["params"]["name"], {})
            o = Outcome(b.get("status", "passed"), "fake", s.get("fidelity"))
            for f, kind in (("v.webm", "video"), ("s.png", "screenshot"), ("t.zip", "trace")):
                p = os.path.join(out, f)
                with open(p, "wb") as fh:
                    fh.write(b"bytes of " + f.encode())
                o.add(kind, p)
            for h in b.get("http", [{"method": "GET", "url": "/api/v1/health", "status": 200, "res": {"ok": True}}]):
                o.obs.add_http(h["method"], h["url"], h["status"], None, h.get("res"))
            o.add("api-transcript", write_json(os.path.join(out, "api.json"), o.obs.http))
            if b.get("test_report"):
                o.add("test-report", write_json(os.path.join(out, "report.json"), {"tests": 1}))
            o.obs.dom_sampled = True
            for cid in unit.caps:
                o.obs.dom[cid + "#0"] = {"ok": True, "value": True}
            res[key] = o
        return res


def run_args(out, **kw):
    a = argparse.Namespace(target="fixture", studio=None, out=out, src=None, checkout=None, python=None,
                           playwright_browsers=None, build_slot=None, step_timeout=60, unit_timeout=60, smoke_arg=None,
                           cargo_target_dir=None, studio_rebuild=False, keep_work=False, plan_only=False, no_vault=False,
                           allow_daemon_port=False)
    for k, val in kw.items():
        setattr(a, k, val)
    return a


class RunnerEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="e2e-runner-test-")
        self.out = os.path.join(self.tmp, "run")
        self.old_vault = os.environ.get("E2E_VAULT")
        os.environ["E2E_VAULT"] = json.dumps(STUB_VAULT)
        self.caps = [
            cap("crew-api.health.ok"),
            cap("crew-api.health.partial", oracle={"kind": "api", "method": "GET", "path": "/api/v1/health",
                                                   "expect": {"status": 200}, "complete": False, "untyped": ["more"]}),
            cap("studio-ui.page.shows", surface="ui", required_evidence=["video", "screenshot", "trace"],
                oracle={"kind": "dom", "selector": "[data-testid=x]", "assert": "visible", "complete": True},
                scenarios=[{"ref": "fake:fixture/journey", "fidelity": "e2e-fixture"}]),
            cap("crew-api.needs.container", deps=["container runtime"]),
            cap("crew-api.only.planned", scenarios=["planned"]),
            cap("crew-api.health.integration", scenarios=[{"ref": "fake:integ/test", "fidelity": "integration"}],
                required_evidence=["api-transcript", "event-log"]),
        ]
        self.fake = FakeAdapter({"integ/test": {"test_report": True}})

    def tearDown(self):
        if self.old_vault is None:
            os.environ.pop("E2E_VAULT", None)
        else:
            os.environ["E2E_VAULT"] = self.old_vault
        shutil.rmtree(self.tmp, ignore_errors=True)

    def execute(self, **kw):
        class NoContainer(deps.Probe):
            def check(self, cls, dep):
                return (False, "no container runtime") if cls == "container" else super().check(cls, dep)
        orig = deps.Probe
        runmod.depsmod.Probe = NoContainer
        try:
            with redirect_stdout(io.StringIO()):
                return runmod.execute(run_args(self.out, **kw), E2E, self.caps, {}, "", None, adapters=[self.fake])
        finally:
            runmod.depsmod.Probe = orig

    def result(self, cid):
        with open(os.path.join(self.out, cid, "result.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def validate(self, **kw):
        return v.check_report(self.out, self.caps, {}, **kw)

    def test_runner_output_validates_and_verdicts_are_honest(self):
        self.execute()
        fails, counts = self.validate()
        self.assertEqual(fails, [])
        self.assertEqual(self.result("crew-api.health.ok")["verdict"], "pass")
        self.assertEqual(self.result("crew-api.health.partial")["verdict"], "partial")
        self.assertEqual(self.result("studio-ui.page.shows")["verdict"], "partial", "fixture fidelity is never a pass")
        self.assertEqual(self.result("crew-api.needs.container")["skip"]["dep"], "container runtime")
        self.assertEqual(self.result("crew-api.only.planned")["skip"]["dep"], "scenario:planned")
        integ = self.result("crew-api.health.integration")
        self.assertEqual(integ["verdict"], "partial")
        self.assertEqual(integ["evidence_substitutes"], {"event-log": "test-report"})
        self.assertEqual(self.fake.runs.count("fake:hermetic"), 1, "one scenario run proves both health capabilities")
        for f in ("report.md", "report.html", "report.json", "vault-index.json", "run-manifest.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, f)), f)
        doc = read_json(os.path.join(self.out, "report.json"))
        self.assertEqual(doc["counts"], {"pass": 1, "partial": 3, "skipped": 2})
        self.assertEqual(doc["capabilities"][0]["verdict"], "partial", "failed/partial first, pass last")
        self.assertEqual(doc["capabilities"][-1]["verdict"], "pass")

    def test_the_report_embeds_validation_and_a_regenerated_report_shows_tampering(self):
        self.execute()
        doc = read_json(os.path.join(self.out, "report.json"))
        self.assertTrue(doc["validation"]["ok"], doc["validation"])
        ev = self.result("crew-api.health.ok")["evidence"]["api-transcript"][0]
        with open(os.path.join(self.out, ev), "a", encoding="utf-8") as fh:
            fh.write(" ")
        by_id = {c["id"]: c for c in self.caps}
        doc = report.write(self.out, by_id, report.validation(self.out, self.caps, {}))
        self.assertFalse(doc["validation"]["ok"])
        self.assertIn("FAILURES", read_text(os.path.join(self.out, "report.md")))

    def test_deleting_a_video_fails_validation(self):
        self.execute()
        ev = self.result("studio-ui.page.shows")["evidence"]["video"][0]
        os.remove(os.path.join(self.out, ev))
        fails, _ = self.validate()
        self.assertTrue(any("video" in f and "missing" in f for f in fails), fails)
        self.assertTrue(any("is gone" in f for f in fails), fails)

    def test_editing_evidence_after_recording_fails_validation(self):
        self.execute()
        ev = self.result("crew-api.health.ok")["evidence"]["api-transcript"][0]
        with open(os.path.join(self.out, ev), "a", encoding="utf-8") as fh:
            fh.write(" ")
        fails, _ = self.validate()
        self.assertTrue(any("changed after it was recorded" in f for f in fails), fails)

    def test_claiming_pass_on_a_partial_oracle_fails_validation(self):
        self.execute()
        p = os.path.join(self.out, "crew-api.health.partial", "result.json")
        r = self.result("crew-api.health.partial")
        r["verdict"] = "pass"
        write_json(p, r)
        fails, _ = self.validate()
        self.assertTrue(any("report `partial`, not `pass`" in f for f in fails), fails)
        self.assertTrue(any("result.json changed after it was recorded" in f for f in fails), fails)
        # Even with the vault check off, the verdict rule still refuses it.
        fails, _ = self.validate(vault=False)
        self.assertTrue(any("report `partial`, not `pass`" in f for f in fails), fails)

    def test_pass_on_a_fixture_or_unobserved_check_fails_validation(self):
        self.execute()
        p = os.path.join(self.out, "studio-ui.page.shows", "result.json")
        r = self.result("studio-ui.page.shows")
        r["verdict"] = "pass"
        write_json(p, r)
        fails, _ = self.validate(vault=False)
        self.assertTrue(any("e2e-live or e2e-hermetic" in f for f in fails), fails)
        r = self.result("crew-api.health.ok")
        r["observed"][0]["ok"] = None
        write_json(os.path.join(self.out, "crew-api.health.ok", "result.json"), r)
        fails, _ = self.validate(vault=False)
        self.assertTrue(any("not observed to hold" in f for f in fails), fails)

    def test_dropping_a_capability_or_tampering_run_json_fails(self):
        self.execute()
        rp = os.path.join(self.out, "run.json")
        run = read_json(rp)
        run["capabilities"].remove("crew-api.needs.container")
        write_json(rp, run)
        fails, _ = self.validate()
        self.assertTrue(any("differ from the selection" in f for f in fails), fails)
        self.assertTrue(any("run.json changed after it was recorded" in f for f in fails), fails)

    def test_vault_tampering_and_missing_vault(self):
        self.execute()
        idx = read_json(os.path.join(self.out, "vault-index.json"))
        aid = idx["entries"]["crew-api.health.ok"]
        entry_p = os.path.join(self.out, ".wicked-vault", "entries", aid + ".json")
        entry = read_json(entry_p)
        with open(os.path.join(self.out, ".wicked-vault", entry["payload_ref"]), "a", encoding="utf-8") as fh:
            fh.write(" ")
        fails, _ = self.validate()
        self.assertTrue(any("vault tampered" in f for f in fails), fails)
        shutil.rmtree(os.path.join(self.out, ".wicked-vault"))
        fails, _ = self.validate()
        self.assertTrue(any("vault" in f and "missing" in f for f in fails), fails)

    def test_no_vault_run_is_refused_unless_allowed(self):
        self.execute(no_vault=True)
        fails, _ = self.validate()
        self.assertTrue(any("not recorded in wicked-vault" in f for f in fails), fails)
        self.assertEqual(self.validate(vault=False)[0], [])

    def test_a_scenario_that_fails_or_contradicts_is_fail(self):
        self.fake.behaviour = {"hermetic/one": {"status": "failed"}}
        self.execute()
        self.assertEqual(self.result("crew-api.health.ok")["verdict"], "fail")
        self.assertEqual(self.validate()[0], [])

    def test_an_unsatisfied_transcript_is_partial_never_pass(self):
        self.fake.behaviour = {"hermetic/one": {"http": [{"method": "GET", "url": "/api/v1/health", "status": 500}]}}
        self.execute()
        r = self.result("crew-api.health.ok")
        self.assertEqual(r["verdict"], "partial")
        self.assertEqual(r["observed"][0]["how"], "transcript: unsatisfied")

    def test_missing_required_evidence_is_error_not_a_verdict(self):
        self.fake.kinds = {"video", "screenshot", "trace", "api-transcript"}
        self.caps.append(cap("crew-api.needs.events", required_evidence=["api-transcript", "event-log"]))
        self.execute()
        r = self.result("crew-api.needs.events")
        self.assertEqual(r["verdict"], "skipped")
        self.assertEqual(r["skip"]["dep"], "evidence:event-log")
        self.assertEqual(self.validate()[0], [])

    def test_plan_only_runs_nothing(self):
        self.execute(plan_only=True)
        self.assertEqual(self.fake.runs, [])
        self.assertTrue(os.path.isfile(os.path.join(self.out, "plan.json")))

    def test_operator_daemon_ports_are_refused(self):
        for port in (7701, 7721):
            with self.assertRaises(runmod.RunError):
                runmod.check_target(run_args(self.out, target="live", studio="http://127.0.0.1:%d" % port))
        runmod.check_target(run_args(self.out, target="live", studio="http://127.0.0.1:7999"))
        with self.assertRaises(runmod.RunError):
            runmod.check_target(run_args(self.out, target="fixture", studio="http://127.0.0.1:7999"))

    @unittest.skipUnless(shutil.which("wicked-vault"), "the real wicked-vault CLI is not installed")
    def test_real_wicked_vault(self):
        os.environ.pop("E2E_VAULT", None)
        self.execute()
        self.assertEqual(self.validate()[0], [])
        ev = self.result("crew-api.health.ok")["evidence"]["api-transcript"][0]
        with open(os.path.join(self.out, ev), "a", encoding="utf-8") as fh:
            fh.write(" ")
        self.assertTrue(any("changed after it was recorded" in f for f in self.validate()[0]))


# ── adapters' parsing (no products) ───────────────────────────────────────────────────────────

class AdapterParsing(unittest.TestCase):
    def test_har(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "a.har")
            with open(p, "w") as fh:
                json.dump({"log": {"entries": [{"request": {"method": "POST", "url": "http://h:1/api/v1/runs",
                                                            "postData": {"text": "{\"workflow\": \"bug\"}"}},
                                                "response": {"status": 201, "content": {"text": "{\"runId\": \"r\"}"}}}]}}, fh)
            h = parse_har(p)[0]
            self.assertEqual((h["method"], h["status"], h["req"], h["res"]), ("POST", 201, {"workflow": "bug"}, {"runId": "r"}))
        finally:
            shutil.rmtree(d)

    def test_smoke_tap_is_split_by_step(self):
        o = Outcome("passed")
        http = [{"step": "S01", "method": "GET", "url": "/api/v1/health", "status": 200, "res": {"ok": True}},
                {"step": "S02", "method": "GET", "url": "/api/v1/diagnostics", "status": 200, "res": {}}]
        ws = [{"step": "S01", "open": "ws://x/ws"}, {"step": "S01", "frame": {"type": "chatReply", "ok": True}}]
        SmokeAdapter._observe(o, "S01", http, ws, [], [], 4321)
        self.assertEqual([h["url"] for h in o.obs.http], ["/api/v1/health"])
        self.assertEqual(o.obs.events[0]["type"], "chatReply")
        self.assertFalse(o.obs.streams["ws"]["complete"])
        self.assertEqual(o.obs.bindings["port"], 4321)

    def test_direct_client_is_read_only(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)

            class R:
                returncode, stdout, stderr = 0, "1.2.3", ""
            return R()
        dc = DirectClient("fixture", runner=fake_run)
        self.assertIsNone(dc.get("/api/v1/health"), "no daemon reads off the live target")
        self.assertIsNone(dc.run_safe("wicked-crew --version"), "no host CLI runs off the live target")
        live = DirectClient("live", runner=fake_run)
        self.assertIsNone(live.run_safe("wicked-crew serve"), "only --version/--help forms run")
        self.assertIsNone(live.run_safe("wicked-crew status --json"))


class ReviewFindings(unittest.TestCase):
    """The cross-review's reproductions (wicked-ci#54): each one must stay closed."""

    def test_complete_stream_with_an_unbound_placeholder_is_a_wildcard(self):
        o = ob.Observations()
        o.stream("network", True)
        o.add_event("network", "POST /api/v1/runs/other-run/cancel", {"body": {}})
        ch = {"kind": "event", "source": "network", "type": "POST /api/v1/runs/{runId}/cancel", "count": {"min": 1}}
        r = ob.evaluate(ch, o, {}, "c#0")
        self.assertTrue(r["ok"] and r.get("wildcard"))
        c = cap("studio-ui.x.y", surface="ui", oracle=dict(ch, complete=True), required_evidence=["video"])
        self.assertEqual(vd.derive(c, "passed", [dict(r)], "e2e-live", True)[0], "partial")
        never = dict(ch, count=0)
        self.assertIsNone(ob.evaluate(never, o, {}, "c#0")["ok"], "a loose forbidden-request hit is not decided")
        self.assertIs(ob.evaluate(never, o, {"runId": "mine"}, "c#0")["ok"], True)

    def test_the_request_body_must_match(self):
        o = ob.Observations()
        o.add_http("POST", "/api/v1/runs", 201, {"workflow": "feature", "problem": "x"}, {"runId": "r"})
        ch = {"kind": "api", "method": "POST", "path": "/api/v1/runs", "expect": {"status": 201}, "body": {"workflow": "bug"}}
        self.assertIsNone(ob.evaluate(ch, o, {}, "c#0")["ok"])
        self.assertIs(ob.evaluate(dict(ch, body={"workflow": "feature"}), o, {}, "c#0")["ok"], True)
        r = ob.evaluate(dict(ch, body={"workflow": "{wf}"}), o, {}, "c#0")
        self.assertTrue(r["ok"] and r.get("wildcard"), "an unbound body placeholder ties the hold to nothing")
        self.assertIs(ob.evaluate(dict(ch, body="{request_body}"), o, {}, "c#0")["ok"], True)

    def test_a_result_cannot_upgrade_its_scenario(self):
        c = cap("crew-api.a.b", scenarios=[{"ref": "wicked-crew:packages/crew/tests/x.test.ts", "fidelity": "integration"},
                                         {"ref": "wicked-ci:smoke/lib/steps/S01-boot.mjs", "fidelity": "e2e-hermetic"}])
        res = {"verdict": "pass", "observed": [{"value": 200, "ok": True}],
               "scenario": {"ref": "wicked-crew:packages/crew/tests/x.test.ts", "name": None, "fidelity": "e2e-live",
                            "status": "passed"}}
        self.assertTrue(any("not the catalog's" in p for p in vd.problems(c, res)))
        res["scenario"] = dict(res["scenario"], name="nonexistent test", fidelity="integration")
        self.assertTrue(any("not one of this capability's scenarios" in p for p in vd.problems(c, res)))
        res["scenario"] = {"ref": "wicked-ci:smoke/lib/steps/S01-boot.mjs", "fidelity": "e2e-hermetic", "status": "passed"}
        self.assertEqual(vd.problems(c, res), [])

    def test_the_live_client_never_follows_a_redirect(self):
        import http.server
        import threading
        from e2ecat.adapters.direct import LiveClient

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/v1/health":
                    self.send_response(302)
                    self.send_header("Location", "/outside-api")
                    self.end_headers()
                else:
                    body = b'{"ok": true}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            lc = LiveClient("http://127.0.0.1:%d" % srv.server_address[1])
            r = lc.get("/api/v1/health")
            self.assertEqual(r["status"], 302)
            self.assertEqual([c["url"] for c in lc.calls], ["/api/v1/health"])
        finally:
            srv.shutdown()
            srv.server_close()

    def test_second_review_round(self):
        # cli tokens: .exe and placeholders inside a token
        self.assertTrue(ob.cli_matches("wicked-core gate-hook --scope=e2e-{runId}",
                                       ["C:/bin/wicked-core.EXE", "gate-hook", "--scope=e2e-123"]))
        self.assertFalse(ob.cli_matches("wicked-core gate-hook --scope=e2e-{runId}", ["wicked-core", "gate-hook", "--x"]))
        # an unbound expected value is undecidable, never a contradiction
        o = ob.Observations()
        o.add_http("GET", "/api/v1/runs/r1", 200, None, {"id": "r1"})

        class Live:
            def get(self, path):
                return {"status": 200, "json": {"id": "r1"}}
        ch = {"kind": "api", "method": "GET", "path": "/api/v1/runs/r1",
              "expect": {"json": [{"path": "$.id", "op": "eq", "value": "{runId}"}]}}
        self.assertIsNone(ob.evaluate(ch, o, {}, "c#0")["ok"])
        self.assertIsNone(ob.evaluate(ch, ob.Observations(), {}, "c#0", direct=Live(), direct_definitive=True)["ok"])
        self.assertIs(ob.evaluate(ch, o, {"runId": "r1"}, "c#0")["ok"], True)
        # a file outside every root is not observed, even for `absent`
        d = tempfile.mkdtemp()
        try:
            o.file_roots = [d]
            self.assertIsNone(ob.evaluate({"kind": "file", "path": "../../outside", "assert": "absent"}, o, {}, "c#0")["ok"])
            self.assertIs(ob.evaluate({"kind": "file", "path": "inside-missing", "assert": "absent"}, o, {}, "c#0")["ok"], True)
        finally:
            shutil.rmtree(d)
        # the runner's own exit run decides only on a read-only path
        o2 = ob.Observations()
        o2.cli.append({"argv": ["wicked-crew", "--version"], "code": 1, "stdout": "", "stderr": "", "source": "direct"})
        exitc = {"kind": "exit", "cmd": "wicked-crew --version", "code": 0}
        self.assertIsNone(ob.evaluate(exitc, o2, {}, "c#0")["ok"])
        self.assertIs(ob.evaluate(exitc, o2, {}, "c#0", direct_definitive=True)["ok"], False)
        # seat states and python modules
        self.assertEqual(deps.classify("seats signed out"), "seat-state")
        self.assertEqual(deps.classify("a seat with a revoked credential"), "seat-state")
        self.assertIn("python module pptx", deps.Probe().check("tool-python", "python-pptx")[1])
        # negative DOM checks hold only at the end
        sys.path.insert(0, os.path.join(E2E, "lib", "e2ecat", "pwhook"))
        import e2e_pw
        self.assertTrue(e2e_pw.negative({"assert": "count", "value": 0}))
        self.assertTrue(e2e_pw.negative({"assert": "hidden"}))
        self.assertFalse(e2e_pw.negative({"assert": "count", "value": 2}))

    @unittest.skipIf(os.name == "nt", "process groups: POSIX (Windows uses taskkill /T)")
    def test_a_timeout_ends_the_whole_process_tree(self):
        from e2ecat.adapters import run_logged
        d = tempfile.mkdtemp()
        try:
            pidf = os.path.join(d, "grandchild.pid")
            code = ("import subprocess, sys, time\n"
                    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                    "open(%r, 'w').write(str(g.pid))\n"
                    "time.sleep(60)\n" % pidf)
            rc, _ = run_logged([sys.executable, "-c", code], d, dict(os.environ), os.path.join(d, "log"), 3)
            self.assertIsNone(rc)
            with open(pidf) as fh:
                gpid = int(fh.read())
            import time
            for _ in range(50):
                try:
                    os.kill(gpid, 0)
                except ProcessLookupError:
                    break
                try:
                    os.waitpid(gpid, os.WNOHANG)
                except ChildProcessError:
                    pass
                time.sleep(0.1)
            else:
                self.fail("the grandchild survived the unit timeout")
        finally:
            shutil.rmtree(d)


class StudioClaims(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "e2e"))
        with open(os.path.join(self.d, "e2e", "run_journeys.py"), "w") as fh:
            fh.write('LIVE = ["seed_surfaces", "test_feature_live"]\n')
        for n in ("desk_home", "seed_surfaces"):
            with open(os.path.join(self.d, "e2e", n + "_test.py"), "w") as fh:
                fh.write("")

    def tearDown(self):
        shutil.rmtree(self.d)

    def ctx(self, target, **kw):
        c = argparse.Namespace(target=target, checkouts={"wicked-studio": self.d}, studio_url="http://127.0.0.1:7999",
                               live_journeys=False, playwright_ok=lambda: (True, "ok"))
        for k, val in kw.items():
            setattr(c, k, val)
        return c

    def test_fixture_never_runs_a_live_journey_and_live_is_opt_in(self):
        from e2ecat.adapters.studio import StudioJourneyAdapter
        ad = StudioJourneyAdapter()
        fx = {"ref": "wicked-studio:e2e/desk_home_test.py", "fidelity": "e2e-fixture"}
        lv = {"ref": "wicked-studio:e2e/seed_surfaces_test.py", "fidelity": "e2e-live"}
        self.assertIsNotNone(ad.claim(fx, self.ctx("fixture")))
        self.assertIsNone(ad.claim(lv, self.ctx("fixture")), "a LIVE journey never runs on the fixture target")
        self.assertIsNone(ad.claim(fx, self.ctx("live")))
        key, params = ad.claim(lv, self.ctx("live"))
        os.makedirs(os.path.join(self.d, "dist-sameorigin"))
        with open(os.path.join(self.d, "dist-sameorigin", "index.html"), "w") as fh:
            fh.write("<html>")
        self.assertEqual(ad.available(self.ctx("live"), params)[0], "adapter:live-journeys")
        self.assertIsNone(ad.available(self.ctx("live", live_journeys=True), params))

    def test_live_client_reads_only_api_paths(self):
        from e2ecat.adapters.direct import LiveClient
        seen = []

        def opener(req, timeout):
            seen.append((req.get_method(), req.full_url))
            raise OSError("no network in tests")
        lc = LiveClient("http://127.0.0.1:7999", opener=opener)
        self.assertIsNone(lc.get("/__fixture"))
        self.assertIsNone(lc.get("/api/v1/health"))
        self.assertEqual(seen, [("GET", "http://127.0.0.1:7999/api/v1/health")])


class Reports(unittest.TestCase):
    def test_html_escapes_and_paths_are_redacted(self):
        d = tempfile.mkdtemp()
        try:
            home = os.path.expanduser("~")
            write_json(os.path.join(d, "run.json"), {"run_id": "r1", "capabilities": ["crew-api.x.y"], "target": "fixture"})
            write_json(os.path.join(d, "crew-api.x.y", "result.json"), {
                "id": "crew-api.x.y", "verdict": "fail", "reason": "<script>alert(1)</script> at %s/secret" % home,
                "observed": [{"ok": False, "value": 1}], "evidence": {}})
            doc = report.write(d, {"crew-api.x.y": cap("crew-api.x.y")})
            self.assertEqual(doc["counts"], {"fail": 1})
            html_ = read_text(os.path.join(d, "report.html"))
            self.assertNotIn("<script>alert", html_)
            for f in ("report.html", "report.md", "report.json"):
                self.assertNotIn(home + os.sep, read_text(os.path.join(d, f)))
        finally:
            shutil.rmtree(d)


class EvidenceManifest(unittest.TestCase):
    def test_manifest_lists_every_evidence_file(self):
        d = tempfile.mkdtemp()
        try:
            write_json(os.path.join(d, "ev", "a.json"), {"a": 1})
            rp = write_json(os.path.join(d, "c.x.y", "result.json"), {"id": "c.x.y", "verdict": "partial",
                                                                      "evidence": {"api-transcript": ["ev/a.json"]}})
            mp = evm.write_manifest(d, "r", "c.x.y", rp, read_json(rp))
            man = read_json(mp)
            self.assertEqual(list(man["files"]), ["ev/a.json"])
            self.assertEqual(man["result_sha256"], evm.sha256_file(rp))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
