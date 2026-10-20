#!/usr/bin/env python3
"""A stand-in for the wicked-vault CLI in unit tests (CI runners do not install it).

It implements the subset the e2e runner calls (`init`, `record --artifact`, `verify`, `--version`)
and writes the same on-disk layout the real vault does: `.wicked-vault/entries/<id>.json` naming
`claim_id`, `scope`, `payload_sha256`, `payload_ref`, and the frozen copy under `payloads/<sha256>`.
`e2e/tests/test_runner.py` also runs against the real CLI when it is on PATH.
"""
import hashlib
import json
import os
import sys
import uuid


def arg(args, name):
    return args[args.index(name) + 1] if name in args else None


def main(argv):
    if argv[:1] in (["--version"], ["-v"]):
        print("0.0.0-stub")
        return 0
    cmd, args = argv[0], argv[1:]
    root = os.path.join(arg(args, "--cwd") or os.getcwd(), ".wicked-vault")
    if cmd == "init":
        os.makedirs(os.path.join(root, "entries"), exist_ok=True)
        os.makedirs(os.path.join(root, "payloads"), exist_ok=True)
        print(json.dumps({"initialized": root}))
        return 0
    if cmd == "record":
        src = os.path.join(os.path.dirname(root), arg(args, "--artifact"))
        with open(src, "rb") as fh:
            raw = fh.read()
        sha = hashlib.sha256(raw).hexdigest()
        with open(os.path.join(root, "payloads", sha), "wb") as fh:
            fh.write(raw)
        aid = uuid.uuid4().hex[:28].upper()
        entry = {"id": aid, "scope": arg(args, "--scope"), "phase": arg(args, "--phase"), "claim_id": arg(args, "--claim"),
                 "kind": arg(args, "--kind"), "payload_sha256": sha, "payload_ref": "payloads/" + sha,
                 "acceptance_criteria": arg(args, "--criteria"), "created_by": arg(args, "--actor")}
        with open(os.path.join(root, "entries", aid + ".json"), "w", encoding="utf-8") as fh:
            json.dump(entry, fh)
        print(json.dumps({"id": aid, "payload_sha256": sha}))
        return 0
    if cmd == "verify":
        aid = args[0]
        with open(os.path.join(root, "entries", aid + ".json"), encoding="utf-8") as fh:
            entry = json.load(fh)
        with open(os.path.join(root, entry["payload_ref"]), "rb") as fh:
            ok = hashlib.sha256(fh.read()).hexdigest() == entry["payload_sha256"]
        print(json.dumps({"id": aid, "hash_ok": ok, "status": "pass" if ok else "fail"}))
        return 0 if ok else 1
    print(json.dumps({"error": "unsupported %s" % cmd}))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
