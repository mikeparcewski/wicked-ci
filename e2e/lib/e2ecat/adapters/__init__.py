"""Scenario adapters: run an EXISTING test or harness without rewriting it, and say what it recorded.

Each adapter claims the scenario references it can run (`claim`), says which requirement classes
its scenarios bring along (`provides`), which evidence kinds it can capture (`evidence_kinds`),
and runs a UNIT (one invocation that may carry several scenarios: one smoke harness run for every
Sxx step, one vitest file, one cargo test target, one run_journeys call). `run` returns an
Outcome per scenario key: the status, the Observations, and the evidence files it left.
"""
import json
import os
import shutil
import subprocess
import sys
import time

from ..observe import Observations

# The runtime classes a lower-fidelity scenario replaces with its own doubles (an integration test's
# in-process daemon and stub adapter, the uxfix fixture's stub API). They are "provided" there, and
# the fidelity cap keeps such a run from ever being a pass.
DOUBLED = ("daemon", "real-engine", "signed-in-seats", "registered-repo", "projects-engine")


class Outcome:
    def __init__(self, status, detail="", fidelity=None):
        self.status = status          # passed | failed | error
        self.detail = detail
        self.fidelity = fidelity
        self.obs = Observations()
        self.evidence = {}            # kind -> [absolute paths] (scenario-level files)
        self.seconds = 0.0
        self.extra = {}               # adapter-specific facts for result.json

    def add(self, kind, path):
        if path and os.path.isfile(path) and os.path.getsize(path) > 0:
            self.evidence.setdefault(kind, [])
            if path not in self.evidence[kind]:
                self.evidence[kind].append(path)


class Unit:
    def __init__(self, key, adapter, params=None):
        self.key = key
        self.adapter = adapter
        self.params = params or {}
        self.scenarios = {}   # scenario key -> scenario dict
        self.caps = []        # capability ids this unit proves
        self.outcomes = {}

    @property
    def slug(self):
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in self.key)[:120]


def scenario_key(s):
    return s["ref"] + ("#" + s["name"] if s.get("name") else "")


class Adapter:
    name = "base"
    targets = ("fixture",)

    def claim(self, scenario, ctx):
        """(unit key, params) when this adapter runs `scenario` on ctx.target, else None."""
        return None

    def available(self, ctx, unit_params):
        """None when this host can run the scenario, else (dep, detail): the unmet requirement, named
        `checkout:<repo>`, `adapter:<tool>` or `target:<target>` (it becomes the skip reason)."""
        return None

    def provides(self, ctx, scenario):
        return {}

    def evidence_kinds(self, ctx, scenario, cap):
        return set()

    def run(self, unit, ctx):
        raise NotImplementedError

    def cleanup(self, unit, ctx):
        pass


def run_logged(argv, cwd, env, log_path, timeout):
    """Run a command to completion with stdout+stderr to `log_path`; (exit code | None on timeout, seconds)."""
    t0 = time.monotonic()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8", errors="replace") as fh:
        fh.write("$ %s\n" % " ".join(argv))
        fh.flush()
        # Its own process group (a new session on POSIX): a timeout ends the WHOLE tree (run_journeys and
        # its journey, the smoke harness and its daemon, cargo and rustc), never just the direct child.
        group = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT, **group)
        except OSError as e:
            fh.write("\n[could not start: %s]\n" % e)
            return -1, time.monotonic() - t0
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(p)
            fh.write("\n[killed (the whole process tree) after %ss]\n" % timeout)
            rc = None
        else:
            kill_tree(p, only_stragglers=True)
    return rc, time.monotonic() - t0


def kill_tree(p, only_stragglers=False):
    """End `p`'s process group (POSIX) or tree (Windows) and wait for it. `only_stragglers`: `p` exited;
    end anything it left behind in its group (a daemon a harness forgot)."""
    if os.name == "nt":
        if not only_stragglers:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        return
    import signal
    # Snapshot the descendants BEFORE signalling (once a parent dies its children re-parent and the tree
    # is lost): a descendant that started its own session (a journey's daemon) is outside the group.
    pids = descendants(p.pid)
    for sig, grace in ((signal.SIGTERM, 10), (signal.SIGKILL, 10)):
        try:
            os.killpg(p.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        for pid in pids:
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            p.poll()  # reap the leader, or its zombie keeps the group "alive"
            if not (_group_alive(p.pid) or any(_alive(x) for x in pids)):
                break
            time.sleep(0.2)
        p.poll()
        if not (_group_alive(p.pid) or any(_alive(x) for x in pids)):
            break
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def descendants(root):
    """Every live descendant pid of `root` (POSIX `ps`), found through parent links."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    kids = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [root]
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in found and c != root:
                found.append(c)
                todo.append(c)
    return found


def _alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:  # a zombie child of ours: reap it
        return os.waitpid(pid, os.WNOHANG) == (0, 0)
    except ChildProcessError:
        return True


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def read_jsonl(path):
    out = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=1, default=str)
        fh.write("\n")
    return path


def _writable(func, path, _exc):
    """rmtree error hook: a read-only dir or file (a test's chmod, a venv) is made writable, then removed."""
    try:
        os.chmod(os.path.dirname(path) or ".", 0o700)
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def rmtree(path):
    if path and os.path.isdir(path):
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_writable)
        else:
            shutil.rmtree(path, onerror=_writable)


def all_adapters():
    from .smoke import SmokeAdapter
    from .studio import StudioJourneyAdapter
    from .vitest import VitestAdapter
    from .cargo import CargoAdapter
    return [SmokeAdapter(), StudioJourneyAdapter(), VitestAdapter(), CargoAdapter()]
