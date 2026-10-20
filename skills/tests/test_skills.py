"""Skill lint and router evals for skills/wicked-e2e* (stdlib unittest; no model, no network).

    python3 -m unittest discover -s skills/tests -v

- Frontmatter: the closed key set of garden's cross-CLI skill format (name, description, license,
  compatibility, metadata, mandates), name == directory, description <= 1024 characters with its
  trigger phrases, string-only metadata with a known role, size bounds.
- CLI references: every `e2e <subcommand> --flag` a skill or ref names is a real subcommand and
  flag, read from `e2e --help` and `e2e <subcommand> --help` (the CLI itself, so they cannot drift).
- Portability: no Claude-only dispatch or tool-call shapes, no `.claude/` paths, and no
  "Claude Code" outside a Hand-off paragraph.
- Honesty guards: the run and report skills validate the run before any verdict is used, and every
  skill that can start a run asks first.
- Router evals: skills/wicked-e2e/evals/resolve-cases.json, each request through `e2e resolve`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(ROOT, "skills")
E2E_BIN = os.path.join(ROOT, "e2e", "bin", "e2e")
sys.path.insert(0, os.path.join(ROOT, "e2e", "lib"))

from e2ecat import resolve as rs  # noqa: E402
from e2ecat import validate as v  # noqa: E402

KEYS = {"name", "description", "license", "compatibility", "metadata", "mandates"}
ROLES = {"worker", "router", "module", "floor"}
EXPECTED = ["wicked-e2e", "wicked-e2e-plan", "wicked-e2e-run", "wicked-e2e-validate", "wicked-e2e-report",
            "wicked-e2e-evidence"]
DISPATCH = re.compile(r"\b(Task|Skill|Agent|TaskCreate|TaskUpdate|TodoWrite)\(|\bAskUserQuestion\b|\bsubagent_type\b")
TOOL_CALL = re.compile(r"\b(Read|Write|Edit|MultiEdit|Bash|Glob|Grep|WebFetch|WebSearch|NotebookEdit)\(\s*[\w\"'{]")
TOOL_NOUN = re.compile(r"\bthe (Read|Write|Edit|Bash|Glob|Grep|WebFetch|Skill|Task) tool\b")


def skill_dirs():
    return sorted(d for d in os.listdir(SKILLS) if d.startswith("wicked-e2e") and os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def frontmatter(text):
    """A strict reader for the subset the format allows: `key: value`, `key: |` blocks, a one-level
    `metadata:` map and a `mandates:` list. Returns (fields, body)."""
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    lines, body = text[4:end].split("\n"), text[end + 5:]
    out, i = {}, 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w-]*):(?: (.*))?$", line)
        if not m:
            raise ValueError("unparsed frontmatter line %r" % line)
        key, val = m.group(1), (m.group(2) or "").strip()
        i += 1
        if val == "|":
            block = []
            while i < len(lines) and (lines[i].startswith("  ") or lines[i] == ""):
                block.append(lines[i][2:])
                i += 1
            out[key] = "\n".join(block).strip()
        elif val == "":
            items = {} if key != "mandates" else []
            while i < len(lines) and lines[i].startswith("  "):
                sub = lines[i].strip()
                if isinstance(items, list):
                    items.append(sub.lstrip("- ").strip())
                else:
                    mm = re.match(r"^([\w-]+): (.+)$", sub)
                    if not mm:
                        raise ValueError("unparsed %s line %r" % (key, sub))
                    items[mm.group(1)] = mm.group(2).strip()
                i += 1
            out[key] = items
        else:
            out[key] = val
    return out, body


def help_text(*args):
    r = subprocess.run([sys.executable, E2E_BIN] + list(args) + ["--help"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


_CLI = None


def cli_surface():
    """{subcommand: {flags}} from the CLI's own --help."""
    global _CLI
    if _CLI is None:
        top = help_text()
        m = re.search(r"\{([a-z,-]+)\}", top)
        subs = m.group(1).split(",")
        _CLI = {s: set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", help_text(s))) | {"--help", "-h"} for s in subs}
    return _CLI


def code_segments(text):
    """Inline code spans and fenced code lines: the places a skill writes a command."""
    segs = []
    fenced = re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.S)
    for block in fenced:
        segs += [ln.strip() for ln in block.splitlines() if ln.strip()]
    rest = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.S)
    segs += re.findall(r"`([^`\n]+)`", rest)
    return segs


def paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


class Frontmatter(unittest.TestCase):
    def test_the_six_skills_exist(self):
        self.assertEqual(skill_dirs(), sorted(EXPECTED))

    def test_closed_key_set_name_description_metadata(self):
        for d in skill_dirs():
            with self.subTest(skill=d):
                fm, body = frontmatter(read(os.path.join(SKILLS, d, "SKILL.md")))
                self.assertLessEqual(set(fm), KEYS, "keys outside the closed set")
                self.assertEqual(fm.get("name"), d, "name must equal the directory")
                desc = fm.get("description") or ""
                self.assertTrue(desc, "description is required")
                self.assertLessEqual(len(desc), 1024, "description over 1024 characters")
                self.assertIn("Use when:", desc, "the description must carry its trigger phrases")
                meta = fm.get("metadata")
                self.assertIsInstance(meta, dict, "metadata is a map")
                self.assertTrue(all(isinstance(x, str) for x in meta.values()), "metadata values are strings")
                self.assertIn(meta.get("role"), ROLES)
                self.assertEqual(meta["role"], "router" if d == "wicked-e2e" else "worker")
                raw = read(os.path.join(SKILLS, d, "SKILL.md"))
                self.assertLess(raw.count("\n"), 500)
                self.assertLess(len(raw.encode("utf-8")), 24 * 1024)
                self.assertIn("## Runtime", body)

    def test_the_reader_is_strict(self):
        with self.assertRaises(ValueError):
            frontmatter("---\nname: x\n  stray\n---\n")
        fm, _ = frontmatter("---\nname: x\ndescription: |\n  a\n  b\nmetadata:\n  role: router\n---\nbody")
        self.assertEqual(fm, {"name": "x", "description": "a\nb", "metadata": {"role": "router"}})


