"""Unit tests for e2e/ (stdlib unittest; no network, no product binaries).

    python3 -m unittest discover -s e2e/tests -v
"""
import copy
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

from e2ecat import cli, schema, surfaces, validate as v  # noqa: E402
from e2ecat.select import SelectError, parse, select  # noqa: E402
from e2ecat.util import read_json, read_text, write_text  # noqa: E402

SCHEMA = read_json(os.path.join(E2E, "catalog", "SCHEMA.json"))


def cap(**kw):
    c = {
        "id": "studio-ui.test.one", "title": "t", "surface": "ui", "user_path": "Open /",
        "deps": [], "cost": "S", "tags": ["studio-ui"], "required_evidence": ["video", "screenshot", "trace"],
        "oracle": {"kind": "dom", "selector": "[data-testid=desk]", "assert": "visible", "complete": True},
        "covers": [], "scenarios": ["planned"], "origin": "inventory-2026-10-20",
    }
    c.update(kw)
    return c


def doc(*caps, area="studio-ui"):
    return {"version": 1, "area": area, "capabilities": list(caps)}


class SchemaSubset(unittest.TestCase):
    def test_shipped_schema_uses_only_supported_keywords(self):
        schema.check_schema(SCHEMA)

    def test_unsupported_keyword_is_refused(self):
        with self.assertRaises(schema.SchemaError):
            schema.check_schema({"type": "object", "if": {"type": "object"}})

    def test_valid_record(self):
        self.assertEqual(schema.validate(doc(cap()), SCHEMA), [])

    def test_missing_required_and_extra_field(self):
        c = cap()
        del c["oracle"]
        c["bogus"] = 1
        errs = schema.validate(doc(c), SCHEMA)
        self.assertTrue(any("missing required 'oracle'" in e for e in errs), errs)
        self.assertTrue(any("unexpected property 'bogus'" in e for e in errs), errs)

    def test_oracle_kind_discriminates(self):
        errs = schema.validate(doc(cap(oracle={"kind": "dom", "selector": "x", "assert": "glows"})), SCHEMA)
        self.assertTrue(any("assert" in e and "glows" in e for e in errs), errs)
        errs = schema.validate(doc(cap(oracle={"kind": "telepathy"})), SCHEMA)
        self.assertTrue(any("kind" in e for e in errs), errs)

    def test_manual_needs_a_reason_and_category(self):
        errs = schema.validate(doc(cap(oracle={"kind": "manual", "category": "model-output", "reason": "short"})), SCHEMA)
        self.assertTrue(any("shorter" in e for e in errs), errs)

    def test_evidence_enum(self):
        errs = schema.validate(doc(cap(required_evidence=["video", "vibes"])), SCHEMA)
        self.assertTrue(any("vibes" in e for e in errs), errs)


