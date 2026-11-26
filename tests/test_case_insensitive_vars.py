import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


class VariableCaseTest(unittest.TestCase):

    def test_create_attribute_and_expression_case_match(self):
        result = helix.Model.from_source("""
HELIX 1
VAR TAG ENTITY
NETWORK
  CREATE(count=1, tag=[7]) -> A
  A: ACTIVITY(duration=tag) -> B
  B: ASSIGN(tag=tag+1) -> C
  C: IF tag == 8 -> DONE
  ELSE -> FAIL
  DONE: EXIT()
  FAIL: ACTIVITY(duration=100) -> BAD
  BAD: EXIT()
END
""").initialize().run(end=100, seed=1)
        self.assertAlmostEqual(result._metric("SYSTEM.TIME"), 7.0)
        self.assertEqual(result._metric("SYSTEM.TIME.COUNT"), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
