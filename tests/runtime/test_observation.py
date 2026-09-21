import unittest

from runtime.input import parse_detection_event
from runtime.models import BoundingBox, Observation, ObservedObject
from runtime.observation import ObservationAdapter

LINE = (
    '{"timestamp":1789762879207,"detections":['
    '{"class":"person","category":1,"confidence":0.901203,'
    '"bbox":{"x":3,"y":2,"width":1242,"height":1044}},'
    '{"class":"clock","category":75,"confidence":0.435167,'
    '"bbox":{"x":940,"y":502,"width":235,"height":373}}]}'
)


class ObservationAdapterTest(unittest.TestCase):
    def test_adapts_detection_event_to_observation(self):
        event = parse_detection_event(LINE)

        observation = ObservationAdapter().adapt(event)

        self.assertEqual(
            observation,
            Observation(
                timestamp=1789762879207,
                objects=(
                    ObservedObject("person", 0.901203, BoundingBox(3, 2, 1242, 1044)),
                    ObservedObject("clock", 0.435167, BoundingBox(940, 502, 235, 373)),
                ),
            ),
        )

    def test_zero_detections_is_a_valid_observation(self):
        event = parse_detection_event('{"timestamp":5,"detections":[]}')

        observation = ObservationAdapter().adapt(event)

        self.assertEqual(observation, Observation(timestamp=5, objects=()))


if __name__ == "__main__":
    unittest.main()
