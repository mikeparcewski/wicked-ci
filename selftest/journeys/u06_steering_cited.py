"""U06 (J7, hermetic): a steering rule imported in studio is in force for the next governed run, and the run cites it.

Path: Steering -> More -> Import rules… -> a markdown rule doc (one rule, `DEV-ST-U06`) -> Import -> the rule is listed
in force; then as U04 (Settings, New job -> /bug -> corpus -> Start) up to the review's rule check card. Passes when the
import went through the UI, the rule is listed on the Steering page, the run's gate (the wire) carries the rule among
the rules it checked, and the card's own rule list, opened as a person would, names it.

What this does not cover: a judge's verdict ON the rule. The hermetic roster has no judge the engine accepts for the
rule check, so every rule in force reads "unchecked" and needs the person's call (the thin-roster card, as in U04).
A plan citing a rule is the `plan.compose` testing rules' path; a doctrine rule like this one is cited at review.
"""
import json
import os
import re

RULE = "DEV-ST-U06"
STATEMENT = "add() in src/add.js returns the sum of its two arguments, never their difference."
INTENT = "add() in src/add.js returns a - b; fix it so it returns the sum (U06: a steering rule applies)."


def doc():
    return "\n".join([
        "---", "id: selftest-u06", "title: Self-test U06 rule", "status: active", "date: 2026-11-11", "---",
        "# Self-test U06 rule", "", "## Rules", "", f"- `{RULE}` (error): {STATEMENT}", ""])


def import_rule(j):
    p = j.page
    p.goto(j.origin + "/steering/policies", wait_until="domcontentloaded")
    j.check("steering_page_renders", j.wait(lambda: p.get_by_test_id("steer-surface").is_visible(), 90, "the Steering page"))
    p.get_by_test_id("steer-more").first.click()
    j.wait(lambda: p.get_by_test_id("steer-import").count() > 0 and p.get_by_test_id("steer-import").first.is_visible(), 20, "the Import item")
    p.get_by_test_id("steer-import").first.click()
    j.check("import_dialog_opens", j.wait(lambda: p.get_by_test_id("steer-import-dialog").is_visible(), 20, "the Import dialog"))
    path = os.path.join(j.out, "u06-rule.md")
    with open(path, "w") as f:
        f.write(doc())
    p.get_by_test_id("steer-import-file").locator("input[type=file]").set_input_files(path)
    n0 = len(j.rec["writes"])
    p.get_by_test_id("steer-import-go").click()
    sent = j.wait(lambda: any(re.match(r"200 POST /api/v1/governance/steering/import", w) for w in j.rec["writes"][n0:]), 30, "the import to send")
    notes = j.wait(lambda: p.get_by_test_id("steer-import-notes").count() > 0 and p.get_by_test_id("steer-import-notes").inner_text().strip(), 30, "the import's result")
    # The receipt says what happened: exactly this one rule imported, nothing skipped or refused.
    ok = bool(sent) and bool(notes) and re.search(r"\b1 of 1 entr(y|ies) imported\b", notes or "") is not None and RULE in (notes or "") \
        and re.search(r"fail|refus|reject|skipp", notes or "", re.I) is None
    j.check("rule_imported_in_the_ui", ok, writes=j.rec["writes"][n0:], notes=(notes or "")[:300])
    j.shot("U06-imported")
    p.get_by_test_id("steer-import-cancel").click()
    p.reload(wait_until="domcontentloaded")
    # The list shows a rule by its statement (its title), not its id.
    j.check("rule_listed_in_force", j.wait(lambda: "never their difference" in p.inner_text("body"), 60, "the rule in the list"))
    j.shots("U06-steering")


def rule_rows(doc):
    """Every rule id a structured rule-check row names in `doc` (a row: an object with a rule id and its outcome)."""
    out = []
    if isinstance(doc, dict):
        rid = doc.get("ruleId") or doc.get("rule_id")
        if isinstance(rid, str) and any(k in doc for k in ("verdict", "status", "outcome", "result", "state")):
            out.append(rid)
        for v in doc.values():
            out += rule_rows(v)
    elif isinstance(doc, list):
        for v in doc:
            out += rule_rows(v)
    return out


def run(j):
    p = j.page
    u04 = j.load("u04_bug_delivered")
    import_rule(j)
    u04.qe_off(j)
    rid = u04.launch(j, INTENT, "U06")
    if not rid:
        return
    cards = []

    def note(card, choices):
        cards.append(card[:1500])
        return bool(u04.RULES_CARD.search(card))

    hit = u04.steer(j, rid, until=note)
    j.rec["cards"] = cards
    if not hit:
        return
    # The wire: the CURRENT gate's structured rule rows (the rule check of this review step) hold the rule by its id;
    # the id appearing anywhere else in the gate (a note, a prompt) does not count.
    gate = j.get(f"/runs/{rid}/gate") or {}
    rows = rule_rows(gate)
    j.check("rule_in_the_gates_rule_check", any(r == RULE for r in rows), rules=rows[:30])
    # The card's "N rules checked" line opens to every rule's row: the person's way to see which rules applied. Only
    # the current gate's own list counts (the last gate row in the thread).
    rules = p.get_by_test_id("session-gate-row").last.get_by_test_id("session-gate-rules")
    listed = ""
    if rules.count():
        if rules.get_attribute("open") is None:
            rules.locator("summary").first.click()
            p.wait_for_timeout(600)
        listed = rules.inner_text()
    j.check("card_lists_the_rule", RULE in listed, rules=listed[:1200], card=hit["card"][:400])
    j.shots("U06-cited")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