class CatalogChecks(unittest.TestCase):
    def setUp(self):
        self.surf = {"wicked-studio": {"repo": "wicked-studio", "sha": "a" * 40,
                                       "elements": [{"key": "studio:testid:desk", "kind": "testid", "name": "desk", "files": []},
                                                    {"key": "studio:testid:rail", "kind": "testid", "name": "rail", "files": []}],
                                       "tests": ["e2e/desk_home_test.py"]}}

    def run_check(self, *caps):
        docs = {a: doc(area=a, *([cap(id="%s.x.y" % a)] if a != "studio-ui" else [])) for a in v.AREAS}
        docs["studio-ui"] = doc(*caps)
        all_caps = []
        for a, d in docs.items():
            for c in d["capabilities"]:
                c = dict(c)
                c["_area"] = a
                all_caps.append(c)
        return v.check_catalog(SCHEMA, docs, all_caps, self.surf, repo_root=os.path.dirname(E2E)), all_caps

    def test_clean(self):
        fails, _ = self.run_check(cap(covers=["studio:testid:desk"]))
        self.assertEqual(fails, [])

    def test_duplicate_ids_and_alias_collisions(self):
        fails, _ = self.run_check(cap(), cap(aliases=["studio-ui.test.one"]))
        self.assertTrue(any("duplicate id studio-ui.test.one" in f for f in fails), fails)
        self.assertTrue(any("alias studio-ui.test.one is also a live id" in f for f in fails), fails)

    def test_ui_needs_video_screenshot_trace(self):
        fails, _ = self.run_check(cap(required_evidence=["video"]))
        self.assertTrue(any("must require video, screenshot and trace" in f for f in fails), fails)

    def test_cover_must_name_a_surface_element(self):
        fails, _ = self.run_check(cap(covers=["studio:testid:nope"]))
        self.assertTrue(any("no surface manifest lists" in f for f in fails), fails)

    def test_scenario_must_exist_at_the_pin(self):
        fails, _ = self.run_check(cap(scenarios=[{"ref": "wicked-studio:e2e/missing_test.py", "fidelity": "e2e-fixture"}]))
        self.assertTrue(any("is not a test file" in f for f in fails), fails)
        fails, _ = self.run_check(cap(scenarios=[{"ref": "wicked-studio:e2e/desk_home_test.py", "fidelity": "e2e-fixture"}]))
        self.assertEqual(fails, [])

    def test_wicked_ci_scenarios_resolve_in_this_checkout(self):
        fails, _ = self.run_check(cap(scenarios=[{"ref": "wicked-ci:smoke/lib/steps/S01-boot.mjs", "fidelity": "e2e-hermetic"}]))
        self.assertEqual(fails, [])
        fails, _ = self.run_check(cap(scenarios=[{"ref": "wicked-ci:smoke/lib/steps/S99.mjs", "fidelity": "e2e-hermetic"}]))
        self.assertTrue(any("does not exist in this checkout" in f for f in fails), fails)

    def test_value_asserts_need_values(self):
        fails, _ = self.run_check(cap(oracle={"kind": "dom", "selector": "x", "assert": "count", "complete": True}))
        self.assertTrue(any("needs a value" in f for f in fails), fails)

    def test_complete_with_untyped_is_contradictory(self):
        o = {"kind": "dom", "selector": "x", "assert": "visible", "complete": True, "untyped": ["a clause"]}
        fails, _ = self.run_check(cap(oracle=o))
        self.assertTrue(any("marked complete" in f for f in fails), fails)

    def test_comparisons_need_values_and_checks_are_not_vacuous(self):
        api = {"kind": "api", "method": "GET", "path": "/api/v1/health", "complete": True}
        cases = [
            (dict(api, expect={"json": [{"path": "$.status", "op": "eq"}]}), "needs a value"),
            (dict(api, expect={}), "expects nothing"),
            (dict(api, expect={"json": []}), "empty json expectation"),
            ({"kind": "event", "type": "sessionCompleted", "count": {"min": 0}, "complete": True}, "vacuous"),
            ({"kind": "gh", "target": "run", "assert": {"path": "$.conclusion", "op": "eq"}, "complete": True}, "needs a value"),
            ({"kind": "dom", "selector": "x", "assert": "attr", "value": "v", "complete": True}, "attribute name"),
        ]
        for oracle, want in cases:
            fails, _ = self.run_check(cap(surface="api", required_evidence=["api-transcript"], oracle=oracle))
            self.assertTrue(any(want in f for f in fails), (oracle, fails))
        ok = dict(api, expect={"json": [{"path": "$.status", "op": "exists"}]})
        fails, _ = self.run_check(cap(surface="api", required_evidence=["api-transcript"], oracle=ok))
        self.assertEqual(fails, [])

    def test_manual_precheck_is_checked_too(self):
        o = {"kind": "manual", "category": "model-output", "reason": "model output only",
             "precheck": {"kind": "api", "method": "GET", "path": "/x", "expect": {}}}
        fails, _ = self.run_check(cap(oracle=o))
        self.assertTrue(any("precheck" in f and "expects nothing" in f for f in fails), fails)

    def test_complete_flag_contract(self):
        base = {"kind": "dom", "selector": "x", "assert": "visible"}
        fails, _ = self.run_check(cap(oracle=dict(base)))
        self.assertTrue(any("must say whether it is complete" in f for f in fails), fails)
        fails, _ = self.run_check(cap(oracle=dict(base, complete=False)))
        self.assertTrue(any("must list its untyped clauses" in f for f in fails), fails)
        o = {"kind": "api", "method": "GET", "path": "/x", "expect": {"status": 200}, "complete": True}
        fails, _ = self.run_check(cap(oracle=o))
        self.assertTrue(any("without a dom check cannot be complete" in f for f in fails), fails)

    def test_unmapped_elements_by_repo_and_ratchet(self):
        _, caps = self.run_check(cap(covers=["studio:testid:desk"]))
        un = v.unmapped_elements(caps, self.surf)
        self.assertEqual(un, {"wicked-studio": ["studio:testid:rail"]})
        new, stale = v.apply_baseline(un, {"unmapped": {"wicked-studio": ["studio:testid:rail"]}})
        self.assertEqual((new, stale), ([], []))
        new, stale = v.apply_baseline(un, {"unmapped": {}})
        self.assertEqual(new, ["studio:testid:rail"])
        new, stale = v.apply_baseline({}, {"unmapped": {"wicked-studio": ["studio:testid:rail"]}})
        self.assertEqual(stale, ["studio:testid:rail"])


