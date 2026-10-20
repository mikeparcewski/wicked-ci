"""`e2e resolve "<request>"`: a plain request -> an action and a selection, deterministically.

The wicked-e2e router skill calls this instead of guessing. It matches words against the catalog
only (area names and their aliases, tags, id segments, ids, profile names, selection-language
terms), with one fixed precedence, and prints how each word was read. Nothing here is a model.

    action     run | plan | select | validate-coverage | validate-report | report | evidence | rerun
               (`select` lists what a selection holds; only `run` and `rerun` lead to running anything)
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
import shlex

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
validate valid complete intact coverage covered uncovered missing gap gaps mapped unmapped not scenario scenarios
surface surfaces catalog pass passed passing passes green block blocks blocker blockers blocking why
live daemon re-run rerun retry again failed fail failing failures errors error broken red""".split())
# Words that are fillers alone but name a group as a phrase ("run page", "testing page", "everything page"),
# and "runs", which is a tag (the runs list) and never a filler.
PROFILE_WORDS = {"smoke": "smoke", "daily": "daily", "release": "release", "full": "full"}
FULL_WORDS = {"everything", "all", "full"}

# What a live URL may look like: scheme, host, optional port and a plain path. Anything else (spaces,
# quotes, `$`, `;`, `#`, backticks) is refused, so a request can never smuggle arguments into a command.
SAFE_URL = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?$")
TERM = re.compile(r"^!?(area:|tag:|id:|surface=|cost<=|oracle=)\S+$")
URL = re.compile(r"https?://[^\s'\"<>]+", re.I)
PORT_ONLY = re.compile(r"(?<![\w.:/]):(\d{2,5})\b")
# host:port with no scheme (localhost:7801, 127.0.0.1:7801, a dotted host) and "port 7801".
HOST_PORT = re.compile(r"(?<![\w/.:-])((?:localhost|\d{1,3}(?:\.\d{1,3}){3}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)):(\d{2,5})\b")
PORT_WORD = re.compile(r"\bport\s+(\d{2,5})\b", re.I)
URL_PORT = re.compile(r"^[^/?#]*:(\d+)(?:[/?#]|$)")

INTENTS = [
    ("rerun", re.compile(r"\b(re-?run|retry|run again)\b.*\b(fail\w*|error\w*|broke\w*|red)\b|\bfailed (ones )?again\b")),
    ("validate-coverage", re.compile(r"\bvalidate\b.*\b(catalog|surfaces?|scenarios?)\b|\bwhy\b.*\bvalidat\w*\b.*\bfail\w*\b|\bcatalog\b.*\bvalid\w*\b|"
                                     r"\bnot covered\b|\buncovered\b|\bcoverage\b|\bunmapped\b|\bgaps?\b|"
                                     r"\bwhat'?s? missing\b|\bnot mapped\b|\bno scenario\b")),
    ("evidence", re.compile(r"\bevidence\b|\bvideos?\b|\bscreenshots?\b|\btraces?\b|\btamper\w*\b|\bhash(es)?\b|"
                            r"\btranscripts?\b")),
    ("validate-report", re.compile(r"\bvalidate\b.*\b(run|report)\b|\b(run|report)\b.*\b(complete|intact|valid)\b")),
    ("select", re.compile(r"\b(which|what|how many|list|show( me)?)( the| all)? (capabilit\w*|tests?|scenarios?)\b|"
                          r"\b(does|do) (anything|any \w+) cover\b|\bwhich (capabilit\w*|tests?|scenarios?)\b|\bwhat (capabilit\w* )?covers?\b|"
                          r"\blist (the |all )?capabilit\w*\b|\bshow (me )?(the )?capabilities\b|"
                          r"\bhow many capabilit\w*\b|\bwhat is in\b")),
    ("plan", re.compile(r"\bplan\b|\bwhat would run\b|\bwhat will run\b|\bdry[- ]?run\b|\bhow long\b|\bestimate\b|"
                        r"\bwould it take\b|\bwhat does .* need\b|\bprerequisites?\b")),
    ("report", re.compile(r"\bblock\w*\b.*\bpass\w*\b|\bblockers?\b|\bwhy\b.*\b(partial|fail\w*|skipped|error\w*|manual)\b|"
                          r"\bis\b.*\bcertified\b|\bdid\b.*\b(pass|fail)\w*\b|\bsummar\w*\b|\breport\b|\bresults?\b|\bwhat (failed|passed)\b|\bverdicts?\b|"
                          r"\bhow did .* go\b")),
]
DRY_RUN = re.compile(r"\bdry[- ]?runs?\b", re.I)
LOOKUP_START = re.compile(r"^\s*(please\s+)?(list|show|find|count|which|what|how many|look up|search)\b")
EXEC_VERB = re.compile(r"\b(test\w*|certif\w*|run|running|check\w*|verif\w*|execut\w*|exercis\w*|e2e)\b")