class CliReferences(unittest.TestCase):
    def files(self):
        out = [os.path.join(SKILLS, d, "SKILL.md") for d in skill_dirs()]
        refs = os.path.join(SKILLS, "wicked-e2e", "refs")
        out += [os.path.join(refs, f) for f in sorted(os.listdir(refs)) if f.endswith(".md")]
        return out

    def problems(self, text):
        cli = cli_surface()
        every = set().union(*cli.values())
        bad = []
        for seg in code_segments(text):
            toks = seg.split()
            if len(toks) >= 2 and toks[0] == "e2e" and not toks[1].startswith("<"):
                if toks[1] not in cli:
                    bad.append("unknown subcommand in `%s`" % seg)
                    continue
                bad += ["`%s`: %s is not a flag of e2e %s" % (seg, f, toks[1])
                        for f in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", seg) if f not in cli[toks[1]]]
            elif toks and toks[0].startswith("--") and len(toks) <= 2:
                if toks[0] not in every:
                    bad.append("`%s` is not a flag of any e2e subcommand" % seg)
        return bad

    def test_every_e2e_command_and_flag_exists(self):
        for p in self.files():
            with self.subTest(file=os.path.relpath(p, ROOT)):
                self.assertEqual(self.problems(read(p)), [])

    def test_the_check_catches_an_invented_command_or_flag(self):
        self.assertTrue(self.problems("run `e2e certify --all`"))
        self.assertTrue(self.problems("```bash\ne2e run --profile smoke --yes-really\n```"))
        self.assertTrue(self.problems("pass `--force-pass` to it"))
        self.assertEqual(self.problems("`e2e run --plan-only` and `--live-journeys`"), [])

    def test_every_named_skill_exists(self):
        names = set(skill_dirs())
        for d in skill_dirs():
            for n in set(re.findall(r"\bwicked-e2e(?:-[a-z]+)?\b", read(os.path.join(SKILLS, d, "SKILL.md")))):
                self.assertIn(n, names, "%s names %s" % (d, n))


class Portability(unittest.TestCase):
    def test_no_claude_only_shapes_outside_hand_off(self):
        for d in skill_dirs():
            _, body = frontmatter(read(os.path.join(SKILLS, d, "SKILL.md")))
            for para in paragraphs(body):
                with self.subTest(skill=d, para=para[:60]):
                    self.assertIsNone(DISPATCH.search(para))
                    self.assertIsNone(TOOL_CALL.search(para))
                    if para.lstrip().startswith(("**Hand-off", "Hand-off")) or "**Hand-off**" in para:
                        continue
                    self.assertNotIn(".claude/", para)
                    self.assertNotIn("Claude Code", para)
                    self.assertIsNone(TOOL_NOUN.search(para))

    def test_every_dispatch_is_a_hand_off_paragraph(self):
        for d in skill_dirs():
            _, body = frontmatter(read(os.path.join(SKILLS, d, "SKILL.md")))
            for para in paragraphs(body):
                if "Hand-off" in para:
                    self.assertIn("on any other seat open the named skill", para, d)


class HonestyGuards(unittest.TestCase):
    """The review question: can a skill lead an agent to claim a pass the CLI did not report, or run a
    costly or live selection without asking? These pin the instructions that prevent both."""

    def body(self, d):
        return frontmatter(read(os.path.join(SKILLS, d, "SKILL.md")))[1]

    def test_run_and_report_validate_before_any_verdict_counts(self):
        for d in ("wicked-e2e-run", "wicked-e2e-report"):
            b = self.body(d)
            self.assertIn("e2e validate --report", b, d)
            self.assertRegex(b, r"not certified", d)

    def test_router_states_where_a_verdict_comes_from(self):
        b = self.body("wicked-e2e")
        self.assertIn("A verdict exists only in the CLI's files", b)
        self.assertIn("`partial`, `skipped`, `manual` and `error` are not passes", b)

    def test_skills_that_can_start_a_run_ask_first_and_refuse_operator_ports(self):
        for d in ("wicked-e2e", "wicked-e2e-run"):
            b = self.body(d)
            self.assertIn("ask before running", b, d)
            self.assertIn("7701", b, d)
            self.assertIn("--allow-daemon-port", b, d)
            self.assertIn("--live-journeys", b, d)

    def test_plan_never_starts_the_run(self):
        b = self.body("wicked-e2e-plan")
        self.assertIn("--plan-only", b)
        self.assertIn("Do not start the run from here", b)
        for seg in code_segments(b):
            if seg.startswith("e2e run"):
                self.assertIn("--plan-only", seg, "the plan skill only ever runs `e2e run --plan-only`")

    def test_every_run_report_validation_keeps_the_baseline(self):
        """Without --baseline, `e2e validate --report` also fails on every known unmapped surface element,
        so a skill that drops it would call every run uncertified (or teach agents to ignore the exit code)."""
        for d in skill_dirs():
            for seg in code_segments(self.body(d)):
                if seg.startswith("e2e validate") and "--report" in seg and len(seg.split()) > 3:
                    self.assertIn("--baseline e2e/coverage-baseline.json", seg, "%s: %s" % (d, seg))
        out = rs.resolve("is the run report complete", [], {}, run_dir=None)
        self.assertTrue(all("--baseline" in c for c in out["commands"] if "--report" in c))

    def test_no_skill_tells_an_agent_to_weaken_validation_unasked(self):
        for d in skill_dirs():
            b = self.body(d)
            for seg in code_segments(b):
                self.assertNotIn("--allow-unvaulted", seg.split("#")[0] if seg.startswith("e2e") else "", d)
                if seg.startswith("e2e run"):
                    self.assertNotIn("--allow-daemon-port", seg, d)


class Refs(unittest.TestCase):
    def test_refs_are_generated_and_complete(self):
        r = subprocess.run([sys.executable, os.path.join(SKILLS, "tools", "gen_refs.py"), "--check"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_area_has_a_ref(self):
        refs = {f[:-3] for f in os.listdir(os.path.join(SKILLS, "wicked-e2e", "refs")) if f.endswith(".md")}
        self.assertEqual(refs, set(v.AREAS))


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="e2e-skills-install-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sh(self, *args, env=None):
        sh = shutil.which("sh")
        if not sh:
            self.skipTest("no POSIX sh")
        return subprocess.run([sh, os.path.join(SKILLS, "install.sh")] + list(args), capture_output=True, text=True,
                              timeout=60, env=dict(os.environ, **(env or {})))

    def test_install_needs_a_destination(self):
        r = self.sh(env={"CODEX_HOME": ""})
        self.assertEqual(r.returncode, 2)
        r = self.sh("--codex", env={"CODEX_HOME": ""})
        self.assertEqual(r.returncode, 2)

    @unittest.skipIf(sys.platform.startswith("win"), "symlinks need privileges on Windows; --copy is the path there")
    def test_symlink_install_and_refresh(self):
        dest = os.path.join(self.tmp, "skills")
        r = self.sh(dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(dest)), sorted(EXPECTED))
        for d in EXPECTED:
            self.assertTrue(os.path.islink(os.path.join(dest, d)))
            real = os.path.realpath(os.path.join(dest, d, "SKILL.md"))
            self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(real))), "e2e", "bin", "e2e")))
        self.assertEqual(self.sh(dest).returncode, 0, "re-running refreshes its own symlinks")

    @unittest.skipIf(sys.platform.startswith("win"), "install.sh runs under Git Bash there; covered on ubuntu and macOS")
    def test_copy_install_writes_the_root_and_refuses_to_clobber(self):
        dest = os.path.join(self.tmp, "codex")
        r = self.sh("--copy", "--codex", env={"CODEX_HOME": dest})
        self.assertEqual(r.returncode, 0, r.stderr)
        root = read(os.path.join(dest, "skills", "wicked-e2e", "wicked-ci-root")).strip()
        self.assertTrue(os.path.isfile(os.path.join(root, "e2e", "bin", "e2e")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "skills", "wicked-e2e", "refs", "studio-ui.md")))
        r = self.sh("--copy", "--codex", env={"CODEX_HOME": dest})
        self.assertEqual(r.returncode, 1, "an existing copy is replaced only with --force")
        self.assertEqual(self.sh("--copy", "--force", "--codex", env={"CODEX_HOME": dest}).returncode, 0)

    @unittest.skipIf(sys.platform.startswith("win"), "install.sh runs under Git Bash there; covered on ubuntu and macOS")
    def test_installing_into_the_sources_is_refused_and_changes_nothing(self):
        # On a disposable copy of the checkout: a broken guard must never touch the real sources.
        mock = os.path.join(self.tmp, "mock")
        shutil.copytree(SKILLS, os.path.join(mock, "skills"), ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(mock, "e2e", "bin"))
        with open(os.path.join(mock, "e2e", "bin", "e2e"), "w", encoding="utf-8") as fh:
            fh.write("# stub\n")
        msk = os.path.join(mock, "skills")
        before = sorted(os.listdir(msk))
        for dest in (msk, os.path.join(msk, "wicked-e2e"), os.path.join(msk, "new") + "/..",
                     os.path.join(msk, "not", "yet")):
            r = subprocess.run([shutil.which("sh"), os.path.join(msk, "install.sh"), "--force", dest],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(msk)), before, "nothing was created or removed in the sources")
        for d in EXPECTED:
            self.assertFalse(os.path.islink(os.path.join(msk, d)))
            self.assertTrue(os.path.isfile(os.path.join(msk, d, "SKILL.md")))

    @unittest.skipIf(sys.platform.startswith("win"), "install.sh runs under Git Bash there; covered on ubuntu and macOS")
    def test_a_checkout_living_at_a_target_is_never_replaced(self):
        # DEST/wicked-e2e is the checkout itself: --force DEST must refuse before touching anything.
        dest = os.path.join(self.tmp, "dest")
        mock = os.path.join(dest, "wicked-e2e")
        shutil.copytree(SKILLS, os.path.join(mock, "skills"), ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(mock, "e2e", "bin"))
        with open(os.path.join(mock, "e2e", "bin", "e2e"), "w", encoding="utf-8") as fh:
            fh.write("# stub\n")
        r = subprocess.run([shutil.which("sh"), os.path.join(mock, "skills", "install.sh"), "--force", dest],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(os.path.islink(mock))
        self.assertTrue(os.path.isfile(os.path.join(mock, "skills", "wicked-e2e", "SKILL.md")))
        self.assertEqual(sorted(os.listdir(dest)), ["wicked-e2e"], "nothing else was installed")

    @unittest.skipIf(sys.platform.startswith("win"), "install.sh runs under Git Bash there; covered on ubuntu and macOS")
    def test_codex_and_a_destination_are_exclusive_in_either_order(self):
        dest = os.path.join(self.tmp, "x")
        for args in (("--codex", dest), (dest, "--codex")):
            r = self.sh(*args, env={"CODEX_HOME": os.path.join(self.tmp, "c")})
            self.assertEqual(r.returncode, 2, args)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "c")))

    @unittest.skipIf(sys.platform.startswith("win"), "install.sh runs under Git Bash there; covered on ubuntu and macOS")
    def test_dry_run_writes_nothing(self):
        dest = os.path.join(self.tmp, "dry")
        r = self.sh("--dry-run", dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(dest))


