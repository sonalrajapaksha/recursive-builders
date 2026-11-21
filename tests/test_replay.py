"""Replay conformance and hostile-observation regression checks."""
from __future__ import annotations

import unittest

from eval.common import load_bot_class, recorded_hello, stream
from eval.synthetic import run as synthetic_run


class ReplayTests(unittest.TestCase):
    def test_recorded_actions_echo_every_tick(self) -> None:
        bot = load_bot_class()(recorded_hello())
        for obs in (m for m in stream() if m.get("type") == "obs"):
            action = bot.act(obs)
            self.assertIsInstance(action, dict)
            self.assertEqual(obs["tick"], action.get("tick"))

    def test_synthetic_actions_are_schema_valid(self) -> None:
        result = synthetic_run()
        self.assertEqual(result["cases"], result["valid_actions"])


if __name__ == "__main__":
    unittest.main()
