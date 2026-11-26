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
from urllib.parse import urlsplit

INTENT = "add() in src/add.js returns a - b; it should return the sum. Fix add() so test/add.test.js passes."
# A card's choice, by what the card is for. Anything else is reported and fails the journey (never guessed).
PLAN = re.compile(r"^approve( the)? plan|^approve$", re.I)
DELIVER = re.compile(r"^deliver\b|^open (the )?pr", re.I)
# "No helper could check this step independently": the hermetic team uses every live seat, so no distinct judge is
# left (the J4 thin-roster case). A person's honest way forward is their own labelled judgment; it is recorded.
JUDGMENT = re.compile(r"^approve as your own judg", re.I)
# "N steering rules need your call": with no signed-in judge distinct from the creator the rules stay unchecked; the
# person confirms or skips them, with the reason, on the card (labelled on the run).
# One unchecked rule is named instead of counted ("Confirm or skip POL-2101"; studio deskWords.rulesHoldWords).
# Since studio's gate-action contract the choice reads "Skip 5 rules" / "Skip POL-2101" and carries the structured key
# data-choice-key="skip-rules" (studio src/board/gateContract.ts): the key is read first, the wording second (#77).
RULES = re.compile(r"^(confirm or )?skip (\d+ rules?|[A-Z][A-Z0-9]*(-[A-Z0-9]+)+)$", re.I)
RULES_KEY = "skip-rules"
JUDGE_CARD = re.compile(r"no helper could check this step independently", re.I)
RULES_CARD = re.compile(r"steering rules? needs? your call|the rule \S+ needs your call", re.I)
QE_SKIP = re.compile(r"skip (qe|the acceptance|acceptance)", re.I)
CONFIRM = re.compile(r"^yes\b|confirm|^deliver$|^push", re.I)
# The chat job's Start on a thin roster (wicked-crew#1884): crew answers 409 stand_in_choice and the card asks "Use
# stand-ins for this job, or go back to the job and add another helper". The person takes stand-ins for this job: the
# run then fills its short roles with labelled stand-ins instead of stopping at "No helper could check this step
# independently". A full roster (or a crew before #1884) is never asked, and the journey runs the old path.
STAND_INS = re.compile(r"^use stand-ins for this job", re.I)
STAND_IN_ROLES = {"evaluator", "judge", "rule_judge", "qe_reviewer", "council", "monitor", "party_excluded"}
STAND_IN_STATES = {"seated", "answered", "failed"}


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


def stand_in_reply(p):
    """The card's "Use stand-ins for this job" reply, when the card asks the stand-in choice; else None."""
    for e in p.get_by_test_id("job-passage-reply").all():
        if (e.get_attribute("data-reply") or "").startswith("choice:") and e.is_visible() and STAND_INS.search(e.inner_text().strip()):
            return e
    return None


def press_start(p):
    if p.get_by_role("button", name=re.compile(r"^Start")).count():
        p.get_by_role("button", name=re.compile(r"^Start")).first.click()
    else:
        p.get_by_text(re.compile(r"^Start v\d")).first.click()


