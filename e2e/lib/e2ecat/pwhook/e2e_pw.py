"""Playwright evidence hook for existing journeys (imported by this directory's sitecustomize.py).

A studio journey is a standalone Python Playwright script. With this directory on PYTHONPATH and
`E2E_PW_DIR` set, every browser context the journey opens records, without a line of the journey
changing:

- a video (`record_video_dir`) and a Playwright trace (screenshots + DOM snapshots) per context;
- a HAR of every `/api/` exchange (request bodies and JSON answers): the UI's API transcript;
- a copy of every screenshot the journey takes, plus a final screenshot of every open page;
- the fixture server's own request log, when the journey serves the in-process fixture
  (`http.server` handlers in this process): method, path and status of every request it answered;
- DOM samples for the oracle checks in `E2E_DOM_CHECKS` (a JSON list of {id, selector, assert,
  value, attr}), taken after navigations, clicks and waits, before screenshots and at close.

A sample only ever records that a check HELD at a moment (`hidden` must hold at a page's final
sample); a check never seen to hold is reported as not observed, never as failed. The journey's
own assertions decide pass or fail.

Every hook body is wrapped: a hook error never changes what the journey does. Output lands under
`$E2E_PW_DIR/<journey>/` (the journey is named from argv[0]).
"""
import atexit
import itertools
import json
import os
import re
import shutil
import sys
import threading
import time

OUT = os.environ.get("E2E_PW_DIR")
JOURNEY = re.sub(r"(_test)?\.py$", "", os.path.basename(sys.argv[0] or "journey")) or "journey"
BASE = os.path.join(OUT, JOURNEY) if OUT and JOURNEY != "run_journeys" else None
# E2E_PW_OFF=har,trace,video turns an instrument off (to bisect a journey the hook perturbs).
OFF = set(filter(None, os.environ.get("E2E_PW_OFF", "").split(",")))

SAMPLE_JS = """(checks) => checks.map((c) => {
  try {
    const els = [...document.querySelectorAll(c.selector)];
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
    const first = els[0] || null;
    return { id: c.id, count: els.length, visible: els.some(vis),
             text: first ? (first.innerText || first.textContent || '').trim().slice(0, 500) : null,
             attr: first && c.attr ? first.getAttribute(c.attr) : null };
  } catch (e) { return { id: c.id, error: String(e) }; }
})"""

_lock = threading.Lock()
_ctx_n = itertools.count(1)
_shot_n = itertools.count(1)
_state = {"contexts": [], "videos": [], "traces": [], "hars": [], "shots": [], "sampled": 0, "errors": [],
          "seen": {}, "final": {}, "last_sample": 0.0, "last_label": None}
_checks = []
_in_sample = threading.local()


def _err(where, e):
    if len(_state["errors"]) < 50:
        _state["errors"].append("%s: %s" % (where, e))


