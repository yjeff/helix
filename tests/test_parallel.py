import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


PARALLEL = """
HELIX 1
NETWORK
  CREATE(interval=0.1, count=2)
  P: PARALLEL
    PATH -> A
    PATH -> B
  END PARALLEL
  A: ACTIVITY(duration=1) -> J
  B: ACTIVITY(duration=1) -> J
  J: JOIN(count=2, merge=SUM)
  TERMINATE()
END NETWORK
"""


SPLIT = """
HELIX 1
NETWORK
  CREATE(count=1)
  S: SPLIT(parts=[loader, truck])
    PATH loader -> L
    PATH truck -> T
  END SPLIT
  L: ACTIVITY(duration=1) -> DONE
  T: ACTIVITY(duration=2) -> DONE
  DONE: TERMINATE()
END NETWORK
"""


class ParallelTest(unittest.TestCase):

    def test_parallel_join(self):
        model = helix.Model.from_source(PARALLEL)
        self.assertEqual(model.nodes["P"].kind, "PARALLEL")
        self.assertEqual(len(model.nodes["P"].paths), 2)
        result = model.initialize().run(end=20, seed=1)
        self.assertEqual(result.services[0].completed, 2)
        self.assertEqual(result.services[1].completed, 2)
        self.assertEqual(result.observations[0].count, 2)

    def test_split_parts(self):
        model = helix.Model.from_source(SPLIT)
        self.assertEqual(model.nodes["S"].kind, "SPLIT")
        result = model.initialize().run(end=20, seed=1)
        self.assertEqual(result.observations[0].count, 2)

    def test_split_lowercase(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  S: split(parts=[loader, truck])
    path loader -> L
    path truck -> T
  end split
  L: activity(duration=1) -> DONE
  T: activity(duration=2) -> DONE
  DONE: exit
END
""")
        self.assertEqual(model.nodes["S"].kind, "SPLIT")
        result = model.initialize().run(end=20, seed=1)
        self.assertEqual(result.observations[0].count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