def launch(j, intent, label):
    """New job -> /bug -> the person's words -> corpus -> Review plan on -> Start (-> on a thin roster, "Use stand-ins
    for this job" -> Start). Returns the new run's id."""
    p = j.page
    p.goto(j.origin + "/jobs", wait_until="domcontentloaded")
    j.check("rail_visible", j.wait(lambda: p.get_by_test_id("desk-rail-new-job").is_visible(), 90, "the rail"))
    before = {r["session"]["id"] for r in j.get("/runs?limit=200").get("runs", [])}
    p.get_by_test_id("desk-rail-new-job").click()
    j.wait(lambda: p.locator('[data-testid="composer-menu-item"][data-card="bug"]').count() > 0, 60, "the /bug card")
    p.locator('[data-testid="composer-menu-item"][data-card="bug"]').first.click()
    p.get_by_test_id("session-composer-input").fill(intent)
    p.keyboard.press("Enter")
    corpus = p.locator('[data-testid="job-passage-repo"][data-repo="corpus"]').first
    more = p.get_by_test_id("job-passage-repos-more").first

    expanded = []

    def corpus_visible():
        if corpus.is_visible():
            return True
        # S05 adds bus repos; the corpus may be behind the question's "more" choice. A person opens it once.
        if not expanded and p.locator('[data-testid="job-passage-repo"]:visible').count() > 0 and more.is_visible():
            more.click()
            expanded.append(True)
        return corpus.is_visible()

    j.check("asks_which_repository", j.wait(corpus_visible, 120, "the repository question"))
    corpus.click()
    j.check("proposal_shown", j.wait(lambda: p.get_by_test_id("job-passage-review-plan-toggle").count() > 0, 120, "the proposal"))
    tg = p.get_by_test_id("job-passage-review-plan-toggle").first
    if (tg.get_attribute("aria-checked") or tg.get_attribute("aria-pressed")) != "true":
        tg.click()
        p.wait_for_timeout(800)
    j.shots(f"{label}-proposal")
    press_start(p)
    words = intent[:40].lower()

    def new_run():
        return next((r["session"]["id"] for r in j.get("/runs?limit=200").get("runs", []) if r["session"]["id"] not in before and words in (r["session"].get("problem") or "").lower()), None)

    # The Start either launches, or (a thin roster, wicked-crew#1884) reopens the card with the stand-in question.
    asked = []

    def launched_or_asked():
        if stand_in_reply(p) is not None:
            asked.append(True)
            return True
        return new_run() is not None

    j.wait(launched_or_asked, 120, "the run to exist, or the stand-in question")
    j.state["standIns"] = bool(asked)
    if asked:
        q = p.get_by_test_id("job-passage-question")
        text = q.last.inner_text()[:600] if q.count() else ""
        j.check("stand_in_choice_asked_on_the_card", "stand-in" in text.lower() and "independent" in text.lower(), question=text)
        j.shots(f"{label}-stand-in-question")
        n0 = len(j.rec["writes"])
        stand_in_reply(p).click()
        revised = j.wait(lambda: any(re.match(r"201 POST /api/v1/chats/[^ ]+/proposals$", w) for w in j.rec["writes"][n0:]), 30, "the stand-in choice to be sent")
        j.check("stand_in_choice_pressed", bool(revised), writes=j.rec["writes"][n0:])
        # The card says the choice is made; its Start launches with stand-ins for this job.
        j.wait(lambda: p.get_by_role("button", name=re.compile(r"^Start")).count() > 0 or p.get_by_text(re.compile(r"^Start v\d")).count() > 0, 60, "the card's Start")
        p.wait_for_timeout(800)
        press_start(p)
    rid = j.wait(new_run, 120, "the run to exist")
    j.check("run_launched_from_the_ui", rid is not None and any(re.match(r"20\d POST /api/v1/", w) for w in j.rec["writes"]), run=rid, writes=j.rec["writes"][-6:])
    j.state["runId"] = rid
    return rid


def pick_choice(card, choices):
    """The way forward a person takes on this card: `(element, is_rules_skip)`, or `(None, False)`.

    `choices` is `[(element, first_line_of_text, data-choice-key)]` in DOM order. A judgment or a rules skip is
    offered on other cards too (a failed repository floor offers "Approve as your own judgment"); the person takes it
    ONLY on the card that is about the missing judge or the unchecked rules. On the rules card the choice keyed
    skip-rules is taken first, in a pass of its own (#77). Then the wording: a choice keyed skip-rules is only ever
    taken as the rules skip, and a choice with another key is never taken as one (the key wins over the text).
    QE skip requires its skip-qe key and QE wording; delivery cannot use a skip or judgment key."""
    rules_card = bool(RULES_CARD.search(card))
    if rules_card:
        keyed = next((e for e, _, key in choices if key == RULES_KEY), None)
        if keyed is not None:
            return keyed, True
    allowed = [PLAN, DELIVER, QE_SKIP]
    if JUDGE_CARD.search(card):
        allowed.append(JUDGMENT)
    if rules_card:
        allowed.append(RULES)
    for rx in allowed:
        for e, text, key in choices:
            if key == RULES_KEY and rx is not RULES:
                continue
            if rx is RULES and key and key != RULES_KEY:
                continue
            if key == "skip-qe" and rx is not QE_SKIP:
                continue
            if rx is QE_SKIP and key != "skip-qe":
                continue
            if rx is DELIVER and key in (RULES_KEY, "skip-qe", "operator-judgment"):
                continue
            if rx.search(text):
                return e, rx is RULES
    return None, False


