"""U04's choice picker (#77), without a browser: python -m unittest discover -s selftest/journeys -p 'test_*.py'"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import u04_bug_delivered as u04  # noqa: E402

RULES_CARD = "The rule POL-2101 needs your call before this step can go on"
OTHER_CARD = "The plan is ready for your review"


def pick(card, *choices):
    e, rules = u04.pick_choice(card, [(text, text, key) for text, key in choices])
    return e, rules


class PickChoice(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
