import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
VAR X GLOBAL
NETWORK
  CREATE(count=1) -> LOOP
  LOOP: ASSIGN(X=1) -> LOOP
END
"""


class EventGuardTest(unittest.TestCase):

    def test_total_event_limit(self):
        model = helix.Model.from_source(MODEL)
        with self.assertRaisesRegex(helix.HelixRuntimeError, "max_events"):
            model.initialize().run(
                end=10, max_events=5, max_same_time_events=None)

    def test_same_time_event_limit(self):
        model = helix.Model.from_source(MODEL)
        with self.assertRaisesRegex(
                helix.HelixRuntimeError, "max_same_time_events"):
            model.initialize().run(
                end=10, max_events=None, max_same_time_events=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
