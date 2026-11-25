import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "port_operations" / "model.helix"


class PortCaseTest(unittest.TestCase):

    def test_book_seed_and_wait_files(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize().run(end=8640, seed=11)

        observations = {item.label: item for item in result.observations}
        self.assertAlmostEqual(
            observations["T1 IN PORT TIME"].mean, 31.19, delta=1.0)
        self.assertAlmostEqual(
            observations["T2 IN PORT TIME"].mean, 36.09, delta=1.0)
        self.assertAlmostEqual(
            observations["T3 IN PORT TIME"].mean, 47.48, delta=1.0)
        self.assertAlmostEqual(
            observations["T4 IN PORT TIME"].mean, 34.48, delta=1.0)

        waits = {item.label: item for item in result.awaits}
        self.assertAlmostEqual(
            waits["BERTH_WAIT"].average_length, 1.0880, delta=0.1)
        self.assertEqual(waits["BERTH_WAIT"].max_length, 6)
        self.assertAlmostEqual(
            waits["TUG_BERTH"].average_length, 0.0187, delta=0.02)
        self.assertAlmostEqual(
            waits["TUG_DEBERTH"].average_length, 0.0215, delta=0.02)

        resources = {item.name: item for item in result.resources}
        self.assertAlmostEqual(
            resources["berth"].average_held, 2.8352, delta=0.1)
        self.assertAlmostEqual(
            resources["tug"].average_held, 0.2153, delta=0.03)


if __name__ == "__main__":
    unittest.main(verbosity=2)
