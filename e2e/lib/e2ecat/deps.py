"""Capability dependencies: classify the catalog's free-text `deps` and check them against a target.

A capability's `deps` are written in prose ("signed-in seats", "container runtime", "crew daemon
:7721"). The runner reduces each one to a REQUIREMENT CLASS with one rule table, then decides, for
the scenario it chose, whether the class is

- PROVIDED by the scenario's adapter (the wicked-ci smoke boots a real daemon with shimmed seats in
  a temp root, so `daemon`, `real-engine`, `signed-in-seats` and `registered-repo` hold there);
- PROBED on the host or the live target (a container runtime, `gh` auth, a tool on PATH, the live
  daemon's /health, its roster's signed-in seats); an unmet probe makes the capability
  `skipped: <dep>`, never a pass;
- a PREREQUISITE capability (the dep names another catalog id): the scenario's own setup performs
  it, so it is recorded, not probed;
- UNCHECKED (scenario-setup state the prose names, such as "open chat" or "snapshot"): recorded on
  the result and in the report, not probed. A scenario that reaches its oracle's end state shows the
  state existed.

`credential` deps (a real provider account, an API key, the OS keychain) are never met by the
runner: it reads no credential, so those capabilities are skipped and the report says why.
"""
import os
import re
import shutil
import socket
import subprocess
import sys

# (class, pattern) — the first match wins, so the specific rules come before the broad ones.
RULES = [
    ("credential", r"provider account|vendor account|subscription|chatgpt account|copilot (account|entitlement)|api[_ ]key|"
                   r"os-keychain|ado-credentials|oidc|image provider credentials|setup-token|pass-through token|"
                   r"signed-in broker|completed vendor sign-in|reads_api_key|real vendor"),
    ("platform-windows", r"^windows$"),
    ("platform-service-manager", r"launchd|systemd"),
    ("platform-unix-socket", r"unix socket"),
    ("platform-sandbox", r"sandbox-exec|bwrap|bubblewrap|landlock|jail \(sandbox\)"),
    ("container", r"container|docker|podman|testcontainers|seat image|floor image|agentgateway image|seat images|base image"),
    ("network", r"^network|network to|network for|cdn download|public url|crates\.io|npm registry|github marketplace"),
    ("gh-auth", r"^gh[- ]auth|gh auth|^github$|open pr|^gh \(issue mode\)$|repo with github remote"),
    ("playwright", r"playwright|chromium|headless chrome|chrome installed|chrome or playwright|recorder browser|"
                   r"render browser|browser on host"),
    ("studio-dist", r"studio:bundled-dist|studio dist|studio-dist|frontend/dist|studio served by crew|^studio$|"
                    r"^wicked-studio$|studio \+ "),
    ("seat-state", r"signed out|signed-out|revoked credential|out of quota|seat record data"),  # a seeded seat state
    ("signed-in-seats", r"signed-in|signed in|seat|claude-code harness|answerer|stalling seat"),
    ("registered-repo", r"registered[- ]repo|repo:registered|registered repos"),
    ("projects-engine", r"projects-engine|project with crew\.repo members"),
    ("real-engine", r"real-engine|core-ts|wicked-core-ts|engine core-ts"),
    ("daemon", r"daemon|gateway|^crew installed$|wicked-crew broker|crew /api/v1|crew get /api|crew editors registry"),
    ("tool-cargo", r"cargo|rust toolchain|^rust"),
    ("tool-node", r"^node|node/npm|node/npx|npm -g|^npm$|node \(adapter\)"),
    ("tool-python", r"^python|pyyaml|python-pptx"),
    ("tool-git", r"^git$|git repo|two git repos|temp git repo"),
    ("tool-ffmpeg", r"ffmpeg"),
    ("tool-jq", r"^jq$"),
    ("tool-uv", r"^uv$"),
    ("bin-wicked-vault", r"wicked-vault"),
    ("bin-wicked-estate", r"wicked-estate|estate symbol db|^estate$"),
    ("bin-wicked-bus", r"wicked-bus|^bus$|bus db"),
    ("bin-wicked-garden", r"wicked-garden|garden plugin|garden installed|garden root|garden qe skill|garden domain skills"),
    ("bin-wicked-interactive", r"wicked-interactive|interactive bridge"),
    ("bin-wicked-ledger", r"wicked-ledger"),
    ("bin-wicked-core", r"wicked-core binary|wicked_core_exe"),
    ("bin-wicked-installer", r"wicked-installer"),
    ("bin-claude", r"^claude cli|claude/codex installed"),
    ("bin-codex", r"^codex(-cli| cli| or stub)"),
    ("bin-opencode", r"^opencode"),
    ("bin-pi", r"^pi cli"),
    ("bin-agy", r"^agy|antigravity"),
    ("bin-copilot", r"^copilot cli"),
    ("bin-cursor", r"cursor installed"),
]
_COMPILED = [(k, re.compile(p, re.I)) for k, p in RULES]

