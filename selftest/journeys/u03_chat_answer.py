"""U03 (J3, shape): a person asks a question in chat and gets an answer under it, from a named helper.

Path: the rail's Chat -> type a question about the fixture repo -> Send.
Passes when: the UI opened a chat (POST /chats 201) and sent the message (POST /chats/:id/messages 202); the answer
appears in the thread AFTER the question, visible, with a body that answers THIS question (the stub quotes it and cites
src/add.js), and its own footer names the helper that answered; no page error. The stub's wording is not otherwise judged (a stub proves the wire and the layout, not an answer's quality: that is the `live` profile).
"""
import re

QUESTION = "What does add() in src/add.js return?"


def run(j):
    p = j.page
    p.goto(j.origin + "/jobs", wait_until="domcontentloaded")
    j.check("rail_chat_visible", j.wait(lambda: p.get_by_test_id("desk-rail-chat").is_visible(), 90, "the rail's Chat"))
    p.get_by_test_id("desk-rail-chat").click()
    j.check("composer_opens", j.wait(lambda: p.get_by_test_id("assist-input").is_visible(), 30, "the chat composer"))
    p.get_by_test_id("assist-input").fill(QUESTION)
    p.get_by_test_id("assist-send").click()
    answered = j.wait(lambda: p.get_by_test_id("assist-chat-msg").count() > 0 and p.get_by_test_id("assist-answer-footer").count() > 0, 180, "the answer")
    j.check("an_answer_arrives", answered)
    p.wait_for_timeout(1500)
    order = p.evaluate("""() => [...document.querySelectorAll('[data-testid="assist-user-msg"], [data-testid="assist-chat-msg"]')]
                           .map(e => ({kind: e.dataset.testid, text: e.innerText.slice(0, 80)}))""")
    q = next((i for i, m in enumerate(order) if m["kind"] == "assist-user-msg" and QUESTION[:30] in m["text"]), None)
    a = next((i for i, m in enumerate(order) if m["kind"] == "assist-chat-msg" and q is not None and i > q), None)
    j.check("answer_sits_under_its_question", q is not None and a is not None, order=order[:6])
    # The answer itself: visible, completed, and the seat's words about THIS question (the stub's reply quotes it), with
    # its attribution inside the same answer.
    ans = p.get_by_test_id("assist-chat-msg").last
    ans_text = ans.inner_text() if ans.count() and ans.is_visible() else ""
    # The stub's SUBSTANCE (not only its echo of the question): add() returns the difference.
    j.check("the_answer_has_a_body", "You asked:" in ans_text and QUESTION in ans_text and "a - b" in ans_text and "the difference" in ans_text, text=ans_text[:240])
    footer_el = ans.locator('[data-testid="assist-answer-footer"]')
    footer = footer_el.first.inner_text() if footer_el.count() and footer_el.first.is_visible() else ""
    # Rendered placement: the question is visible and drawn above its answer.
    qel = p.get_by_test_id("assist-user-msg").filter(has_text=QUESTION[:30]).last
    qb = qel.bounding_box() if qel.count() and qel.is_visible() else None
    ab = ans.bounding_box() if ans.count() else None
    j.check("question_drawn_above_answer", qb is not None and ab is not None and qb["y"] + qb["height"] <= ab["y"] + 1, question=qb, answer=ab)
    j.check("answer_names_its_helper", bool(re.search(r"Answered by \S", footer)), footer=footer[:160])
    writes = j.rec["writes"]
    j.check("ui_opened_a_chat", any(re.match(r"201 POST /api/v1/chats$", w) for w in writes), writes=writes)
    j.check("ui_sent_the_message", any(re.match(r"202 POST /api/v1/chats/[^/]+/messages$", w) for w in writes), writes=writes)
    j.shots("U03-chat-answered")
    j.check("no_page_errors", not j.rec["page_errors"], errors=j.rec["page_errors"][:5])