def _load_checks():
    p = os.environ.get("E2E_DOM_CHECKS")
    if not p or not os.path.isfile(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            return [c for c in json.load(fh) if isinstance(c, dict) and c.get("selector")]
    except (OSError, ValueError) as e:
        _err("checks", e)
        return []


def _holds(c, r):
    if r.get("error"):
        return None
    a = c.get("assert", "visible")
    if a == "visible":
        return bool(r["visible"]), r["visible"]
    if a == "hidden":
        return not r["visible"], {"count": r["count"], "visible": r["visible"]}
    if a == "count":
        return r["count"] == c.get("value"), r["count"]
    if a == "text-equals":
        return r["text"] == c.get("value"), r["text"]
    if a == "text-matches":
        try:
            return r["text"] is not None and re.search(str(c.get("value")), r["text"]) is not None, r["text"]
        except re.error:
            return None
    if a == "attr":
        return r["attr"] == c.get("value"), r["attr"]
    return None


def negative(c):
    """A check that says something is NOT there: it can only hold at the end, never by a moment."""
    return c.get("assert") == "hidden" or (c.get("assert") == "count" and c.get("value") == 0)


def sample(page, label, final=False, force=False):
    """Evaluate every DOM check on `page` now; record what held. Only a repeat of the SAME action within
    250 ms is skipped (a wait loop); a different action right after a navigation is always sampled."""
    if not _checks or getattr(_in_sample, "on", False):
        return
    now = time.monotonic()
    if not (final or force) and label == _state["last_label"] and now - _state["last_sample"] < 0.25:
        return
    _state["last_label"] = label
    _in_sample.on = True
    try:
        if page.is_closed():
            if final:
                _final_failed("the page closed before its final sample")
            return
        res = page.evaluate(SAMPLE_JS, _checks)
        _state["last_sample"] = time.monotonic()
        _state["sampled"] += 1
        url = page.url
        for c, r in zip(_checks, res):
            h = _holds(c, r)
            if h is None:
                if final and negative(c):
                    _state["final"][c["id"]] = {"held": False, "value": r.get("error"), "url": url}
                continue
            held, value = h
            if final:
                # A negative check must hold at the final sample of EVERY page the journey ends: one page
                # still showing the element is enough to say it did not.
                prev = _state["final"].get(c["id"])
                _state["final"][c["id"]] = {"held": held and (prev is None or prev["held"]), "value": value, "url": url}
            if held and not negative(c) and c["id"] not in _state["seen"]:
                _state["seen"][c["id"]] = {"ok": True, "value": value, "url": url, "at": label}
    except Exception as e:  # navigation in flight, page closing: a missed sample, never a failure
        _err("sample(%s)" % label, e)
        if final:
            _final_failed("final sample failed: %s" % e)
    finally:
        _in_sample.on = False


def _final_failed(why):
    """A page whose final state could not be read: no negative check may claim the end state held."""
    for c in _checks:
        if negative(c):
            _state["final"][c["id"]] = {"held": False, "value": why, "url": None}


def _dump():
    if not BASE:
        return
    _dump_fixture_log()
    dom = dict(_state["seen"])
    for c in _checks:
        f = _state["final"].get(c["id"])
        if negative(c) and f and f["held"]:
            dom[c["id"]] = {"ok": True, "value": f["value"], "url": f["url"], "at": "final"}
    doc = {"journey": JOURNEY, "contexts": len(_state["contexts"]), "videos": _state["videos"],
           "traces": _state["traces"], "hars": _state["hars"], "shots": _state["shots"],
           "sampled": _state["sampled"], "checks": len(_checks), "dom": dom, "errors": _state["errors"]}
    try:
        with open(os.path.join(BASE, "hook.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
    except OSError:
        pass


def _shot_path(tag):
    return os.path.join(BASE, "shots", "%03d-%s.png" % (next(_shot_n), re.sub(r"[^\w.-]+", "_", tag)[:60]))


def _final_page(page, rec, i):
    """The final sample, screenshot and video path of one page (once)."""
    if getattr(page, "_e2e_final", False):
        return
    page._e2e_final = True
    try:
        sample(page, "final", final=True)
        _state["tag"] = "final-ctx%d-page%d" % (rec["n"], i)
        page.screenshot()  # the patched screenshot keeps the copy under shots/
        _state["tag"] = None
    except Exception as e:
        _err("final screenshot", e)
    try:
        if page.video:
            rec["videos"].append(page.video.path())
    except Exception as e:
        _err("video path", e)


def _finalize(ctx):
    rec = getattr(ctx, "_e2e_rec", None)
    if rec is None or rec["done"]:
        return
    rec["done"] = True
    for i, page in enumerate(list(ctx.pages)):
        _final_page(page, rec, i)
    if rec["tracing"]:
        try:
            p = os.path.join(BASE, "trace", "ctx-%d.zip" % rec["n"])
            ctx.tracing.stop(path=p)
            _state["traces"].append(os.path.relpath(p, BASE))
        except Exception as e:
            _err("tracing.stop", e)


def _collect_videos(rec):
    for v in rec["videos"]:
        try:
            src = str(v)
            if not os.path.isfile(src):
                continue
            vd = os.path.join(BASE, "video")
            if os.path.commonpath([os.path.realpath(vd), os.path.realpath(src)]) != os.path.realpath(vd):
                dst = os.path.join(vd, "ctx-%d-%s" % (rec["n"], os.path.basename(src)))
                shutil.copyfile(src, dst)
                src = dst
            rp = os.path.relpath(src, BASE)
            if rp not in _state["videos"]:
                _state["videos"].append(rp)
        except Exception as e:
            _err("video copy", e)
    if rec.get("har") and os.path.isfile(rec["har"]):
        _state["hars"].append(os.path.relpath(rec["har"], BASE))


def install():
    global _checks
    if not BASE:
        return
    for d in ("video", "trace", "shots", "har"):
        os.makedirs(os.path.join(BASE, d), exist_ok=True)
    _checks = _load_checks()
    if "fixturelog" not in OFF:
        _install_fixture_log()
    try:
        from playwright.sync_api._generated import Browser, BrowserContext, Locator, Page
        from playwright.sync_api._context_manager import PlaywrightContextManager
    except Exception as e:  # not a Playwright process
        _err("import", e)
        atexit.register(_dump)
        return

    orig_new_context = Browser.new_context
    orig_new_page = Browser.new_page
    orig_ctx_close = BrowserContext.close
    orig_browser_close = Browser.close
    orig_page_close = Page.close
    orig_exit = PlaywrightContextManager.__exit__

    def new_context(self, *a, **kw):
        n = next(_ctx_n)
        try:
            if "video" not in OFF:
                kw.setdefault("record_video_dir", os.path.join(BASE, "video"))
            vp = kw.get("viewport")
            if isinstance(vp, dict) and "record_video_size" not in kw:
                kw["record_video_size"] = {"width": vp["width"], "height": vp["height"]}
            har = None
            if "record_har_path" not in kw and "har" not in OFF:
                har = os.path.join(BASE, "har", "ctx-%d.har" % n)
                kw["record_har_path"] = har
                kw.setdefault("record_har_url_filter", "**/api/**")
        except Exception as e:
            _err("new_context kw", e)
        ctx = orig_new_context(self, *a, **kw)
        rec = {"n": n, "done": False, "tracing": False, "videos": [], "har": har}
        try:
            if "trace" not in OFF:
                ctx.tracing.start(screenshots=True, snapshots=True, title=JOURNEY)
                rec["tracing"] = True
        except Exception as e:  # the journey traces itself: keep its trace, add ours nowhere
            _err("tracing.start", e)
        ctx._e2e_rec = rec
        with _lock:
            _state["contexts"].append(ctx)
        return ctx

    def new_page(self, *a, **kw):
        if "ownpage" in OFF:
            return orig_new_page(self, *a, **kw)
        ctx = self.new_context(*a, **kw)
        page = ctx.new_page()
        page._e2e_owner = ctx  # Browser.new_page owns its context: closing the page closes it
        return page

    def ctx_close(self, *a, **kw):
        try:
            _finalize(self)
        except Exception as e:
            _err("finalize", e)
        r = orig_ctx_close(self, *a, **kw)
        rec = getattr(self, "_e2e_rec", None)
        if rec is not None:
            _collect_videos(rec)
            _dump()
        return r

    def page_close(self, *a, **kw):
        owner = getattr(self, "_e2e_owner", None)
        if owner is not None:
            if a or kw:  # e.g. run_before_unload=True: honour it, then close the owned context
                try:
                    _finalize(owner)
                except Exception as e:
                    _err("finalize", e)
                orig_page_close(self, *a, **kw)
            return ctx_close(owner)
        rec = getattr(self.context, "_e2e_rec", None) if not self.is_closed() else None
        if rec is not None and not rec["done"]:
            # A page closed before its context: its end state counts too (a negative check must hold on it).
            _final_page(self, rec, len(rec["videos"]))
        return orig_page_close(self, *a, **kw)

    def browser_close(self, *a, **kw):
        for ctx in list(self.contexts):
            try:
                ctx_close(ctx)
            except Exception as e:
                _err("browser close ctx", e)
        return orig_browser_close(self, *a, **kw)

    def pw_exit(self, *a):
        for ctx in list(_state["contexts"]):
            rec = getattr(ctx, "_e2e_rec", None)
            if rec is not None and not rec["done"]:
                try:
                    ctx_close(ctx)
                except Exception as e:
                    _err("exit ctx close", e)
        _dump()
        return orig_exit(self, *a)

    def after(fn, label):
        def wrapped(self, *a, **kw):
            r = fn(self, *a, **kw)
            page = self if isinstance(self, Page) else getattr(self, "page", None)
            if page is not None:
                sample(page, label)
            return r
        return wrapped

    def before_shot(fn):
        def wrapped(self, *a, **kw):
            sample(self, "screenshot", force=True)
            r = fn(self, *a, **kw)
            try:
                tag = _state.get("tag") or os.path.splitext(os.path.basename(str(kw.get("path") or "shot")))[0]
                ext = "jpg" if kw.get("type") == "jpeg" or str(kw.get("path") or "").lower().endswith((".jpg", ".jpeg")) else "png"
                p = _shot_path(tag)[:-3] + ext
                with open(p, "wb") as fh:
                    fh.write(r)
                _state["shots"].append(os.path.relpath(p, BASE))
            except Exception as e:
                _err("screenshot copy", e)
            return r
        return wrapped

    Browser.new_context = new_context
    Browser.new_page = new_page
    BrowserContext.close = ctx_close
    Browser.close = browser_close
    Page.close = page_close
    PlaywrightContextManager.__exit__ = pw_exit
    for name in ("goto", "reload", "click", "wait_for_selector", "wait_for_timeout", "wait_for_function",
                 "wait_for_load_state", "fill", "press", "keyboard"):
        fn = getattr(Page, name, None)
        if callable(fn) and name != "keyboard":
            setattr(Page, name, after(fn, name))
    for name in ("click", "wait_for", "fill", "press", "check"):
        fn = getattr(Locator, name, None)
        if callable(fn):
            setattr(Locator, name, after(fn, "locator." + name))
    Page.screenshot = before_shot(Page.screenshot)
    atexit.register(_dump)


_fixture_log = []


def _install_fixture_log():
    """Record every request an in-process `http.server` handler answers (the uxfix fixture). Lines are
    buffered in memory and written at exit: a file write per request perturbed timing-sensitive journeys."""
    import http.server
    orig = http.server.BaseHTTPRequestHandler.send_response

    def send_response(self, code, message=None):
        _fixture_log.append((getattr(self, "command", None), getattr(self, "path", None), code, time.time()))
        return orig(self, code, message)

    http.server.BaseHTTPRequestHandler.send_response = send_response


def _dump_fixture_log():
    if not BASE or not _fixture_log:
        return
    try:
        with open(os.path.join(BASE, "fixture-requests.jsonl"), "w", encoding="utf-8") as fh:
            for m, p, c, t in list(_fixture_log):
                fh.write(json.dumps({"method": m, "path": p, "status": c, "t": round(t, 3)}) + "\n")
    except OSError:
        pass
