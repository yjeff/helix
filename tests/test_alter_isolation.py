import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


class AlterIsolationTest(unittest.TestCase):

    def test_alter_activity_does_not_mutate_model(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1) -> A
  A: ACTIVITY(duration=5) -> B
  B: ALTER(activity=A, duration=1) -> C
  C: EXIT()
END
""")
        scenario = model.initialize()
        first = scenario.run(end=10, seed=1)
        second = scenario.run(end=10, seed=1)

        self.assertEqual(model.nodes["A"].args["duration"], "5")
        self.assertAlmostEqual(first.observations[0].mean, 5.0)
        self.assertAlmostEqual(second.observations[0].mean, 5.0)

    def test_alter_create_does_not_mutate_model(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(interval=5, count=2) -> A
  A: ACTIVITY(duration=1) -> B
  B: ALTER(create=ARR, interval=1) -> C
  C: EXIT()

  ARR: CREATE(interval=5, count=2) -> A
END
""")
        scenario = model.initialize()
        scenario.run(end=7, seed=1)
        scenario.run(end=7, seed=1)
        self.assertEqual(model.nodes["ARR"].args["interval"], "5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