# Tool deps whose prose may carry "or stub": a stub satisfies them, so a scenario that ships its own
# stub (the test does) needs no host binary.
STUB_OK = re.compile(r"\bor (its )?stub\b|-stub\b|\(or tests/", re.I)

BINARIES = {
    "bin-wicked-vault": "wicked-vault", "bin-wicked-estate": "wicked-estate", "bin-wicked-bus": "wicked-bus",
    "bin-wicked-garden": "wicked-garden", "bin-wicked-interactive": "wicked-interactive",
    "bin-wicked-ledger": None,  # a library: no binary, it is resolved from a repo
    "bin-wicked-core": "wicked-core", "bin-wicked-installer": "wicked-installer", "bin-claude": "claude",
    "bin-codex": "codex", "bin-opencode": "opencode", "bin-pi": "pi", "bin-agy": "agy", "bin-copilot": "copilot",
    "bin-cursor": "cursor", "tool-cargo": "cargo", "tool-node": "node", "tool-python": None, "tool-git": "git",
    "tool-ffmpeg": "ffmpeg", "tool-jq": "jq", "tool-uv": "uv",
}

# Python packages a dep names (the probe imports them).
PY_MODULES = {"pyyaml": "yaml", "python-pptx": "pptx", "flask": "flask", "requests": "requests"}

# The classes a live target answers for (probed on the daemon's read-only API).
TARGET_CLASSES = {"daemon", "real-engine", "signed-in-seats", "registered-repo", "projects-engine", "studio-dist"}


def classify(dep, catalog_ids=frozenset()):
    """Return the requirement class of one dep string."""
    d = dep.strip()
    if d in catalog_ids or re.sub(r"\s*\(.*\)$", "", d) in catalog_ids:
        return "prerequisite"
    for k, rx in _COMPILED:
        if rx.search(d):
            return k
    return "unchecked"


