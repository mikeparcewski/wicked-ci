"""`e2e resolve "<request>"`: a plain request -> an action and a selection, deterministically.

The wicked-e2e router skill calls this instead of guessing. It matches words against the catalog
only (area names and their aliases, tags, id segments, ids, profile names, selection-language
terms), with one fixed precedence, and prints how each word was read. Nothing here is a model.

    action     run | plan | validate-coverage | validate-report | report | evidence | rerun
    selection  a selection expression (or a profile) the runner takes unchanged
    status     resolved | no-match | needs-input | refused   (exit 0 only for `resolved`)

Precedence, per position in the request (longest phrase first, up to 4 words):
  1. a literal selection term (`tag:x`, `id:a.b.*`, `cost<=S`, ...) is kept as written
  2. a full capability id, an id glob, or an id prefix (`crew-api.health` -> `id:crew-api.health.*`)
  3. an area name or alias ("plugins" -> area:plugins-and-installs, "studio" -> area:studio-ui)
  4. a tag (hyphen-insensitive: "sign in", "sign-in" and "signin" are one group)
  5. an id segment no tag carries (`id:*.<seg>.*,*.<seg>`)
Words that match nothing are reported as ignored; a request whose words match nothing selects
nothing (it never falls back to "everything").
"""
import json
import os
import re

from .select import SelectError, select

OPERATOR_PORTS = (7701, 7721)

AREA_ALIASES = {
    "studio": "studio-ui", "ui": "studio-ui",
    "crew": "crew-api", "api": "crew-api", "daemon-api": "crew-api",
    "core": "core-engine", "engine": "core-engine",
    "plugins": "plugins-and-installs", "installs": "plugins-and-installs",
    "interactive": "interactive-and-docs", "docs": "interactive-and-docs", "documents": "interactive-and-docs",
    "seats": "seats-and-clis", "clis": "seats-and-clis",
}

# Phrases that name a tag the words alone would not reach.
PHRASES = {"everything page": "everything", "everything tab": "everything", "run panel": "run-panel",
           "testing page": "testing", "testing tab": "testing", "live check": "livecheck", "live checks": "livecheck"}

STOP = set("""a an the of for to and or me my our all about on in at with that this these those is are be it its
what whats s which please can could you i we us do does did would will should give show tell list
everything every whole entire any some just only also then""".split())
FILLER = set("""test tests testing tested certify certification certified check checks checking verify verified run
running e2e suite page pages screen screens flow flows feature features capability capabilities stuff things thing
tool tools work works working against target fixture id profile profiles new
plan planned estimate dry long how take takes need needs needed prerequisite prerequisites cost time
report reports result results summary summarise summarize verdict verdicts last latest previous went go
evidence video videos screenshot screenshots trace traces transcript transcripts hash hashes tamper tampered open proof
validate valid complete intact coverage covered uncovered missing gap gaps mapped unmapped not scenario
live daemon re-run rerun retry again failed fail failing failures errors error broken red""".split())
# Words that are fillers alone but name a group as a phrase ("run page", "testing page", "everything page"),
# and "runs", which is a tag (the runs list) and never a filler.
PROFILE_WORDS = {"smoke": "smoke", "daily": "daily", "release": "release", "full": "full"}
FULL_WORDS = {"everything", "all", "full"}

TERM = re.compile(r"^!?(area:|tag:|id:|surface=|cost<=|oracle=)\S+$")
URL = re.compile(r"https?://[^\s'\"<>]+", re.I)
PORT_ONLY = re.compile(r"(?<![\w.:/]):(\d{2,5})\b")

INTENTS = [
    ("rerun", re.compile(r"\b(re-?run|retry|run again)\b.*\b(fail\w*|error\w*|broke\w*|red)\b|\bfailed (ones )?again\b")),
    ("validate-coverage", re.compile(r"\bnot covered\b|\buncovered\b|\bcoverage\b|\bunmapped\b|\bgaps?\b|"
                                     r"\bwhat'?s missing\b|\bnot mapped\b|\bno scenario\b")),
    ("evidence", re.compile(r"\bevidence\b|\bvideos?\b|\bscreenshots?\b|\btraces?\b|\btamper\w*\b|\bhash(es)?\b|"
                            r"\btranscripts?\b")),
    ("validate-report", re.compile(r"\bvalidate\b.*\b(run|report)\b|\b(run|report)\b.*\b(complete|intact|valid)\b")),
    ("plan", re.compile(r"\bplan\b|\bwhat would run\b|\bwhat will run\b|\bdry[- ]?run\b|\bhow long\b|\bestimate\b|"
                        r"\bwould it take\b|\bwhat does .* need\b|\bprerequisites?\b")),
    ("report", re.compile(r"\bsummar\w*\b|\breport\b|\bresults?\b|\bwhat (failed|passed)\b|\bverdicts?\b|"
                          r"\bhow did .* go\b")),
]
NEEDS_RUN_DIR = ("validate-report", "report", "evidence", "rerun")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tokens(text):
    """Words, lowercased, except a literal selection term, which is kept as written (`cost<=S`)."""
    t = PORT_ONLY.sub(" ", URL.sub(" ", text.replace("\u2019", "'")))
    out = []
    for tok in re.findall(r"!?[A-Za-z0-9][A-Za-z0-9.\-_*:<=,?!\[\]]*", t):
        out.append(tok if TERM.match(tok) else tok.rstrip(".,?!:").lower())
    return [x for x in out if x]


