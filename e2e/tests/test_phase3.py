"""Phase 3 CLI helpers the skills call: the plan summary (`run --plan-only`), the report's
blockers, `e2e evidence` and `e2e resolve` edge cases (stdlib unittest; fake adapter, stub vault).

The router evals (request -> selection) live with the skill: skills/tests/test_skills.py.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
E2E = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(E2E, "lib"))
sys.path.insert(0, HERE)

from e2ecat import deps, evidence as evm, plansum, report, resolve as rs, run as runmod, validate as v  # noqa: E402
from e2ecat.adapters import write_json  # noqa: E402
from e2ecat.util import read_json, read_text  # noqa: E402
from test_runner import STUB_VAULT, FakeAdapter, cap, run_args  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="e2e-phase3-test-")
        self.out = os.path.join(self.tmp, "run")
        self.old_vault = os.environ.get("E2E_VAULT")
        os.environ["E2E_VAULT"] = json.dumps(STUB_VAULT)
        self.caps = [
            cap("crew-api.health.ok", deps=["daemon"]),
            cap("crew-api.health.partial", oracle={"kind": "api", "method": "GET", "path": "/api/v1/health",
                                                   "expect": {"status": 200}, "complete": False, "untyped": ["more"]}),
            cap("studio-ui.page.shows", surface="ui", required_evidence=["video", "screenshot", "trace"],
                oracle={"kind": "dom", "selector": "[data-testid=x]", "assert": "visible", "complete": True},
                scenarios=[{"ref": "fake:fixture/journey", "fidelity": "e2e-fixture"}]),
            cap("crew-api.needs.container", deps=["container runtime"]),
            cap("crew-api.only.planned", scenarios=["planned"]),
            cap("crew-api.manual.one", oracle={"kind": "manual", "category": "human-gui", "reason": "a login"}),
        ]
        self.fake = FakeAdapter()

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
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                rc = runmod.execute(run_args(self.out, **kw), E2E, self.caps, {}, "", None, adapters=[self.fake])
        finally:
            runmod.depsmod.Probe = orig
        return rc, buf.getvalue()


class PlanSummary(Fixture):
    def test_plan_only_prints_and_writes_an_honest_summary(self):
        (_, rc), text = self.execute(plan_only=True)
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.runs, [], "a plan runs nothing")
        s = read_json(os.path.join(self.out, "plan.json"))["summary"]
        self.assertEqual((s["selected"], s["will_run"], s["skipped"]), (6, 4, 2))
        self.assertEqual(s["ceilings"], {"pass": 1, "partial": 2, "manual": 1},
                         "only the complete hermetic one can pass; partial oracle and fixture fidelity cap at partial")
        self.assertEqual(set(s["skips"]), {"container runtime", "scenario:planned"})
        self.assertIn("daemon", s["requirements"])
        self.assertEqual(s["requirements"]["daemon"]["provided"], 1, "the fake scenario provides the daemon")
        self.assertGreater(s["estimate"]["high_s"], s["estimate"]["low_s"])
        self.assertTrue(all(u["basis"] for u in s["units"]))
        self.assertFalse(s["ask_before_running"], "all cost S on the fixture target")
        self.assertIn("best possible verdicts: pass 1, partial 2, manual 1", text)
        self.assertIn("skipped before running", text)

    def test_cost_m_or_l_asks(self):
        self.caps[0] = cap("crew-api.health.ok", cost="L")
        (_, _), text = self.execute(plan_only=True)
        s = read_json(os.path.join(self.out, "plan.json"))["summary"]
        self.assertTrue(s["ask_before_running"])
        self.assertIn("ask before running", text)

    def test_live_target_asks_and_names_the_daemon(self):
        class Ctx:
            target, studio_url, live_journeys = "live", "http://127.0.0.1:7801", True
        s = plansum.summarize([], [], {}, Ctx())
        self.assertTrue(s["ask_before_running"])
        self.assertIn("--live-journeys", s["ask_reasons"][0])

    def test_ceiling_of_direct_reads_on_a_driven_path(self):
        c = cap("crew-api.runs.launch", user_path="POST /api/v1/runs {}")

        class U:
            class adapter:
                name = "direct"
        self.assertEqual(plansum.ceiling(c, U, {"fidelity": "e2e-live"})[0], "partial")
        self.assertEqual(plansum.ceiling(cap("crew-api.health.ok"), U, {"fidelity": "e2e-live"})[0], "pass")


class Blockers(Fixture):
    def test_report_lists_what_blocks_a_pass(self):
        self.execute()
        doc = read_json(os.path.join(self.out, "report.json"))
        b = doc["blockers"]
        self.assertIn("partial: incomplete oracle (untyped clauses)", b)
        self.assertIn("partial: scenario fidelity e2e-fixture is not certification", b)
        self.assertIn("skipped: no scenario exists yet (planned)", b)
        self.assertIn("manual oracle (never a pass)", b)
        self.assertTrue(any(k.startswith("skipped: unmet dependency") for k in b), b)
        self.assertNotIn("crew-api.health.ok", [c for g in b.values() for c in g["capabilities"]], "a pass has no blocker")
        md = read_text(os.path.join(self.out, "report.md"))
        self.assertIn("## What blocks a pass", md)
        self.assertIn("What blocks a pass", read_text(os.path.join(self.out, "report.html")))

    def test_blocks_reads_structure_not_reason_text(self):
        c = cap("x.y.z")
        self.assertEqual(report.blocks(c, {"verdict": "pass", "reason": "the oracle is partial"}), [])
        self.assertEqual(report.blocks(c, {"verdict": "skipped", "skip": {"dep": "checkout:wicked-crew"}}),
                         ["skipped: missing checkout (wicked-crew; pass --src or --checkout)"])
        self.assertEqual(report.blocks(c, {"verdict": "partial", "observed": [{"ok": True, "wildcard": True}],
                                           "scenario": {"adapter": "smoke", "fidelity": "e2e-hermetic"}}),
                         ["partial: a check held only on something not tied to this path (wildcard)"])
        self.assertEqual(report.blocks(c, {}), ["no result.json (the run did not record it)"])


class PlanAndBlockerReasons(Fixture):
    def test_manual_is_never_listed_as_at_most_partial(self):
        (_, _), text = self.execute(plan_only=True)
        s = read_json(os.path.join(self.out, "plan.json"))["summary"]
        self.assertEqual(sum(s["ceiling_reasons"].values()) >= s["ceilings"]["partial"], True)
        self.assertNotIn("manual", " ".join(s["ceiling_reasons"]))
        self.assertNotIn("at most partial: the oracle is manual", text)

    def test_direct_reads_do_not_block_a_read_only_path(self):
        c = cap("crew-api.health.partial", oracle={"kind": "api", "method": "GET", "path": "/api/v1/health",
                                                   "expect": {"status": 200}, "complete": False, "untyped": ["x"]})
        b = report.blocks(c, {"verdict": "partial", "observed": [{"ok": True}],
                              "scenario": {"adapter": "direct", "fidelity": "e2e-live"}})
        self.assertEqual(b, ["partial: incomplete oracle (untyped clauses)"])


class Evidence(Fixture):
    def cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(E2E, "bin", "e2e")] + list(args), capture_output=True,
                              text=True, timeout=60, env=dict(os.environ, E2E_VAULT=json.dumps(STUB_VAULT)))

    def test_intact_evidence_lists_every_file(self):
        self.execute()
        out = evm.inspect(self.out, "studio-ui.page.shows")
        self.assertTrue(out["intact"], out["problems"])
        kinds = {r["kind"] for r in out["evidence"]}
        self.assertLessEqual({"video", "screenshot", "trace"}, kinds)
        self.assertTrue(all(r["status"] == "ok" for r in out["evidence"]))
        self.assertEqual(out["vault"].get("verify"), "pass")
        r = self.cli("evidence", self.out, "studio-ui.page.shows")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("integrity: INTACT", r.stdout)

    def test_edited_deleted_and_flipped_are_not_intact(self):
        self.execute()
        res = read_json(os.path.join(self.out, "studio-ui.page.shows", "result.json"))
        vid = res["evidence"]["video"][0]
        shot = res["evidence"]["screenshot"][0]
        with open(os.path.join(self.out, shot), "ab") as fh:
            fh.write(b"x")
        os.remove(os.path.join(self.out, vid))
        out = evm.inspect(self.out, "studio-ui.page.shows", use_cli=False)
        st = {r["path"]: r["status"] for r in out["evidence"]}
        self.assertEqual(st[vid], "gone")
        self.assertEqual(st[shot], "changed")
        self.assertFalse(out["intact"])
        p = os.path.join(self.out, "crew-api.health.partial", "result.json")
        r = read_json(p)
        r["verdict"] = "pass"
        write_json(p, r)
        out = evm.inspect(self.out, "crew-api.health.partial", use_cli=False)
        self.assertEqual(out["result"]["status"], "changed")
        self.assertFalse(out["intact"])
        cp = self.cli("evidence", self.out, "crew-api.health.partial", "--no-vault-cli", "--json")
        self.assertEqual(cp.returncode, 1)
        self.assertFalse(json.loads(cp.stdout)["intact"])

    def test_an_evidence_path_outside_the_run_is_not_read(self):
        self.execute(no_vault=True)
        p = os.path.join(self.out, "crew-api.health.ok", "result.json")
        r = read_json(p)
        r["evidence"]["api-transcript"] = ["../../../../etc/hosts"]
        write_json(p, r)
        out = evm.inspect(self.out, "crew-api.health.ok", use_cli=False)
        self.assertEqual(out["evidence"][0]["status"], "outside")
        self.assertIsNone(out["evidence"][0]["sha256"])
        self.assertFalse(out["intact"])

    def test_an_unsealed_run_is_never_intact(self):
        self.execute(no_vault=True)
        out = evm.inspect(self.out, "crew-api.health.ok")
        self.assertFalse(out["intact"])
        self.assertTrue(all(r["status"] == "unverified" for r in out["evidence"]))

    def test_an_empty_frozen_manifest_is_not_intact(self):
        self.execute()
        idx = read_json(os.path.join(self.out, "vault-index.json"))
        aid = idx["entries"]["crew-api.health.ok"]
        orig = evm._frozen
        evm._frozen = lambda vdir, scope, claim, a: ({}, None)
        try:
            out = evm.inspect(self.out, "crew-api.health.ok", use_cli=False)
        finally:
            evm._frozen = orig
        self.assertTrue(aid)
        self.assertFalse(out["intact"])
        self.assertTrue(any("malformed" in p for p in out["problems"]))

    def test_unknown_capability_is_an_error(self):
        self.execute()
        r = self.cli("evidence", self.out, "nope.nope.nope")
        self.assertEqual(r.returncode, 2)


class ResolveEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.caps = v.load_catalog(E2E)
        cls.profiles = read_json(os.path.join(E2E, "profiles.json"))["profiles"]

    def r(self, text, **kw):
        return rs.resolve(text, self.caps, self.profiles, **kw)

    def test_operator_ports_are_refused_in_every_spelling(self):
        for text in ("test it on http://127.0.0.1:7701", "studio on :7721", "check the bus at http://localhost:7701/api"):
            out = self.r(text)
            self.assertEqual(out["status"], "refused", text)
            self.assertEqual(out["commands"], [], text)

    def test_a_rerun_of_an_operator_port_run_is_refused(self):
        tmp = tempfile.mkdtemp(prefix="e2e-resolve-")
        try:
            write_json(os.path.join(tmp, "run.json"), {"target": "live", "studio": "http://127.0.0.1:7701",
                                                       "capabilities": ["crew-api.runs.cancel"]})
            write_json(os.path.join(tmp, "crew-api.runs.cancel", "result.json"), {"verdict": "fail"})
            out = self.r("re-run what failed", run_dir=tmp)
            self.assertEqual(out["status"], "refused")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_nothing_failed_means_nothing_to_rerun(self):
        tmp = tempfile.mkdtemp(prefix="e2e-resolve-")
        try:
            write_json(os.path.join(tmp, "run.json"), {"target": "fixture", "capabilities": ["crew-api.runs.cancel"]})
            write_json(os.path.join(tmp, "crew-api.runs.cancel", "result.json"), {"verdict": "partial"})
            out = self.r("re-run what failed", run_dir=tmp)
            self.assertEqual(out["status"], "no-match")
            self.assertIsNone(out["selection"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_request_cannot_smuggle_arguments_into_a_command(self):
        import shlex
        evil = "test studio http://127.0.0.1:7801/${IFS}--out${IFS}X${IFS}--live-journeys;#"
        out = self.r(evil)
        self.assertEqual(out["status"], "refused")
        self.assertEqual(out["commands"], [])
        self.assertIsNone(out["studio"])
        out = self.r("test the run page against http://127.0.0.1:7801/studio")
        argv = shlex.split(out["commands"][0])
        self.assertEqual(argv[-1], "--plan-only")
        self.assertEqual(argv[argv.index("--studio") + 1], "http://127.0.0.1:7801/studio")
        self.assertNotIn("--live-journeys", argv)
        tmp = tempfile.mkdtemp(prefix="e2e resolve; rm -rf x #")
        try:
            write_json(os.path.join(tmp, "run.json"), {"target": "fixture", "capabilities": ["crew-api.runs.cancel"]})
            write_json(os.path.join(tmp, "crew-api.runs.cancel", "result.json"), {"verdict": "fail"})
            for c in self.r("summarise the last run", run_dir=tmp)["commands"]:
                self.assertIn(tmp, shlex.split(c), "the run dir stays one argument")
            write_json(os.path.join(tmp, "run.json"), {"target": "live", "studio": "http://h:1/$(id)",
                                                       "capabilities": ["crew-api.runs.cancel"]})
            out = self.r("re-run what failed", run_dir=tmp)
            self.assertEqual(out["status"], "refused")
            self.assertEqual(out["commands"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_words_inside_an_id_never_pick_the_action(self):
        for cid in ("studio-ui.launch.plan-preview", "studio-ui.projects.coverage-domain", "crew-api.chats.transcript"):
            out = self.r("test %s" % cid)
            self.assertEqual((out["action"], out["status"], out["selection"]), ("run", "resolved", "id:%s" % cid))

    def test_operator_ports_without_a_scheme_or_before_a_query_are_refused(self):
        for text in ("cheap studio checks on localhost:7701", "test the live daemon on port 7701",
                     "test it on 127.0.0.1:7721", "test it on http://127.0.0.1:7701?foo=1"):
            out = self.r(text)
            self.assertEqual((out["status"], out["target"], out["commands"]), ("refused", "live", []), text)

    def test_a_refusal_is_never_downgraded_and_a_rerun_without_a_run_dir_runs_nothing(self):
        tmp = tempfile.mkdtemp(prefix="e2e-resolve-")
        try:
            write_json(os.path.join(tmp, "run.json"), {"target": "fixture", "capabilities": ["crew-api.runs.cancel"]})
            write_json(os.path.join(tmp, "crew-api.runs.cancel", "result.json"), {"verdict": "partial"})
            out = self.r("re-run what failed on :7701", run_dir=tmp)
            self.assertEqual((out["status"], out["commands"]), ("refused", []))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        out = self.r("re-run the studio failures")
        self.assertEqual((out["status"], out["selection"], out["commands"]), ("needs-input", None, []))

    def test_a_rerun_keeps_the_request_topic(self):
        tmp = tempfile.mkdtemp(prefix="e2e-resolve-")
        try:
            write_json(os.path.join(tmp, "run.json"), {"target": "fixture",
                                                       "capabilities": ["crew-api.runs.cancel", "studio-ui.rail.order"]})
            for cid in ("crew-api.runs.cancel", "studio-ui.rail.order"):
                write_json(os.path.join(tmp, cid, "result.json"), {"verdict": "fail"})
            out = self.r("re-run the studio failures", run_dir=tmp)
            self.assertEqual((out["selection"], out["count"]), ("id:studio-ui.rail.order", 1))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_filler_word_that_is_a_tag_is_named(self):
        out = self.r("certify crew testing")
        self.assertEqual(out["shadowed"], ["testing"])
        self.assertTrue(any("tag:testing" in e["as"] for e in out["explain"]))
        self.assertIn("is also a catalog tag", rs.render(out))
        self.assertEqual(self.r("check a plugin's hooks")["selection"], "tag:plugin,hooks", "'s is not a plural")

    def test_a_rerun_sizes_and_asks_for_the_failed_ids_not_the_request_words(self):
        tmp = tempfile.mkdtemp(prefix="e2e-resolve-")
        try:
            write_json(os.path.join(tmp, "run.json"), {"target": "fixture", "capabilities": ["crew-api.runs.boot-resume"]})
            write_json(os.path.join(tmp, "crew-api.runs.boot-resume", "result.json"), {"verdict": "error"})
            out = self.r("re-run what failed", run_dir=tmp)
            self.assertEqual(out["selection"], "id:crew-api.runs.boot-resume")
            self.assertIsNone(out["profile"])
            self.assertEqual((out["count"], out["cost"]), (1, {"L": 1}))
            self.assertTrue(out["ask_before_running"])
            self.assertIn("L x1", out["ask_reasons"][0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_manual_exclusion_is_read_before_the_vocabulary(self):
        from e2ecat.select import select
        out = self.r("run full without manual")
        self.assertEqual((out["profile"], out["selection"]), (None, "!oracle=manual"), "the whole catalog, narrowed")
        out = self.r("test crew without manual")
        self.assertEqual(out["selection"], "area:crew-api !oracle=manual")
        self.assertTrue(all(c["oracle"]["kind"] != "manual" for c in select(self.caps, out["selection"])))

    def run_dir(self, run, verdicts):
        tmp = tempfile.mkdtemp(prefix="e2e-resolve-")
        self.addCleanup(shutil.rmtree, tmp, True)
        write_json(os.path.join(tmp, "run.json"), dict(run, capabilities=list(verdicts)))
        for cid, verdict in verdicts.items():
            write_json(os.path.join(tmp, cid, "result.json"), {"verdict": verdict})
        return tmp

    def test_round3_a_modifier_left_after_a_dropped_profile_selects_nothing(self):
        out = self.r("cheap everything about zorblax")
        self.assertEqual((out["status"], out["selection"], out["profile"], out["commands"]), ("no-match", None, None, []))

    def test_round3_an_unmatched_rerun_topic_reruns_nothing(self):
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail"})
        out = self.r("re-run zorblax failures", run_dir=tmp)
        self.assertEqual((out["status"], out["selection"], out["commands"]), ("no-match", None, []))
        self.assertEqual(self.r("re-run what failed", run_dir=tmp)["selection"], "id:crew-api.runs.cancel")

    def test_round3_an_explicit_fixture_rerun_does_not_inherit_the_live_target(self):
        tmp = self.run_dir({"target": "live", "studio": "http://127.0.0.1:7801"}, {"crew-api.runs.cancel": "fail"})
        out = self.r("re-run what failed on fixture", run_dir=tmp)
        self.assertEqual((out["target"], out["studio"]), ("fixture", None))
        self.assertNotIn("--studio", " ".join(out["commands"]))
        out = self.r("re-run what failed", run_dir=tmp)
        self.assertEqual((out["target"], out["studio"]), ("live", "http://127.0.0.1:7801"))

    def test_round3_evidence_by_alias_opens_the_canonical_id(self):
        tmp = self.run_dir({"target": "fixture"}, {"studio-ui.agents.check-now": "partial"})
        out = self.r("show evidence for seats.ui.copy-signin-and-check-again", run_dir=tmp)
        self.assertEqual(out["status"], "resolved")
        self.assertTrue(out["commands"][0].endswith(" studio-ui.agents.check-now"), out["commands"])

    def test_round3_live_checks_is_a_topic_not_the_live_target(self):
        out = self.r("test live checks")
        self.assertEqual((out["status"], out["target"], out["selection"]), ("resolved", "fixture", "tag:livecheck"))
        self.assertEqual(self.r("what's missing")["action"], "validate-coverage")

    def test_round3_a_rerun_keeps_its_cost_modifier(self):
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail", "crew-api.runs.boot-resume": "error"})
        for text in ("re-run the cheap failures", "re-run what failed without governed runs"):
            out = self.r(text, run_dir=tmp)
            self.assertEqual(out["selection"], "id:crew-api.runs.cancel", text)
        out = self.r("re-run what failed cost<=XL", run_dir=tmp)
        self.assertEqual(out["status"], "no-match")

    def test_round4_evidence_needs_one_canonical_id_with_or_without_a_run_dir(self):
        out = self.r("show evidence for seats.ui.copy-signin-and-check-again")
        self.assertTrue(out["commands"][0].endswith(" studio-ui.agents.check-now"), out["commands"])
        out = self.r("show evidence for studio")
        self.assertTrue(any("one capability id" in n for n in out["needs"]), out["needs"])

    def test_round4_a_live_rerun_without_a_recorded_url_needs_one(self):
        tmp = self.run_dir({"target": "live"}, {"crew-api.runs.cancel": "fail"})
        out = self.r("re-run what failed", run_dir=tmp)
        self.assertEqual(out["status"], "needs-input")
        self.assertEqual(out["commands"], [], "no run command for a live target with no URL")

    def test_round5_punctuated_live_words_still_mean_live(self):
        for text in ("Test the run page on live.", "Run the studio checks against the daemon.",
                     "Certify studio on the running daemon."):
            out = self.r(text)
            self.assertEqual((out["target"], out["status"]), ("live", "needs-input"), text)

    def test_round5_all_and_everything_keep_their_modifiers(self):
        out = self.r("run all cheap tests")
        self.assertEqual((out["profile"], out["selection"]), (None, "cost<=S"))
        self.assertEqual(self.r("run everything without governed runs")["selection"], "cost<=M")
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail", "crew-api.runs.boot-resume": "error"})
        for text in ("re-run all cheap failures", "re-run everything that failed without governed runs"):
            self.assertEqual(self.r(text, run_dir=tmp)["selection"], "id:crew-api.runs.cancel", text)
        self.assertEqual(self.r("run the smoke scenarios")["profile"], "smoke")

    def test_a_request_without_an_execution_verb_only_lists(self):
        for text in ("does the run page work?", "studio smoke", "show crew-api.standing-orders.read",
                     "list crew-api.standing-orders.read", "everything about sign-in"):
            out = self.r(text)
            self.assertEqual(out["action"], "select", text)
            self.assertFalse(any(c.startswith("e2e run") for c in out["commands"]), text)
        self.assertEqual(self.r("dry-run the smoke")["action"], "plan")

    def test_round11_negated_runs_and_dry_run_ids(self):
        for text in ("please do not run crew-api.standing-orders.read", "don't run the smoke", "never test the run page"):
            out = self.r(text)
            self.assertEqual(out["action"], "select", text)
            self.assertFalse(any(c.startswith("e2e run") for c in out["commands"]), text)
        tmp = self.run_dir({"target": "fixture"}, {"interactive.cli.dry-run": "partial"})
        out = self.r("show evidence for interactive.cli.dry-run", run_dir=tmp)
        self.assertEqual((out["action"], out["selection"]), ("evidence", "id:interactive.cli.dry-run"))
        out = self.r("run id:interactive.cli.dry-run")
        self.assertEqual((out["action"], out["status"], out["count"]), ("run", "resolved", 1))
        self.assertEqual(self.r("dry run the smoke")["action"], "plan")

    def test_round12_how_to_and_exclusions(self):
        out = self.r("tell me how to test crew-api.standing-orders.read")
        self.assertEqual(out["action"], "select")
        self.assertFalse(any(c.startswith("e2e run") for c in out["commands"]))
        from e2ecat.select import select
        out = self.r("run all cheap tests except studio")
        sel = select(self.caps, out["selection"])
        self.assertTrue(sel and all(c["_area"] != "studio-ui" and c["cost"] == "S" for c in sel))
        out = self.r("test crew but not crew-api.runs.cancel")
        self.assertNotIn("crew-api.runs.cancel", [c["id"] for c in select(self.caps, out["selection"])])
        self.assertEqual(report.blocks(cap("x.y.z"), {"verdict": "skipped", "skip": {"dep": "adapter:live-journeys"}}),
                         ["skipped: the adapter needs live-journeys"])

    def test_round12_literal_bounds_need_a_scope_and_cancel_is_a_topic(self):
        for text in ("test cost<=S", "test cheap !oracle=manual", "test !id:crew-api.runs.cancel"):
            out = self.r(text)
            self.assertEqual((out["status"], out["commands"]), ("no-match", []), text)
        self.assertEqual(self.r("test surface=ui zorblax")["selection"], "surface=ui")
        self.assertEqual(self.r("run all cost<=S")["selection"], "cost<=S")
        self.assertEqual(self.r("test cancel run")["action"], "run")
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail"})
        self.assertEqual(self.r("re-run the cancel test failures", run_dir=tmp)["action"], "rerun")

    def test_round13_profile_filters_and_literal_exclusions(self):
        from e2ecat.select import select
        ids = lambda e: {c["id"] for c in select(self.caps, e)}
        daily = {c["id"] for c in select(self.caps, self.profiles["daily"]["select"])}
        self.assertEqual(ids(self.r("run daily surface=ui")["selection"]), daily & ids("surface=ui"))
        smoke = {c["id"] for c in select(self.caps, self.profiles["smoke"]["select"])}
        self.assertEqual(ids(self.r("run smoke oracle=api")["selection"]), smoke & ids("oracle=api"))
        out = self.r("run all cheap tests except tag:run-page")
        self.assertEqual(ids(out["selection"]), ids("cost<=S") - ids("tag:run-page"))
        out = self.r("test area:crew-api except id:crew-api.runs.cancel")
        self.assertEqual(ids(out["selection"]), ids("area:crew-api") - {"crew-api.runs.cancel"})
        out = self.r("test crew except tag:runs plugins")
        self.assertEqual(out["selection"], "area:crew-api,plugins-and-installs !tag:runs", "only the next term is excluded")

    def test_round13_every_exclusion_word_excludes(self):
        from e2ecat.select import select
        ids = lambda e: {c["id"] for c in select(self.caps, e)}
        out = self.r("run cheap tests without plugins")
        self.assertEqual(out["status"], "no-match", "a bound plus an exclusion with no scope selects nothing")
        out = self.r("run daily without studio")
        daily = {c["id"] for c in select(self.caps, self.profiles["daily"]["select"])}
        self.assertEqual(ids(out["selection"]), daily - ids("area:studio-ui"))
        out = self.r("run release except governed runs")
        rel = {c["id"] for c in select(self.caps, self.profiles["release"]["select"])}
        self.assertEqual(ids(out["selection"]), rel & ids("cost<=M"))
        self.assertEqual(self.r("test crew except manual")["selection"], "area:crew-api !oracle=manual")
        self.assertEqual(self.r("run all except area:studio-ui")["selection"], "!area:studio-ui")
        self.assertEqual(self.r("test crew without zorblax")["status"], "no-match")
        for text in ("test studio on devbox:7701", "cheap studio checks on myhost:7721"):
            self.assertEqual(self.r(text)["status"], "refused", text)
        self.assertEqual(self.r("cheap studio checks on myhost:7801")["target"], "live")
        tmp = self.run_dir({"target": "live", "studio": "http://127.0.0.1:7801"}, {"crew-api.runs.cancel": "fail"})
        self.assertEqual(self.r("summarise the live run", run_dir=tmp)["status"], "resolved")
        self.assertEqual(self.r("list the live capabilities")["target"], "fixture")
        self.assertEqual(self.r("test cli dry-run")["action"], "run")
        out = self.r("run interactive dry-run")
        self.assertEqual(out["action"], "run")
        self.assertIn("*.dry-run", out["selection"], "dry-run stays a catalog word here")
        self.assertEqual(self.r("do a dry run of the smoke")["action"], "plan")

    def test_round14_negations_fillers_stop_words_live_journeys(self):
        for text in ("test studio, do not run page", "do not exercise crew-api.standing-orders.read"):
            self.assertEqual(self.r(text)["action"], "select", text)
        self.assertEqual(self.r("execute the smoke profile")["profile"], "smoke")
        self.assertEqual(self.r("run all without the governed runs")["selection"], "cost<=M")
        self.assertEqual(self.r("test crew except for manual")["selection"], "area:crew-api !oracle=manual")
        out = self.r("test crew-api.standing-orders.read --live-journeys")
        self.assertEqual((out["target"], out["status"]), ("live", "needs-input"))
        self.assertEqual(self.r("test crew without")["status"], "no-match")
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail"})
        self.assertEqual(self.r("re-run what broke", run_dir=tmp)["selection"], "id:crew-api.runs.cancel")

    def test_round15_live_journeys_carry_into_plan_and_run(self):
        out = self.r("run live journeys for studio-ui.live.seed-surfaces on http://127.0.0.1:7801")
        self.assertEqual(out["status"], "resolved")
        self.assertTrue(all("--live-journeys" in c and "--src CHECKOUTS_DIR" in c for c in out["commands"][:2]), out["commands"])
        self.assertTrue(out["ask_before_running"])
        self.assertFalse(any("--live-journeys" in c for c in self.r("test crew on http://127.0.0.1:7801")["commands"]))

    def test_round16_live_journeys_only_from_a_positive_prose_request(self):
        for text in ("test studio on http://localhost:7801/live-journeys/",
                     "test studio !id:*live-journeys* on http://localhost:7801",
                     "test studio on http://localhost:7801; live journeys are forbidden",
                     "test studio on http://localhost:7801 without live journeys"):
            out = self.r(text)
            self.assertFalse(out["live_journeys"], text)
            self.assertFalse(any("--live-journeys" in c for c in out["commands"]), text)
        for text in ("run studio with live journeys on http://localhost:7801",
                     "test studio on http://localhost:7801 --live-journeys"):
            self.assertTrue(self.r(text)["live_journeys"], text)

    def test_round16_an_exclusion_never_leaks_onto_a_later_term(self):
        out = self.r("run without smoke in crew")
        self.assertNotIn("!area:crew-api", out["selection"] or "")
        self.assertIn("!tag:smoke", out["selection"] or "")
        self.assertEqual(self.r("test crew, without smoke, and plugins")["selection"],
                         "area:crew-api,plugins-and-installs !tag:smoke")
        for text in ("test without testing in studio", "test without cheap checks in studio"):
            self.assertEqual(self.r(text)["status"], "no-match", text)

    def test_a_question_read_as_a_run_always_asks(self):
        out = self.r("does running the run page work?")
        self.assertEqual(out["action"], "run")
        self.assertTrue(out["ask_before_running"])
        self.assertIn("question", out["ask_reasons"][-1] if len(out["ask_reasons"]) == 1 else " ".join(out["ask_reasons"]))
        self.assertFalse(self.r("certify crew-api.standing-orders.read")["ask_before_running"])

    def test_round6_profiles_narrowed_by_modifiers_and_blocker_questions(self):
        from e2ecat.select import select
        out = self.r("run the cheap daily tests")
        self.assertEqual((out["profile"], out["selection"]), (None, "!oracle=manual cost<=S"))
        self.assertTrue(all(c["cost"] == "S" and c["oracle"]["kind"] != "manual" for c in select(self.caps, out["selection"])))
        self.assertEqual(self.r("run release without governed runs")["selection"].count("cost<=M"), 1)
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail", "crew-api.runs.boot-resume": "error"})
        out = self.r("re-run the cheap zorblax failures", run_dir=tmp)
        self.assertEqual((out["status"], out["commands"]), ("no-match", []))
        for text in ("what blocks a pass in studio", "did smoke pass", "what passed in smoke"):
            out = self.r(text, run_dir=tmp)
            self.assertEqual(out["action"], "report", text)
            self.assertFalse(any(c.startswith("e2e run") for c in out["commands"]), text)
        self.assertEqual(self.r("why does validate fail")["action"], "validate-coverage")

    def test_round6_the_plan_command_carries_the_checkouts(self):
        out = self.r("test the run page")
        self.assertIn("--src CHECKOUTS_DIR", out["commands"][0])
        self.assertIn("--plan-only", out["commands"][0])

    def test_round6_live_reruns_inherit_the_recorded_url_and_its_refusal(self):
        tmp = self.run_dir({"target": "live", "studio": "http://127.0.0.1:7801"}, {"crew-api.runs.cancel": "fail"})
        out = self.r("re-run the live failures", run_dir=tmp)
        self.assertEqual((out["status"], out["target"], out["studio"]), ("resolved", "live", "http://127.0.0.1:7801"))
        tmp2 = self.run_dir({"target": "live", "studio": "http://127.0.0.1:7701"}, {"crew-api.runs.cancel": "fail"})
        self.assertEqual(self.r("re-run what failed on the daemon", run_dir=tmp2)["status"], "refused")
        tmp3 = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail"})
        out = self.r("re-run what failed on live", run_dir=tmp3)
        self.assertEqual((out["target"], out["status"]), ("live", "needs-input"))
        out = self.r("Can you test the run page on http://127.0.0.1:7801?")
        self.assertEqual((out["status"], out["studio"]), ("resolved", "http://127.0.0.1:7801"))

    def test_round7_cost_bounds_intersect_and_id_globs_keep_their_question_mark(self):
        self.assertEqual(self.r("test crew cost<=S without governed runs")["selection"], "area:crew-api cost<=S")
        self.assertEqual(self.r("test crew cost<=L cheap")["selection"], "area:crew-api cost<=S")
        out = self.r("run id:crew-api.runs.* !id:crew-api.runs.cance? on fixture")
        self.assertEqual(out["selection"], "id:crew-api.runs.* !id:crew-api.runs.cance?")
        from e2ecat.select import select
        self.assertNotIn("crew-api.runs.cancel", [c["id"] for c in select(self.caps, out["selection"])])

    def test_round7_profile_bounds_survive_and_shadowed_topics_block_widening(self):
        for text, bound in (("run release without manual", "cost<=L"), ("run daily without manual", "cost<=M"),
                            ("run smoke without manual", "cost<=M")):
            self.assertIn(bound, self.r(text)["selection"], text)
        out = self.r("run all the cheap testing checks")
        self.assertEqual((out["status"], out["commands"]), ("no-match", []))
        tmp = self.run_dir({"target": "fixture"}, {"crew-api.runs.cancel": "fail"})
        self.assertEqual(self.r("re-run the testing failures", run_dir=tmp)["status"], "no-match")
        out = self.r("check the bus against http://127.0.0.1:7801")
        self.assertFalse(any("--src" in c for c in out["commands"]), out["commands"])

    def test_round8_literal_bounds_and_exclusions_narrow_a_profile(self):
        from e2ecat.select import select
        rel = {c["id"] for c in select(self.caps, self.profiles["release"]["select"])}
        out = self.r("run release cost<=S")
        got = {c["id"] for c in select(self.caps, out["selection"])}
        self.assertEqual(got, {c for c in rel if next(x for x in self.caps if x["id"] == c)["cost"] == "S"})
        daily = {c["id"] for c in select(self.caps, self.profiles["daily"]["select"])}
        out = self.r("run daily !id:crew-api.runs.cancel")
        self.assertEqual({c["id"] for c in select(self.caps, out["selection"])}, daily - {"crew-api.runs.cancel"})
        out = self.r("run smoke !oracle=manual")
        smoke = {c["id"] for c in select(self.caps, self.profiles["smoke"]["select"])}
        self.assertEqual({c["id"] for c in select(self.caps, out["selection"])}, smoke)

    def test_round9_literal_scopes_keep_prose_limits_and_bad_bounds_fail(self):
        from e2ecat.select import select
        out = self.r("run surface=ui without governed runs")
        self.assertEqual(out["selection"], "surface=ui cost<=M")
        self.assertEqual(self.r("run surface=ui cheap")["selection"], "surface=ui cost<=S")
        out = self.r("run surface=ui without manual cost<=S")
        self.assertTrue(all(c["oracle"]["kind"] != "manual" and c["cost"] == "S" for c in select(self.caps, out["selection"])))
        for text in ("run daily cost<=s", "run release cost<=XL", "test crew cost<=XL cheap"):
            out = self.r(text)
            self.assertEqual((out["status"], out["commands"]), ("no-match", []), text)

    def test_round9_unmatched_topics_never_keep_literal_modifiers_and_bounds_intersect(self):
        for text in ("test zorblax cost<=S", "cost<=S everything about zorblax", "test zorblax !oracle=manual",
                     "run all the cost<=S testing checks"):
            out = self.r(text)
            self.assertEqual((out["status"], out["commands"]), ("no-match", []), text)
        self.assertEqual(self.r("run smoke tag:run-page")["selection"], "tag:run-page")
        self.assertEqual(self.r("test crew cost<=S cost<=L")["selection"], "area:crew-api cost<=S")
        self.assertEqual(self.r("run smoke cost<=XL")["status"], "no-match")

    def test_the_plan_action_never_asks_but_the_run_does(self):
        self.assertFalse(self.r("plan the release profile")["ask_before_running"])
        self.assertTrue(self.r("run the release profile")["ask_before_running"])

    def test_every_suggested_command_parses(self):
        import shlex
        from e2ecat import cli
        for text in ("test the run page", "smoke", "what's not covered", "check the bus against http://127.0.0.1:7801",
                     "summarise the last run", "show me the evidence for crew-api.runs.cancel"):
            for c in self.r(text)["commands"]:
                with self.subTest(cmd=c):
                    a = cli.build_parser().parse_args(shlex.split(c)[1:])  # argparse exits on an unknown flag
                    self.assertTrue(a.cmd)

if __name__ == "__main__":
    unittest.main()
