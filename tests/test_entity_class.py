import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


class EntityClassTest(unittest.TestCase):

    def test_internal_entities_are_excluded(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1, entity_class=CUSTOMER) -> CUST
  CREATE(count=1, entity_class=INTERNAL) -> INT

  CUST: ACTIVITY(duration=2) -> CUST_END
  INT: ACTIVITY(duration=5) -> INT_END
  CUST_END: EXIT()
  INT_END: EXIT()
END
""")
        result = model.initialize().run(end=10, seed=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["TIME IN SYSTEM"].count, 1)
        self.assertAlmostEqual(observations["TIME IN SYSTEM"].mean, 2.0)

    def test_unknown_entity_class_is_rejected(self):
        with self.assertRaises(helix.HelixCompileError):
            helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1, entity_class=OTHER)
  EXIT()
END
""")


if __name__ == "__main__":
    unittest.main(verbosity=2)
