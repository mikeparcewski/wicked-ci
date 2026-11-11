"""U01 (J1, J8): a person opens studio and the Nerve Center tells the truth.

Path: open / -> the Desk renders -> the rail's Nerve Center -> /watch.
Passes when: the Desk and the Nerve Center render with no page error and no 5xx; the rail tile's tone equals the page's
light; and something the daemon reports down is shown down. The hermetic daemon has no wicked-estate binary, so
Services must read failing and name Estate, and the page must not read as all good.
"""
import re

ALL_GOOD = re.compile(r"\b(all good|everything('s| is) (fine|ok|working|ready)|nothing (is )?wrong)\b", re.I)


def run(j):
    p = j.page
    p.goto(j.origin + "/", wait_until="domcontentloaded")
    j.check("desk_renders", j.wait(lambda: p.get_by_test_id("desk-rail-new-job").is_visible(), 90, "the Desk rail"))
    p.wait_for_timeout(2500)
    j.shots("U01-home")
    p.get_by_test_id("desk-rail-nerve").click()
    j.check("nerve_center_opens", j.wait(lambda: p.get_by_test_id("nerve-center-page").is_visible() and "/watch" in p.url, 60, "the Nerve Center page"))
    j.wait(lambda: p.get_by_test_id("nc-headline").inner_text().strip() != "", 60, "the headline")
    j.wait(lambda: p.get_by_test_id("nc-tile").count() > 0, 60, "the tiles")
    p.wait_for_timeout(2000)
    page_tone = p.get_by_test_id("nerve-center-light").get_attribute("data-tone")
    rail_tone = p.get_by_test_id("desk-rail-nerve").get_attribute("data-tone")
    j.check("rail_tone_equals_page_tone", page_tone is not None and page_tone == rail_tone, page=page_tone, rail=rail_tone)
    services = p.locator('[data-testid="nc-tile"][data-tile="services"]')
    s_tone = services.get_attribute("data-tone") if services.count() else None
    s_text = services.inner_text() if services.count() else ""
    j.check("a_down_service_reads_down", s_tone in ("fail", "warn") and "Estate" in s_text, tone=s_tone, text=s_text[:200])
    headline = p.get_by_test_id("nc-headline").inner_text()
    words = p.get_by_test_id("nerve-center-words").inner_text()
    j.check("not_called_all_good", page_tone not in ("green", "ok") and not ALL_GOOD.search(headline + " " + words), tone=page_tone, headline=headline[:200], words=words[:200])
    j.shots("U01-nerve")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
    # A 500 is a crash. A 502/503 is a dependency reported down (the hermetic daemon has no estate, so its memory and
    # proposal routes answer 502): recorded, not judged here; the down service itself is judged above.
    j.check("no_internal_server_errors", not [r for r in j.rec["bad_responses"] if r.startswith("500 ")], bad=j.rec["bad_responses"][:10])
