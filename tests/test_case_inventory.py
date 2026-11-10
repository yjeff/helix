import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "inventory_problem" / "model.helix"


class InventoryCaseTest(unittest.TestCase):

    def test_lost_sales_and_radio_stock(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(initial={
            "invposition": 72,
            "reorderpos": 18,
            "invcontrolpos": 72,
            "LAST_LOST": 0,
            "HAS_LOST": 0,
        }).run(end=312, clear_time=52, seed=1)

        observations = {item.label: item for item in result.observations}
        lost = observations["TIME BETWEEN LOST SALES"]
        safety = observations["SAFETY STOCK"]
        radio = result.resources[0]

        self.assertGreaterEqual(lost.count, 90)
        self.assertLessEqual(lost.count, 150)
        self.assertGreater(lost.mean, 1.5)
        self.assertLess(lost.mean, 4.0)
        self.assertGreaterEqual(safety.count, 10)
        self.assertGreater(radio.average_held, 35.0)
        self.assertLess(radio.average_held, 50.0)
        self.assertEqual(radio.capacity, 72)


if __name__ == "__main__":
    unittest.main(verbosity=2)