def decision_matches(body, kind, note):
    """Whether the gate body carries the person's chosen decision and the exact note they typed."""
    if not isinstance(body, dict):
        return False
    if kind == "skip_rules":
        rules = body.get("skipRules")
        return (body.get("action") == "skip_rules" and isinstance(rules, list) and bool(rules)
                and all(isinstance(rule, dict) and rule.get("reason") == note for rule in rules))
    if kind == "skip_qe":
        return body.get("action") == "skip_qe" and body.get("amend") == note
    if kind == "operator_judgment":
        # The plain "Approve as your own judgment" takes no note (the gate lists it as optional): note None means no
        # note was typed, so none may ride the request either.
        return (body.get("approve") is True and body.get("action") in (None, "approve", "operator_judgment")
                and body.get("amend") == note)
    return body.get("approve") is True


def stand_in_problems(session, units):
    """What the run's record lacks after the person chose stand-ins for this job (wicked-crew#1884): the launch
    consent (`assurance.standInAware`, `standIn` scope job via launch, by and at), and a label on every stand-in it
    seated (key `<base>~<slot>`, a core role and state; every unit on a stand-in seat has its binding). As wicked-ci
    S04's `checkStandInRecord`. `[]` when the record is whole."""
    a = (session or {}).get("assurance") or {}
    c = a.get("standIn") or {}
    out = []
    if not (a.get("standInAware") is True and c.get("scope") == "job" and c.get("via") == "launch"
            and isinstance(c.get("by"), str) and c.get("by") and isinstance(c.get("at"), (int, float))):
        out.append(f"no launch consent on the record: standInAware={a.get('standInAware')!r} standIn={c!r}")
    bindings = a.get("standIns")
    if bindings is not None and not isinstance(bindings, list):
        out.append(f"standIns is {bindings!r}")
        bindings = []
    bindings = bindings or []
    for b in bindings:
        base, slot = b.get("base"), b.get("slot")
        if not (isinstance(base, str) and base and isinstance(slot, int) and slot >= 1 and b.get("key") == f"{base}~{slot}"
                and b.get("role") in STAND_IN_ROLES and b.get("state") in STAND_IN_STATES):
            out.append(f"unlabelled stand-in {b!r}")
    keys = {b.get("key") for b in bindings}
    for k in sorted({u.get("assigned_cli") for u in (units or []) if isinstance(u.get("assigned_cli"), str) and "~" in u.get("assigned_cli")}):
        if k not in keys:
            out.append(f"unit on stand-in seat {k} has no binding")
    return out


def stand_in_record(j, rid, answered):
    """After the stand-in choice: the record names the consent and labels each stand-in, the run used at least one,
    and no card asked the person for their own judgment in place of the missing judge."""
    view = j.get(f"/runs/{rid}") or {}
    session = view.get("session") or (run_of(j, rid) or {}).get("session") or {}
    units = view.get("units") or []
    problems = stand_in_problems(session, units)
    bindings = ((session.get("assurance") or {}).get("standIns")) or []
    j.check("stand_in_record_labelled", not problems, problems=problems[:6], standIns=[f"{b.get('key')}/{b.get('role')}/{b.get('state')}" for b in bindings][:10])
    j.check("stand_ins_used_on_the_thin_roster", len(bindings) > 0, standIns=len(bindings))
    j.check("no_own_judgment_in_place_of_a_stand_in", not any(JUDGMENT.search(a) for a in answered), answered=answered)


def gate_post_for(j, rid, since, label, rules_pick, note):
    """Wait for this answer's successful gate POST; other writes cannot stand in for a decision."""
    if rules_pick:
        kind = "skip_rules"
    elif QE_SKIP.search(label):
        kind = "skip_qe"
    elif JUDGMENT.search(label):
        kind = "operator_judgment"
    else:
        kind = "approve"

    def sent_ok(post):
        return (200 <= post["status"] < 300 and post["method"] == "POST"
                and urlsplit(post["url"]).path == f"/api/v1/runs/{rid}/gate"
                and decision_matches(post["body"], kind, note))

    return j.wait(lambda: any(sent_ok(post) for post in j.rec["posts"][since:]), 30, f"the UI to send '{label}'")


