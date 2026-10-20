"""wicked-core cargo tests: `tests/<t>.rs` (an integration target), `src/**.rs` (the lib's unit tests),
and the same under `crates/<crate>/`. One cargo invocation per test target, inside the host's build
slot (`--build-slot`), filtered by test name when the scenario names one. The test output is the
test report. Integration/unit fidelity: never a pass.
"""
import os
import re

from . import DOUBLED, Adapter, Outcome, run_logged

PATH_RE = re.compile(r"^(?:crates/(?P<crate>[\w-]+)/)?(?P<kind>tests|src)/(?P<rest>.+)\.rs$")
TEST_FN = re.compile(r"^[a-z_][a-z0-9_]*(::[a-z_][a-z0-9_]*)*$")
LINE_RE = re.compile(r"^test (\S+) \.\.\. (ok|FAILED|ignored)")


def _package(core, crate):
    if not crate:
        p = os.path.join(core, "Cargo.toml")
    else:
        p = os.path.join(core, "crates", crate, "Cargo.toml")
    try:
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
    except OSError:
        return None
    m = re.search(r"^\[package\][^\[]*?^name\s*=\s*\"([^\"]+)\"", txt, re.M | re.S)
    return m.group(1) if m else None


class CargoAdapter(Adapter):
    name = "wicked-core-cargo"
    targets = ("fixture",)

    def claim(self, scenario, ctx):
        repo, _, path = scenario["ref"].partition(":")
        m = PATH_RE.match(path)
        if repo != "wicked-core" or not m or ctx.target not in self.targets:
            return None
        crate, kind, rest = m.group("crate"), m.group("kind"), m.group("rest")
        if kind == "tests":
            if "/" in rest:  # tests/<dir>/x.rs is a module of a target, not a target: run the crate's tests
                target = ["--tests"]
            else:
                target = ["--test", rest]
        elif rest.startswith("bin/"):
            target = ["--bin", rest[4:].split("/")[0]]
        else:
            target = ["--lib"]
        name = scenario.get("name")
        filt = name if name and TEST_FN.match(name) and name != "tests" else None
        key = "wicked-core-cargo:%s:%s" % (crate or "root", " ".join(target))
        return key, {"crate": crate, "target": target, "filter": filt, "path": path}

    def available(self, ctx, params):
        core = ctx.checkouts.get("wicked-core")
        if not core:
            return "checkout:wicked-core", "pass --src DIR or --checkout wicked-core=PATH"
        if not os.path.isfile(os.path.join(core, params["path"])):
            return "checkout:wicked-core", "%s is not in this checkout" % params["path"]
        ok, detail = ctx.probe.check("tool-cargo", "cargo")
        if not ok:
            return "adapter:cargo", detail
        return None

    def provides(self, ctx, scenario):
        return {k: "the test's in-process engine and doubles" for k in DOUBLED}

    def evidence_kinds(self, ctx, scenario, cap):
        return {"test-report"}

    def run(self, unit, ctx):
        core = ctx.checkouts["wicked-core"]
        any_s = next(iter(unit.scenarios.values()))
        p = any_s["params"]
        out = os.path.join(ctx.run_dir, "scenarios", unit.slug)
        pkg = _package(core, p["crate"]) if p["crate"] else None
        filters = sorted({s["params"]["filter"] for s in unit.scenarios.values() if s["params"]["filter"]})
        whole = any(s["params"]["filter"] is None for s in unit.scenarios.values())
        argv = ctx.build_slot + ["cargo", "test"] + (["-p", pkg] if pkg else []) + p["target"]
        argv += ["--target-dir", ctx.cargo_target_dir(core)]
        argv += ["--"] + ([] if whole else filters)
        log = os.path.join(out, "cargo-test.log")
        rc, secs = run_logged(argv, core, dict(os.environ), log, ctx.unit_timeout)
        results = {}
        summary = False
        with open(log, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = LINE_RE.match(line.strip())
                if m:
                    results[m.group(1)] = m.group(2)
                if line.startswith("test result:"):
                    summary = True
        outcomes = {}
        for key, s in unit.scenarios.items():
            f = s["params"]["filter"]
            if not summary:
                o = Outcome("error", "cargo printed no test result (exit %s: a build failure or timeout; see the log)" % rc,
                            s.get("fidelity"))
            elif f:
                mine = {n: v for n, v in results.items() if n == f or n.endswith("::" + f)}
                if not mine:
                    o = Outcome("error", "no test named %s ran" % f, s.get("fidelity"))
                elif "FAILED" in mine.values():
                    o = Outcome("failed", "FAILED %s" % f, s.get("fidelity"))
                elif all(v == "ignored" for v in mine.values()):
                    o = Outcome("error", "%s is #[ignore]d" % f, s.get("fidelity"))
                elif rc != 0:
                    o = Outcome("failed" if rc is not None else "error",
                                "ok %s, but cargo exited %s" % (f, rc), s.get("fidelity"))
                else:
                    o = Outcome("passed", "ok %s" % f, s.get("fidelity"))
            else:
                failed = [n for n, v in results.items() if v == "FAILED"]
                named = s.get("name")
                o = Outcome("error" if rc is None else ("failed" if failed or rc != 0 else "passed"),
                            ("FAILED " + ", ".join(failed[:5])) if failed else "%d tests ok (exit %s)%s" % (
                                sum(v == "ok" for v in results.values()), rc,
                                "; the scenario's name %r is not a test filter, so the whole target ran" % named
                                if named else ""), s.get("fidelity"))
            o.add("test-report", log)
            o.extra = {"cargo": " ".join(argv[len(ctx.build_slot):]), "tests": len(results)}
            outcomes[key] = o
        return outcomes
