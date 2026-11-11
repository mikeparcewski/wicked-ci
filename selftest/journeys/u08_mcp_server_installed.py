"""U08 (PRODUCT-WORKS J6): New job -> /workflow-mcp-server -> corpus -> plan/steering cards -> install consent
-> completed -> MCP -> the installed row -> Inspect -> Connect -> echo -> the server's answer -> Disconnect.

Only clicks send writes. GETs corroborate the run/registry; observed browser responses bind the launch, consent and
call to those clicks. The inspector must already have a consented editor claiming mcp-server (see U08-DESIGN.md).
Missing plugin/grant/selectors fail explicitly; no fixture is installed or request synthesized to fill that gap.
"""
import json
import re

SERVER = "selftest-u08-mcp"
TAG = "U08: build and install an MCP server"
INTENT = (TAG + ". Build selftest-u08-mcp in the corpus repository's selftest-u08-mcp/ directory: a minimal "
          "TypeScript stdio server with one credential-free, local-only read-only echo({text}) tool. "
          "No upstream or HTTP transport. Include dist/server.js, package.json and its lock, "
          "mcp-server.config.json (key selftest-u08-mcp, auth none), tools.json, build/typecheck/lint/test scripts "
          "and a real stdio contract test. Keep the existing corpus tests; correct its seeded add arithmetic "
          "defect if necessary to keep them green. Deliver and ask to install for workers.")
TERMINAL = ("completed", "failed", "cancelled")


def run(j):
    p = j.page
    u04 = j.load("u04_bug_delivered")
    # Record the UI's request bodies as well as driver.py's write receipts. This is observation only.
    wire = []

    def observe(response):
        req = response.request
        if req.method not in ("POST", "DELETE") or not response.url.startswith(j.origin + "/api/v1/"):
            return
        try:
            body = json.loads(req.post_data or "{}")
        except (ValueError, TypeError):
            body = None
        reply = None
        if req.method == "POST" and "/mcp-inspect/" in response.url:
            try:
                reply = response.json()
            except Exception:
                pass  # no JSON receipt: the corresponding check fails, observation must not crash the page
        wire.append({"path": response.url[len(j.origin + "/api/v1"):].split("?")[0],
                     "method": req.method, "status": response.status, "body": body,
                     "response": reply})

    p.on("response", observe)
    j.rec["u08_ui_requests"] = wire
    before_servers = j.get("/mcp/servers").get("servers", [])
    if not j.check("server_is_not_already_installed", not any(s.get("name") == SERVER for s in before_servers)):
        return
    u04.qe_off(j)  # the same disclosed thin-roster/no-ledger choice as U04, made through Settings
    rid = launch(j, u04, wire)
    if not rid:
        return

    def is_consent(card, choices):
        s = (u04.run_of(j, rid) or {}).get("session", {})
        return (s.get("awaitingHuman") or {}).get("gateKind") == "consent"

    hit = u04.steer(j, rid, until=is_consent)
    if not hit:
        return
    j.rec["judgments"] = hit.get("judgments", [])
    j.check("plan_and_delivery_precede_install", any(u04.PLAN.search(a) for a in hit["answered"])
            and any(u04.DELIVER.search(a) for a in hit["answered"]), answered=hit["answered"])
    # Reaching the consent card must not already have registered the server.
    j.check("nothing_installed_before_consent", not any(s.get("name") == SERVER for s in j.get("/mcp/servers").get("servers", [])))
    row = p.get_by_test_id("session-gate-row").last
    more = row.get_by_test_id("session-gate-more-about")
    if more.count() and more.get_attribute("open") is None:
        more.locator("summary").first.click()
    writes = row.locator('[data-testid="session-gate-consent-writes"][data-choice-key="consent:worker"]')
    if not j.check("install_consent_lists_worker_files", writes.count() == 1, card=hit["card"][:800]):
        return
    if writes.get_attribute("open") is None:
        writes.locator("summary").click()
    targets = writes.get_by_test_id("session-gate-consent-write")
    if not j.check("worker_install_writes_program_owned_files", targets.count() > 0
                   and all(e.get_attribute("data-own") == "false" for e in targets.all()), files=writes.inner_text()):
        return
    choice = row.locator('[data-testid="session-gate-choice"][data-choice-key="consent:worker"]')
    if not j.check("worker_consent_is_offered", choice.count() == 1 and choice.is_enabled(), choices=hit["choices"]):
        return
    j.shots("U08-install-consent")
    n0 = len(wire)
    choice.click()
    # AskCard uses these same controls as U04; wait for the undo window's own POST before leaving.
    p.wait_for_timeout(800)
    for tid in ("session-gate-send", "session-gate-confirm"):
        b = row.get_by_test_id(tid)
        if b.count() and b.first.is_visible() and b.first.is_enabled():
            b.first.click()
            p.wait_for_timeout(1200)
    sent = j.wait(lambda: any(w["path"] == f"/runs/{rid}/gate" and w["method"] == "POST"
                             and 200 <= w["status"] < 300 and isinstance(w["body"], dict)
                             and w["body"].get("approve") is True and w["body"].get("action") == "consent:worker"
                             for w in wire[n0:]), 30, "the UI's worker consent POST")
    if not j.check("install_consented_in_the_ui", sent, writes=wire[n0:]):
        return
    # Hand subsequent steering back to the shared helper, without U04's bug-specific terminal assertions.
    u04.steer(j, rid, stop_when=lambda: (u04.run_of(j, rid) or {}).get("session", {}).get("status") in TERMINAL)
    s = (u04.run_of(j, rid) or {}).get("session", {})
    if not j.check("run_completed_after_consent", s.get("status") == "completed", status=s.get("status")):
        return
    qe = (s.get("assurance") or {}).get("qe") or {}
    j.check("qe_labelled_not_passed", qe.get("basis") == "operator" and qe.get("status") in ("skipped", "not_required", "waived"), qe=qe)
    p.goto(f"{j.origin}/s/run%3A{rid}", wait_until="domcontentloaded")
    j.check("completion_shown_on_run_page", j.wait(lambda: re.search(r"Finished\s*·\s*delivered", p.inner_text("body")), 60, "the finished run"))
    j.shots("U08-installed-run")
    installed(j, wire)
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])