def steer(j, rid, until=None, answer_then_return=None, stop_when=None):
    """Answer the run's cards as a person would. With `until(card_text, choices)`, stop and return that card when it
    matches (a journey whose terminal state is a card, not a delivery); with `stop_when()`, hand back as soon as it is
    true (U07: the run sits in its stalled turn); otherwise judge the delivery at the end."""
    p = j.page
    answered, seen, judgments, confirmed = [], [], [], []
    t0 = time.time()
    while time.time() - t0 < 900:
        if stop_when is not None and stop_when():
            return {"answered": answered, "seen": seen}
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
            enabled = [e.inner_text().strip().split("\n")[0] for e in props + gates if e.is_enabled()]
            return {"card": card, "choices": texts, "enabled": enabled, "answered": answered, "judgments": judgments}
        choices = [(e, e.inner_text().strip().split("\n")[0], e.get_attribute("data-choice-key")) for e in props + gates]
        pick, rules_pick = pick_choice(card, choices)
        if pick is None:
            j.check("every_card_has_a_known_way_forward", False, kind=kind, choices=texts, card=(p.get_by_test_id("session-gate-row").last.inner_text()[:600] if p.get_by_test_id("session-gate-row").count() else None))
            j.shot("unknown-card")
            return
        label = pick.inner_text().strip().split("\n")[0]
        j.shots(f"U04-card-{len(answered) + 1}")
        sent_before = len(j.rec["posts"])
        pick.click()
        p.wait_for_timeout(800)
        note = "Hermetic self-test (U04): stub seats; no distinct judge or QE ledger exists here. This proves the governed path and delivery, not the fix."
        # The reason is REQUIRED for a rules skip and a QE skip (the gate's note is `required`): the box must be driven.
        # The plain "Approve as your own judgment" (key approve) carries no note box (the note is optional there); the
        # noted variants (keys steer, operator-judgment) require it. When a box is offered it is filled and must ride.
        sent_note = None
        if QE_SKIP.search(label) or rules_pick or JUDGMENT.search(label):
            box = p.get_by_test_id("session-gate-note").last
            shown = box.count() > 0 and box.is_visible()
            needs_note = QE_SKIP.search(label) or rules_pick or pick.get_attribute("data-choice-key") in ("operator-judgment", "steer")
            if shown or needs_note:
                try:
                    if not (shown and box.is_enabled() and box.is_editable()):
                        j.check("decision_note_field_driven", False, choice=label, reason="note field is not visible and fillable")
                        return
                    box.fill(note)
                except Exception as e:
                    j.check("decision_note_field_driven", False, choice=label, error=str(e)[:200])
                    return
                sent_note = note
                j.check("decision_note_field_driven", True, choice=label)
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
        sent = gate_post_for(j, rid, sent_before, label, rules_pick, sent_note)
        if not sent:
            j.check("each_decision_is_sent", False, choice=label, posts=j.rec["posts"][sent_before:])
            return
        answered.append(label)
        if JUDGMENT.search(label) or rules_pick or QE_SKIP.search(label):
            judgments.append(label)
        p.wait_for_timeout(3000)
    if until is not None or stop_when is not None:
        j.check("the_expected_card_came" if until is not None else "the_expected_state_came", False, status=(run_of(j, rid) or {}).get("session", {}).get("status"), seen=seen[-4:])
        return None
    r = run_of(j, rid) or {}
    s = r.get("session", {})
    # The plan gate and the delivery confirmation are the person's: both must have been answered in the UI.
    j.check("plan_and_delivery_answered_in_the_ui", any(PLAN.search(a) for a in answered) and any(DELIVER.search(a) for a in answered), answered=answered, seen=seen[-6:])
    # The delivery asked "Are you sure?" and the person said yes (a delivery sent from the first press would fail this).
    j.check("delivery_confirmed_with_yes", bool(confirmed), confirmed=confirmed)
    # The thin roster's judgments are the person's, labelled with their reason: disclosed, never hidden.
    j.rec["judgments"] = judgments
    if j.state.get("standIns"):
        stand_in_record(j, rid, answered)
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
