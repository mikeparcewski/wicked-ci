"""U05 (J5, hermetic): a change that breaks a test is denied with the failing test named, and the person has a way
forward on the card.

Path: as U04 (Settings, New job -> /bug -> corpus -> Start, the plan and the judgment cards), but the stub's fix adds a
test that fails, `add keeps zero as the identity` (scenario `fix: break`, written by the step; the fixture's own tests
already fail on the base, so a new test is what a regression looks like here). Passes when the run stops at a card that names the
failing test, offers a way forward (send back / retry / redo), and nothing is delivered. The run is left at that card (the
ephemeral daemon is torn down with it).
"""
import re

INTENT = "add() in src/add.js returns a - b; fix it so it returns the sum (U05: the fix will break a test)."
FAILING = "add keeps zero as the identity"


def run(j):
    u04 = j.load("u04_bug_delivered")
    u04.qe_off(j)
    rid = u04.launch(j, INTENT, "U05")
    if not rid:
        return
    hit = u04.steer(j, rid, until=lambda card, choices: FAILING in card or re.search(r"\bfail", card, re.I) is not None and "judge" not in card.lower() and "rules" not in card.lower())
    if not hit:
        return
    p = j.page
    j.check("the_card_names_the_failing_test", FAILING in hit["card"], card=hit["card"][:600])
    forward = [c for c in hit["choices"] if re.search(r"send back|retry|redo", c, re.I)]
    j.check("a_way_forward_is_offered", bool(forward), choices=hit["choices"])
    run = u04.run_of(j, rid) or {}
    j.check("nothing_delivered", run.get("session", {}).get("delivery") in (None, "", "none", "not_delivered", "pending"), delivery=run.get("session", {}).get("delivery"))
    j.shots("U05-red-check")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