def launch(j, u04, wire):
    """U04's New job/repository/proposal path, choosing the catalog's explicit MCP workflow command."""
    p = j.page
    p.goto(j.origin + "/jobs", wait_until="domcontentloaded")
    if not j.check("rail_visible", j.wait(lambda: p.get_by_test_id("desk-rail-new-job").is_visible(), 90, "the rail")):
        return None
    before = {r["session"]["id"] for r in j.get("/runs?limit=200").get("runs", [])}
    n0 = len(wire)
    p.get_by_test_id("desk-rail-new-job").click()
    item = p.locator('[data-testid="composer-menu-item"][data-cmd="/workflow-mcp-server"]')
    # New job can show the catalog immediately; filtering the person's composer text also reaches a long menu.
    if not item.count():
        p.get_by_test_id("session-composer-input").fill("/workflow-mcp-server")
    if not j.check("mcp_workflow_command_offered", j.wait(lambda: item.count() > 0 and item.first.is_visible(), 60, "the /workflow-mcp-server command")):
        return None
    item.first.click()
    p.get_by_test_id("session-composer-input").fill(INTENT)
    p.keyboard.press("Enter")
    if not j.check("asks_which_repository", j.wait(lambda: p.get_by_test_id("job-passage-repo").filter(has_text="corpus").count() > 0, 120, "the repository question")):
        return None
    p.get_by_test_id("job-passage-repo").filter(has_text="corpus").first.click()
    if not j.check("proposal_shown", j.wait(lambda: p.get_by_test_id("job-passage-review-plan-toggle").count() > 0, 120, "the proposal")):
        return None
    tg = p.get_by_test_id("job-passage-review-plan-toggle").first
    if (tg.get_attribute("aria-checked") or tg.get_attribute("aria-pressed")) != "true":
        tg.click()
        p.wait_for_timeout(800)
    j.shots("U08-proposal")
    p.get_by_role("button", name=re.compile(r"^Start")).first.click() if p.get_by_role("button", name=re.compile(r"^Start")).count() else p.get_by_text(re.compile(r"^Start v\d")).first.click()
    rid = j.wait(lambda: next((r["session"]["id"] for r in j.get("/runs?limit=200").get("runs", [])
                               if r["session"]["id"] not in before and TAG in (r["session"].get("problem") or "")), None), 120, "the MCP run to exist")
    j.state["runId"] = rid
    # The new run is the one our words launched; the browser's successful launch request must name this workflow.
    j.check("mcp_run_launched_from_the_ui", rid is not None and any(w["method"] == "POST" and w["path"] == "/runs"
            and 200 <= w["status"] < 300 and (w["body"] or {}).get("workflow") == "mcp-server" for w in wire[n0:]), run=rid, writes=wire[n0:])
    return rid


