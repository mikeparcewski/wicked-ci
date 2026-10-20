"""THE verdict rule. The runner derives every verdict with `derive()`, and `e2e validate --report`
re-checks a recorded verdict with `problems()`, so a run directory cannot claim more than the rule
allows, however it was written.

    error    the scenario could not run (an infrastructure failure, a timeout, evidence it could
             not capture). Never a judgment about the product.
    fail     the scenario failed, or a typed check was CONTRADICTED by what the run recorded.
    manual   the oracle is manual: it is never `pass`.
    pass     every typed check was OBSERVED to hold (`ok: true`) on something tied to this path
             (no `wildcard` match), the oracle is complete (recursively), the proof is
             certification-grade (`e2e-live` or `e2e-hermetic` fidelity), and the path was DRIVEN
             by the scenario, not only read afterwards.
    partial  everything else that ran: a check not observed, a partial oracle, or a lower fidelity
             (`e2e-fixture` is evidence, not certification; `integration`/`unit` do not drive the
             user's path).
    skipped  the capability did not run, and `skip.dep` names the unmet dependency.
"""
import re

from .validate import _checks, oracle_complete

CERTIFYING = ("e2e-live", "e2e-hermetic")
VERDICTS = ("pass", "fail", "partial", "manual", "error", "skipped")
# A capability whose every check is a read the runner itself can make IS its own user path, so a direct
# read can prove it. Anything else needs a scenario that drives the path.
READ_KINDS = ("npm", "gh")


READ_STEP = re.compile(r"^(GET /|npm view |gh (api|run (view|list)|release (view|list)|pr (view|list)) )", re.I)


def path_is_read(cap):
    """The user path, up to its terminal state, is only reads (each step a GET, `npm view` or a gh read):
    no setup, no launch, no seeded state. Then the runner's own read IS the path."""
    action = re.split(r"\bterminal\s*:", cap.get("user_path", ""), maxsplit=1, flags=re.I)[0]
    steps = [x.strip(" .`") for x in re.split(r";|\.\s", action) if x.strip(" .`")]
    return bool(steps) and all(READ_STEP.match(x) for x in steps)


def read_only(cap):
    """True when the capability's path is a read the runner makes itself: every typed check is a GET, an
    npm or a gh read, and the user path is nothing but such reads (`path_is_read`)."""
    o = cap["oracle"]
    if o["kind"] == "manual":
        return False
    checks = _checks(o)
    return bool(checks) and path_is_read(cap) and all(
        (c["kind"] == "api" and c.get("method", "GET").upper() == "GET") or c["kind"] in READ_KINDS for c in checks)


def derive(cap, scenario_status, observed, fidelity, driven):
    """Return (verdict, reasons). `scenario_status` is passed | failed | error.
    `driven` is False when the observations come only from the runner's own direct reads."""
    o = cap["oracle"]
    oks = [ob.get("ok") for ob in observed]
    if scenario_status == "error":
        return "error", ["the scenario could not run"]
    if scenario_status == "failed":
        return "fail", ["the scenario failed"]
    if False in oks:
        bad = [i for i, ok in enumerate(oks) if ok is False]
        return "fail", ["check %s contradicted by what the run recorded" % ", ".join(map(str, bad))]
    if o["kind"] == "manual":
        return "manual", ["the oracle is manual (%s)" % o.get("category")]
    reasons = []
    if not oracle_complete(o):
        reasons.append("the oracle is partial: %s" % "; ".join(o.get("untyped") or ["a child is incomplete"]))
    missing = [i for i, ok in enumerate(oks) if ok is not True]
    if missing:
        reasons.append("check %s not observed" % ", ".join(map(str, missing)))
    wild = [i for i, ob in enumerate(observed) if ob.get("ok") is True and ob.get("wildcard")]
    if wild:
        reasons.append("check %s held only on something not tied to this path (an unbound placeholder, a shared "
                       "event window, the latest workflow run)" % ", ".join(map(str, wild)))
    if len(oks) != len(_checks(o)):
        reasons.append("observed does not list every check")
    if fidelity not in CERTIFYING:
        reasons.append("fidelity %s is not certification (needs e2e-live or e2e-hermetic)" % fidelity)
    if not driven and not read_only(cap):
        reasons.append("the runner only read the end state; no scenario drove the user's path")
    return ("partial", reasons) if reasons else ("pass", [])


def problems(cap, res):
    """What is wrong with a recorded result under the verdict rule (for `validate --report`)."""
    out = []
    v = res.get("verdict")
    obs = res.get("observed") if isinstance(res.get("observed"), list) else []
    oks = [ob.get("ok") for ob in obs if isinstance(ob, dict)]
    scen = res.get("scenario") or {}
    if v in ("pass", "partial", "manual") and False in oks:
        out.append("a contradicted check (ok: false) must be `fail`, not `%s`" % v)
    if v == "pass":
        if any(ok is not True for ok in oks):
            out.append("`pass` with a check that was not observed to hold (ok must be true for every check)")
        if any(isinstance(ob, dict) and ob.get("wildcard") for ob in obs):
            out.append("`pass` with a check that held only on a wildcard match (not tied to this path)")
        if scen.get("status") != "passed":
            out.append("`pass` needs a scenario that passed (scenario.status is %r)" % scen.get("status"))
        if scen.get("fidelity") not in CERTIFYING:
            out.append("`pass` needs e2e-live or e2e-hermetic fidelity, got %r" % scen.get("fidelity"))
        refs = {s["ref"] for s in cap.get("scenarios", []) if isinstance(s, dict)}
        if scen.get("ref") == "direct":
            if not read_only(cap):
                out.append("`pass` from direct reads only: this capability's path must be driven by a scenario")
            if scen.get("fidelity") != "e2e-live":
                out.append("a direct read certifies only a live target")
        elif scen.get("ref") not in refs:
            out.append("the proving scenario %r is not one of this capability's scenarios" % scen.get("ref"))
    if v in ("skipped", "error") and not (res.get("skip") or res.get("reason")):
        out.append("`%s` must say why (skip.dep or reason)" % v)
    if v == "skipped":
        skip = res.get("skip") or {}
        dep = skip.get("dep")
        allowed = set(cap.get("deps", []))
        if not dep:
            out.append("`skipped` must name the unmet dependency (skip.dep)")
        elif dep not in allowed and not str(dep).startswith(("evidence:", "scenario:", "target:", "checkout:", "adapter:")):
            out.append("skip.dep %r is neither a dep of the capability nor a runner requirement" % dep)
    return out
