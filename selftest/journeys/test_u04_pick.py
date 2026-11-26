"""U04's choice picker and decision evidence, without a browser."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import u04_bug_delivered as u04  # noqa: E402

RULES_CARD = "The rule POL-2101 needs your call before this step can go on"
OTHER_CARD = "The plan is ready for your review"


def pick(card, *choices):
    e, rules = u04.pick_choice(card, [(text, text, key) for text, key in choices])
    return e, rules


class PickChoice(unittest.TestCase):
    def test_qe_skip_requires_its_key_and_specific_wording(self):
        for label in ("Skip QE", "Skip acceptance", "Skip with a reason"):
            with self.subTest(label=label):
                self.assertEqual(pick(OTHER_CARD, (label, None)), (None, False))
        self.assertEqual(pick(OTHER_CARD, ("Skip QE", "skip-qe")), ("Skip QE", False))
        self.assertEqual(pick(OTHER_CARD, ("Skip the acceptance checks", "skip-qe")), ("Skip the acceptance checks", False))
        self.assertEqual(pick(OTHER_CARD, ("Skip with a reason", "skip-qe")), (None, False))
        self.assertEqual(pick(OTHER_CARD, ("Skip QE", "steer")), (None, False))

    def test_delivery_requires_the_label_start_and_cannot_use_a_skip_or_judgment_key(self):
        for label in ("Pushover", "Push", "Do not open the PR", "Do not deliver"):
            with self.subTest(label=label):
                self.assertEqual(pick(OTHER_CARD, (label, None)), (None, False))
        for key in ("skip-rules", "skip-qe", "operator-judgment"):
            with self.subTest(key=key):
                self.assertEqual(pick(OTHER_CARD, ("Deliver", key)), (None, False))
        self.assertEqual(pick(OTHER_CARD, ("Deliver the change", "approve")), ("Deliver the change", False))
        self.assertEqual(pick(OTHER_CARD, ("Open the PR", "steer")), ("Open the PR", False))

    def test_the_keyed_rules_skip_is_taken_on_the_rules_card(self):
        self.assertEqual(pick(RULES_CARD, ("Retry this step", "retry"), ("Skip 5 rules", "skip-rules")), ("Skip 5 rules", True))
        self.assertEqual(pick(RULES_CARD, ("Skip POL-2101", "skip-rules")), ("Skip POL-2101", True))

    def test_the_key_wins_over_an_earlier_lookalike_label(self):
        # An earlier "Skip POL-2101" with another key is not the rules skip; the keyed one is.
        self.assertEqual(pick(RULES_CARD, ("Skip POL-2101", "skip-qe"), ("Skip the rule", "skip-rules")), ("Skip the rule", True))

    def test_wording_fallback_only_without_a_key_and_only_the_whole_label(self):
        self.assertEqual(pick(RULES_CARD, ("Confirm or skip 3 rules", None)), ("Confirm or skip 3 rules", True))
        self.assertEqual(pick(RULES_CARD, ("Skip POL-2101 and all checks", None)), (None, False))
        self.assertEqual(pick(RULES_CARD, ("Skip 5 rules", "send-back")), (None, False))

    def test_a_rules_skip_is_never_taken_off_the_rules_card(self):
        self.assertEqual(pick(OTHER_CARD, ("Skip 5 rules", "skip-rules")), (None, False))
        self.assertEqual(pick(OTHER_CARD, ("Skip QE-123", "skip-rules")), (None, False))
        self.assertEqual(pick(OTHER_CARD, ("Skip PUSH-1", "skip-rules")), (None, False))
        self.assertEqual(pick(OTHER_CARD, ("Approve plan", "approve"), ("Skip 5 rules", None)), ("Approve plan", False))


NOTE = "Hermetic self-test: no distinct judge or QE ledger."


class DecisionMatches(unittest.TestCase):
    def test_plain_approval_requires_boolean_true(self):
        self.assertTrue(u04.decision_matches({"approve": True}, "approve", NOTE))
        for body in (None, [], "approve", {}, {"approve": False}, {"approve": 1}, {"approve": "true"}):
            with self.subTest(body=body):
                self.assertFalse(u04.decision_matches(body, "approve", NOTE))

    def test_rules_skip_requires_the_action_and_every_reason(self):
        valid = {"action": "skip_rules", "skipRules": [{"id": "POL-1", "reason": NOTE}, {"id": "POL-2", "reason": NOTE}]}
        self.assertTrue(u04.decision_matches(valid, "skip_rules", NOTE))
        for body in (
            {**valid, "action": "skip_qe"},
            {"approve": True},
            {**valid, "skipRules": []},
            {**valid, "skipRules": None},
            {**valid, "skipRules": {}},
            {**valid, "skipRules": [None]},
            {**valid, "skipRules": [{"id": "POL-1"}]},
            {**valid, "skipRules": [valid["skipRules"][0], {"id": "POL-2", "reason": "different"}]},
        ):
            with self.subTest(body=body):
                self.assertFalse(u04.decision_matches(body, "skip_rules", NOTE))

    def test_qe_skip_requires_its_action_and_exact_note(self):
        self.assertTrue(u04.decision_matches({"action": "skip_qe", "amend": NOTE}, "skip_qe", NOTE))
        for body in ({"approve": True, "amend": NOTE}, {"action": "skip_rules", "amend": NOTE},
                     {"action": "skip_qe"}, {"action": "skip_qe", "amend": "different"}):
            with self.subTest(body=body):
                self.assertFalse(u04.decision_matches(body, "skip_qe", NOTE))

    def test_a_plain_judgment_carries_no_note(self):
        self.assertTrue(u04.decision_matches({"approve": True}, "operator_judgment", None))
        self.assertTrue(u04.decision_matches({"approve": True, "action": "operator_judgment"}, "operator_judgment", None))
        self.assertFalse(u04.decision_matches({"approve": True, "amend": NOTE}, "operator_judgment", None))
        self.assertFalse(u04.decision_matches({"approve": False}, "operator_judgment", None))

    def test_judgment_requires_approval_a_judgment_action_and_exact_note(self):
        for action in (None, "approve", "operator_judgment"):
            with self.subTest(action=action):
                self.assertTrue(u04.decision_matches({"approve": True, "action": action, "amend": NOTE}, "operator_judgment", NOTE))
        self.assertTrue(u04.decision_matches({"approve": True, "amend": NOTE}, "operator_judgment", NOTE))
        for body in ({"approve": False, "amend": NOTE}, {"amend": NOTE},
                     {"approve": True, "action": "skip_qe", "amend": NOTE},
                     {"approve": True}, {"approve": True, "amend": "different"}):
            with self.subTest(body=body):
                self.assertFalse(u04.decision_matches(body, "operator_judgment", NOTE))


class GatePostFor(unittest.TestCase):
    def sent(self, posts, label="Approve plan", rules_pick=False, since=0):
        j = SimpleNamespace(rec={"posts": posts}, wait=lambda cond, seconds, what: cond())
        return u04.gate_post_for(j, "run-123", since, label, rules_pick, NOTE)

    def test_only_a_successful_post_to_this_runs_exact_gate_counts(self):
        valid = {"status": 200, "method": "POST", "url": "/api/v1/runs/run-123/gate", "body": {"approve": True}}
        self.assertTrue(self.sent([valid]))
        for change in ({"url": "/api/v1/telemetry"}, {"url": "/api/v1/runs/other/gate"},
                       {"url": valid["url"] + "/extra"}, {"url": valid["url"] + "/"},
                       {"method": "PUT"}, {"status": 400}, {"status": 302}, {"body": None},
                       {"body": {"approve": False}}):
            with self.subTest(change=change):
                self.assertFalse(self.sent([{**valid, **change}]))
        self.assertFalse(self.sent([valid], since=1))
        self.assertTrue(self.sent([{**valid, "status": 204}]))

    def test_the_post_body_must_match_the_selected_decision(self):
        post = {"status": 200, "method": "POST", "url": "/api/v1/runs/run-123/gate"}
        for label, rules_pick, body in (
            ("Skip POL-1", True, {"action": "skip_rules", "skipRules": [{"id": "POL-1", "reason": NOTE}]}),
            ("Skip QE", False, {"action": "skip_qe", "amend": NOTE}),
            ("Approve as your own judgment", False, {"approve": True, "action": "operator_judgment", "amend": NOTE}),
        ):
            with self.subTest(label=label):
                self.assertTrue(self.sent([{**post, "body": body}], label, rules_pick))
                self.assertFalse(self.sent([{**post, "body": {"approve": True}}], label, rules_pick))
                self.assertFalse(self.sent([{**post, "body": {**body, "action": "reject"}}], label, rules_pick))


class SteerNote(unittest.TestCase):
    def journey(self, label, key, card):
        j = MagicMock()
        j.origin = "http://127.0.0.1:1234"
        j.rec = {"posts": [], "writes": []}
        j.get.return_value = {"runs": [{"session": {"id": "run-123", "status": "awaiting_human"}}]}
        j.wait.side_effect = lambda cond, seconds, what: cond()
        empty = MagicMock()
        empty.count.return_value = 0
        empty.all.return_value = []
        choice = MagicMock()
        choice.inner_text.return_value = label
        choice.get_attribute.return_value = key
        choices = MagicMock()
        choices.count.return_value = 1
        choices.all.return_value = [choice]
        row = MagicMock()
        row.last.inner_text.return_value = card
        note = MagicMock()
        note.last = note
        note.count.return_value = 1
        note.is_visible.return_value = True
        note.is_enabled.return_value = True
        note.is_editable.return_value = True
        elements = {"session-gate-choice": choices, "session-gate-row": row, "session-gate-note": note}
        j.page.get_by_test_id.side_effect = lambda tid: elements.get(tid, empty)
        return j, note

    def test_a_plain_judgment_without_a_note_box_is_sent_without_a_note(self):
        j, note = self.journey("Approve as your own judgment", "approve", "No helper could check this step independently")
        note.count.return_value = 0
        u04.steer(j, "run-123")
        self.assertFalse(any(call.args[:2] == ("decision_note_field_driven", False) for call in j.check.call_args_list))

    def test_a_required_note_that_cannot_be_driven_fails_before_sending(self):
        for label, key, card in (("Skip QE", "skip-qe", OTHER_CARD),
                                 ("Skip POL-1", "skip-rules", RULES_CARD),
                                 ("Approve as your own judgment", "operator-judgment", "No helper could check this step independently")):
            for unavailable in ("missing", "hidden", "disabled", "readonly", "fill_error"):
                with self.subTest(label=label, unavailable=unavailable):
                    j, note = self.journey(label, key, card)
                    if unavailable == "missing":
                        note.count.return_value = 0
                    elif unavailable == "hidden":
                        note.is_visible.return_value = False
                    elif unavailable == "disabled":
                        note.is_enabled.return_value = False
                    elif unavailable == "readonly":
                        note.is_editable.return_value = False
                    else:
                        note.fill.side_effect = RuntimeError("field detached")
                    u04.steer(j, "run-123")
                    checks = [call for call in j.check.call_args_list if call.args[:2] == ("decision_note_field_driven", False)]
                    self.assertEqual(len(checks), 1)
                    self.assertFalse(any(call.args[0] == "each_decision_is_sent" for call in j.check.call_args_list))



class StandInRecord(unittest.TestCase):
    """wicked-crew#1884: after the person chose stand-ins for the job, the record names the consent and labels each."""

    GOOD = {"assurance": {"standInAware": True, "standIn": {"scope": "job", "by": "ann (human)", "at": 7, "via": "launch"},
                          "standIns": [{"key": "claude~1", "base": "claude", "slot": 1, "role": "judge", "state": "answered"}]}}

    def test_a_whole_record_passes(self):
        self.assertEqual(u04.stand_in_problems(self.GOOD, [{"assigned_cli": "claude~1"}, {"assigned_cli": "claude"}]), [])

    def test_each_way_the_record_falls_short_is_named(self):
        a = self.GOOD["assurance"]
        bad = [
            {},
            {"assurance": {**a, "standInAware": False}},
            {"assurance": {**a, "standIn": {**a["standIn"], "scope": "always", "via": "setting"}}},
            {"assurance": {**a, "standIn": {**a["standIn"], "by": ""}}},
            {"assurance": {**a, "standIns": [{**a["standIns"][0], "key": "claude"}]}},
            {"assurance": {**a, "standIns": [{**a["standIns"][0], "role": "builder"}]}},
            {"assurance": {**a, "standIns": "claude~1"}},
        ]
        for session in bad:
            with self.subTest(session=session):
                self.assertNotEqual(u04.stand_in_problems(session, []), [])

    def test_a_unit_on_a_stand_in_seat_needs_its_binding(self):
        self.assertNotEqual(u04.stand_in_problems(self.GOOD, [{"assigned_cli": "claude~2"}]), [])

    def test_malformed_records_are_named_never_raised(self):
        a = self.GOOD["assurance"]
        for session in ({"assurance": {**a, "standIns": [None]}}, {"assurance": "x"}, {"assurance": {**a, "standIn": "job"}}, None):
            with self.subTest(session=session):
                self.assertNotEqual(u04.stand_in_problems(session, [None, {"assigned_cli": 3}]), [])

    def test_numbers_are_real_numbers_and_slots_are_u32(self):
        a = self.GOOD["assurance"]
        for session in ({"assurance": {**a, "standIn": {**a["standIn"], "at": True}}},
                        {"assurance": {**a, "standIn": {**a["standIn"], "at": float("inf")}}},
                        {"assurance": {**a, "standIns": [{**a["standIns"][0], "slot": 4294967296, "key": "claude~4294967296"}]}},
                        {"assurance": {**a, "standIns": [{**a["standIns"][0], "slot": True, "key": "claude~True"}]}}):
            with self.subTest(session=session):
                self.assertNotEqual(u04.stand_in_problems(session, []), [])

    def test_the_disclosure_must_say_not_independent(self):
        self.assertTrue(u04.NOT_INDEPENDENT.search("They are not independent reviews."))
        self.assertFalse(u04.NOT_INDEPENDENT.search("Stand-ins are independent reviews."))
        self.assertFalse(u04.NOT_INDEPENDENT.search("No helper could check this independently."))