class Probe:
    """Host and target probes, each run once per runner invocation (results cached)."""

    def __init__(self, target="fixture", live=None, gh=None, env=None, runner=subprocess.run):
        self.target = target
        self.live = live            # a LiveClient (read-only GETs) when target == live
        self.gh = gh or os.environ.get("E2E_GH") or "gh"
        self.env = env or os.environ
        self.run = runner
        self._cache = {}

    def _once(self, key, fn):
        if key not in self._cache:
            try:
                self._cache[key] = fn()
            except Exception as e:  # a probe that crashes is an unmet dep, with the reason
                self._cache[key] = (False, "probe failed: %s" % e)
        return self._cache[key]

    def _cmd_ok(self, argv, timeout=15):
        try:
            r = self.run(argv, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        return r.returncode == 0, (r.stdout or r.stderr or "").strip()[:200]

    def which(self, name):
        return shutil.which(name)

    def check(self, cls, dep):
        """(met, detail) for one requirement class that is not provided by the scenario."""
        if cls == "credential":
            return False, "needs a real credential (the runner reads none)"
        if cls == "platform-windows":
            return sys.platform.startswith("win"), sys.platform
        if cls == "platform-service-manager":
            return sys.platform in ("darwin", "linux") or sys.platform.startswith("linux"), sys.platform
        if cls == "platform-unix-socket":
            return not sys.platform.startswith("win"), sys.platform
        if cls == "platform-sandbox":
            if sys.platform == "darwin":
                return bool(self.which("sandbox-exec")), "sandbox-exec"
            return bool(self.which("bwrap")), "bwrap"
        if cls == "container":
            return self._once("container", self._container)
        if cls == "network":
            return self._once("network", self._network)
        if cls == "gh-auth":
            return self._once("gh-auth", lambda: self._cmd_ok([self.gh, "auth", "status", "--hostname", "github.com"]))
        if cls == "tool-python":
            m = re.search(r">=\s*3\.(\d+)", dep)
            need = int(m.group(1)) if m else 0
            if sys.version_info < (3, need):
                return False, "python %d.%d" % sys.version_info[:2]
            mod = next((m_ for k, m_ in PY_MODULES.items() if k in dep.lower()), None)
            if mod:
                import importlib.util
                return importlib.util.find_spec(mod) is not None, "python module %s" % mod
            return True, "python %d.%d" % sys.version_info[:2]
        if cls == "tool-node":
            return self._once("node:" + dep, lambda: self._node(dep))
        if cls in BINARIES:
            if STUB_OK.search(dep):
                return True, "a stub satisfies it (%s)" % dep
            name = BINARIES[cls]
            if name is None:
                return True, "resolved by the scenario"
            p = self.which(name)
            return bool(p), ("%s on PATH" % name) if p else ("%s not on PATH" % name)
        if cls in TARGET_CLASSES:
            if self.target != "live" or self.live is None:
                return False, "not provided by this scenario on the %s target" % self.target
            return self._once("live:" + cls + ":" + dep, lambda: self.live.probe(cls, dep))
        if cls == "playwright":
            return False, "no browser on this path"
        return True, "unchecked"

    def _container(self):
        for tool in ("docker", "podman", "nerdctl"):
            if self.which(tool):
                ok, detail = self._cmd_ok([tool, "info"], timeout=20)
                if ok:
                    return True, "%s info ok" % tool
        return False, "no container runtime answers `info` (docker/podman/nerdctl)"

    def _network(self):
        try:
            socket.getaddrinfo("registry.npmjs.org", 443)
            return True, "registry.npmjs.org resolves"
        except OSError as e:
            return False, "no DNS for registry.npmjs.org (%s)" % e

    def _node(self, dep):
        p = self.which("node")
        if not p:
            return False, "node not on PATH"
        ok, out = self._cmd_ok([p, "--version"])
        if not ok:
            return False, "node --version failed: %s" % out
        m = re.search(r"(\d+)", out or "")
        have = int(m.group(1)) if m else 0
        need = re.search(r"(?:>=\s*|node )(\d+)", dep)
        if need and have < int(need.group(1)):
            return False, "node %s < %s" % (out, need.group(1))
        return True, "node %s" % out


def resolve(cap, provides, probe, catalog_ids=frozenset()):
    """Check every dep of `cap` for a scenario whose adapter provides `provides`.

    Returns {"unmet": [(dep, class, detail)], "met": [...], "provided": [...], "prerequisite": [...],
    "unchecked": [...]}. The capability runs only when `unmet` is empty."""
    out = {"unmet": [], "met": [], "provided": [], "prerequisite": [], "unchecked": []}
    for dep in cap.get("deps", []):
        cls = classify(dep, catalog_ids)
        if cls == "prerequisite":
            out["prerequisite"].append(dep)
        elif cls == "unchecked":
            out["unchecked"].append(dep)
        elif cls in provides:
            out["provided"].append("%s (%s)" % (dep, provides[cls]))
        else:
            ok, detail = probe.check(cls, dep)
            (out["met"] if ok else out["unmet"]).append([dep, cls, detail] if not ok else "%s (%s)" % (dep, detail))
    return out