def _only_profile_words(itext):
    """`smoke`, `the daily`: a bare profile name is a request to run that profile."""
    words = [w for w in re.findall(r"[a-z]+", itext) if w not in STOP]
    return bool(words) and all(w in PROFILE_WORDS for w in words)


NEEDS_RUN_DIR = ("validate-report", "report", "evidence", "rerun")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tokens(text):
    """Words, lowercased, except a literal selection term, which is kept as written (`cost<=S`)."""
    t = text.replace("\u2019", "'")
    t = re.sub(r"'s\b", "", t, flags=re.I)  # possessives and contractions ("run's", "what's") are not plurals
    t = PORT_WORD.sub(" ", PORT_ONLY.sub(" ", HOST_PORT.sub(" ", URL.sub(" ", t))))
    out = []
    for tok in re.findall(r"!?[A-Za-z0-9][A-Za-z0-9.\-_*:<=,?!\[\]]*", t):
        if re.match(r"^!?id:", tok):
            tok = tok.rstrip(".,!:")  # `?` is a glob character in an id term (`!id:crew-api.runs.cance?`)
        else:
            tok = tok.rstrip(".,?!:")
        out.append(tok if TERM.match(tok) else tok.lower())
    return [x for x in out if x]


class Vocab:
    def __init__(self, caps, profiles):
        self.caps = caps
        self.profiles = profiles
        self.ids = {c["id"] for c in caps} | {a for c in caps for a in c.get("aliases", [])}
        self.canonical = {a: c["id"] for c in caps for a in c.get("aliases", [])}
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


def _url_port(url):
    m = URL_PORT.match(url.split("//", 1)[-1])
    return int(m.group(1)) if m else None


def _live(text):
    """(url, port, live) for a live target the request names: a URL, host:port, `:port` or `port N`."""
    m = URL.search(text)
    if m:
        url = m.group(0).rstrip(".,;:!?)")
        return url, _url_port(url), True
    m = HOST_PORT.search(text)
    if m:
        return "http://%s:%s" % (m.group(1), m.group(2)), int(m.group(2)), True
    m = PORT_ONLY.search(text) or PORT_WORD.search(text)
    if m:
        p = int(m.group(1))
        return "http://127.0.0.1:%d" % p, p, True
    low = text.lower()
    for ph in PHRASES:  # "live checks" is a topic, not the live target
        low = low.replace(ph, " ")
    low = " ".join(b for b in (w.strip(".,?!:;()'\"") for w in low.split())
                   if b and not any(ch in b for ch in ".:-="))  # nor is a tag or id with "live" ("live." is a word)
    return None, None, bool(re.search(r"\blive\b|\bthe daemon\b|\brunning daemon\b|\breal daemon\b", low))


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


