"""Observations and typed-check evaluation: what a scenario run recorded, and what each oracle check saw.

A scenario run leaves OBSERVATIONS: HTTP exchanges (the smoke harness's API tap, a browser HAR, a
fixture's request log, a test's inject/fetch tap), event streams (the daemon's /ws frames, events
read back from `GET /runs/:id/events`, the browser's network requests), CLI invocations (argv,
exit code, output), DOM samples (the Playwright hook), and file roots it left behind.

`evaluate()` turns one typed oracle check into `{"value", "ok", "how"}`:

- `ok: True`  the check held on something the run recorded (or a read-only direct check made).
- `ok: False` a DEFINITIVE contradiction: the runner's own read of the end state answers otherwise
              (a direct GET, npm or gh read, a direct `--version` run), a COMPLETE event stream
              does not hold the event (or holds a forbidden one), a file the scenario left behind
              holds another value.
- `ok: None`  NOT OBSERVED: nothing recorded can decide it. Either nothing matched (no such request,
              invocation or event; a partial stream; a check this scenario cannot see), or the
              matching exchanges were UNSATISFIED (`how: "transcript: unsatisfied"`): a scenario's
              request is not necessarily made in the state the oracle describes.

Only `True` counts toward a pass. A runner never turns `None` into `True`.
"""
import hashlib
import json
import os
import re
import shlex

PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w-]*)\}")


# ── JSONPath subset: $.a.b, $.a[0], $.a[?(@.k=='v')].f ─────────────────────────────────────────

_TOKEN = re.compile(r"\.([A-Za-z_$][\w$-]*)|\[(\d+)\]|\[\?\(@\.([\w.-]+)\s*(==|!=)\s*(?:'([^']*)'|\"([^\"]*)\"|(-?\d+(?:\.\d+)?|true|false|null))\)\]|\[\*\]|\.\*")


class PathError(ValueError):
    pass


def _literal(s):
    return json.loads(s)


def jsonpath(doc, path):
    """Every value `path` selects in `doc` (a list; empty when nothing matches)."""
    if not isinstance(path, str) or not path.startswith("$"):
        raise PathError("not a JSONPath: %r" % path)
    cur = [doc]
    pos = 1
    while pos < len(path):
        m = _TOKEN.match(path, pos)
        if not m:
            raise PathError("unsupported JSONPath at %r in %r" % (path[pos:], path))
        nxt = []
        if m.group(1) is not None:
            for v in cur:
                if isinstance(v, dict) and m.group(1) in v:
                    nxt.append(v[m.group(1)])
        elif m.group(2) is not None:
            i = int(m.group(2))
            for v in cur:
                if isinstance(v, list) and i < len(v):
                    nxt.append(v[i])
        elif m.group(3) is not None:
            key, op = m.group(3), m.group(4)
            want = m.group(5) if m.group(5) is not None else m.group(6) if m.group(6) is not None else _literal(m.group(7))
            for v in cur:
                for el in (v if isinstance(v, list) else []):
                    got = dig(el, key)
                    if jeq(got, want) == (op == "=="):
                        nxt.append(el)
        else:  # wildcard
            for v in cur:
                nxt.extend(v.values() if isinstance(v, dict) else v if isinstance(v, list) else [])
        cur = nxt
        pos = m.end()
    return cur


