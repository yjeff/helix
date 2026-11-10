import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "cedar_bog_lake" / "model.helix"


class CedarCaseTest(unittest.TestCase):

    def test_old_new_parity(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(initial={
            "PLANTS": 0.83,
            "HERBIVORES": 0.003,
            "CARNIVORES": 0.0001,
            "ORGANIC": 0.0,
            "ENVIRONMENT": 0.0,
        }).run(end=2.0)

        self.assertEqual(len(result.continuous), 81)
        final = result.continuous[-1]["values"]
        self.assertAlmostEqual(final["PLANTS"], 16.9244498, places=4)
        self.assertAlmostEqual(final["HERBIVORES"], 0.4378359, places=5)
        self.assertAlmostEqual(final["CARNIVORES"], 0.5676731, places=5)
        self.assertAlmostEqual(final["ORGANIC"], 120.2910921, places=3)
        self.assertAlmostEqual(final["ENVIRONMENT"], 54.4120491, places=3)
        self.assertAlmostEqual(final["SOLAR"], 95.9, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
