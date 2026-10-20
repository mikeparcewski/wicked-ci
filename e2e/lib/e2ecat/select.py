"""The selection language a profile (and phase 2's runner) uses to pick capabilities.

    EXPR   := TERM ( WS TERM )*
    TERM   := [!] ( area:NAME | tag:NAME | id:GLOB | surface=NAME | cost<=S|M|L | oracle=KIND )
              NAME and GLOB may list alternatives with commas: area:crew-api,foundation

Terms with the same key are OR'd; different keys are AND'd; a `!` term excludes whatever it matches.
An empty expression (or `*`) selects everything. Matching is deterministic and case-sensitive;
`id:` globs use fnmatch (`*`, `?`, `[...]`) against the id AND its aliases.
"""
import fnmatch
import re

COST_ORDER = {"S": 0, "M": 1, "L": 2}
TERM = re.compile(r"^(!?)(area:|tag:|id:|surface=|cost<=|oracle=)(.+)$")


class SelectError(Exception):
    pass


def parse(expr):
    """Return [(negated, key, [values])]."""
    expr = (expr or "").strip()
    if expr in ("", "*"):
        return []
    terms = []
    for tok in expr.split():
        m = TERM.match(tok)
        if not m:
            raise SelectError("unknown selection term %r (use area:, tag:, id:, surface=, cost<=, oracle=)" % tok)
        neg, key, val = m.group(1) == "!", m.group(2).rstrip(":=<"), m.group(3)
        vals = [v for v in val.split(",") if v]
        if not vals:
            raise SelectError("empty value in %r" % tok)
        if key == "cost":
            if len(vals) != 1 or vals[0] not in COST_ORDER:
                raise SelectError("cost<= takes one of S, M, L (got %r)" % val)
        terms.append((neg, key, vals))
    return terms


def _oracle_kind(cap):
    return cap["oracle"]["kind"]


def _match(cap, key, vals):
    if key == "area":
        return cap["_area"] in vals
    if key == "tag":
        return bool(set(cap["tags"]) & set(vals))
    if key == "id":
        names = [cap["id"]] + cap.get("aliases", [])
        return any(fnmatch.fnmatchcase(n, g) for n in names for g in vals)
    if key == "surface":
        return cap["surface"] in vals
    if key == "cost":
        return any(COST_ORDER[cap["cost"]] <= COST_ORDER[v] for v in vals)
    if key == "oracle":
        return _oracle_kind(cap) in vals
    raise SelectError(key)


def select(caps, expr):
    """Filter capabilities (each carrying `_area`) by a selection expression; order is preserved."""
    terms = parse(expr)
    pos, neg = {}, []
    for n, k, v in terms:
        if n:
            neg.append((k, v))
        else:
            pos.setdefault(k, []).extend(v)
    out = []
    for c in caps:
        if all(_match(c, k, v) for k, v in pos.items()) and not any(_match(c, k, v) for k, v in neg):
            out.append(c)
    return out
