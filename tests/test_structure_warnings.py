import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


class StructureWarningTest(unittest.TestCase):

    def test_valid_model_has_no_warnings(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1) -> DONE
  DONE: EXIT()
END
""")
        self.assertEqual(model.structure_warnings(), [])

    def test_no_entry_and_no_terminal(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  A: ASSIGN(X=1) -> B
  B: ASSIGN(X=2) -> A
END
""")
        warnings = model.structure_warnings()
        self.assertTrue(any("没有 CREATE" in item for item in warnings))
        self.assertTrue(any("没有 EXIT" in item for item in warnings))

    def test_isolated_and_unreachable(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1) -> DONE
  DONE: EXIT()

  ORPHAN: ASSIGN(X=1) -> ORPHAN2
  ORPHAN2: EXIT()
  ISOLATED: ASSIGN(X=3)
END
""")
        warnings = model.structure_warnings()
        self.assertTrue(any("不可达" in item and "ORPHAN" in item
                            for item in warnings))
        self.assertTrue(any("孤立" in item and "ISOLATED" in item
                            for item in warnings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
