"""U04 (J4, hermetic): a governed bug fix launched, steered and delivered through studio, to a PR.

Path: New job -> /bug -> the person's words -> "Which repository?" -> corpus -> Review plan on -> Start -> the plan
gate (approve) -> the run's own questions, answered on their cards as a person would -> the deliver gate -> "Yes,
deliver" -> the run page shows it delivered (the corpus origin is a local bare repo, so the delivery is the pushed
branch, as the card says).
Passes when: every decision went through the UI (the run's gate decisions are the UI's own POSTs); the run reaches
`completed`; the run page shows the delivery; the branch is on the local bare origin and its add() returns the sum; QE is
labelled as the person's setting, never as passed. The stub seats write a deterministic fix; this proves the product's
governed path and its UI, not a model's code.
"""
import re
import subprocess
import time

INTENT = "add() in src/add.js returns a - b; it should return the sum. Fix add() so test/add.test.js passes."
# A card's choice, by what the card is for. Anything else is reported and fails the journey (never guessed).
PLAN = re.compile(r"^approve( the)? plan|^approve$", re.I)
DELIVER = re.compile(r"^deliver\b|open (the )?pr|push", re.I)
# "No helper could check this step independently": the hermetic team uses every live seat, so no distinct judge is
# left (the J4 thin-roster case). A person's honest way forward is their own labelled judgment; it is recorded.
JUDGMENT = re.compile(r"^approve as your own judg", re.I)
# "N steering rules need your call": with no signed-in judge distinct from the creator the rules stay unchecked; the
# person confirms or skips them, with the reason, on the card (labelled on the run).
RULES = re.compile(r"^confirm or skip \d+ rules?", re.I)
JUDGE_CARD = re.compile(r"no helper could check this step independently", re.I)
RULES_CARD = re.compile(r"steering rules? need your call", re.I)
QE_SKIP = re.compile(r"skip (qe|the acceptance|acceptance)|skip,? with a reason", re.I)
CONFIRM = re.compile(r"^yes\b|confirm|^deliver$|^push", re.I)


def run_of(j, rid):
    for r in j.get("/runs?limit=50").get("runs", []):
        if r["session"]["id"] == rid:
            return r
    return None


def run(j):
    if j.state.get("resumeRun"):  # development only: follow a run this journey already launched
        return steer(j, j.state["resumeRun"])
    qe_off(j)
    rid = launch(j, INTENT, "U04")
    if rid:
        steer(j, rid)


def qe_off(j):
    p = j.page
    # The stub seats keep no QE ledger, so the person turns "Require QE acceptance before delivery" off in Settings
    # first (their labelled choice; the run must then say QE was not required by the operator, never that it passed).
    p.goto(j.origin + "/system", wait_until="domcontentloaded")
    j.wait(lambda: p.get_by_test_id("qe-acceptance-toggle").is_visible(), 60, "the QE acceptance setting")
    tg = p.get_by_test_id("qe-acceptance-toggle")
    on = (tg.get_attribute("aria-checked") or tg.get_attribute("aria-pressed") or ("true" if tg.is_checked() else "false")) == "true"
    if on:
        n0 = len(j.rec["writes"])
        tg.click()
        p.get_by_role("button", name="Save", exact=True).first.click()  # Settings save on the page's own Save
        j.check("qe_setting_turned_off", j.wait(lambda: any(re.match(r"2\d\d (PUT|PATCH|POST) /api/v1/", w) for w in j.rec["writes"][n0:]), 30, "the setting to save"), writes=j.rec["writes"][n0:])
    j.shot("qe-setting")


