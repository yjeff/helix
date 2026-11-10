import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "soaking_pit" / "model.helix"


class SoakingCaseTest(unittest.TestCase):

    def test_structural_parity(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(initial={
            "FURNACE": 1650.0,
            "TEMP": [0.0] * 10,
            "ACTIVE": [0.0] * 10,
            "C": [0.15] * 10,
        }).run(end=500.0, seed=4)

        final = result.continuous_final
        # 旧版 seed=0: FURNACE≈2514.6, MAX_TEMP≈2133, ACTIVE=9。
        self.assertGreaterEqual(final["FURNACE"], 2300.0)
        self.assertLessEqual(final["FURNACE"], 2600.0)
        self.assertGreaterEqual(final["MAX_TEMP"], 2000.0)
        self.assertLessEqual(final["MAX_TEMP"], 2300.0)
        active = sum(result.global_values[f"ACTIVE[{i}]"]
                     for i in range(1, 11))
        self.assertGreaterEqual(active, 9.0)
        self.assertLessEqual(active, 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
