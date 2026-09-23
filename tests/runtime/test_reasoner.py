import unittest

from runtime.event import RuntimeEvent
from runtime.models import BoundingBox, Decision, DecisionType, Observation, ObservedObject
from runtime.reasoner import RuleBasedReasoner

BOX = BoundingBox(0, 0, 10, 10)


def observation(*types: str) -> Observation:
    return Observation(
        timestamp=1,
        objects=tuple(ObservedObject(t, 0.9, BOX) for t in types),
    )


class RuleBasedReasonerTest(unittest.TestCase):
    def setUp(self):
        self.reasoner = RuleBasedReasoner()

    def test_person_present(self):
        self.assertEqual(
            self.reasoner.reason(observation("person")),
            Decision(DecisionType.PERSON_DETECTED),
        )

    def test_person_among_other_objects(self):
        self.assertEqual(
            self.reasoner.reason(observation("clock", "person", "chair")),
            Decision(DecisionType.PERSON_DETECTED),
        )

    def test_only_other_objects(self):
        self.assertEqual(
            self.reasoner.reason(observation("clock", "chair")),
            Decision(DecisionType.NO_PERSON),
        )

    def test_no_objects(self):
        self.assertEqual(
            self.reasoner.reason(observation()),
            Decision(DecisionType.NO_PERSON),
        )

    def test_button_pressed_event_is_acknowledged(self):
        self.assertEqual(
            self.reasoner.reason(RuntimeEvent("BUTTON_PRESSED")),
            Decision(DecisionType.BUTTON_ACKNOWLEDGED),
        )

    def test_unknown_event_type_raises(self):
        with self.assertRaises(ValueError):
            self.reasoner.reason(RuntimeEvent("SOMETHING_ELSE"))


if __name__ == "__main__":
    unittest.main()
