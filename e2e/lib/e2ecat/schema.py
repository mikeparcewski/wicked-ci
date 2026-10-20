"""A small JSON Schema (draft 2020-12) validator for the keyword subset SCHEMA.json uses.

Stdlib only, so `e2e validate` runs anywhere python3 does. A schema that uses a keyword outside
the subset is REFUSED (SchemaError), never silently ignored: the catalog cannot pass a check the
validator does not implement.
"""
import re

ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "examples", "default", "$defs"}
SUPPORTED = ANNOTATIONS | {
    "type", "properties", "required", "additionalProperties", "items", "minItems", "uniqueItems",
    "enum", "const", "pattern", "minLength", "minimum", "maximum", "oneOf", "anyOf", "$ref",
}
TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaError(Exception):
    """The schema itself uses something this validator does not implement."""


def check_schema(schema, path="#"):
    """Refuse unsupported keywords anywhere in the schema tree."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaError("%s: a schema must be an object or boolean" % path)
    for k, v in schema.items():
        if k not in SUPPORTED:
            raise SchemaError("%s: unsupported keyword %r" % (path, k))
        if k in ("properties", "$defs"):
            for name, sub in v.items():
                check_schema(sub, "%s/%s/%s" % (path, k, name))
        elif k in ("items", "additionalProperties") and not isinstance(v, bool):
            check_schema(v, "%s/%s" % (path, k))
        elif k in ("oneOf", "anyOf"):
            for i, sub in enumerate(v):
                check_schema(sub, "%s/%s/%d" % (path, k, i))
        elif k == "$ref" and not v.startswith("#/"):
            raise SchemaError("%s: only local $ref (#/...) is supported, got %r" % (path, v))


def _resolve(root, ref):
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _kind_const(branch, root):
    if "$ref" in branch:
        branch = _resolve(root, branch["$ref"])
    if not isinstance(branch, dict):
        return None
    k = branch.get("properties", {}).get("kind", {})
    return k.get("const") if isinstance(k, dict) else None


def validate(instance, schema, root=None, path="$"):
    """Return a list of error strings (empty = valid)."""
    root = schema if root is None else root
    if schema is True:
        return []
    if schema is False:
        return ["%s: not allowed" % path]
    errs = []
    if "$ref" in schema:
        errs += validate(instance, _resolve(root, schema["$ref"]), root, path)
    t = schema.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(TYPES[x](instance) for x in ts):
            return errs + ["%s: expected %s, got %s" % (path, "/".join(ts), type(instance).__name__)]
    if "const" in schema and instance != schema["const"]:
        errs.append("%s: expected %r" % (path, schema["const"]))
    if "enum" in schema and instance not in schema["enum"]:
        errs.append("%s: %r is not one of %s" % (path, instance, schema["enum"]))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errs.append("%s: shorter than %d" % (path, schema["minLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errs.append("%s: %r does not match %s" % (path, instance, schema["pattern"]))
    if TYPES["number"](instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errs.append("%s: below minimum %s" % (path, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errs.append("%s: above maximum %s" % (path, schema["maximum"]))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errs.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if schema.get("uniqueItems"):
            seen = []
            for i, v in enumerate(instance):
                if v in seen:
                    errs.append("%s[%d]: duplicate item %r" % (path, i, v))
                seen.append(v)
        if "items" in schema:
            for i, v in enumerate(instance):
                errs += validate(v, schema["items"], root, "%s[%d]" % (path, i))
    if isinstance(instance, dict):
        for r in schema.get("required", []):
            if r not in instance:
                errs.append("%s: missing required %r" % (path, r))
        props = schema.get("properties", {})
        for k, v in instance.items():
            if k in props:
                errs += validate(v, props[k], root, "%s.%s" % (path, k))
            elif "additionalProperties" in schema:
                ap = schema["additionalProperties"]
                if ap is False:
                    errs.append("%s: unexpected property %r" % (path, k))
                elif isinstance(ap, dict):
                    errs += validate(v, ap, root, "%s.%s" % (path, k))
    if "anyOf" in schema:
        if not any(not validate(instance, s, root, path) for s in schema["anyOf"]):
            errs.append("%s: matches none of anyOf" % path)
    if "oneOf" in schema:
        branches = schema["oneOf"]
        kinds = [_kind_const(b, root) for b in branches]
        if isinstance(instance, dict) and all(k is not None for k in kinds):
            # A discriminated union on `kind`: report the chosen branch's errors, not "none matched".
            if instance.get("kind") not in kinds:
                errs.append("%s.kind: %r is not one of %s" % (path, instance.get("kind"), kinds))
            else:
                errs += validate(instance, branches[kinds.index(instance["kind"])], root, path)
        else:
            ok = [i for i, s in enumerate(branches) if not validate(instance, s, root, path)]
            if len(ok) != 1:
                errs.append("%s: must match exactly one of oneOf (matched %d)" % (path, len(ok)))
    return errs
