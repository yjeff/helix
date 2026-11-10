import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "truck_hauling" / "model.helix"


class TruckCaseTest(unittest.TestCase):

    def test_old_new_parity(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(entities={
            "TRKS": [{}, {}, {}, {}],
            "LDER": [{}, {}],
        }).run(end=560, seed=1230)

        self.assertAlmostEqual(result.queues[0].average_length, 0.1758,
                               places=3)
        self.assertAlmostEqual(result.queues[1].average_length, 0.9589,
                               places=3)
        self.assertAlmostEqual(result.queues[2].average_length, 1.0761,
                               places=3)
        self.assertEqual(result.queues[0].max_length, 3)
        self.assertEqual(result.queues[1].max_length, 4)
        self.assertEqual(result.queues[2].max_length, 2)

        services = {service.activity: service for service in result.services}
        self.assertEqual(services["L1"].completed, 13)
        self.assertEqual(services["L2"].completed, 16)
        self.assertEqual(services["LOADER_REST"].completed, 29)
        self.assertEqual(services["HAUL"].completed, 29)
        self.assertEqual(services["DUMP"].completed, 29)
        self.assertEqual(services["RETURN"].completed, 29)


if __name__ == "__main__":
    unittest.main(verbosity=2)
