"""U01 (J1, J8): a person opens studio and the Nerve Center tells the truth.

Path: open / -> the Desk renders -> the rail's Nerve Center -> /watch.
Passes when: the Desk's own content and the Nerve Center render with no page error and no 500; the rail tile's tone
equals the PAGE's tone (two independent readings); and something the daemon reports down is shown down. The hermetic
daemon has no wicked-estate binary, so Estate's own entry must read down (red), the Services tile must not read ok,
and the page must not read as all good.
"""
import re

ALL_GOOD = re.compile(r"\b(all good|everything('s| is) (fine|ok|working|ready)|nothing (is )?wrong)\b", re.I)


def run(j):
    p = j.page
    p.goto(j.origin + "/", wait_until="domcontentloaded")
    j.check("desk_renders", j.wait(lambda: p.get_by_test_id("desk-rail-new-job").is_visible(), 90, "the Desk rail"))
    # The Desk's own content, not just the shared rail: on a first run the Desk is the setup guide (Helpers + its
    # steps); afterwards it is Home. Either way a page heading and its body must be visible.
    body = j.wait(lambda: next((t for t in ("agents-setup", "desk-home", "agents-page") if p.get_by_test_id(t).first.is_visible()), None), 60, "the Desk's content")
    steps = p.locator('[data-testid^="agents-setup-step-"]').count() if body == "agents-setup" else None
    j.check("desk_content_renders", body is not None and (body != "agents-setup" or steps >= 4), content=body, setup_steps=steps, url=p.url.replace(j.origin, ""))
    p.wait_for_timeout(1500)
    j.shots("U01-home")
    p.get_by_test_id("desk-rail-nerve").click()
    j.check("nerve_center_opens", j.wait(lambda: p.get_by_test_id("nerve-center-page").is_visible() and "/watch" in p.url, 60, "the Nerve Center page"))
    j.wait(lambda: p.get_by_test_id("nc-headline").inner_text().strip() != "", 60, "the headline")
    j.wait(lambda: p.get_by_test_id("nc-tile").count() > 0, 60, "the tiles")
    p.wait_for_timeout(2000)
    # Two independent readings: the PAGE's own tone and the rail tile's (the light inside the rail is the rail's).
    page_tone = p.get_by_test_id("nerve-center-page").get_attribute("data-tone")
    rail_tone = p.get_by_test_id("desk-rail-nerve").get_attribute("data-tone")
    j.check("rail_tone_equals_page_tone", page_tone is not None and page_tone == rail_tone, page=page_tone, rail=rail_tone)
    # Estate's OWN entry reads down (not just a red aggregate that mentions it).
    estate = p.locator('[data-testid="nc-slow"][data-id="infra:estate"]')
    e_level = estate.get_attribute("data-level") if estate.count() else None
    e_text = estate.inner_text() if estate.count() else ""
    j.check("estate_reads_down", e_level == "red" and "down" in e_text.lower(), level=e_level, text=e_text[:200])
    services = p.locator('[data-testid="nc-tile"][data-tile="services"]')
    s_tone = services.get_attribute("data-tone") if services.count() else None
    j.check("services_tile_not_ok", s_tone in ("fail", "warn"), tone=s_tone)
    headline = p.get_by_test_id("nc-headline").inner_text()
    j.check("not_called_all_good", page_tone not in ("green", "ok") and not ALL_GOOD.search(headline), tone=page_tone, headline=headline[:200])
    j.shots("U01-nerve")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
    # A 500 is a crash. A 502/503 is a dependency reported down (the hermetic daemon has no estate, so its memory and
    # proposal routes answer 502): recorded, not judged here; the down service itself is judged above.
    j.check("no_internal_server_errors", not [r for r in j.rec["bad_responses"] if r.startswith("500 ")], bad=j.rec["bad_responses"][:10])
