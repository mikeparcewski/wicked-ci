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
import math
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
STAND_IN_LABEL = "Use stand-ins for this job"
# The card's own disclosure (crew `preflightRefusal`): a stand-in is a labelled check, not an independent review.
NOT_INDEPENDENT = re.compile(r"\bnot independent reviews?\b", re.I)
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
    """The current card's "Use stand-ins for this job" reply when it asks the stand-in choice: `(element, None)`, or
    `(None, why)` naming what the card offers instead. Only the newest job card counts, and only its first choice
    (`data-reply="choice:0"`) with exactly that label: the other choice ("Back to the job") or a wider one never."""
    passage = p.get_by_test_id("job-passage").last
    if passage.count() == 0 or passage.get_by_test_id("job-passage-question").count() == 0:
        return None, "no question on the card"
    replies = [(e, e.get_attribute("data-reply") or "", e.inner_text().strip()) for e in passage.get_by_test_id("job-passage-reply").all() if e.is_visible()]
    hits = [e for e, key, text in replies if key == "choice:0" and text.split("\n")[0].strip() == STAND_IN_LABEL and e.is_enabled()]
    if len(hits) == 1:
        return hits[0], None
    return None, f"replies {[(key, text[:60]) for _, key, text in replies]}"


def press_start(p):
    if p.get_by_role("button", name=re.compile(r"^Start")).count():
        p.get_by_role("button", name=re.compile(r"^Start")).first.click()
    else:
        p.get_by_text(re.compile(r"^Start v\d")).first.click()


def card_start(p):
    """The newest job card's own Start reply, when it is shown and enabled; else None."""
    b = p.get_by_test_id("job-passage").last.locator('[data-testid="job-passage-reply"][data-reply="start"]')
    return b.first if b.count() == 1 and b.first.is_visible() and b.first.is_enabled() else None


def chat_of(url):
    """The chat id of a `/api/v1/chats/<id>/proposals[/...]` path, or None."""
    m = re.match(r"^/api/v1/chats/([^/]+)/proposals(?:/|$)", urlsplit(url).path)
    return m.group(1) if m else None


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

    # The Start either launches, or (a thin roster, wicked-crew#1884) reopens the card with the stand-in question. One
    # budget for the whole launch, so the steps that follow keep theirs.
    deadline = time.time() + 240
    left = lambda: max(1, deadline - time.time())  # noqa: E731
    asked = []

    def launched_or_asked():
        q = p.get_by_test_id("job-passage").last.get_by_test_id("job-passage-question")
        if q.count() and "stand-in" in q.first.inner_text().lower():
            asked.append(True)
            return True
        return new_run() is not None

    if not j.wait(launched_or_asked, left(), "the run to exist, or the stand-in question"):
        j.check("run_launched_from_the_ui", False, stage="waiting for the run or the stand-in question", writes=j.rec["writes"][-6:])
        return None
    j.state["standIns"] = bool(asked)
    if asked:
        text = p.get_by_test_id("job-passage").last.get_by_test_id("job-passage-question").first.inner_text()
        reply, why = stand_in_reply(p)
        j.check("stand_in_choice_asked_on_the_card", reply is not None and NOT_INDEPENDENT.search(text) is not None, question=text[:600], replies=why)
        j.shots(f"{label}-stand-in-question")
        if reply is None:
            return None
        version = p.get_by_test_id("job-passage").last.get_attribute("data-version")
        refused = [w for w in j.rec["posts"] if w["status"] == 409 and chat_of(w["url"]) is not None]
        chat = chat_of(refused[-1]["url"]) if refused else None
        n0 = len(j.rec["posts"])
        reply.click()

        def consent_sent():
            # The person's revision of this chat's card: exactly the stand-in choice, from the question.
            return next((w for w in j.rec["posts"][n0:] if w["status"] == 201 and w["method"] == "POST" and chat is not None
                         and urlsplit(w["url"]).path == f"/api/v1/chats/{chat}/proposals" and isinstance(w["body"], dict)
                         and w["body"].get("edits") == {"standIns": True} and w["body"].get("source") == "question"), None)

        sent = j.wait(consent_sent, min(30, left()), "the stand-in choice to be sent")
        j.check("stand_in_choice_pressed", bool(sent), chat=chat, posts=[(w["status"], w["url"], w["body"]) for w in j.rec["posts"][n0:]][-4:])
        if not sent:
            return None
        # The revised card (a new version) shows its own Start: that card launches with stand-ins for this job.
        start_btn = j.wait(lambda: p.get_by_test_id("job-passage").last.get_attribute("data-version") != version and card_start(p), min(60, left()), "the revised card's Start")
        if not start_btn:
            j.check("run_launched_from_the_ui", False, stage="waiting for the revised card's Start", version=version)
            return None
        n1 = len(j.rec["posts"])
        start_btn.click()
        # Its Start is a 2xx answer on the same chat's proposal route.
        started = j.wait(lambda: any(200 <= w["status"] < 300 and chat_of(w["url"]) == chat and urlsplit(w["url"]).path != f"/api/v1/chats/{chat}/proposals" for w in j.rec["posts"][n1:]), min(60, left()), "the revised card's Start to launch")
        j.state["standInStart"] = [(w["status"], w["url"]) for w in j.rec["posts"][n1:]][-3:]
        if not started:
            # The revised card's own Start must answer 2xx: a run found later, or an earlier 2xx write, is not it.
            j.check("run_launched_from_the_ui", False, stage="the revised card's Start was not answered 2xx", posts=j.state["standInStart"])
            return None
    rid = j.wait(new_run, left(), "the run to exist")
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


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def stand_in_problems(session, units):
    """What the run's record lacks after the person chose stand-ins for this job (wicked-crew#1884): the launch
    consent (`assurance.standInAware`, `standIn` scope job via launch, by and at), and a label on every stand-in it
    seated (key `<base>~<slot>`, a core role and state; every unit on a stand-in seat has its binding). As wicked-ci
    S04's `checkStandInRecord`. `[]` when the record is whole; never raises on a malformed record."""
    a = (session or {}).get("assurance") if isinstance(session, dict) else None
    a = a if isinstance(a, dict) else {}
    c = a.get("standIn") if isinstance(a.get("standIn"), dict) else {}
    out = []
    if not (a.get("standInAware") is True and c.get("scope") == "job" and c.get("via") == "launch"
            and isinstance(c.get("by"), str) and c.get("by") and _num(c.get("at"))):
        out.append(f"no launch consent on the record: standInAware={a.get('standInAware')!r} standIn={a.get('standIn')!r}"[:300])
    keys = set()
    for b in bindings_of(session, out):
        base, slot, key, role, state = (b.get(f) for f in ("base", "slot", "key", "role", "state"))
        # Every field is checked for its type before any set or string use, so a malformed one is named, never raised.
        if not (isinstance(base, str) and base and isinstance(slot, int) and not isinstance(slot, bool) and 1 <= slot <= 0xFFFFFFFF
                and isinstance(key, str) and key == f"{base}~{slot}" and isinstance(role, str) and role in STAND_IN_ROLES
                and isinstance(state, str) and state in STAND_IN_STATES):
            out.append(f"unlabelled stand-in {b!r}"[:300])
        if isinstance(key, str):
            keys.add(key)
    if units is not None and not isinstance(units, list):
        out.append(f"units is {units!r}"[:300])
        units = []
    seats = set()
    for u in units or []:
        cli = u.get("assigned_cli") if isinstance(u, dict) else None
        if not isinstance(u, dict) or not (cli is None or isinstance(cli, str)):
            out.append(f"malformed unit {u!r}"[:300])
        elif isinstance(cli, str):
            seats.add(cli)
    for k in sorted(k for k in seats if "~" in k):
        if k not in keys:
            out.append(f"unit on stand-in seat {k} has no binding")
    return out