class Vocab:
    def __init__(self, caps, profiles):
        self.caps = caps
        self.profiles = profiles
        self.ids = {c["id"] for c in caps} | {a for c in caps for a in c.get("aliases", [])}
        self.areas = sorted({c["_area"] for c in caps})
        self.area_norm = {_norm(a): a for a in self.areas}
        for k, a in AREA_ALIASES.items():
            if a in self.areas:
                self.area_norm.setdefault(_norm(k), a)
        self.tag_norm = {}
        for c in caps:
            for t in c["tags"]:
                self.tag_norm.setdefault(_norm(t), set()).add(t)
        tags = {t for c in caps for t in c["tags"]}
        self.seg_norm = {}
        for c in caps:
            for seg in c["id"].split(".")[1:]:
                if seg not in tags:
                    self.seg_norm.setdefault(_norm(seg), seg)


def _match_span(vocab, span, segments=False):
    """(key, values, label) for a span of tokens, or None. Id segments are tried only in the second pass
    (`segments=True`), so an area or a tag inside a phrase wins over a longer id segment."""
    raw = " ".join(span)
    if len(span) == 1 and TERM.match(span[0]):
        return ("literal", [span[0]], "selection term")
    if len(span) == 1 and "." in span[0]:
        tok = span[0]
        if tok in vocab.ids or any(ch in tok for ch in "*?["):
            return ("id", [tok], "capability id")
        if any(i.startswith(tok + ".") for i in vocab.ids):
            return ("id", [tok + ".*"], "capability id prefix")
    if raw in PHRASES:
        return ("tag", [PHRASES[raw]], "phrase")
    key = _norm("".join(span))
    if not key:
        return None
    if len(span) == 1 and (span[0] in STOP or span[0] in FILLER or span[0] in PROFILE_WORDS):
        return None
    if not segments and key in vocab.area_norm:
        return ("area", [vocab.area_norm[key]], "area")
    if not segments and key in vocab.tag_norm:
        return ("tag", sorted(vocab.tag_norm[key]), "tag")
    if segments and key in vocab.seg_norm:
        seg = vocab.seg_norm[key]
        return ("id", ["*.%s.*" % seg, "*.%s" % seg], "id segment")
    return None


def _live(text):
    m = URL.search(text)
    if m:
        url = m.group(0).rstrip(".,)")
        port = re.search(r":(\d+)(/|$)", url.split("//", 1)[1])
        return url, int(port.group(1)) if port else None, True
    m = PORT_ONLY.search(text)
    if m:
        p = int(m.group(1))
        return "http://127.0.0.1:%d" % p, p, True
    return None, None, bool(re.search(r"\blive\b|\bthe daemon\b|\brunning daemon\b|\breal daemon\b", text.lower()))