def launch(j, intent, label):
    """New job -> /bug -> the person's words -> corpus -> Review plan on -> Start. Returns the new run's id."""
    p = j.page
    p.goto(j.origin + "/jobs", wait_until="domcontentloaded")
    j.check("rail_visible", j.wait(lambda: p.get_by_test_id("desk-rail-new-job").is_visible(), 90, "the rail"))
    before = {r["session"]["id"] for r in j.get("/runs?limit=200").get("runs", [])}
    p.get_by_test_id("desk-rail-new-job").click()
    j.wait(lambda: p.locator('[data-testid="composer-menu-item"][data-card="bug"]').count() > 0, 60, "the /bug card")
    p.locator('[data-testid="composer-menu-item"][data-card="bug"]').first.click()
    p.get_by_test_id("session-composer-input").fill(intent)
    p.keyboard.press("Enter")
    j.check("asks_which_repository", j.wait(lambda: p.get_by_test_id("job-passage-repo").filter(has_text="corpus").count() > 0, 120, "the repository question"))
    p.get_by_test_id("job-passage-repo").filter(has_text="corpus").first.click()
    j.check("proposal_shown", j.wait(lambda: p.get_by_test_id("job-passage-review-plan-toggle").count() > 0, 120, "the proposal"))
    tg = p.get_by_test_id("job-passage-review-plan-toggle").first
    if (tg.get_attribute("aria-checked") or tg.get_attribute("aria-pressed")) != "true":
        tg.click()
        p.wait_for_timeout(800)
    j.shots(f"{label}-proposal")
    p.get_by_role("button", name=re.compile(r"^Start")).first.click() if p.get_by_role("button", name=re.compile(r"^Start")).count() else p.get_by_text(re.compile(r"^Start v\d")).first.click()
    words = intent[:40].lower()
    rid = j.wait(lambda: next((r["session"]["id"] for r in j.get("/runs?limit=200").get("runs", []) if r["session"]["id"] not in before and words in (r["session"].get("problem") or "").lower()), None), 120, "the run to exist")
    j.check("run_launched_from_the_ui", rid is not None and any(re.match(r"20\d POST /api/v1/", w) for w in j.rec["writes"]), run=rid, writes=j.rec["writes"][-6:])
    j.state["runId"] = rid
    return rid


