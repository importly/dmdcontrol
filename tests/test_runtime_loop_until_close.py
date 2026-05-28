import types
import unittest

from dmdcontrol.runtime.loop import run_render_loop


class _Engine:
    def __init__(self):
        self.displayed = 0

    def should_close(self):
        return self.displayed >= 1

    def display_frame(self, frame):
        self.displayed += 1


class RuntimeLoopUntilCloseTests(unittest.TestCase):
    def test_runtime_seconds_zero_runs_until_window_close(self):
        engine = _Engine()
        args = types.SimpleNamespace(runtime_seconds=0, verbose=0)

        run_render_loop(
            dlpc=None,
            engine=engine,
            frame_provider=lambda: object(),
            args=args,
            sequence_state={},
        )

        self.assertEqual(engine.displayed, 1)


if __name__ == "__main__":
    unittest.main()