def installed(j, wire):
    p = j.page
    p.goto(j.origin + "/mcp", wait_until="domcontentloaded")
    row = p.locator(f'[data-testid="mcp-server-row"][data-server="{SERVER}"]')
    if not j.check("installed_server_listed_in_mcp", j.wait(lambda: row.is_visible(), 60, "the installed MCP row")):
        return
    if row.get_attribute("data-open") != "true":
        row.get_by_test_id("mcp-server-toggle").click()
    tool = row.locator(f'[data-testid="mcp-tool-row"][data-subject="mcp:{SERVER}/echo"]')
    j.check("installed_echo_listed", j.wait(lambda: tool.is_visible(), 30, "echo in the server row"))
    server = next((s for s in j.get("/mcp/servers").get("servers", []) if s.get("name") == SERVER), {})
    args = server.get("args") or []
    # The registry must point at the staged copy, not the run's source worktree or an unrelated fixture.
    j.check("registry_points_at_installed_copy", server.get("kind") == "mcp-stdio" and server.get("enabled") is True
            and any(f"/mcp-servers/{SERVER}/current/" in a and a.endswith("/dist/server.js") for a in args),
            args=args, health=server.get("health"))
    j.check("server_health_shown_ok", "health ok" in row.get_by_test_id("mcp-server-health").inner_text())
    j.shots("U08-mcp-listed")
    row.get_by_test_id("mcp-server-inspect").click()
    ready = j.wait(lambda: p.get_by_test_id("mcp-inspect-ready").is_visible()
                   or p.get_by_test_id("mcp-inspect-no-plugin").is_visible()
                   or p.get_by_test_id("mcp-inspect-unsupported").is_visible(), 60, "the MCP inspector")
    if not j.check("inspector_editor_available", ready and p.get_by_test_id("mcp-inspect-ready").is_visible(),
                   detail=p.inner_text("body")[:1200]):
        j.shots("U08-inspector-unavailable")
        return
    connect = p.get_by_test_id("mcp-inspect-connect")
    if not j.check("inspector_has_install_grant", j.wait(lambda: connect.is_enabled(), 30, "the editor's mcp.session grant")):
        return
    j.check("inspector_targets_installed_server", p.get_by_test_id("mcp-inspect-server").input_value() == SERVER)
    n0 = len(wire)
    connect.click()
    live = p.locator('[data-testid="mcp-inspect-state"][data-state="ready"]')
    if not j.check("installed_server_connected", j.wait(lambda: live.is_visible(), 45, "the installed server connection")
                   and any(w["method"] == "POST" and w["path"] == "/mcp-inspect/sessions" and 200 <= w["status"] < 300
                           and (w["body"] or {}).get("target") == {"server": SERVER} for w in wire[n0:]), writes=wire[n0:]):
        return
    started = next(w for w in wire[n0:] if w["path"] == "/mcp-inspect/sessions" and w["method"] == "POST"
                   and 200 <= w["status"] < 300 and (w["body"] or {}).get("target") == {"server": SERVER})
    sid = (started.get("response") or {}).get("session", {}).get("id")
    if not j.check("connected_session_identified", isinstance(sid, str) and bool(sid)):
        return
    try:
        # These are the inspector plugin's selectors exercised in studio/e2e/desk_mcp_inspect_test.py. They are a
        # prerequisite of this draft, not a universal host contract; absence fails, never triggers an API fallback.
        plugin = p.get_by_test_id("plugin-card").frame_locator('[data-testid="editor-frame"]')
        echo = plugin.locator('[data-item="echo"]')
        if not j.check("inspector_lists_installed_echo", j.wait(lambda: echo.is_visible(), 30, "the inspector's echo tool")):
            return
        echo.click()
        text = "U08 person called the installed server"
        plugin.locator('input[data-arg="text"]').fill(text)
        n0 = len(wire)
        plugin.get_by_test_id("plugin-call").click()
        result = plugin.get_by_test_id("plugin-result")
        answered = j.wait(lambda: text in result.inner_text() and result.get_attribute("data-error") == "0", 30, "echo's answer in the inspector")
        calls = p.get_by_test_id("mcp-inspect-calls")
        j.check("installed_echo_called_through_the_ui", answered and "tools/call echo" in calls.inner_text()
                and any(w["method"] == "POST" and w["path"] == f"/mcp-inspect/sessions/{sid}/rpc"
                        and 200 <= w["status"] < 300 and w["body"] == {"method": "tools/call", "params": {"name": "echo", "arguments": {"text": text}}}
                        and ((w.get("response") or {}).get("response") or {}).get("result") == {"content": [{"type": "text", "text": text}], "isError": False}
                        for w in wire[n0:]), result=result.inner_text()[:600], calls=calls.inner_text(), writes=wire[n0:])
        j.shots("U08-installed-echo-called")
    finally:
        n0 = len(wire)
        p.get_by_test_id("mcp-inspect-disconnect").click()
        j.check("inspector_disconnected_in_the_ui", j.wait(lambda: any(w["method"] == "DELETE"
                and w["path"] == f"/mcp-inspect/sessions/{sid}" and 200 <= w["status"] < 300 for w in wire[n0:]), 30, "Disconnect to close the session"))
