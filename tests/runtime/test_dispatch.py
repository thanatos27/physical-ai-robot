import io
import threading
import time
import unittest

from runtime.dispatch import DispatchingVisionSource, DispatchQueue
from runtime.event import RuntimeEvent
from runtime.input import JsonlInputSource, parse_detection_event


def two_events():
    line = '{"timestamp":%d,"detections":[]}'
    return [parse_detection_event(line % 1), parse_detection_event(line % 2)]


class StateChannelCoalescingTest(unittest.TestCase):
    def test_multiple_publishes_before_pop_coalesce_into_one_notification(self):
        dispatch = DispatchQueue()
        channel = dispatch.new_state_channel("VISION_STATE_UPDATED")

        channel.publish(100)
        channel.publish(101)
        channel.publish(102)

        first = dispatch.pop()
        self.assertEqual(first.type, "VISION_STATE_UPDATED")
        self.assertEqual(first.payload.latest(), 102)

        # 3回 publish しても Queue に積まれた通知は1件だけ = 2回目以降の pop は
        # ブロックする (ここではタイムアウト付きで「何もない」ことを確認する)。
        popped_again = threading.Event()

        def try_pop():
            dispatch.pop()
            popped_again.set()

        t = threading.Thread(target=try_pop, daemon=True)
        t.start()
        self.assertFalse(popped_again.wait(timeout=0.2))

    def test_publish_after_pop_re_enables_notification(self):
        dispatch = DispatchQueue()
        channel = dispatch.new_state_channel("VISION_STATE_UPDATED")

        channel.publish(1)
        dispatch.pop()
        channel.publish(2)

        second = dispatch.pop()
        self.assertEqual(second.payload.latest(), 2)

    def test_value_visible_even_when_notification_is_skipped(self):
        # publish 直後に pending が既に True の場合でも、value 自体は常に更新される。
        dispatch = DispatchQueue()
        channel = dispatch.new_state_channel("VISION_STATE_UPDATED")

        channel.publish(1)  # enqueue される
        channel.publish(2)  # pending 済みなので enqueue されないが value は更新

        event = dispatch.pop()
        self.assertEqual(event.payload.latest(), 2)


class DispatchQueueEventOrderingTest(unittest.TestCase):
    def test_real_events_are_never_dropped_and_keep_fifo_order(self):
        dispatch = DispatchQueue()

        for i in range(5):
            dispatch.push_event(RuntimeEvent("BUTTON_PRESSED", i))

        popped = [dispatch.pop() for _ in range(5)]
        self.assertEqual([e.payload for e in popped], [0, 1, 2, 3, 4])

    def test_state_notifications_and_events_share_enqueue_order(self):
        dispatch = DispatchQueue()
        channel = dispatch.new_state_channel("VISION_STATE_UPDATED")

        channel.publish("v1")
        dispatch.push_event(RuntimeEvent("BUTTON_PRESSED"))

        first = dispatch.pop()
        second = dispatch.pop()

        self.assertEqual(first.type, "VISION_STATE_UPDATED")
        self.assertEqual(second.type, "BUTTON_PRESSED")


class DispatchingVisionSourceTest(unittest.TestCase):
    """DispatchingVisionSource は State Coalescing (PR #3) を適用するため、
    producer が consumer より速い場合、中間の DetectionEvent は
    `RobotRuntime` へ配送されない (最新値だけが配送される)。

    これは Phase 0.5 の「JSONL 1行 = 1 RobotLoopRecord」という現行の
    regression 要件と矛盾するため、現時点では本番の Vision 経路 (main()) へは
    配線していない (Design Issue #4 を参照)。
    """

    def test_consumer_keeping_up_receives_every_item(self):
        # producer と consumer を交互に進めることで coalescing を発生させず、
        # Dispatch Queue 自体は「詰まっていなければ全件届く」ことを確認する。
        events = two_events()
        dispatch = DispatchQueue()
        channel = dispatch.new_state_channel("VISION_STATE_UPDATED")

        received = []
        for event in events:
            channel.publish(event)
            popped = dispatch.pop()
            received.append(popped.payload.latest())

        self.assertEqual(received, events)

    def test_fast_producer_coalesces_intermediate_values_but_keeps_the_latest(self):
        # producer が consumer より速い場合、中間値は失われるが、
        # 最終的に配送される値は必ず最新のものである。
        dispatch = DispatchQueue()
        channel = dispatch.new_state_channel("VISION_STATE_UPDATED")

        for i in range(5):
            channel.publish(i)

        delivered = dispatch.pop().payload.latest()
        self.assertEqual(delivered, 4)

    def test_slow_consumer_over_full_fixture_receives_fewer_records_than_lines(self):
        from pathlib import Path

        fixture = (
            Path(__file__).resolve().parents[2]
            / "tests"
            / "fixtures"
            / "detections_sample.jsonl"
        )
        with fixture.open(encoding="utf-8") as stream:
            direct = list(JsonlInputSource(stream))

        with fixture.open(encoding="utf-8") as stream:
            via_dispatch = list(DispatchingVisionSource(JsonlInputSource(stream)))

        # producer thread がファイル全体を瞬時に読み切るため、consumer 側の
        # 最初の pop が間に合わず coalescing が発生し、direct 読み取りより
        # 件数が少なくなり得る (少なくとも最後の要素は必ず含まれる)。
        self.assertLessEqual(len(via_dispatch), len(direct))
        self.assertGreaterEqual(len(via_dispatch), 1)
        self.assertEqual(via_dispatch[-1], direct[-1])

    def test_eof_raises_stop_iteration_eventually(self):
        source = DispatchingVisionSource(iter(two_events()))
        it = iter(source)

        received = []
        with self.assertRaises(StopIteration):
            while True:
                received.append(next(it))

        self.assertGreaterEqual(len(received), 1)
        self.assertEqual(received[-1], two_events()[-1])

    def test_producer_exception_propagates_to_consumer(self):
        def failing_source():
            yield two_events()[0]
            raise ValueError("boom")

        source = DispatchingVisionSource(failing_source())
        it = iter(source)

        next(it)
        with self.assertRaisesRegex(ValueError, "boom"):
            next(it)

    def test_keyboard_interrupt_on_dispatch_pop_propagates(self):
        # main thread が SIGINT を受けた際に real 環境で起きるのと同じ状況を
        # 再現する: DispatchQueue.pop() (blocking call) が KeyboardInterrupt を
        # 送出したら、そのまま呼び出し元へ伝播する。
        source = DispatchingVisionSource(iter(two_events()))
        source._dispatch.pop = lambda: (_ for _ in ()).throw(KeyboardInterrupt)  # noqa: E731

        with self.assertRaises(KeyboardInterrupt):
            next(source)


if __name__ == "__main__":
    unittest.main()
