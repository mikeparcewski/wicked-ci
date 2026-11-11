#!/usr/bin/env python3
"""The self-test's studio journey driver: run ONE journey against the ephemeral daemon's own studio, in a real browser.

usage: python -I driver.py <journey> --origin http://127.0.0.1:<port> --out <dir> [--state <json>]

A journey is `journeys/<journey>.py` defining `run(j)`. The driver hands it `j`, which carries:
  j.page, j.ctx            the Playwright page and context (1440x700, Wicked Light)
  j.origin, j.state        the daemon origin; what earlier steps produced (repo id, run ids), from --state
  j.get(path)              GET <origin>/api/v1<path> (JSON); the driver itself sends nothing else
  j.check(name, ok, **d)   one typed result; the journey passes only when every check passed
  j.shots(label)           the terminal-state evidence: 1440x700 and 390x844 in Wicked Light and Wicked Dark
  j.shot(label)            one screenshot at the current viewport
  j.wait(cond, s, what)    poll cond() up to s seconds; records what it waited for and how long
  j.log(...)
It writes <out>/result.json: {ok, checks, page_errors, console_errors, bad_responses, writes, blocked, shots, waits,
error}. Exit 0 only when the journey ran and every check passed.

Boundary: the browser reaches the daemon's origin only. Every HTTP request and every WebSocket to any other origin is
aborted and recorded (`blocked`), so a journey can't depend on the network and nothing leaves the hermetic root. A
redirect hop the browser follows is seen as a new request; one that reached another origin is recorded (`escaped`),
and the driver adds the check `stayed_on_origin` to every journey. The driver's own GETs refuse redirects. Every non-GET the UI sends
to the daemon is recorded (`writes`): a journey proves what the PERSON's clicks sent, never what a script sent.
"""
import importlib.util
import json
import os
import sys

sys.dont_write_bytecode = True  # importing a journey writes no __pycache__ into the harness checkout
import time
import traceback
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

VIEWPORTS = ((1440, 700), (390, 844))
THEMES = ("wicked-light", "wicked-dark")


