import unittest
from pathlib import Path

from runtime.input import InvalidInputError, JsonlInputSource, parse_detection_event

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "detections_sample.jsonl"

SPEC_EXAMPLE = (
    '{"timestamp":1789762879207,"detections":['
    '{"class":"person","category":1,"confidence":0.901203,'
    '"bbox":{"x":3,"y":2,"width":1242,"height":1044}},'
    '{"class":"clock","category":75,"confidence":0.435167,'
    '"bbox":{"x":940,"y":502,"width":235,"height":373}}]}'
)

VALID_DETECTION = (
    '{"class":"person","category":1,"confidence":0.9,'
    '"bbox":{"x":1,"y":2,"width":3,"height":4}}'
)


class ParseDetectionEventTest(unittest.TestCase):
    def test_parses_spec_example(self):
        event = parse_detection_event(SPEC_EXAMPLE)

        self.assertEqual(event.timestamp, 1789762879207)
        self.assertEqual(len(event.detections), 2)
        person = event.detections[0]
        self.assertEqual(person.class_name, "person")
        self.assertEqual(person.category, 1)
        self.assertAlmostEqual(person.confidence, 0.901203)
        self.assertEqual(person.bbox.x, 3)
        self.assertEqual(person.bbox.y, 2)
        self.assertEqual(person.bbox.width, 1242)
        self.assertEqual(person.bbox.height, 1044)
        self.assertEqual(event.detections[1].class_name, "clock")

    def test_parses_zero_detections(self):
        event = parse_detection_event('{"timestamp":1,"detections":[]}\n')

        self.assertEqual(event.timestamp, 1)
        self.assertEqual(event.detections, ())

    def test_rejects_invalid_lines(self):
        cases = [
            "",
            "   \n",
            "not json",
            "{",
            "[]",
            "null",
            '{"timestamp":1}',
            '{"detections":[]}',
            '{"timestamp":"1","detections":[]}',
            '{"timestamp":true,"detections":[]}',
            '{"timestamp":1,"detections":{}}',
            '{"timestamp":1,"detections":[1]}',
            '{"timestamp":1,"detections":[{"class":"person","category":1,"confidence":0.9}]}',
            '{"timestamp":1,"detections":[{"class":"person","category":1,"confidence":0.9,'
            '"bbox":{"x":1,"y":2,"width":3}}]}',
            '{"timestamp":1,"detections":[{"class":"person","category":1,"confidence":"high",'
            '"bbox":{"x":1,"y":2,"width":3,"height":4}}]}',
            '{"timestamp":1,"detections":[{"class":"person","category":1,"confidence":NaN,'
            '"bbox":{"x":1,"y":2,"width":3,"height":4}}]}',
            '{"timestamp":1,"detections":[{"class":"person","category":1.5,"confidence":0.9,'
            '"bbox":{"x":1,"y":2,"width":3,"height":4}}]}',
            '{"timestamp":1,"detections":[{"class":7,"category":1,"confidence":0.9,'
            '"bbox":{"x":1,"y":2,"width":3,"height":4}}]}',
        ]
        for line in cases:
            with self.subTest(line=line):
                with self.assertRaises(InvalidInputError):
                    parse_detection_event(line)


class JsonlInputSourceTest(unittest.TestCase):
    def test_yields_valid_events_only_and_warns_on_invalid_lines(self):
        lines = [
            '{"timestamp":1,"detections":[' + VALID_DETECTION + "]}\n",
            "garbage\n",
            "\n",
            '{"timestamp":2,"detections":[]}\n',
        ]

        with self.assertLogs("runtime.input", level="WARNING") as logs:
            events = list(JsonlInputSource(lines))

        self.assertEqual([e.timestamp for e in events], [1, 2])
        self.assertEqual(len(logs.records), 2)

    def test_no_warning_for_valid_input(self):
        lines = ['{"timestamp":1,"detections":[]}\n']

        with self.assertNoLogs("runtime.input", level="WARNING"):
            events = list(JsonlInputSource(lines))

        self.assertEqual(len(events), 1)

    def test_reads_fixture_file(self):
        with FIXTURE.open(encoding="utf-8") as stream:
            with self.assertLogs("runtime.input", level="WARNING") as logs:
                events = list(JsonlInputSource(stream))

        self.assertEqual(len(events), 4)
        self.assertEqual(len(logs.records), 3)


if __name__ == "__main__":
    unittest.main()