def _intent_text(text, vocab):
    """The request without what names a selection (URLs, ids, id prefixes and globs, literal terms), so a
    word inside a capability id (`studio-ui.launch.plan-preview`) never picks the action."""
    words = []
    t = re.sub(r"'s\b", "", URL.sub(" ", text.replace("\u2019", "'")), flags=re.I)
    raw = t.split()
    multi = set()  # word positions inside a spaced multi-word tag or id group ("plan preview", "coverage domain")
    for n in (3, 2):
        for i in range(len(raw) - n + 1):
            key = _norm("".join(x.strip(".,?!:;()'\"") for x in raw[i:i + n]))
            if key and (key in vocab.tag_norm or key in vocab.seg_norm):
                multi.update(range(i, i + n))
    for pos, w in enumerate(raw):
        if pos in multi:
            continue
        bare = w.strip(".,?!:;()'\"")
        if "-" in bare and any(_norm(bare) in d for d in (vocab.tag_norm, vocab.seg_norm, vocab.area_norm)):
            continue  # a hyphenated tag or id group (plan-preview, coverage-domain) names a topic, not an action
        if TERM.match(bare) or ("." in bare and (bare in vocab.ids or any(ch in bare for ch in "*?[")
                                                  or any(i.startswith(bare + ".") for i in vocab.ids))):
            continue
        words.append(w)
    return " ".join(words).lower().replace("\u2019", "'")


def _status(out, status):
    """Set the status, except that a refusal is never downgraded."""
    if out["status"] != "refused":
        out["status"] = status


