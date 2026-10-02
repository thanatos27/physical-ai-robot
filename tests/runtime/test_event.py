import queue
import unittest

from runtime.event import EventQueue, RuntimeEvent


class EventQueueTest(unittest.TestCase):
    def test_pops_events_in_fifo_order(self):
        events = EventQueue()
        events.push(RuntimeEvent("BUTTON_PRESSED", 1))
        events.push(RuntimeEvent("BUTTON_PRESSED", 2))
        events.push(RuntimeEvent("AI_JOB_COMPLETED", "job-1"))

        popped = [events.pop() for _ in range(3)]

        self.assertEqual(
            [(e.type, e.payload) for e in popped],
            [("BUTTON_PRESSED", 1), ("BUTTON_PRESSED", 2), ("AI_JOB_COMPLETED", "job-1")],
        )

    def test_empty_queue_reports_empty(self):
        events = EventQueue()

        self.assertTrue(events.empty())
        events.push(RuntimeEvent("BUTTON_PRESSED"))
        self.assertFalse(events.empty())

    def test_non_blocking_pop_on_empty_raises(self):
        events = EventQueue()

        with self.assertRaises(queue.Empty):
            events.pop(block=False)

    def test_no_event_is_lost_or_reordered_under_concurrent_push(self):
        import threading

        events = EventQueue()
        total_per_thread = 50

        def producer(tag: str) -> None:
            for i in range(total_per_thread):
                events.push(RuntimeEvent(tag, i))

        threads = [
            threading.Thread(target=producer, args=(f"T{n}",)) for n in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        popped = [events.pop(block=False) for _ in range(4 * total_per_thread)]
        self.assertTrue(events.empty())

        per_tag = {}
        for e in popped:
            per_tag.setdefault(e.type, []).append(e.payload)
        for tag, payloads in per_tag.items():
            self.assertEqual(payloads, list(range(total_per_thread)), tag)


if __name__ == "__main__":
    unittest.main()
