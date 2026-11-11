#!/usr/bin/env python3
"""e2e-1105 fixture: a minimal stdio MCP server (JSON-RPC 2.0, newline-delimited). Tools:
  echo      (read-only): returns its text argument reversed and upper-cased.
  note_add  (write):     appends a note line to a file under this fixture dir (the only side effect).
"""
import json, os, sys, time
NOTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "echo-mcp-notes.txt")
TOOLS = [
    {"name": "echo", "description": "Echo text back reversed and upper-cased.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
     "annotations": {"readOnlyHint": True, "title": "Echo"}},
    {"name": "note_add", "description": "Append a note line to the fixture's notes file.",
     "inputSchema": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "title": "Add a note"}},
]
def reply(i, result=None, error=None):
    m = {"jsonrpc": "2.0", "id": i}
    m["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(m) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    mid, meth, p = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        continue
    if meth == "initialize":
        reply(mid, {"protocolVersion": p.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                    "serverInfo": {"name": "echo-mcp", "version": "0.1.0"}})
    elif meth == "tools/list":
        reply(mid, {"tools": TOOLS})
    elif meth == "tools/call":
        n, a = p.get("name"), p.get("arguments") or {}
        if n == "echo":
            reply(mid, {"content": [{"type": "text", "text": str(a.get("text", ""))[::-1].upper()}]})
        elif n == "note_add":
            with open(NOTES, "a") as f:
                f.write(time.strftime("%H:%M:%S ") + str(a.get("note", "")) + "\n")
            reply(mid, {"content": [{"type": "text", "text": "noted"}]})
        else:
            reply(mid, error={"code": -32602, "message": "unknown tool"})
    elif meth == "ping":
        reply(mid, {})
    else:
        reply(mid, error={"code": -32601, "message": "method not found"})
