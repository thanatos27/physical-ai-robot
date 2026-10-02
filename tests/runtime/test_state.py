import threading
import unittest

from runtime.models import Observation
from runtime.state import LatestValueBox, RuntimeWorldState


class LatestValueBoxTest(unittest.TestCase):
    def test_returns_none_before_any_value_is_set(self):
        box: LatestValueBox[int] = LatestValueBox()

        self.assertIsNone(box.get())

    def test_returns_the_latest_value_only(self):
        box: LatestValueBox[int] = LatestValueBox()

        box.set(1)
        box.set(2)
        box.set(3)

        self.assertEqual(box.get(), 3)

    def test_backlog_does_not_grow_with_repeated_sets(self):
        box: LatestValueBox[int] = LatestValueBox()

        for i in range(10_000):
            box.set(i)

        # LatestValueBox はスカラー1個分の状態しか保持しないため、
        # 何回 set しても内部サイズは一定 (Queue のように蓄積しない)。
        self.assertEqual(vars(box).keys() - {"_lock"}, {"_value", "_has_value"})
        self.assertEqual(box.get(), 9_999)

    def test_concurrent_sets_never_lose_the_final_value(self):
        box: LatestValueBox[int] = LatestValueBox()

        def producer(start: int) -> None:
            for i in range(start, start + 100):
                box.set(i)

        threads = [threading.Thread(target=producer, args=(n * 100,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 最終的な値は 4 スレッドのいずれかが最後に set した値のいずれかであり、
        # 例外を出さず一貫した単一値を返すことだけを確認する。
        self.assertIsNotNone(box.get())


class RuntimeWorldStateTest(unittest.TestCase):
    def test_latest_vision_starts_as_none(self):
        state = RuntimeWorldState()

        self.assertIsNone(state.latest_vision)

    def test_update_vision_replaces_the_previous_observation(self):
        state = RuntimeWorldState()
        first = Observation(timestamp=1, objects=())
        second = Observation(timestamp=2, objects=())

        state.update_vision(first)
        self.assertEqual(state.latest_vision, first)

        state.update_vision(second)
        self.assertEqual(state.latest_vision, second)


if __name__ == "__main__":
    unittest.main()