class Selection(unittest.TestCase):
    caps = [
        dict(cap(id="crew-api.runs.launch", surface="api", cost="L", tags=["launch", "gates"]), _area="crew-api"),
        dict(cap(id="studio-ui.shell.desk", tags=["shell"], aliases=["studio.old.desk"]), _area="studio-ui"),
        dict(cap(id="garden.mem.answer", surface="plugin", cost="M", tags=["memory"],
                 oracle={"kind": "manual", "category": "model-output", "reason": "model output only"}), _area="garden"),
    ]

    def ids(self, expr):
        return [c["id"] for c in select(self.caps, expr)]

    def test_empty_selects_all(self):
        self.assertEqual(len(self.ids("")), 3)
        self.assertEqual(len(self.ids("*")), 3)

    def test_keys(self):
        self.assertEqual(self.ids("area:crew-api"), ["crew-api.runs.launch"])
        self.assertEqual(self.ids("tag:memory,shell"), ["studio-ui.shell.desk", "garden.mem.answer"])
        self.assertEqual(self.ids("id:studio-ui.*"), ["studio-ui.shell.desk"])
        self.assertEqual(self.ids("id:studio.old.*"), ["studio-ui.shell.desk"])
        self.assertEqual(self.ids("surface=api"), ["crew-api.runs.launch"])
        self.assertEqual(self.ids("cost<=M"), ["studio-ui.shell.desk", "garden.mem.answer"])
        self.assertEqual(self.ids("oracle=manual"), ["garden.mem.answer"])

    def test_and_or_not(self):
        self.assertEqual(self.ids("cost<=M !oracle=manual"), ["studio-ui.shell.desk"])
        self.assertEqual(self.ids("area:crew-api,garden tag:launch"), ["crew-api.runs.launch"])

    def test_errors(self):
        for bad in ("colour:red", "cost<=XL", "area:", "cost<=S,M"):
            with self.assertRaises(SelectError, msg=bad):
                parse(bad)