def resolve(request, caps, profiles, run_dir=None):
    vocab = Vocab(caps, profiles)
    text = request.strip()
    low = text.lower().replace("\u2019", "'")
    explain_pre = []
    if DRY_RUN.search(text):
        # "dry run X": a plan. Read before the vocabulary, which also holds `dry-run` as an id group.
        action = "plan"
        explain_pre.append({"words": "dry run", "as": "action plan (--plan-only)"})
        text = DRY_RUN.sub(" ", text)
    else:
        itext = _intent_text(text, vocab)
        action = next((name for name, rx in INTENTS if rx.search(itext)), None)
        if action is None:
            if LOOKUP_START.match(itext):
                action = "select"  # "list cheap studio checks", "show crew-api.x": a lookup, never a run
            elif EXEC_VERB.search(itext) or _only_profile_words(itext):
                action = "run"
            else:
                # No execution verb ("everything about sign-in"): list what it selects; running is asked for.
                action = "select"
    url, port, live = _live(text)
    toks = _tokens(text)
    terms, explain, ignored, shadowed = {}, list(explain_pre), [], []
    literal, cost, negate = [], None, []
    profile, pword, whole = None, None, False
    i = 0
    while i < len(toks):
        # "without manual", "no governed runs": exclusions are read before the vocabulary, which also
        # holds `manual` and `governed` as id segments.
        if toks[i] in ("no", "without", "skip", "exclude", "excluding") and i + 1 < len(toks):
            nxt = toks[i + 1]
            if nxt == "manual":
                negate.append("!oracle=manual")
                explain.append({"words": "%s manual" % toks[i], "as": "!oracle=manual"})
                i += 2
                continue
            if nxt == "governed":
                cost = cost or "M"
                n = 3 if i + 2 < len(toks) and toks[i + 2] in ("run", "runs") else 2
                explain.append({"words": " ".join(toks[i:i + n]), "as": "cost<=M"})
                i += n
                continue
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
        elif w in FULL_WORDS and action == "rerun":
            pass  # "re-run all failures": the re-run is the failed ids; "all" is not the full profile
        elif w in PROFILE_WORDS or w in FULL_WORDS:
            if not profile:
                profile, pword = PROFILE_WORDS.get(w, "full"), w
        elif w not in STOP and w not in FILLER and w not in ("no", "without", "skip", "exclude", "governed", "manual"):
            ignored.append(w)
        elif i > 0 and w not in ("live", "daemon") and _norm(w) in vocab.tag_norm:
            # A filler word that is also a catalog tag or id group: say so, so a widened selection is caught.
            shadowed.append(w)
        i += 1
    # A profile word is a profile only when nothing else names the topic ("smoke" alone, "studio smoke" is a tag).
    # A literal area:/tag:/id: term names a topic; a literal bound or exclusion (cost<=, surface=, oracle=,
    # any `!` term) only narrows, so with a profile it narrows the profile instead of replacing it.
    lit_topic = [t for t in literal if re.match(r"^(area:|tag:|id:)", t)]
    lit_mod = [t for t in literal if t not in lit_topic]
    # A malformed literal is left for the selection parser to refuse: it is never merged away or dropped.
    bad_literal = [t for t in literal if re.match(r"^!?cost<=", t) and t.split("<=", 1)[1] not in ("S", "M", "L")]
    if bad_literal:
        profile = None
    topic = bool(terms or lit_topic)
    # A shadowed word that is not just a verb ("testing" in "run all testing") was meant as a topic: it
    # must not let a profile or a re-run widen past it.
    topical_shadow = [w for w in shadowed if w not in ("run", "runs", "test", "tests", "check", "checks", "verify",
                                                       "plan", "evidence", "video", "report", "live", "daemon")]
    if profile and topic:
        if profile == "smoke" and "tag" not in terms and not any(t.startswith("tag:") for t in lit_topic):
            terms["tag"] = ["smoke"]
            explain.append({"words": "smoke", "as": "tag tag:smoke (with a topic, smoke is the tag)"})
        elif profile == "smoke":
            explain.append({"words": "smoke", "as": "ignored: tags are OR'd, so tag:smoke would widen the selection"})
        else:
            explain.append({"words": pword, "as": "profile word ignored: the request names a topic"})
        profile = None
    elif profile and (ignored or topical_shadow):
        # "everything about signon": the topic word matched nothing, so the profile word must not widen to it.
        explain.append({"words": pword, "as": "profile word ignored: the request's other words matched nothing"})
        profile = None
    elif profile == "full" and (cost or negate or lit_mod):
        # "run all cheap tests": the whole catalog narrowed by the modifier, as a selection.
        explain.append({"words": pword, "as": "every capability, narrowed by the modifier"})
        profile, whole = None, True
    elif profile and (cost or negate or lit_mod):
        # "the cheap daily tests", "release cost<=S": the profile narrowed. cost<= is monotone, so the lowest
        # bound is the intersection; the profile's other terms and every exclusion are kept.
        ptoks = (profiles[profile]["select"] or "").split()
        pcost = [t[len("cost<="):] for t in ptoks + lit_mod if t.startswith("cost<=") and t[len("cost<="):] in ("S", "M", "L")]
        if pcost:  # the profile's own bound always holds; a modifier can only lower it
            cost = min(([cost] if cost else []) + pcost, key=lambda c: "SML".index(c))
        literal = [t for t in ptoks if not t.startswith("cost<=") and t not in negate]
        literal += [t for t in lit_mod if not t.startswith("cost<=") and t not in literal and t not in negate]
        topic = True
        explain.append({"words": pword, "as": "profile %s narrowed by the modifier" % profile})
        profile = None
    elif profile:
        explain.append({"words": pword,
                        "as": "profile %s (%s)" % (profile, profiles.get(profile, {}).get("select", "?") or "*")})
    if not profile and not topic and action != "rerun" and not whole and (ignored or topical_shadow) and lit_mod:
        # "test zorblax cost<=S": the topic word matched nothing, so a literal bound must not widen to it either.
        explain.append({"words": " ".join(lit_mod), "as": "ignored: the request's topic words matched nothing"})
        literal = [t for t in literal if t in lit_topic]
        lit_mod = []
    if not profile and not topic and not lit_mod and (cost or negate) and action != "rerun" and not whole:
        # A modifier narrows a topic or a profile; alone it would select across every area.
        explain.append({"words": "cost/manual modifier", "as": "ignored: no word names a topic to narrow"})
        cost, negate = None, []
    lit_costs = [t[len("cost<="):] for t in literal if t.startswith("cost<=") and t[len("cost<="):] in ("S", "M", "L")]
    if lit_costs and (cost or len(lit_costs) > 1):
        # cost<= terms are OR'd, so a second one would widen: keep the lower bound only (the intersection).
        cost = min(([cost] if cost else []) + lit_costs, key=lambda c: "SML".index(c))
        literal = [t for t in literal if not (t.startswith("cost<=") and t[len("cost<="):] in ("S", "M", "L"))]
        explain.append({"words": "cost bounds", "as": "the lower one, cost<=%s (same-key terms would widen)" % cost})
    parts = ["%s:%s" % (k, ",".join(v)) for k, v in terms.items() if k in ("area", "tag", "id")]
    parts += literal + (["cost<=%s" % cost] if cost else []) + negate
    expr = " ".join(parts)
    for w in shadowed:
        explain.append({"words": w, "as": "read as a filler word; it is also a catalog tag (write `tag:%s` to "
                                          "select it)" % w})
    out = {"request": request, "action": action, "status": "resolved", "explain": explain, "ignored": ignored,
           "shadowed": shadowed,
           "selection": expr or None, "profile": profile, "target": "live" if live else "fixture",
           "studio": url, "needs": [], "ask_before_running": False, "ask_reasons": [], "count": None,
           "cost": {}, "areas": {}, "commands": []}
    if live and url and not SAFE_URL.match(url):
        out["status"] = "refused"
        out["needs"].append("the live URL %r is not a plain http(s)://host[:port][/path] URL" % url)
        out["studio"] = None
    elif live and port in OPERATOR_PORTS:
        out["status"] = "refused"
        out["needs"].append("a throwaway daemon: %s is an operator daemon port (%d); the runner refuses it "
                            "without --allow-daemon-port. Start `wicked-crew serve --port <free>` with its own "
                            "state home and pass that URL" % (url, port))
    elif live and not url and not (action == "rerun" and run_dir):
        out["status"] = "needs-input"
        out["needs"].append("--studio URL: the live target needs the URL of the crew daemon to certify")
    # Run-dir actions.
    if action in NEEDS_RUN_DIR and not run_dir:
        if out["status"] == "resolved":
            _status(out, "needs-input")
        out["needs"].append("--run-dir DIR: which run directory (the --out of an earlier `e2e run`)")
    if action == "rerun" and not run_dir:
        out["selection"], out["profile"], profile = None, None, None  # nothing to run until the run is named
    if action == "rerun" and run_dir:
        run, results = _read_run(run_dir)
        bad = [cid for cid in run.get("capabilities", []) if (results.get(cid) or {}).get("verdict") in ("fail", "error")]
        explain.append({"words": "what failed", "as": "%d of %d capabilities in %s with verdict fail or error" % (
            len(bad), len(run.get("capabilities", [])), os.path.basename(os.path.normpath(run_dir)))})
        topic_expr = profiles[profile]["select"] if profile else expr
        if (ignored or topical_shadow) and not topic:
            # "re-run zorblax failures": a topic was given and matched nothing, so nothing is re-run.
            _status(out, "no-match")
            out["needs"].append("the topic words (%s) match nothing in the catalog" % ", ".join(ignored + topical_shadow))
            bad = []
        if bad and topic_expr:
            try:
                keep = {c["id"] for c in select(caps, topic_expr)}
            except SelectError as e:
                _status(out, "no-match")
                out["needs"].append("the selection does not parse: %s" % e)
                keep = set()
            explain.append({"words": "topic", "as": "only the failed ones that %s also selects (%d of %d)" % (
                topic_expr, len([b for b in bad if b in keep]), len(bad))})
            bad = [b for b in bad if b in keep]
        if not bad:
            _status(out, "no-match")
            out["needs"].append("nothing to re-run: no capability in that run%s is fail or error" % (
                " matching the request's topic" if topic_expr else ""))
        expr = "id:" + ",".join(bad) if bad else ""
        profile = None  # the re-run is exactly these ids
        out["selection"], out["profile"] = expr or None, None
        if not url and not re.search(r"\bfixture\b", low):  # a target the request names wins; else the earlier run's
            out["target"] = run.get("target") if run.get("target") in ("fixture", "live") else out["target"]
            if live and out["target"] != "live":  # "re-run ... on live" after a fixture run: which daemon?
                out["target"] = "live"
            out["studio"] = run.get("studio") if out["target"] == "live" else None
            if out["studio"] and not SAFE_URL.match(str(out["studio"])):
                _status(out, "refused")
                out["needs"].append("the earlier run's studio URL is not a plain http(s) URL")
                out["studio"] = None
            elif out["studio"] and _url_port(str(out["studio"])) in OPERATOR_PORTS:
                _status(out, "refused")
                out["needs"].append("the earlier run targeted an operator daemon port; certify a throwaway daemon")
            elif out["target"] == "live" and not out["studio"]:
                _status(out, "needs-input")
                out["needs"].append("--studio URL: the earlier run was live but records no daemon URL")
    if action == "evidence":
        ids = [x for x in (expr or "").split() if x.startswith("id:")]
        one = ids[0][3:] if len(ids) == 1 else ""
        if one in vocab.canonical:  # a run records the canonical id, never an alias
            explain.append({"words": one, "as": "alias of %s" % vocab.canonical[one]})
            one = vocab.canonical[one]
            out["selection"] = "id:" + one
        if not one or "," in one or any(ch in one for ch in "*?[") or one not in vocab.ids:
            _status(out, "needs-input" if not ignored else "no-match")
            out["needs"].append("one capability id: `e2e evidence` opens one capability's evidence (an area or "
                                "tag names many; list them with `e2e report` first)")
    # Size the selection.
    sel_expr = profiles[profile]["select"] if profile else expr
    sel = []
    if action in ("run", "plan", "select") or (action == "rerun" and run_dir) or (action in ("report", "evidence", "validate-coverage") and (expr or profile)):
        if not (expr or profile):
            if out["status"] == "resolved":
                _status(out, "no-match")
            out["needs"].append("a topic: no word of the request names a catalog area, tag, id or profile "
                                "(try `e2e select 'tag:<x>'`, or name an area: %s)" % ", ".join(vocab.areas))
        else:
            try:
                sel = select(caps, sel_expr)
            except SelectError as e:
                _status(out, "no-match")
                out["needs"].append("the selection does not parse: %s" % e)
            if not sel and out["status"] == "resolved":
                _status(out, "no-match")
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
        if re.match(r"^\s*(what|which|how|is|are|does|do|did|can|could|has|have)\b", low) or low.rstrip().endswith("?"):
            out["ask_reasons"].append("the request is a question, read here as a run: confirm a run is wanted")
        if out["target"] == "live":
            out["ask_reasons"].append("the live target %s (direct GETs; journeys only with --live-journeys)" % (out["studio"] or "?"))
        out["ask_before_running"] = bool(out["ask_reasons"])
    # Commands only for a request that resolved (or only lacks an input); never for a refusal or no match.
    out["commands"] = _commands(out, run_dir) if out["status"] in ("resolved", "needs-input") else []
    return out


