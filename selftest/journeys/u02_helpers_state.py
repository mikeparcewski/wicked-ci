"""U02 (J2, hermetic half): each helper reads as it is.

Path: open /agents (Helpers). The stub roster has a signed-in seat (claude), a signed-out one (codex, 401 on every
turn), one not installed (pi), a quota-exhausted one (copilot) and seats with no credential rule.
Passes when: every roster seat has a row; a signed-in seat reads Ready, unless the engine benched it (after a bug run the
quota-exhausted copilot is `council_eligible: false`), when it must NOT read Ready; a signed-out or missing seat reads Not
ready with a way forward on the row (Sign in / Fix); nothing signed out reads Ready.
"""


def run(j):
    p = j.page
    roster = {r["key"]: r for r in j.get("/roster").get("roster", [])}
    p.goto(j.origin + "/agents", wait_until="domcontentloaded")
    j.check("helpers_page_renders", j.wait(lambda: p.get_by_test_id("agents-list").is_visible(), 90, "the Helpers list"))
    j.wait(lambda: p.locator('[data-testid="agents-row"][data-agent]').count() >= len(roster), 60, "a row per roster seat")
    rows = {e.get_attribute("data-agent"): e for e in p.locator('[data-testid="agents-row"][data-agent]').all()}
    missing = sorted(set(roster) - set(rows))
    j.check("every_seat_has_a_row", not missing, missing=missing, roster=sorted(roster))
    wrong = []
    for key, r in roster.items():
        row = rows.get(key)
        if row is None:
            continue
        ready = row.get_attribute("data-ready") or ""
        benched = r.get("council_eligible") is False  # the engine benched it (quota, failures) and carries the cause
        if r.get("auth") == "signed_in" and not benched and not ready.startswith("Ready"):
            wrong.append(f"{key}: signed in and eligible but reads {ready!r}")
        if r.get("auth") == "signed_in" and benched and ready.startswith("Ready"):
            wrong.append(f"{key}: benched by the engine but reads {ready!r}")
        if r.get("auth") == "signed_out":
            fix = p.locator(f'[data-testid="agents-fix"][data-agent="{key}"]')
            if ready.startswith("Ready"):
                wrong.append(f"{key}: signed out but reads {ready!r}")
            elif fix.count() == 0:
                wrong.append(f"{key}: not ready with no way forward on the row")
    j.check("each_seat_reads_as_it_is", not wrong, wrong=wrong, roster={k: {f: r.get(f) for f in ("auth", "council_eligible", "seat_eligible_for_work")} for k, r in roster.items()})
    j.shots("U02-helpers")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