class U06RecordedRules(unittest.TestCase):
    """U06's stand-in branch reads the rule where the run recorded its rule check. The rows are wicked-crew
    tests/fixtures/stand-in-receipts.wire.json gateEvaluated ord 3 `assurance.rules` (train-14 proof daemon), verbatim
    in shape: a `how` row with no top-level status, a `status` row, and a proposal rule with its key."""

    ROWS = [
        {"evidenceKey": "e3", "how": "operator", "origin": "operator", "reason": "skipped by local (human)",
         "reviewer": {"by": "reviewer", "cite": "no code", "seat": "claude~1", "status": "kept"}, "ruleId": "POL-2101"},
        {"blocking": False, "evidenceKey": "2a", "how": "none", "party": "engine", "reason": "no distinct judge seat",
         "ruleId": "RVWL-1002"},
        {"how": "fact", "origin": "fact", "reason": "selected only for tool tokens", "ruleId": "EDITOR-GRANTS",
         "ruleKey": "15", "status": "n_a"},
    ]

    def setUp(self):
        import u06_steering_cited as u06
        self.u06 = u06

    def test_rows_with_how_and_no_status_are_rule_rows(self):
        events = [{"type": "gateEvaluated", "ord": 3, "assurance": {"rules": self.ROWS}}]
        self.assertEqual(self.u06.recorded_rule_rows(events), ["POL-2101", "RVWL-1002", "EDITOR-GRANTS"])

    def test_only_gate_frames_and_named_rows_count(self):
        events = [
            {"type": "noteAdded", "text": "DEV-ST-U06"},
            {"type": "gateEvaluated", "ord": 2, "assurance": {"rules": [{"ruleId": "DEV-ST-U06"}]}},
            {"type": "gateEvaluated", "ord": 3},
            "junk", None,
        ]
        self.assertEqual(self.u06.recorded_rule_rows(events), [])
        self.assertEqual(self.u06.recorded_rule_rows(None), [])

    def test_the_rule_is_found_on_any_gate(self):
        events = [{"type": "gateEvaluated", "ord": 2, "assurance": {"rules": []}},
                  {"type": "gateEvaluated", "ord": 4, "assurance": {"rules": [dict(self.ROWS[1], ruleId="DEV-ST-U06")]}}]
        self.assertIn("DEV-ST-U06", self.u06.recorded_rule_rows(events))


if __name__ == "__main__":
    unittest.main()
