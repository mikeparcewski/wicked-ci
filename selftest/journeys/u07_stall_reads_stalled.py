"""U07 (J8, hermetic): a stalled run reads stalled, not working.

Path: as U04 (Settings, New job -> /bug -> corpus -> Start, the plan and the judgment cards), but the stub's fix turn sits
silent and idle (scenario `fix: stall`, written by the step with the watchdog's threshold at 1 minute). Once the run is
in that turn, the person opens the Nerve Center's Runs tab. Passes when, within the threshold plus two sweeps, the
daemon's own liveness (`GET /system`) and the run's row on the page both say stalled, and the row never says working.
Open: wicked-crew#1501 (F-CREW-1501), the engine's 15 s working heartbeat re-arms crew's watchdog.
"""
import os
import time

INTENT = "add() in src/add.js returns a - b; fix it so it returns the sum (U07: the fix turn will stall)."
FINDING = "F-CREW-1501"
# 1 minute of silence, then up to two 30 s sweeps, then the page's own refresh: 4 minutes is generous.
WAIT_S = 240


def liveness_of(j, rid):
    runs = (j.get("/system") or {}).get("runs") or []
    row = next((r for r in runs if r.get("runId") == rid), None)
    return (row or {}).get("liveness"), (row or {}).get("reason")


def run(j):
    u04 = j.load("u04_bug_delivered")
    marker = j.state.get("stallMarker")
    u04.qe_off(j)
    rid = u04.launch(j, INTENT, "U07")
    if not rid:
        return
    hit = u04.steer(j, rid, stop_when=lambda: bool(marker) and os.path.exists(marker))
    if not hit:
        return
    j.check("run_reached_its_stalled_turn", True, answered=hit.get("answered"))
    t_stall = time.time()
    p = j.page
    p.goto(j.origin + "/watch?tab=runs", wait_until="domcontentloaded")
    j.check("runs_tab_opens", j.wait(lambda: p.get_by_test_id("nerve-center-page").is_visible(), 60, "the Nerve Center"))
    row = p.locator(f'[data-testid="nc-run"][data-run-id="{rid}"]')
    seen = []

    def stalled_on_page():
        if row.count() == 0:
            seen.append("no row")
            return False
        word = row.first.get_attribute("data-liveness")
        if not seen or seen[-1] != word:
            seen.append(word)
        return word == "stalled"

    shown = j.wait(stalled_on_page, WAIT_S, "the run's row to read stalled")
    if not shown:  # the page may only refresh on navigation: one reload before the verdict
        p.reload(wait_until="domcontentloaded")
        shown = j.wait(stalled_on_page, 30, "the run's row after a reload")
    live, reason = liveness_of(j, rid)
    j.check("daemon_calls_it_stalled", live == "stalled", finding=FINDING, liveness=live, reason=reason, after_s=round(time.time() - t_stall))
    j.check("nerve_center_row_reads_stalled", bool(shown), finding=FINDING, seen=seen[-6:], after_s=round(time.time() - t_stall))
    word = row.first.inner_text().split("\n")[0].strip().lower() if row.count() else None
    j.check("row_never_says_working", word is not None and word != "working", finding=FINDING, word=word)
    j.shots("U07-stalled")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