def _sel_args(out):
    if out["profile"]:
        return ["--profile", out["profile"]]
    return ["--select", out["selection"]] if out["selection"] else None


def _commands(out, run_dir):
    """Each command is an argv list joined with shell quoting, so no part of the request, a run directory
    or an earlier run's URL can add, drop or reorder an argument."""
    a, cmds = out["action"], []
    rd = run_dir or "RUN_DIR"
    tgt = ["--target", out["target"]] + (["--studio", out["studio"]] if out["target"] == "live" and out["studio"] else [])
    sel = _sel_args(out)
    base = ["--baseline", "e2e/coverage-baseline.json"]
    if a in ("run", "plan", "rerun") and sel and not (out["target"] == "live" and not out["studio"]):
        src = ["--src", "CHECKOUTS_DIR"] if out["target"] == "fixture" else []
        cmds.append(["e2e", "run"] + sel + tgt + ["--out", "PLAN_DIR", "--plan-only"] + src)
        if a != "plan":
            cmds.append(["e2e", "run"] + sel + tgt + ["--out", "NEW_RUN_DIR"] + src)
            cmds.append(["e2e", "validate", "--report", "NEW_RUN_DIR"] + base)
    elif a == "select" and sel:
        cmds.append(["e2e", "select"] + (["--profile", out["profile"]] if out["profile"] else [out["selection"]]))
    elif a == "validate-coverage":
        cmds.append(["e2e", "validate"] + base + ["--out", "COVERAGE_DIR"])
    elif a == "validate-report":
        cmds.append(["e2e", "validate", "--report", rd] + base)
    elif a == "report":
        cmds += [["e2e", "report", rd], ["e2e", "validate", "--report", rd] + base]
    elif a == "evidence":
        ids = [x for x in (out["selection"] or "").split() if x.startswith("id:")]
        cid = ids[0][3:].split(",")[0] if ids and not any(ch in ids[0] for ch in "*?[") else "CAP_ID"
        cmds.append(["e2e", "evidence", rd, cid])
    return [shlex.join(c) for c in cmds]


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
