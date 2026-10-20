"""visit.py URL — one read-only look at a page: load it, let it settle, screenshot it, close.

Run by the e2e runner's direct adapter with this directory on PYTHONPATH and E2E_PW_DIR set, so
sitecustomize's hook records the video, trace, HAR and DOM samples. It never clicks or types, and
it ABORTS every request that is not a GET to the target's own origin (whatever the page tries to
send on load), so the visit cannot change the daemon. A navigation that ends on another origin
exits 3: what was sampled is not the target.
"""
import json
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

url = sys.argv[1]
origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
blocked = []


def guard(route, request):
    u = urlsplit(request.url)
    same = "{0.scheme}://{0.netloc}".format(u) == origin or u.scheme in ("data", "blob")
    if request.method != "GET" or not same:
        blocked.append("%s %s" % (request.method, request.url))
        route.abort()
    else:
        route.continue_()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.context.route("**/*", guard)
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass  # a live page keeps a socket open; the samples below still run
    page.wait_for_timeout(1500)
    page.screenshot(path="visit.png")
    final = "{0.scheme}://{0.netloc}".format(urlsplit(page.url))
    browser.close()
with open("visit-guard.json", "w", encoding="utf-8") as fh:
    json.dump({"origin": origin, "final": final, "blocked": blocked}, fh, indent=1)
if blocked:
    print("visit: blocked %d request(s) that were not a same-origin GET: %s" % (len(blocked), blocked[:5]))
sys.exit(0 if final == origin else 3)