class RunReport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="e2e-report-test-")
        self.caps = [
            dict(cap(id="studio-ui.a.b"), _area="studio-ui"),
            dict(cap(id="crew-api.c.d", surface="api", required_evidence=["api-transcript"],
                     oracle={"kind": "all", "complete": False, "untyped": ["x"],
                             "of": [{"kind": "api", "method": "GET", "path": "/api/v1/health", "expect": {"status": 200}},
                                    {"kind": "event", "type": "sessionCompleted"}]}), _area="crew-api"),
            dict(cap(id="garden.e.f", surface="plugin", required_evidence=["cli-transcript"],
                     oracle={"kind": "manual", "category": "model-output", "reason": "model output only"}), _area="garden"),
        ]
        self.write("run.json", {"version": 1, "capabilities": ["studio-ui.a.b", "crew-api.c.d", "garden.e.f"]})
        for p in ("ev/a.webm", "ev/a.png", "ev/a.zip", "ev/c.json", "ev/e.txt"):
            self.write(p, "x")
        self.write("results/studio-ui.a.b.json", {"id": "studio-ui.a.b", "verdict": "pass",
                   "observed": [{"value": True, "ok": True}],
                   "evidence": {"video": ["ev/a.webm"], "screenshot": ["ev/a.png"], "trace": ["ev/a.zip"]}})
        self.write("results/crew-api.c.d.json", {"id": "crew-api.c.d", "verdict": "partial",
                   "observed": [{"value": 200, "ok": True}, {"value": 1, "ok": True}],
                   "evidence": {"api-transcript": ["ev/c.json"]}})
        self.write("results/garden.e.f.json", {"id": "garden.e.f", "verdict": "manual", "observed": [],
                   "evidence": {"cli-transcript": ["ev/e.txt"]}})

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, rel, obj):
        p = os.path.join(self.d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(obj if isinstance(obj, str) else json.dumps(obj))

    def check(self):
        return v.check_report(self.d, self.caps, {})[0]

    def edit(self, cid, **kw):
        p = os.path.join(self.d, "results", cid + ".json")
        r = read_json(p)
        r.update(kw)
        self.write("results/%s.json" % cid, r)

    def test_complete_report_passes(self):
        self.assertEqual(self.check(), [])

    def test_missing_verdict(self):
        os.remove(os.path.join(self.d, "results", "crew-api.c.d.json"))
        self.assertTrue(any("no verdict" in f for f in self.check()))

    def test_missing_or_empty_video(self):
        self.write("ev/a.webm", "")
        self.assertTrue(any("missing or empty" in f for f in self.check()))
        self.edit("studio-ui.a.b", evidence={"screenshot": ["ev/a.png"], "trace": ["ev/a.zip"]})
        self.assertTrue(any("required evidence video missing" in f for f in self.check()))

    def test_ui_video_must_be_webm(self):
        self.write("ev/a.mp4", "x")
        self.edit("studio-ui.a.b", evidence={"video": ["ev/a.mp4"], "screenshot": ["ev/a.png"], "trace": ["ev/a.zip"]})
        self.assertTrue(any("must be .webm" in f for f in self.check()))

    def test_pass_on_manual_or_partial_is_refused(self):
        self.edit("garden.e.f", verdict="pass")
        self.edit("crew-api.c.d", verdict="pass")
        fails = self.check()
        self.assertTrue(any("manual oracle can never be `pass`" in f for f in fails), fails)
        self.assertTrue(any("report `partial`" in f for f in fails), fails)

    def test_observed_per_check(self):
        self.edit("crew-api.c.d", observed=[{"value": 200, "ok": True}])
        self.assertTrue(any("one entry per oracle check (2)" in f for f in self.check()))

    def test_evidence_cannot_escape_the_run_dir(self):
        self.edit("crew-api.c.d", evidence={"api-transcript": ["../outside.json"]})
        self.assertTrue(any("escapes the run dir" in f for f in self.check()))

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "symlinks need privileges on Windows")
    def test_symlink_out_of_the_run_dir_escapes(self):
        outside = tempfile.mkdtemp(prefix="e2e-outside-")
        try:
            write_text(os.path.join(outside, "secret.json"), "x")
            os.symlink(os.path.join(outside, "secret.json"), os.path.join(self.d, "ev", "link.json"))
            self.edit("crew-api.c.d", evidence={"api-transcript": ["ev/link.json"]})
            self.assertTrue(any("escapes the run dir" in f for f in self.check()))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_skipped_is_not_a_verdict_for_a_selected_capability(self):
        self.edit("crew-api.c.d", verdict="skipped")
        self.assertTrue(any("skipped" in f for f in self.check()))

    def test_relative_run_dir(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.d)
            self.assertEqual(v.check_report(".", self.caps, {})[0], [])
        finally:
            os.chdir(cwd)

    def test_selection_by_profile(self):
        self.write("run.json", {"version": 1, "profile": "p"})
        fails, _ = v.check_report(self.d, self.caps, {"p": {"select": "area:crew-api"}})
        self.assertEqual(fails, [])


class Extractors(unittest.TestCase):
    def test_crew_cli_text(self):
        idx = ("console.log('Usage: wicked-crew serve [options]');\n"
               "console.error('Usage: wicked-crew serve|start|status|version');\n--install-service")
        gov = "Usage: wicked-crew governance replay [--dry-run]"
        self.assertEqual(surfaces.crew_cli_from_text(idx, gov),
                         ["serve", "start", "status", "version", "serve --install-service",
                          "serve --uninstall-service", "governance replay"])

    def test_test_index_rules(self):
        d = tempfile.mkdtemp(prefix="e2e-idx-")
        try:
            os.makedirs(os.path.join(d, "src"))
            write_text(os.path.join(d, "src", "a.rs"), "#[cfg(test)]\nmod t {}\n")
            write_text(os.path.join(d, "src", "b.rs"), "fn main() {}\n")
            files = ["src/a.rs", "src/b.rs", "tests/x.ts", "pkg/y.test.ts", ".github/workflows/ci.yml", "README.md",
                     "tests/fixtures/f.ts", "tests/data.json", "scenarios/a.md"]
            self.assertEqual(surfaces.test_index(d, files), ["src/a.rs", "tests/x.ts", "pkg/y.test.ts", ".github/workflows/ci.yml"])
        finally:
            shutil.rmtree(d)


