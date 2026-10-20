"""visit.py URL — one read-only look at a page: load it, let it settle, screenshot it, close.

Run by the e2e runner's direct adapter with this directory on PYTHONPATH and E2E_PW_DIR set, so
sitecustomize's hook records the video, trace, HAR and DOM samples. It never clicks or types.
"""
import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass  # a live page keeps a socket open; the samples below still run
    page.wait_for_timeout(1500)
    page.screenshot(path="visit.png")
    browser.close()