class RouterEvals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.caps = v.load_catalog(os.path.join(ROOT, "e2e"))
        cls.profiles = json.loads(read(os.path.join(ROOT, "e2e", "profiles.json")))["profiles"]
        cls.doc = json.loads(read(os.path.join(SKILLS, "wicked-e2e", "evals", "resolve-cases.json")))
        cls.tmp = tempfile.mkdtemp(prefix="e2e-resolve-eval-")
        fx = cls.doc["run_fixture"]
        ids = list(fx["results"])
        with open(os.path.join(cls.tmp, "run.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 2, "run_id": "eval", "target": fx["target"], "capabilities": ids}, fh)
        for cid, verdict in fx["results"].items():
            os.makedirs(os.path.join(cls.tmp, cid))
            with open(os.path.join(cls.tmp, cid, "result.json"), "w", encoding="utf-8") as fh:
                json.dump({"id": cid, "verdict": verdict}, fh)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_there_are_at_least_fifteen_cases(self):
        self.assertGreaterEqual(len(self.doc["cases"]), 15)

    def test_every_case_resolves_as_expected(self):
        for case in self.doc["cases"]:
            with self.subTest(request=case["request"], run_dir=case.get("run_dir", False)):
                out = rs.resolve(case["request"], self.caps, self.profiles, run_dir=self.tmp if case.get("run_dir") else None)
                for k, want in case["expect"].items():
                    self.assertEqual(out[k], want, "%s: %s" % (k, json.dumps(out, indent=1)[:1500]))

    def test_the_cli_wires_the_resolver_and_its_exit_code(self):
        ok = subprocess.run([sys.executable, E2E_BIN, "resolve", "test the run page", "--json"], capture_output=True,
                            text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["selection"], "tag:run-page")
        bad = subprocess.run([sys.executable, E2E_BIN, "resolve", "test the foobar widget"], capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(bad.returncode, 1)

    def test_a_resolved_selection_is_what_the_runner_selects(self):
        from e2ecat.select import select
        for case in self.doc["cases"]:
            out = rs.resolve(case["request"], self.caps, self.profiles, run_dir=self.tmp if case.get("run_dir") else None)
            if out["status"] == "resolved" and out["count"]:
                expr = self.profiles[out["profile"]]["select"] if out["profile"] else out["selection"]
                self.assertEqual(len(select(self.caps, expr)), out["count"], case["request"])

    def test_costly_or_live_selections_always_ask(self):
        for case in self.doc["cases"]:
            out = rs.resolve(case["request"], self.caps, self.profiles, run_dir=self.tmp if case.get("run_dir") else None)
            if out["action"] in ("run", "rerun") and out["count"]:
                costly = any(k in ("M", "L") for k in out["cost"])
                question = bool(re.match(r"^\s*(what|which|how|is|are|does|do|did|can|could|has|have)\b",
                                         case["request"].lower())) or case["request"].rstrip().endswith("?")
                self.assertEqual(out["ask_before_running"], costly or out["target"] == "live" or question, case["request"])

    def test_an_unmatched_request_never_widens_to_everything(self):
        out = rs.resolve("please test the zorblax", self.caps, self.profiles)
        self.assertEqual(out["status"], "no-match")
        self.assertIsNone(out["selection"])
        self.assertIsNone(out["profile"])
        self.assertEqual(out["commands"], [])


if __name__ == "__main__":
    unittest.main()