def steer(j, rid, until=None, answer_then_return=None):
    """Answer the run's cards as a person would. With `until(card_text, choices)`, stop and return that card when it
    matches (a journey whose terminal state is a card, not a delivery); otherwise judge the delivery at the end."""
    p = j.page
    answered, seen, judgments, confirmed = [], [], [], []
    t0 = time.time()
    while time.time() - t0 < 900:
        r = run_of(j, rid)
        st = (r or {}).get("session", {}).get("status")
        if st in ("completed", "failed", "cancelled"):
            break
        if st != "awaiting_human":
            # `answer_then_return=N`: hand back once N cards are answered and the run is moving again.
            if answer_then_return is not None and len(answered) >= answer_then_return:
                return {"answered": answered, "status": st}
            p.wait_for_timeout(3000)
            continue
        p.goto(f"{j.origin}/s/run%3A{rid}", wait_until="domcontentloaded")
        p.wait_for_timeout(2500)
        got = j.wait(lambda: sum(p.get_by_test_id(t).count() for t in ("session-proposal-option", "session-gate-choice", "job-passage-reply")) > 0, 60, "a decision card")
        if not got:
            continue
        p.wait_for_timeout(1500)
        props = [e for e in p.get_by_test_id("session-proposal-option").all() if e.is_visible()]
        gates = [e for e in p.get_by_test_id("session-gate-choice").all() if e.is_visible()]
        gates += [e for e in p.get_by_test_id("job-passage-reply").all() if e.is_visible()]  # the plan's reply in the thread
        texts = [e.inner_text().strip().split("\n")[0] for e in props + gates]
        kind = (r["session"].get("awaitingHuman") or {}).get("gateKind") if isinstance(r["session"].get("awaitingHuman"), dict) else None
        seen.append({"kind": kind, "choices": texts})
        card = p.get_by_test_id("session-gate-row").last.inner_text() if p.get_by_test_id("session-gate-row").count() else ""
        if until is not None and until(card, texts):
            return {"card": card, "choices": texts, "answered": answered, "judgments": judgments}
        pick = None
        # A judgment or a rules skip is offered on other cards too (a failed repository floor offers "Approve as your
        # own judgment"); the person takes it ONLY on the card that is about the missing judge or the unchecked rules.
        allowed = [PLAN, DELIVER, QE_SKIP]
        if JUDGE_CARD.search(card):
            allowed.append(JUDGMENT)
        if RULES_CARD.search(card):
            allowed.append(RULES)
        for rx in allowed:
            pick = next((e for e in props + gates if rx.search(e.inner_text().strip().split("\n")[0])), None)
            if pick is not None:
                break
        if pick is None:
            j.check("every_card_has_a_known_way_forward", False, kind=kind, choices=texts, card=(p.get_by_test_id("session-gate-row").last.inner_text()[:600] if p.get_by_test_id("session-gate-row").count() else None))
            j.shot("unknown-card")
            return
        label = pick.inner_text().strip().split("\n")[0]
        j.shots(f"U04-card-{len(answered) + 1}")
        sent_before = len(j.rec["writes"])
        pick.click()
        p.wait_for_timeout(800)
        if JUDGMENT.search(label) or QE_SKIP.search(label) or RULES.search(label):
            box = p.get_by_test_id("session-gate-note").last
            if box.count() and box.is_visible():
                box.fill("Hermetic self-test (U04): stub seats; no distinct judge or QE ledger exists here. This proves the governed path and delivery, not the fix.")
        for tid in ("session-proposal-go", "session-gate-send", "session-gate-confirm", "session-proposal-confirm-yes"):
            if tid == "session-proposal-confirm-yes":  # the deliver card's "Are you sure?": the person's yes
                if not DELIVER.search(label):
                    continue
                b = p.get_by_test_id(tid)
                if j.wait(lambda: b.count() > 0 and b.first.is_visible() and b.first.is_enabled(), 8, "the delivery confirmation"):
                    b.first.click()  # recorded only once the person's yes is actually pressed
                    confirmed.append(label)
                    p.wait_for_timeout(1200)
                continue
            b = p.get_by_test_id(tid)
            if b.count() and b.first.is_visible() and b.first.is_enabled():
                b.first.click()
                p.wait_for_timeout(1200)
        dock = p.get_by_test_id("decision-dock")
        if dock.count():
            yes = [b for b in dock.locator("button").all() if b.is_visible() and CONFIRM.search(b.inner_text().strip())]
            if yes:
                yes[0].click()
        # A decision is SENT only after the card's undo window (about 10 s); leaving the page earlier drops it. Wait for
        # the UI's own POST, and fail if it never goes out.
        sent = j.wait(lambda: any(re.match(r"2\d\d POST /api/v1/", w) for w in j.rec["writes"][sent_before:]), 30, f"the UI to send '{label}'")
        if not sent:
            j.check("each_decision_is_sent", False, choice=label, writes=j.rec["writes"][sent_before:])
            return
        answered.append(label)
        if JUDGMENT.search(label) or RULES.search(label) or QE_SKIP.search(label):
            judgments.append(label)
        p.wait_for_timeout(3000)
    if until is not None:
        j.check("the_expected_card_came", False, status=(run_of(j, rid) or {}).get("session", {}).get("status"), seen=seen[-4:])
        return None
    r = run_of(j, rid) or {}
    s = r.get("session", {})
    # The plan gate and the delivery confirmation are the person's: both must have been answered in the UI.
    j.check("plan_and_delivery_answered_in_the_ui", any(PLAN.search(a) for a in answered) and any(DELIVER.search(a) for a in answered), answered=answered, seen=seen[-6:])
    # The delivery asked "Are you sure?" and the person said yes (a delivery sent from the first press would fail this).
    j.check("delivery_confirmed_with_yes", bool(confirmed), confirmed=confirmed)
    # The thin roster's judgments are the person's, labelled with their reason: disclosed, never hidden.
    j.rec["judgments"] = judgments
    j.check("run_completed", s.get("status") == "completed", status=s.get("status"), delivery=s.get("delivery"))
    qe = (s.get("assurance") or {}).get("qe") or {}
    j.check("qe_labelled_not_passed", qe.get("basis") == "operator" and qe.get("status") in ("skipped", "not_required", "waived"), qe=qe)
    p.goto(f"{j.origin}/s/run%3A{rid}", wait_until="domcontentloaded")
    # The corpus origin is a bare repository on this machine, so the delivery is the pushed branch ("There is no pull
    # request: the branch is the delivery", the card says). The run page must show it delivered, not "Nothing
    # delivered yet".
    shown = j.wait(lambda: re.search(r"Finished\s*·\s*delivered", p.inner_text("body")) is not None and "Nothing delivered yet" not in p.inner_text("body"), 60, "the delivery on the run page")
    j.check("delivery_shown_on_the_run_page", bool(shown), delivery=s.get("delivery"))
    # The QE skip is disclosed where the person reads the result, and nothing there says QE passed.
    body = p.inner_text("body")
    j.check("qe_skip_disclosed_on_the_page", re.search(r"QE acceptance[^.\n]{0,40}\boff\b", body, re.I) is not None and re.search(r"QE acceptance:?\s*(PASS|passed|ok)\b", body, re.I) is None, excerpt=(re.search(r"QE acceptance[^\n]{0,80}", body) or [None])[0])
    origin_git = j.state.get("origin")
    if origin_git:
        show = subprocess.run(["git", "--git-dir", origin_git, "show", f"wicked/{rid}:src/add.js"], capture_output=True, text=True)
        j.check("branch_on_origin_returns_the_sum", show.returncode == 0 and re.search(r"a\s*\+\s*b", show.stdout) is not None, out=(show.stdout or show.stderr)[:200])
    j.shots("U04-delivered")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
