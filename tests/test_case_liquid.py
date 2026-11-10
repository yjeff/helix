import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "liquid_level" / "model.helix"


class LiquidLevelCaseTest(unittest.TestCase):

    def test_old_new_parity(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(
            initial={"LEVEL": 60.0, "PUMP_ON": 0.0},
            constants={"QIN": 3.0, "QOUT": 4.0},
        ).run(end=80.0, seed=1)

        levels = [row["values"]["LEVEL"] for row in result.continuous]
        highs = sum(1 for a, b in zip(levels, levels[1:])
                    if a <= 80.0 < b)
        lows = sum(1 for a, b in zip(levels, levels[1:])
                   if a >= 20.0 > b)

        # 旧版：final=60.25, max=84.428, min=16.027,
        # high=2, low=2, pump=0。
        self.assertAlmostEqual(result.continuous_final["LEVEL"],
                               60.25, places=2)
        self.assertAlmostEqual(max(levels), 84.425, places=2)
        self.assertAlmostEqual(min(levels), 16.025, places=2)
        self.assertEqual(highs, 2)
        self.assertEqual(lows, 2)
        self.assertEqual(result.continuous_final["PUMP_ON"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