def main(argv):
    journey = argv[0]
    opt = {argv[i]: argv[i + 1] for i in range(1, len(argv) - 1, 2)}
    origin = opt["--origin"].rstrip("/")
    out = opt["--out"]
    state = json.loads(opt.get("--state", "{}"))
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, f"{journey}.py")
    if not os.path.isfile(path):
        print(f"driver: no journey {journey}", file=sys.stderr)
        return 2
    os.makedirs(out, exist_ok=True)
    rec = {"journey": journey, "ok": False, "checks": {}, "page_errors": [], "console_errors": [], "bad_responses": [],
           "writes": [], "blocked": [], "escaped": [], "shots": [], "waits": [], "error": None,
           "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def rel(url):
        return url[len(origin):].split("?")[0] if url.startswith(origin) else url[:160]

    class J:
        pass

    j = J()
    j.origin, j.state, j.out, j.rec = origin, state, out, rec
    n = [0]

    def log(*a):
        print(time.strftime("%H:%M:%S"), journey, *a, flush=True)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl} refused (origin boundary)", headers, fp)

    opener = urllib.request.build_opener(NoRedirect)

    def get(p):
        last = None
        for _ in range(4):
            try:
                with opener.open(origin + "/api/v1" + p, timeout=30) as r:
                    return json.loads(r.read() or b"{}")
            except Exception as e:  # a busy daemon: retry briefly
                last = e
                time.sleep(3)
        raise last

    def check(name, ok, **detail):
        rec["checks"][name] = {"ok": bool(ok), **detail}
        log("CHECK", name, "PASS" if ok else "FAIL", json.dumps(detail, default=str)[:600])
        return bool(ok)

    def shot(label, full=False):
        n[0] += 1
        p = os.path.join(out, f"{n[0]:02d}-{label}.png")
        j.page.wait_for_timeout(300)
        j.page.screenshot(path=p, full_page=full)
        rec["shots"].append(os.path.basename(p))
        return p

    def set_theme(t):
        j.page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", t)
        j.page.wait_for_timeout(400)

    def shots(label):
        vs = j.page.viewport_size
        orig = j.page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        for (w, h) in VIEWPORTS:
            j.page.set_viewport_size({"width": w, "height": h})
            j.page.wait_for_timeout(700)
            for t in THEMES:
                set_theme(t)
                shot(f"{label}-{w}x{h}-{t.split('-')[1]}")
        j.page.set_viewport_size(vs)
        if orig:
            set_theme(orig)

    def wait(cond, seconds, what):
        t0 = time.time()
        last = None
        while time.time() - t0 < seconds:
            try:
                last = cond()
                if last:
                    rec["waits"].append({"what": what, "s": round(time.time() - t0, 1), "ok": True})
                    return last
            except Exception as e:  # the page is still settling
                last = repr(e)[:200]
            j.page.wait_for_timeout(1000)
        rec["waits"].append({"what": what, "s": round(time.time() - t0, 1), "ok": False, "last": str(last)[:200]})
        return None

    j.get, j.check, j.shot, j.shots, j.wait, j.log, j.set_theme = get, check, shot, shots, wait, log, set_theme

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 700}, color_scheme="light")

        def boundary(route):
            url = route.request.url
            if url.startswith(origin + "/") or url == origin or url.startswith(origin.replace("http", "ws", 1)):
                route.continue_()
            elif url.startswith(("data:", "blob:")):
                route.continue_()
            else:
                rec["blocked"].append(f"{route.request.method} {url[:160]}")
                route.abort()
        ctx.route("**/*", boundary)
        ws_origin = origin.replace("http", "ws", 1)

        def ws_boundary(ws):
            if ws.url.startswith(ws_origin + "/") or ws.url == ws_origin:
                ws.connect_to_server()
            else:
                rec["blocked"].append(f"WS {ws.url[:160]}")
                ws.close()
        ctx.route_web_socket("**/*", ws_boundary)

        def seen(req):
            u = req.url
            if not (u.startswith(origin + "/") or u == origin or u.startswith(("data:", "blob:"))) and req.redirected_from is not None:
                rec["escaped"].append(f"{req.method} {u[:160]} (redirected from {req.redirected_from.url[:120]})")
        ctx.on("request", seen)
        page = ctx.new_page()

        def watch(pg):
            pg.on("pageerror", lambda e: rec["page_errors"].append(str(e)[:400]))
            pg.on("console", lambda m: rec["console_errors"].append(m.text[:300]) if m.type == "error" else None)

            def resp(r):
                m = r.request.method
                if r.status >= 400:
                    rec["bad_responses"].append(f"{r.status} {m} {rel(r.url)}")
                if m not in ("GET", "HEAD", "OPTIONS") and r.url.startswith(origin):
                    rec["writes"].append(f"{r.status} {m} {rel(r.url)}")
            pg.on("response", resp)
        watch(page)
        ctx.on("page", watch)
        j.page, j.ctx = page, ctx
        try:
            spec = importlib.util.spec_from_file_location(journey, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run(j)
        except Exception as e:
            rec["error"] = repr(e)[:1500]
            log("ERROR", traceback.format_exc()[-1500:])
            try:
                shot("error")
            except Exception:
                pass
        check("stayed_on_origin", not rec["escaped"], escaped=rec["escaped"][:10])
        ctx.close()
        browser.close()

    rec["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rec["ok"] = rec["error"] is None and len(rec["checks"]) > 0 and all(c["ok"] for c in rec["checks"].values())
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(rec, f, indent=1, default=str)
    print("RESULT", json.dumps({"ok": rec["ok"], "error": rec["error"], "checks": {k: v["ok"] for k, v in rec["checks"].items()}}), flush=True)
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