def jeq(a, b):
    """JSON equality: a boolean equals only a boolean (Python's `1 == True` does not hold in JSON)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(jeq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(jeq(x, y) for x, y in zip(a, b))
    if _num(a) and _num(b):
        return a == b
    return type(a) is type(b) and a == b


def dig(obj, dotted):
    """`a.b.0.c` into nested dicts/lists; None when absent."""
    for part in str(dotted).split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit() and int(part) < len(obj):
            obj = obj[int(part)]
        else:
            return None
    return obj


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Unbound(PathError):
    """An expected value names a {placeholder} the run never bound: the check cannot be decided."""


def bind_value(v, bindings):
    """Bind placeholders inside an expected value (strings, recursively); raise Unbound if any remain."""
    if isinstance(v, str):
        b = bind(v, bindings or {})
        if unbound(b):
            raise Unbound("unbound %s in an expected value" % ", ".join("{%s}" % u for u in unbound(b)))
        return b
    if isinstance(v, list):
        return [bind_value(x, bindings) for x in v]
    if isinstance(v, dict):
        return {k: bind_value(x, bindings) for k, x in v.items()}
    return v


def compare(doc, cmp_, bindings=None):
    """One `{path, op, value}` comparison over a JSON document: (holds, observed values). Raises Unbound
    when the expected value names an unbound placeholder."""
    op, want = cmp_.get("op", "eq"), bind_value(cmp_.get("value"), bindings)
    vals = jsonpath(doc, bind_value(cmp_["path"], bindings))
    if op == "exists":
        return bool(vals), vals[:3]
    if op == "absent":
        return not vals, vals[:3]
    if not vals:
        return False, []

    def one(v):
        if op == "eq":
            return jeq(v, want)
        if op == "ne":
            return not jeq(v, want)
        if op == "in":
            return isinstance(want, list) and any(jeq(v, w) for w in want)
        if op == "matches":
            return isinstance(v, str) and re.search(str(want), v) is not None
        if op in ("gt", "gte", "lt", "lte"):
            if not (_num(v) and _num(want)):
                return False
            return {"gt": v > want, "gte": v >= want, "lt": v < want, "lte": v <= want}[op]
        if op == "length":
            return isinstance(v, (list, str, dict)) and len(v) == want
        if op == "contains":
            if isinstance(v, str):
                return isinstance(want, str) and want in v
            if isinstance(v, list):
                return any(jeq(e, want) for e in v) or (isinstance(want, dict) and any(
                    isinstance(e, dict) and all(k in e and jeq(e[k], x) for k, x in want.items()) for e in v))
            return False
        raise PathError("unknown op %r" % op)

    held = all(one(v) for v in vals) if op == "ne" else any(one(v) for v in vals)
    return held, vals[:3]


# ── request matching ──────────────────────────────────────────────────────────────────────────

def bind(text, bindings):
    """Substitute every bound `{name}`; unbound placeholders stay."""
    return PLACEHOLDER.sub(lambda m: str(bindings[m.group(1)]) if m.group(1) in bindings else m.group(0), text)


def unbound(text):
    return PLACEHOLDER.findall(text or "")


def path_matcher(template):
    """(regex over the path, {query key: regex}, literal?) for a request template like
    `/api/v1/runs/{runId}/events?since={n}` — an unbound `{x}` matches one path segment."""
    path, _, query = template.partition("?")
    literal = not unbound(template)
    rx = "^" + "".join("[^/?#]+" if PLACEHOLDER.fullmatch(seg) else re.escape(seg)
                       for seg in re.split(r"(\{[A-Za-z_][\w-]*\})", path)) + "/?$"
    q = {}
    for part in filter(None, query.split("&")):
        k, _, val = part.partition("=")
        q[k] = re.compile("^" + "".join("[^&]*" if PLACEHOLDER.fullmatch(s) else re.escape(s)
                                        for s in re.split(r"(\{[A-Za-z_][\w-]*\})", val)) + "$")
    return re.compile(rx), q, literal


def _split_url(u):
    """`http://h:p/a/b?x=1` or `/a/b?x=1` -> ("/a/b", {"x": "1"})."""
    u = re.sub(r"^[a-z]+://[^/]+", "", u or "")
    p, _, q = u.partition("?")
    qs = {}
    for part in filter(None, q.split("&")):
        k, _, v = part.partition("=")
        qs[k] = v
    return p, qs


def request_matches(template, observed_url):
    rx, q, _ = path_matcher(template)
    p, qs = _split_url(observed_url)
    if not rx.match(p):
        return False
    return all(k in qs and r.match(qs[k]) for k, r in q.items())


# ── the observation store ─────────────────────────────────────────────────────────────────────

class Observations:
    """What one scenario run recorded. Every list is append-only and JSON-serialisable."""

    def __init__(self):
        self.http = []        # {method, url, status, req, res, source}
        self.events = []      # {source, type, data}
        self.streams = {}     # source -> {"complete": bool, "detail": str}
        self.cli = []         # {argv: [..], code, stdout, stderr}
        self.dom = {}         # check id -> {"ok": bool|None, "value": ..., "url": ...}
        self.dom_sampled = False
        self.file_roots = []  # directories the scenario left behind
        self.bindings = {}

    def add_http(self, method, url, status, req=None, res=None, source="tap"):
        self.http.append({"method": (method or "").upper(), "url": url, "status": status, "req": req,
                          "res": res, "source": source})

    def add_event(self, source, type_, data):
        self.events.append({"source": source, "type": type_, "data": data})

    def stream(self, source, complete, detail=""):
        prev = self.streams.get(source)
        self.streams[source] = {"complete": bool(complete) and (prev is None or prev["complete"]),
                                "detail": detail or (prev or {}).get("detail", "")}

    def events_from_http(self):
        """CoreEvents read back from `GET /runs/:id/events` answers (the daemon's durable view)."""
        seen = set()
        for h in self.http:
            p, _ = _split_url(h["url"])
            if h["method"] == "GET" and re.search(r"/api/v1/runs/[^/]+/events$", p) and isinstance(h["res"], (dict, list)):
                evs = h["res"].get("events") if isinstance(h["res"], dict) else h["res"]
                for e in evs if isinstance(evs, list) else []:
                    if not isinstance(e, dict):
                        continue
                    key = json.dumps(e, sort_keys=True, default=str)
                    if key in seen:
                        continue
                    seen.add(key)
                    self.add_event("core-event", event_type(e), e)
        if seen:
            # A run's event read is its whole durable log at that moment: complete for that run only,
            # so it is recorded as partial (other runs' events are not in it).
            self.stream("core-event", False, "read back from GET /runs/:id/events")

    def to_json(self):
        return {"http": self.http, "events": self.events, "streams": self.streams, "cli": self.cli,
                "dom": self.dom, "file_roots": self.file_roots}


def event_type(frame):
    """The event name of a /ws frame or a CoreEvent record (crew wraps core events in frames)."""
    if not isinstance(frame, dict):
        return None
    for k in ("type", "kind", "event", "name"):
        v = frame.get(k)
        if isinstance(v, str) and v not in ("coreEvent", "core-event", "event", "frame"):
            return v
    for k in ("event", "payload", "data", "coreEvent"):
        inner = frame.get(k)
        if isinstance(inner, dict):
            t = event_type(inner)
            if t:
                return t
    return None


# ── evaluation ────────────────────────────────────────────────────────────────────────────────

def _res(ok, value, how, wildcard=False):
    r = {"ok": ok, "value": value, "how": how}
    if wildcard and ok is True:
        # It held on SOMETHING the run recorded, but nothing ties that something to this path: a request
        # matched through an unbound {placeholder}, an event in a window other runs share, "the latest"
        # workflow run. Recorded as held; the verdict rule never counts it toward a pass.
        r["wildcard"] = True
    return r


def _status_ok(want, got):
    if want is None:
        return True
    return got in want if isinstance(want, list) else got == want


def _str_match(w, got):
    """(holds, loose) for a string pattern whose unbound {placeholders} match any non-empty text."""
    if not unbound(w):
        return isinstance(got, str) and got == w, False
    if PLACEHOLDER.fullmatch(w):
        return got is not None, True  # any value at all, tied to nothing
    return isinstance(got, str) and _token_rx(w).match(got) is not None, True


def _subset(want, got, bindings):
    """(holds, unbound?): every field the check's body names is in the recorded request body, equal."""
    if isinstance(want, str):
        return _str_match(bind(want, bindings), got)
    if isinstance(want, list):
        if not isinstance(got, list) or len(got) != len(want):
            return False, False
        loose = False
        for w, g in zip(want, got):
            ok, u = _subset(w, g, bindings)
            if not ok:
                return False, False
            loose = loose or u
        return True, loose
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return False, False
        loose = False
        for k, v in want.items():
            if k not in got:
                return False, False
            ok, u = _subset(v, got[k], bindings)
            if not ok:
                return False, False
            loose = loose or u
        return True, loose
    return jeq(want, got), False


def body_matches(ch, h, bindings):
    """(holds, wildcard) for the check's request `body` against the recorded request.
    `{request_body}` is the user path's own body, which the scenario (the user path) sent: it holds."""
    body = ch.get("body")
    if body is None or body == "{request_body}":
        return True, False
    return _subset(body, h.get("req"), bindings)


def _api_holds(ch, h, bindings=None):
    exp = ch.get("expect") or {}
    # An expectation the run cannot bind is undecidable, whatever else mismatches (raise before deciding).
    for cmp_ in exp.get("json", []) or []:
        bind_value(cmp_.get("value"), bindings)
        bind_value(cmp_.get("path"), bindings)
    if "error_code" in exp:
        bind_value(exp["error_code"], bindings)
    if not _status_ok(exp.get("status"), h["status"]):
        return False, {"status": h["status"]}
    seen = {"status": h["status"]}
    for cmp_ in exp.get("json", []) or []:
        try:
            ok, vals = compare(h["res"], cmp_, bindings)
        except Unbound:
            raise
        except PathError as e:
            return False, {"status": h["status"], "error": str(e)}
        seen[cmp_["path"]] = vals
        if not ok:
            return False, seen
    if "error_code" in exp:
        code = dig(h["res"], "error.code") or dig(h["res"], "code") or dig(h["res"], "error")
        seen["error_code"] = code
        if code != bind_value(exp["error_code"], bindings):
            return False, seen
    return True, seen


def eval_api(ch, obs, bindings, direct=None, direct_definitive=False):
    method = ch.get("method", "GET").upper()
    tmpl = bind(ch.get("path", ""), bindings)
    if method == "JSONRPC":
        cand = [h for h in obs.http if h["method"] == "JSONRPC" and h["url"] == tmpl]
    else:
        cand = [h for h in obs.http if h["method"] == method and request_matches(tmpl, h["url"])]
    loose_body = False
    if cand and ch.get("body") is not None:
        # The request must be the one the check names: its body too, not only its method and URL.
        kept = []
        for h in cand:
            ok, loose = body_matches(ch, h, bindings)
            if ok:
                kept.append(h)
                loose_body = loose_body or loose
        cand = kept
    literal = not unbound(tmpl) and not loose_body
    if cand:
        last = None
        for h in cand:
            ok, seen = _api_holds(ch, h, bindings)
            if ok:
                for name, p in (ch.get("capture") or {}).items():
                    vals = jsonpath(h["res"], p) if isinstance(h["res"], (dict, list)) else []
                    if vals:
                        bindings[name] = vals[0]
                return _res(True, dict(seen, request="%s %s" % (method, h["url"]), matched=len(cand)),
                            "direct" if h.get("source") == "direct" else
                            ("transcript (wildcard %s)" % ", ".join("{%s}" % u for u in unbound(tmpl)) if not literal
                             else "transcript"), wildcard=not literal)
            last = dict(seen, request="%s %s" % (method, h["url"]), matched=len(cand))
        # Recorded, but no answer satisfied the check. A scenario's request is not necessarily made in the
        # state the oracle describes (a poll before the run settled, a step that seeds a warning on
        # purpose, a wildcard that named another resource), so this is UNSATISFIED, not a contradiction:
        # it is never a pass, and only a read the runner itself makes of the end state is definitive.
        if literal and any(h.get("source") == "direct" for h in cand):
            # The runner's own read (live target). It is the end state only when the capability's path is
            # itself that read (verdict.read_only): then a mismatch is a contradiction. Otherwise the
            # runner read a daemon nobody drove down this path: unsatisfied, never a pass.
            return _res(False, last, "direct") if direct_definitive else _res(None, last, "direct: unsatisfied")
        return _res(None, last, "transcript: unsatisfied")
    if direct is not None and method == "GET" and literal:
        h = direct.get(tmpl)
        if h is not None:
            obs.add_http("GET", tmpl, h["status"], None, h.get("json"), source="direct")
            ok, seen = _api_holds(ch, {"status": h["status"], "res": h.get("json")}, bindings)
            if not ok and not direct_definitive:
                return _res(None, dict(seen, request="GET %s" % tmpl), "direct: unsatisfied")
            return _res(ok, dict(seen, request="GET %s" % tmpl), "direct")
    why = "unbound %s" % ", ".join("{%s}" % u for u in unbound(tmpl)) if not literal else "no matching request recorded"
    return _res(None, why, "not observed")


def _count_ok(count, n, complete):
    """(decision, text). decision None = not decidable on a partial stream."""
    if count is None:
        lo, hi = 1, None
    elif isinstance(count, int):
        lo, hi = count, count
    else:
        lo, hi = count.get("min", 0), count.get("max")
    if hi is not None and n > hi:
        # On a partial stream the extra events may belong to another run or turn in the same window.
        return (False, "%d > max %d" % (n, hi)) if complete else (None, "%d > max %d on a partial stream" % (n, hi))
    if n >= lo and (hi is None or complete):
        return True, "%d seen" % n
    if complete:
        return False, "%d seen, want %s" % (n, count if count is not None else ">= 1")
    return None, "%d seen on a partial stream" % n


STREAM_ALIASES = {"ws": ("ws", "core-event"), "core-event": ("core-event", "ws")}


def eval_event(ch, obs, bindings):
    src = ch.get("source", "core-event")
    sources = STREAM_ALIASES.get(src, (src,))
    recorded = [s for s in sources if s in obs.streams]
    if not recorded:
        return _res(None, "no %s stream recorded" % src, "not observed")
    complete = all(obs.streams[s]["complete"] for s in recorded)
    typ = bind(ch.get("type", ""), bindings)
    where = {k: (bind(v, bindings) if isinstance(v, str) else v) for k, v in (ch.get("where") or {}).items()}
    # An unbound {placeholder} in the type or a filter matches ANY resource: the stream may be complete, but
    # nothing ties a hit to this path's resource.
    loose = bool(unbound(typ)) or any(isinstance(v, str) and unbound(v) for v in where.values())
    hits = []
    for e in obs.events:
        if e["source"] not in sources:
            continue
        if src == "network":
            m, _, p = typ.partition(" ")
            em, _, ep = (e["type"] or "").partition(" ")
            if m.upper() != em.upper() or not request_matches(p, ep):
                continue
        elif not _str_match(typ, e["type"])[0]:
            continue
        if all(_str_match(v, dig(e["data"], k))[0] if isinstance(v, str) and unbound(v) else jeq(dig(e["data"], k), v)
               for k, v in where.items()):
            hits.append(e)
    ok, txt = _count_ok(ch.get("count"), len(hits), complete)
    if ok is False and loose:
        ok, txt = None, txt + " (matched through an unbound placeholder: not decided)"
    # "never sent to ANY resource" is also "never sent to this one": a loose zero-count hold stays tied.
    zero = isinstance(ch.get("count"), int) and ch.get("count") == 0
    return _res(ok, {"count": len(hits), "detail": txt, "stream": "complete" if complete else "partial"},
                "event stream" if complete else "event stream (partial window)",
                wildcard=not complete or (loose and not (zero and not hits)))


def eval_dom(ch, obs, check_id):
    s = obs.dom.get(check_id)
    if s is None:
        return _res(None, "not sampled" if not obs.dom_sampled else "never seen at a sample point", "not observed")
    return _res(True if s.get("ok") else None, s.get("value"), "dom sample")


def _cmd_tokens(cmd):
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


_NODE = re.compile(r"^node(\.exe)?$")
_PKG_BIN = re.compile(r"[\\/]node_modules[\\/]((?:@[^\\/]+[\\/])?[^\\/]+)[\\/]")


def program_argv(argv):
    """`node <...>/node_modules/wicked-crew/dist/cli/index.js serve` reads as `wicked-crew serve`."""
    argv = [str(a) for a in argv or []]
    if len(argv) >= 2 and _NODE.match(os.path.basename(argv[0])):
        m = _PKG_BIN.search(argv[1])
        if m:
            return [m.group(1).replace("\\", "/")] + argv[2:]
    return argv


_EXE = re.compile(r"\.(exe|cmd|bat)$", re.I)


def _token_rx(w):
    """A command token: literal, with each {placeholder} matching any non-empty run of characters."""
    return re.compile("^" + "".join(".+" if PLACEHOLDER.fullmatch(part) else re.escape(part)
                                    for part in re.split(r"(\{[A-Za-z_][\w-]*\})", w)) + "$", re.S)


def cli_matches(cmd, argv):
    want = _cmd_tokens(cmd)
    argv = program_argv(argv)
    if not want or not argv or len(want) != len(argv):
        return False
    if _EXE.sub("", os.path.basename(argv[0])) != _EXE.sub("", os.path.basename(want[0])):
        return False
    return all(_token_rx(w).match(str(a)) for w, a in zip(want[1:], argv[1:]))


def _exit_holds(ch, e):
    code = ch.get("code", 0)
    ok = (e["code"] not in (0, None)) if code == "nonzero" else e["code"] == code
    if ok and ch.get("stdout_matches"):
        ok = re.search(ch["stdout_matches"], e.get("stdout") or "") is not None
    if ok and ch.get("stderr_matches"):
        ok = re.search(ch["stderr_matches"], e.get("stderr") or "") is not None
    return ok


def _direct_exit(ch, e, direct_definitive, wildcard=False):
    val = {"code": e["code"], "argv": " ".join(map(str, e["argv"]))}
    if _exit_holds(ch, e):
        return _res(True, val, "direct", wildcard=wildcard)
    return _res(False, val, "direct") if direct_definitive else _res(None, val, "direct: unsatisfied")


def eval_exit(ch, obs, bindings, direct=None, direct_definitive=False):
    cmd = bind(ch.get("cmd", ""), bindings)
    cand = [e for e in obs.cli if cli_matches(cmd, e["argv"])]
    if cand:
        mine = [e for e in cand if e.get("source") == "direct"]
        if mine:  # the runner's own run (live target): decided like a direct GET
            return _direct_exit(ch, mine[-1], direct_definitive and not unbound(cmd), wildcard=bool(unbound(cmd)))
        for e in cand:
            if _exit_holds(ch, e):
                return _res(True, {"code": e["code"], "argv": " ".join(map(str, e["argv"]))}, "transcript",
                            wildcard=bool(unbound(cmd)))
        e = cand[-1]
        return _res(None, {"code": e["code"], "argv": " ".join(map(str, e["argv"]))}, "transcript: unsatisfied")
    if direct is not None and not unbound(cmd):
        e = direct.run_safe(cmd)
        if e is not None:
            obs.cli.append(dict(e, source="direct"))
            return _direct_exit(ch, e, direct_definitive)
    return _res(None, "no matching invocation recorded" if not unbound(cmd) else "unbound placeholder", "not observed")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def eval_file(ch, obs, bindings, examined):
    path = bind(ch.get("path", ""), bindings)
    if unbound(path):
        return _res(None, "unbound %s" % path, "not observed")
    roots = obs.file_roots
    if not roots:
        return _res(None, "the scenario left no file root", "not observed")
    found = None
    inside = False
    for r in roots:
        cand = path if os.path.isabs(path) else os.path.join(r, path)
        real_r = os.path.realpath(r)
        real = os.path.realpath(cand)
        try:
            if os.path.commonpath([real_r, real]) != real_r:
                continue  # never read outside the scenario's roots
        except ValueError:  # another drive (Windows)
            continue
        inside = True
        if os.path.exists(cand):
            found = cand
            break
    if not inside:
        return _res(None, {"path": path, "outside": "every root the scenario left"}, "not observed")
    a = ch.get("assert", "exists")
    if a == "absent":
        if found is not None and os.path.isfile(found):
            examined.append(found)
        return _res(found is None, {"path": path, "present": found is not None}, "file roots")
    if found is None:
        # Absent from every root the scenario left: the file may live in a root this run cannot see.
        return _res(None, {"path": path, "present": False}, "file roots (not found)")
    if os.path.isfile(found):
        examined.append(found)
    if a == "exists":
        return _res(True, {"path": path}, "file roots")
    if a == "non-empty":
        return _res(os.path.getsize(found) > 0, {"path": path, "bytes": os.path.getsize(found)}, "file roots")
    if a in ("sha256", "matches"):
        try:
            want = bind_value(str(ch.get("value")), bindings)
        except Unbound as e:
            return _res(None, {"path": path, "unbound": str(e)}, "not observed")
        if a == "sha256":
            got = sha256_file(found)
            return _res(got == want, {"path": path, "sha256": got}, "file roots")
        with open(found, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        return _res(re.search(want, txt) is not None, {"path": path}, "file roots")
    if a == "json-path":
        try:
            jp = bind_value(ch.get("json_path"), bindings)
            want = bind_value(ch.get("value"), bindings)
        except Unbound as e:
            return _res(None, {"path": path, "unbound": str(e)}, "not observed")
        with open(found, encoding="utf-8") as fh:
            doc = json.load(fh)
        vals = jsonpath(doc, jp)
        return _res(any(jeq(v, want) for v in vals), {"path": path, "values": vals[:3]}, "file roots")
    return _res(None, "unknown assert %r" % a, "not observed")


def eval_npm(ch, bindings, direct):
    pkg = bind(ch.get("pkg", ""), bindings)
    ver = bind(str(ch.get("version", "")), bindings) if ch.get("version") is not None else None
    tag = bind(str(ch.get("dist_tag", "")), bindings) if ch.get("dist_tag") else None
    if unbound(pkg) or (ver and unbound(ver)) or (tag and unbound(tag)):
        return _res(None, "unbound placeholder", "not observed")
    if direct is None:
        return _res(None, "no registry access on this path", "not observed")
    info = direct.npm_view(pkg)
    if info is None:
        return _res(None, "npm view failed", "not observed")
    versions = info.get("versions") or []
    tags = info.get("dist-tags") or {}
    ok = True
    if ver:
        ok = ver in versions
    if tag:
        ok = ok and (tags.get(tag) == ver if ver else tag in tags)
    return _res(ok, {"pkg": pkg, "latest": tags.get("latest"), "has_version": ver in versions if ver else None,
                     "tag": {tag: tags.get(tag)} if tag else None}, "direct")


def eval_gh(ch, bindings, direct):
    if direct is None:
        return _res(None, "no GitHub access on this path", "not observed")
    repo = bind(ch.get("repo", ""), bindings)
    if unbound(repo):
        return _res(None, "unbound repo", "not observed")
    doc = direct.gh(ch.get("target"), repo, ch, bindings)
    if doc is None:
        return _res(None, "gh read failed or the object is not addressable", "not observed")
    try:
        ok, vals = compare(doc, ch["assert"], bindings)
    except PathError as e:
        return _res(None, str(e), "not observed")
    # `target: run` reads the repo's LATEST workflow run, not one this path named.
    return _res(ok, {"repo": repo, ch["assert"]["path"]: vals}, "direct", wildcard=ch.get("target") == "run")


def evaluate(ch, obs, bindings, check_id, direct=None, examined=None, direct_definitive=False):
    """One typed check -> {value, ok, how}. `direct` is a read-only client (or None). `direct_definitive`:
    the capability's path is itself a read (verdict.read_only), so the runner's own read of it decides."""
    k = ch.get("kind")
    examined = examined if examined is not None else []
    try:
        if k == "all":
            subs = [evaluate(c, obs, bindings, "%s.%d" % (check_id, i), direct, examined, direct_definitive)
                    for i, c in enumerate(ch.get("of", []))]
            oks = [s["ok"] for s in subs]
            ok = False if False in oks else (True if subs and all(o is True for o in oks) else None)
            return _res(ok, [s["value"] for s in subs], "all", wildcard=any(s.get("wildcard") for s in subs))
        if k == "api":
            return eval_api(ch, obs, bindings, direct, direct_definitive)
        if k == "event":
            return eval_event(ch, obs, bindings)
        if k == "dom":
            return eval_dom(ch, obs, check_id)
        if k == "exit":
            return eval_exit(ch, obs, bindings, direct, direct_definitive)
        if k == "file":
            return eval_file(ch, obs, bindings, examined)
        if k == "npm":
            return eval_npm(ch, bindings, direct)
        if k == "gh":
            return eval_gh(ch, bindings, direct)
    except Unbound as e:
        return _res(None, str(e), "not observed")
    except (PathError, ValueError, OSError, KeyError, TypeError) as e:
        return _res(None, "evaluation error: %s" % e, "not observed")
    return _res(None, "unknown check kind %r" % k, "not observed")
