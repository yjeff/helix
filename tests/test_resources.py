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
  CREATE(interval=1, count=3)
  AWAIT(resource=R, units=1)
  ACTIVITY(duration=2)
  FREE(resource=R, units=1)
  TERMINATE()
END NETWORK
"""


class ResourceTest(unittest.TestCase):

    def test_resource_utilization_stats(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=2)
NETWORK
  CREATE(count=1)
  AWAIT(R)
  ACTIVITY(duration=1)
  FREE(R)
  EXIT()
END
""")
        result = model.initialize().run(end=2, seed=1)
        resource = result.resources[0]
        self.assertAlmostEqual(resource.average_utilization, 0.25)
        self.assertAlmostEqual(resource.std_utilization, 0.25)
        self.assertAlmostEqual(resource.maximum_utilization, 0.5)
        self.assertAlmostEqual(resource.current_utilization, 0.0)

    def test_dynamic_units_expressions(self):
        model = helix.Model.from_source("""
HELIX 1
VAR Q GLOBAL
RESOURCE R(capacity=10, mode=RESTOCK)
NETWORK
  CREATE(count=1)
  ASSIGN(Q=7)
  AWAIT(resource=R, units=Q)
  OBSERVE("AFTER TAKE", AVAILABLE(R))
  FREE(resource=R, units=Q)
  OBSERVE("AFTER FREE", AVAILABLE(R))
  EXIT()
END
""")
        result = model.initialize().run(end=1, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["AFTER TAKE"].values, [3])
        self.assertEqual(observations["AFTER FREE"].values, [10])

    def test_restock_mode(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=72, mode=RESTOCK)
NETWORK
  CREATE(count=1)
  AWAIT(resource=R, units=1)
  OBSERVE("AVAILABLE AFTER TAKE", AVAILABLE(R))
  OBSERVE("HELD AFTER TAKE", HELD(R))
  FREE(resource=R, units=50)
  OBSERVE("AVAILABLE AFTER FREE", AVAILABLE(R))
  OBSERVE("HELD AFTER FREE", HELD(R))
  EXIT()
END
""")
        result = model.initialize().run(end=1, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["AVAILABLE AFTER TAKE"].values, [71])
        self.assertEqual(observations["HELD AFTER TAKE"].values, [1])
        self.assertEqual(observations["AVAILABLE AFTER FREE"].values, [72])
        self.assertEqual(observations["HELD AFTER FREE"].values, [0])

    def test_restock_free_without_await(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=10, mode=RESTOCK)
NETWORK
  CREATE(count=1)
  ALTER(resource=R, capacity=5)
  FREE(resource=R, units=3)
  OBSERVE("AVAILABLE", AVAILABLE(R))
  EXIT()
END
""")
        result = model.initialize().run(end=1, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["AVAILABLE"].values, [5])

    def test_alter_capacity_expression(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=2)
NETWORK
  CREATE(count=1)
  ALTER(resource=R, capacity=CAPACITY(R) + 3)
  OBSERVE("CAPACITY", CAPACITY(R))
  EXIT()
END
""")
        result = model.initialize().run(end=1, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["CAPACITY"].values, [5])

    def test_if_resource_or_random(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=2)
NETWORK
  CREATE(count=1)
  AWAIT(R)
  CHECK: IF AVAILABLE(R) > 0 OR RANDOM() <= 0.2 -> A
  ELSE -> B
  A: OBSERVE("A", 1) -> DONE
  B: OBSERVE("B", 1) -> DONE
  DONE: FREE(R)
        EXIT()
END
""")
        result = model.initialize().run(end=1, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["A"].count, 1)
        self.assertNotIn("B", observations)

    def test_resource_query_functions(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=2)
NETWORK
  CREATE(count=1)
  AWAIT(R)
  OBSERVE("AVAILABLE", AVAILABLE(R))
  OBSERVE("CAPACITY", CAPACITY(R))
  OBSERVE("HELD", HELD(R))
  FREE(R)
  EXIT()
END
""")
        result = model.initialize().run(end=1, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["AVAILABLE"].values, [1])
        self.assertEqual(observations["CAPACITY"].values, [2])
        self.assertEqual(observations["HELD"].values, [1])

    def test_await_free(self):
        model = helix.Model.from_source(MODEL)
        result = model.initialize().run(end=15, seed=1)
        self.assertEqual(result.observations[0].count, 3)
        self.assertEqual(result.resources[0].capacity, 1)
        self.assertEqual(result.resources[0].wait_count, 2)
        self.assertEqual(result.resources[0].maximum_held, 1)
        self.assertEqual(result._metric("RESOURCE.R.AVAILABLE"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
