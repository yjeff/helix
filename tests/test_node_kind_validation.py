import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


class NodeKindValidationTest(unittest.TestCase):

    def test_match_is_rejected_at_compile_time(self):
        with self.assertRaises(helix.HelixCompileError) as ctx:
            helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  X: MATCH()
  EXIT()
END
""")
        self.assertIn("MATCH", str(ctx.exception))

    def test_misspelled_activity_is_rejected_at_compile_time(self):
        with self.assertRaises(helix.HelixCompileError) as ctx:
            helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  X: ACTIVTY(duration=1)
  EXIT()
END
""")
        self.assertIn("ACTIVTY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