class StudioRoutes(unittest.TestCase):
    SRC = """function parse(pathname: string): Route {
  if (first === '') {
    return route({ panel: 'home' });
  }
  if (first === 'rules') {
    if (third) return route({ panel: 'not-found' });
    return route({ panel: 'rules', ruleId: second ? safeDecode(second) : null });
  }
  if (first === 'testing') {
    if (second === 'campaigns' && third) {
      return route({ panel: 'testing' });
    }
    return isTestingSubPage(second) ? route({ panel: 'testing' }) : route({ panel: 'not-found' });
  }
  if (first === 's' && second) {
    if (third === 'a' && fourth !== '' && restEmpty(5)) {
      return route({ panel: 'session' });
    }
    return route({ panel: 'session' });
  }
  if (first === 'projects' && second && third === 'requirements' && restEmpty(4)) {
    return route({ panel: 'project-requirements' });
  }
  if (first === 'mcp' && second === 'inspect' && !third) {
    return route({ panel: 'mcp' });
  }
  if (first === 'runs') {
    if (second === 'new') return route({ panel: 'runs', showLaunch: true });
    if (second && third === 'events') return route({ panel: 'run-events' });
    return route({ panel: 'not-found' });
  }
  return route({ panel: 'not-found' });
}
"""

    def test_nested_routes_are_extracted(self):
        got = surfaces.route_shapes(self.SRC, lambda name: ["campaigns", "evals"])
        for r in ("/", "/rules", "/rules/:id", "/testing", "/testing/campaigns", "/testing/evals",
                  "/testing/campaigns/:id", "/s/:id", "/s/:id/a/:key", "/projects/:id/requirements",
                  "/mcp/inspect", "/runs", "/runs/new", "/runs/:id/events"):
            self.assertIn(r, got)


class Drift(unittest.TestCase):
    def test_missing_fresh_manifest_is_unavailable_not_removed(self):
        d = tempfile.mkdtemp(prefix="e2e-drift-")
        try:
            with redirect_stdout(io.StringIO()) as buf:
                rc = cli.main(["drift", "--against", d, "--out", d])
            self.assertEqual(rc, 0)
            out = read_json(os.path.join(d, "drift.json"))
            self.assertTrue(all(v.get("unavailable") for v in out.values()), out)
            self.assertNotIn("removed:", buf.getvalue())
        finally:
            shutil.rmtree(d)


class ShippedCatalog(unittest.TestCase):
    """The committed catalog, manifests and profiles: (a) holds and the run is deterministic."""

    def test_catalog_checks_hold(self):
        sch, docs, caps = v.load_catalog()
        fails = v.check_catalog(sch, docs, caps, v.load_surfaces())
        self.assertEqual(fails, [], "\n".join(fails[:20]))

    def test_profiles_select(self):
        _, _, caps = v.load_catalog()
        profiles = read_json(os.path.join(E2E, "profiles.json"))["profiles"]
        self.assertEqual(v.check_profiles(profiles, caps), [])
        self.assertEqual({"smoke", "daily", "release", "full"}, set(profiles))

    def test_validate_is_deterministic_and_baseline_holds(self):
        outs = []
        for _ in range(2):
            d = tempfile.mkdtemp(prefix="e2e-det-")
            try:
                with redirect_stdout(io.StringIO()):
                    rc = cli.main(["validate", "--baseline", os.path.join(E2E, "coverage-baseline.json"), "--out", d])
                outs.append((rc, read_text(os.path.join(d, "coverage.json"))))
            finally:
                shutil.rmtree(d)
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0][0], 0, json.loads(outs[0][1])["failures"][:20])

    def test_no_machine_paths(self):
        """Catalog, manifests and docs carry repo-relative paths only, never a machine's home or temp dir."""
        import re
        bad = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/|/private/(?:tmp|var)/")
        for root, _, files in os.walk(E2E):
            for f in files:
                if f.endswith((".json", ".md", ".py")) and "tests" not in root:
                    txt = read_text(os.path.join(root, f))
                    self.assertIsNone(bad.search(txt), os.path.join(root, f))


if __name__ == "__main__":
    unittest.main()