def _read_run(run_dir):
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    results = {}
    for cid in run.get("capabilities", []):
        p = os.path.join(run_dir, cid, "result.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                results[cid] = json.load(fh)
    return run, results


def _q(expr):
    return "'%s'" % expr.replace("'", "'\\''")


def resolve(request, caps, profiles, run_dir=None):
    vocab = Vocab(caps, profiles)
    text = request.strip()
    low = text.lower().replace("’", "'")
    action = next((name for name, rx in INTENTS if rx.search(low)), "run")
    url, port, live = _live(text)
    toks = _tokens(text)
    terms, explain, ignored = {}, [], []
    literal, cost, negate = [], None, []
    profile, pword = None, None
    i = 0
    while i < len(toks):
        hit = None
        for segments in (False, True):
            for n in (4, 3, 2, 1):
                span = toks[i:i + n]
                if len(span) < n:
                    continue
                hit = _match_span(vocab, span, segments)
                if hit:
                    break
            if hit:
                break
        if hit:
            key, vals, label = hit
            if key == "literal":
                literal.extend(vals)
            else:
                cur = terms.setdefault(key, [])
                cur.extend(v for v in vals if v not in cur)
            explain.append({"words": " ".join(toks[i:i + n]), "as": "%s %s" % (label, "%s:%s" % (key, ",".join(vals))
                                                                                if key != "literal" else vals[0])})
            i += n
            continue
        w = toks[i]
        if w in ("cheap", "quick", "fast", "hermetic", "seconds"):
            cost = "S"
            explain.append({"words": w, "as": "cost<=S"})
        elif w == "governed" and re.search(r"\b(no|without|skip)\s+governed\b", low):
            cost = cost or "M"
            explain.append({"words": "no governed runs", "as": "cost<=M"})
        elif w == "manual" and re.search(r"\b(no|without|skip|exclude)\s+manual\b", low):
            negate.append("!oracle=manual")
            explain.append({"words": "no manual", "as": "!oracle=manual"})
        elif w in PROFILE_WORDS or w in FULL_WORDS:
            if not profile:
                profile, pword = PROFILE_WORDS.get(w, "full"), w
        elif w not in STOP and w not in FILLER and w not in ("no", "without", "skip", "exclude", "governed", "manual"):
            ignored.append(w)
        i += 1
    # A profile word is a profile only when nothing else names the topic ("smoke" alone, "studio smoke" is a tag).
    topic = bool(terms or literal)
    if profile and topic:
        if profile == "smoke" and "tag" not in terms:
            terms["tag"] = ["smoke"]
            explain.append({"words": "smoke", "as": "tag tag:smoke (with a topic, smoke is the tag)"})
        elif profile == "smoke":
            explain.append({"words": "smoke", "as": "ignored: tags are OR'd, so tag:smoke would widen the selection"})
        else:
            explain.append({"words": pword, "as": "profile word ignored: the request names a topic"})
        profile = None
    elif profile:
        if cost or negate:
            explain.append({"words": "cost/manual modifier", "as": "ignored with a profile (use --select to narrow)"})
            cost, negate = None, []
        explain.append({"words": pword,
                        "as": "profile %s (%s)" % (profile, profiles.get(profile, {}).get("select", "?") or "*")})
    parts = ["%s:%s" % (k, ",".join(v)) for k, v in terms.items() if k in ("area", "tag", "id")]
    parts += literal + (["cost<=%s" % cost] if cost else []) + negate
    expr = " ".join(parts)
    out = {"request": request, "action": action, "status": "resolved", "explain": explain, "ignored": ignored,
           "selection": expr or None, "profile": profile, "target": "live" if live else "fixture",
           "studio": url, "needs": [], "ask_before_running": False, "ask_reasons": [], "count": None,
           "cost": {}, "areas": {}, "commands": []}
    if live and port in OPERATOR_PORTS:
        out["status"] = "refused"
        out["needs"].append("a throwaway daemon: %s is an operator daemon port (%d); the runner refuses it "
                            "without --allow-daemon-port. Start `wicked-crew serve --port <free>` with its own "
                            "state home and pass that URL" % (url, port))
    elif live and not url:
        out["status"] = "needs-input"
        out["needs"].append("--studio URL: the live target needs the URL of the crew daemon to certify")
    # Run-dir actions.
    if action in NEEDS_RUN_DIR and not run_dir:
        if out["status"] == "resolved":
            out["status"] = "needs-input"
        out["needs"].append("--run-dir DIR: which run directory (the --out of an earlier `e2e run`)")
    if action == "rerun" and run_dir:
        run, results = _read_run(run_dir)
        bad = [cid for cid in run.get("capabilities", []) if (results.get(cid) or {}).get("verdict") in ("fail", "error")]
        explain.append({"words": "what failed", "as": "%d of %d capabilities in %s with verdict fail or error" % (
            len(bad), len(run.get("capabilities", [])), os.path.basename(os.path.normpath(run_dir)))})
        if not bad:
            out["status"] = "no-match"
            out["needs"].append("nothing to re-run: no capability in that run is fail or error")
        expr = "id:" + ",".join(bad) if bad else ""
        out["selection"], out["profile"] = expr or None, None
        out["target"] = run.get("target") or out["target"]
        out["studio"] = run.get("studio") or out["studio"]
        if out["target"] == "live" and out["studio"]:
            p = re.search(r":(\d+)(/|$)", out["studio"].split("//", 1)[-1])
            if p and int(p.group(1)) in OPERATOR_PORTS:
                out["status"] = "refused"
                out["needs"].append("the earlier run targeted an operator daemon port; certify a throwaway daemon")
    # Size the selection.
    sel_expr = profiles[profile]["select"] if profile else expr
    sel = []
    if action in ("run", "plan") or (action == "rerun" and run_dir) or (action in ("report", "evidence", "validate-coverage") and (expr or profile)):
        if not (expr or profile):
            if out["status"] == "resolved":
                out["status"] = "no-match"
            out["needs"].append("a topic: no word of the request names a catalog area, tag, id or profile "
                                "(try `e2e select 'tag:<x>'`, or name an area: %s)" % ", ".join(vocab.areas))
        else:
            try:
                sel = select(caps, sel_expr)
            except SelectError as e:
                out["status"] = "no-match"
                out["needs"].append("the selection does not parse: %s" % e)
            if not sel and out["status"] == "resolved":
                out["status"] = "no-match"
                out["needs"].append("the selection %s selects no capability" % (sel_expr or "*"))
    if sel:
        out["count"] = len(sel)
        for c in sel:
            out["cost"][c["cost"]] = out["cost"].get(c["cost"], 0) + 1
            out["areas"][c["_area"]] = out["areas"].get(c["_area"], 0) + 1
    if action in ("run", "rerun") and sel:
        costly = {k: n for k, n in out["cost"].items() if k in ("M", "L")}
        if costly:
            out["ask_reasons"].append("cost %s (M = a live seat turn, L = a governed run)" % ", ".join(
                "%s x%d" % kv for kv in sorted(costly.items())))
        if out["target"] == "live":
            out["ask_reasons"].append("the live target %s (direct GETs; journeys only with --live-journeys)" % (out["studio"] or "?"))
        out["ask_before_running"] = bool(out["ask_reasons"])
    # Commands only for a request that resolved (or only lacks an input); never for a refusal or no match.
    out["commands"] = _commands(out, run_dir) if out["status"] in ("resolved", "needs-input") else []
    return out


def _sel_args(out):
    if out["profile"]:
        return "--profile %s" % out["profile"]
    return "--select %s" % _q(out["selection"]) if out["selection"] else None


def _commands(out, run_dir):
    a, cmds = out["action"], []
    rd = run_dir or "RUN_DIR"
    tgt = "--target %s%s" % (out["target"], " --studio %s" % out["studio"] if out["target"] == "live" and out["studio"] else "")
    sel = _sel_args(out)
    if a in ("run", "plan", "rerun") and sel:
        cmds.append("e2e run %s %s --out PLAN_DIR --plan-only" % (sel, tgt))
        if a != "plan":
            cmds.append("e2e run %s %s --out NEW_RUN_DIR --src CHECKOUTS_DIR" % (sel, tgt))
            cmds.append("e2e validate --report NEW_RUN_DIR --baseline e2e/coverage-baseline.json")
    elif a == "validate-coverage":
        cmds.append("e2e validate --baseline e2e/coverage-baseline.json --out COVERAGE_DIR")
    elif a == "validate-report":
        cmds.append("e2e validate --report %s --baseline e2e/coverage-baseline.json" % rd)
    elif a == "report":
        cmds += ["e2e report %s" % rd, "e2e validate --report %s --baseline e2e/coverage-baseline.json" % rd]
    elif a == "evidence":
        ids = [x for x in (out["selection"] or "").split() if x.startswith("id:")]
        cid = ids[0][3:].split(",")[0] if ids and "*" not in ids[0] else "CAP_ID"
        cmds.append("e2e evidence %s %s" % (rd, cid))
    return cmds


def render(out):
    L = ["request: %s" % out["request"], "action: %s" % out["action"], "status: %s" % out["status"]]
    for e in out["explain"]:
        L.append("  %r -> %s" % (e["words"], e["as"]))
    if out["ignored"]:
        L.append("  ignored (no catalog match): %s" % ", ".join(out["ignored"]))
    if out["profile"]:
        L.append("selection: --profile %s" % out["profile"])
    elif out["selection"]:
        L.append("selection: %s   (same key: OR; different keys: AND)" % out["selection"])
    if out["count"] is not None:
        L.append("selects: %d capabilities (cost %s; areas %s)" % (
            out["count"], ", ".join("%s %d" % kv for kv in sorted(out["cost"].items())),
            ", ".join("%s %d" % kv for kv in sorted(out["areas"].items()))))
    L.append("target: %s%s" % (out["target"], " %s" % out["studio"] if out["studio"] else ""))
    for n in out["needs"]:
        L.append("needs: %s" % n)
    if out["ask_before_running"]:
        L.append("ask before running: %s" % "; ".join(out["ask_reasons"]))
    for c in out["commands"]:
        L.append("next: %s" % c)
    return "\n".join(L) + "\n"
