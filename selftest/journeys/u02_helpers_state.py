"""U02 (J2, hermetic half): each helper reads as it is.

Path: open /agents (Helpers). The stub roster has a signed-in seat (claude), a signed-out one (codex, 401 on every
turn), one not installed (pi), a quota-exhausted one (copilot) and seats with no credential rule.
Passes when: GET /roster is the fixture roster; every fixture seat has a row; its VISIBLE readiness agrees: a signed-in seat reads Ready, unless the engine benched it (after a bug run the
quota-exhausted copilot is `council_eligible: false`), when it must NOT read Ready; a signed-out or missing seat reads Not
ready with a way forward on the row (Sign in / Fix); nothing signed out reads Ready.
"""
import re

# The stub roster the harness writes (selftest/lib/shims.mjs), stated here independently of GET /roster, so an API
# regression that drops seats can't make this journey pass on an empty list.
FIXTURE = {"claude": "signed_in", "codex": "signed_out", "pi": "signed_out", "copilot": "signed_in", "opencode": "not_required", "smoke-judge": "unknown"}


# What the row may say when a seat can't work: the product's own unavailable wording (positive, not "anything but Ready").
UNAVAILABLE = re.compile(r"not signed in|signed out|not installed|out of quota|quota|not ready|benched|can.t work|sign in", re.I)


def run(j):
    p = j.page
    fixture = dict(FIXTURE)
    if j.state.get("piCredential"):
        fixture["pi"] = "signed_in"  # WICKED_SMOKE_PI_CREDENTIAL: the credential exists, the binary does not
    if j.state.get("chatSeat"):
        fixture[j.state["chatSeat"]] = None  # S08 enabled the chat seat: it must be listed (any auth)
    roster = {r["key"]: r for r in j.get("/roster").get("roster", [])}
    drift = {k: roster.get(k, {}).get("auth", "MISSING") for k, want in fixture.items() if k not in roster or (want is not None and roster[k].get("auth") != want)}
    j.check("roster_is_the_fixture_roster", not drift, drift=drift)
    p.goto(j.origin + "/agents", wait_until="domcontentloaded")
    j.check("helpers_page_renders", j.wait(lambda: p.get_by_test_id("agents-list").is_visible(), 90, "the Helpers list"))
    j.wait(lambda: p.locator('[data-testid="agents-row"][data-agent]').count() >= len(fixture), 60, "a row per fixture seat")
    rows = {e.get_attribute("data-agent"): e for e in p.locator('[data-testid="agents-row"][data-agent]').all()}
    missing = sorted(set(fixture) - set(rows))
    j.check("every_seat_has_a_row", not missing, missing=missing)
    wrong = []
    for key in fixture:
        row, r = rows.get(key), roster.get(key, {})
        if row is None:
            continue
        # What the person SEES on the row: its status line, else the summary under the helper's name (the detailed
        # readiness sits in a collapsed panel and is not what the row says).
        status = row.locator('[data-testid="agents-status"]')
        if status.count() and status.first.is_visible():
            visible_ready = status.first.inner_text().strip()
        else:
            summary = row.locator('[data-testid="agents-open"]')
            lines = [l.strip() for l in summary.first.inner_text().split("\n") if l.strip()] if summary.count() and summary.first.is_visible() else []
            visible_ready = " / ".join(lines[1:]) if len(lines) > 1 else None
        benched = r.get("council_eligible") is False  # the engine benched it (quota, failures) and carries the cause
        if visible_ready is None:
            wrong.append(f"{key}: no visible readiness")
            continue
        if r.get("auth") == "signed_in" and not benched and not visible_ready.startswith("Ready"):
            wrong.append(f"{key}: signed in and eligible but reads {visible_ready!r}")
        if benched and not UNAVAILABLE.search(visible_ready):
            wrong.append(f"{key}: benched by the engine but reads {visible_ready!r}")
        if r.get("auth") == "signed_out":
            fix = row.locator('[data-testid="agents-fix"]')
            if not UNAVAILABLE.search(visible_ready):
                wrong.append(f"{key}: signed out but reads {visible_ready!r}")
            elif not (fix.count() and fix.first.is_visible() and fix.first.is_enabled()):
                wrong.append(f"{key}: not ready with no visible, enabled way forward on the row")
    j.check("each_seat_reads_as_it_is", not wrong, wrong=wrong, roster={k: {f: r.get(f) for f in ("auth", "council_eligible")} for k, r in roster.items()})
    j.shots("U02-helpers")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