def bindings_of(session, problems):
    """The record's stand-in bindings that are objects; anything else is named in `problems`."""
    a = (session or {}).get("assurance") if isinstance(session, dict) else None
    if not isinstance(a, dict) or "standIns" not in a:
        return []  # omitted: no stand-in seated (S04 accepts only the omitted list as empty)
    raw = a.get("standIns")
    if not isinstance(raw, list):
        problems.append(f"standIns is {raw!r}"[:300])
        return []
    bad = [b for b in raw if not isinstance(b, dict)]
    if bad:
        problems.append(f"standIns holds non-objects {bad!r}"[:300])
    return [b for b in raw if isinstance(b, dict)]


def stand_in_record(j, rid, answered, used=True):
    """After the stand-in choice: the record names the consent and labels each stand-in; with `used`, at least one
    stand-in answered (a seat only reserved is not a check); and no card offered or took the person's own judgment in
    place of the missing judge."""
    try:
        view = j.get(f"/runs/{rid}") or {}
    except Exception as e:  # noqa: BLE001 - a busy daemon: named in the check, not a crash
        view = {"error": repr(e)[:200]}
    view = view if isinstance(view, dict) else {"error": f"not an object: {view!r}"[:200]}
    # GET /runs/:id answers `{ run: SessionView }` (crew's endpoint manifest): the session and its units. Its own
    # answer is the record: a failed read, or one without its units, is named rather than read around.
    run = view.get("run") if isinstance(view.get("run"), dict) else {}
    session = run.get("session") if isinstance(run.get("session"), dict) else {}
    units = run.get("units")
    problems = []
    if "error" in view:
        problems.append(f"GET /runs/{rid}: {view['error']}")
    elif not (isinstance(units, list) and units):
        problems.append(f"GET /runs/{rid} returned no units: {units!r}"[:300])
    problems += stand_in_problems(session, units)
    bindings = bindings_of(session, [])
    j.check("stand_in_record_labelled", not problems, problems=problems[:6], standIns=[f"{b.get('key')}/{b.get('role')}/{b.get('state')}" for b in bindings][:10])
    if used:
        j.check("stand_ins_used_on_the_thin_roster", any(b.get("state") == "answered" for b in bindings), standIns=[f"{b.get('key')}/{b.get('state')}" for b in bindings][:10])
    seen = j.state.get("judgeCards") or []
    j.check("no_own_judgment_in_place_of_a_stand_in", not seen and not any(JUDGMENT.search(a) for a in answered), answered=answered, judge_cards=seen[:3])


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
            # The run settled between `stop_when`'s read and this one: a stop condition that now holds still wins.
            if stop_when is not None and stop_when():
                return {"answered": answered, "seen": seen}
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
        if j.state.get("standIns") and JUDGE_CARD.search(card):
            # With stand-ins for the job, the missing judge is a labelled stand-in: this card should not come.
            j.state.setdefault("judgeCards", []).append({"card": card[:400], "choices": texts})
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
