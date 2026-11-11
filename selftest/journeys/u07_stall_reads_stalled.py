"""U07 (J8, hermetic): a stalled run reads stalled, not working.

Path: as U04 (Settings, New job -> /bug -> corpus -> Start, the plan and the judgment cards), but the stub's fix turn sits
silent and idle (scenario `fix: stall`, written by the step with the watchdog's threshold at 1 minute). Once THIS run is in
that turn (the shim's marker names the run's worktree), the person opens the Nerve Center's Runs tab. Passes when, within
4 minutes of the turn going silent, the daemon's own liveness (`GET /system`) and the run's row on the page both say
stalled, with the run still executing in that turn.

Open: wicked-crew#1501 (F-CREW-1501), the engine's 15 s working heartbeat re-arms crew's watchdog. Only that signature
(the run present, still executing, read as "working") carries the label; a missing run or row, a finished run or any other
state is an ordinary failure.
"""
import json
import os
import time

INTENT = "add() in src/add.js returns a - b; fix it so it returns the sum (U07: the fix turn will stall)."
FINDING = "F-CREW-1501"
# 1 minute of silence, then up to two 30 s sweeps, then the page's own refresh: 4 minutes from the turn going silent.
WINDOW_S = 240


def system_row(j, rid):
    runs = (j.get("/system") or {}).get("runs") or []
    return next((r for r in runs if r.get("runId") == rid), None)


def shown_word(row):
    """The row's liveness as the person sees it: the visible label, and only when the row's own data agrees with it
    (a disagreement is reported as such, never as either word)."""
    if row.count() == 0:
        return None
    label = row.first.get_by_test_id("nc-run-liveness")
    text = label.inner_text().strip().lower() if label.count() and label.first.is_visible() else None
    attr = row.first.get_attribute("data-liveness")
    return text if text == attr else "label %r / data %r" % (text, attr)


def marker_of(path, rid):
    """The shim's marker, only when it is THIS run's turn (its worktree path names the run)."""
    try:
        with open(path) as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    return m if rid in str(m.get("cwd", "")) and isinstance(m.get("at"), (int, float)) else None


def run(j):
    u04 = j.load("u04_bug_delivered")
    path = j.state.get("stallMarker")
    u04.qe_off(j)
    rid = u04.launch(j, INTENT, "U07")
    if not rid:
        return
    hit = u04.steer(j, rid, stop_when=lambda: bool(path) and marker_of(path, rid) is not None)
    if not hit:
        return
    m = marker_of(path, rid)
    j.check("run_reached_its_stalled_turn", m is not None, answered=hit.get("answered"), marker=m)
    if m is None:
        return
    deadline = m["at"] / 1000.0 + WINDOW_S
    p = j.page
    p.goto(j.origin + "/watch?tab=runs", wait_until="domcontentloaded")
    j.check("runs_tab_opens", j.wait(lambda: p.get_by_test_id("nerve-center-page").is_visible(), 60, "the Nerve Center"))
    row = p.locator(f'[data-testid="nc-run"][data-run-id="{rid}"]')
    first = {"api": None, "ui": None}
    seen_api, seen_ui = [], []
    last_reload = time.time()
    # One budget for both surfaces, from the moment the turn went silent; the page is reloaded every 30 s in case it
    # refreshes only on navigation.
    while time.time() < deadline and (first["api"] is None or first["ui"] is None):
        # An observation counts only when it was made inside the budget (a slow GET can return after the deadline).
        live = (system_row(j, rid) or {}).get("liveness")
        if not seen_api or seen_api[-1] != live:
            seen_api.append(live)
        if live == "stalled" and first["api"] is None and time.time() <= deadline:
            first["api"] = time.time()
        word = shown_word(row)
        if not seen_ui or seen_ui[-1] != word:
            seen_ui.append(word)
        if word == "stalled" and first["ui"] is None and time.time() <= deadline:
            first["ui"] = time.time()
        if time.time() - last_reload > 30:
            p.reload(wait_until="domcontentloaded")
            last_reload = time.time()
        p.wait_for_timeout(2000)
    after = lambda k: None if first[k] is None else round(first[k] - m["at"] / 1000.0)
    # The preconditions of the verdict, unlabelled: the run is still in its silent turn and both surfaces list it.
    r = u04.run_of(j, rid) or {}
    status = r.get("session", {}).get("status")
    srow = system_row(j, rid)
    j.check("run_still_executing_in_its_silent_turn", status == "executing", status=status)
    j.check("daemon_lists_the_run", srow is not None, liveness=(srow or {}).get("liveness"))
    j.check("nerve_center_lists_the_run", row.count() > 0, seen=seen_ui[-6:])
    # The verdict. Labelled only when it shows the heartbeat's signature: the run read as working.
    # A pass carries the label too, so the expected-fail policy reports UNEXPECTED-PASS when crew#1501 is fixed and the
    # label has not been retired yet.
    live, reason = (srow or {}).get("liveness"), (srow or {}).get("reason")
    j.check("daemon_calls_it_stalled", first["api"] is not None, **({"finding": FINDING} if first["api"] is not None or live == "working" else {}),
            liveness=live, reason=reason, seen=seen_api[-6:], after_s=after("api"), window_s=WINDOW_S)
    word = shown_word(row)
    j.check("nerve_center_row_reads_stalled", first["ui"] is not None, **({"finding": FINDING} if first["ui"] is not None or word == "working" else {}),
            word=word, seen=seen_ui[-6:], after_s=after("ui"), window_s=WINDOW_S)
    j.shots("U07-stalled")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
