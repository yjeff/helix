import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
RESOURCE R(capacity=1)

NETWORK
  CREATE(interval=10, count=1, priority=1) -> P
  CREATE(interval=10, count=1, priority=5) -> P

  P: PREEMPT(resource=R)
  ACTIVITY(duration=5) -> FREE
  FREE: FREE(resource=R, units=1) -> DONE
  DONE: TERMINATE()
END NETWORK
"""


class PreemptTest(unittest.TestCase):

    def test_preempt_and_resume(self):
        model = helix.Model.from_source(MODEL)
        result = model.initialize().run(end=30, seed=1)
        self.assertEqual(result.observations[0].count, 2)
        self.assertEqual(result.resources[0].wait_count, 1)
        self.assertEqual(result.resources[0].maximum_held, 1)

    def test_high_priority_preempt_to(self):
        model = helix.Model.from_source("""
HELIX 1
VAR REMAIN ENTITY
RESOURCE R(capacity=1)

NETWORK
  CREATE(interval=10, count=1, priority=1) -> P
  CREATE(interval=10, count=1, priority=5) -> P

  P: PREEMPT(resource=R, priority=HIGH(PRIORITY),
             preempted_to=DOWN, remaining_at=REMAIN)
  ACTIVITY(duration=5) -> FREE
  FREE: FREE(resource=R, units=1) -> DONE
  DONE: TERMINATE()

  DOWN: ACTIVITY(duration=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=30, seed=1)
        self.assertEqual(result.observations[0].count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
