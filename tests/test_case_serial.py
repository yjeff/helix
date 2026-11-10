import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "serial_workstations" / "model.helix"


class SerialCaseTest(unittest.TestCase):
    """Serial 是 RNG 调用顺序最简单的案例，必须与旧版高度一致。"""

    def test_old_new_parity(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize().run(end=300, seed=1381)

        self.assertEqual(result.observations[0].count, 562)
        self.assertAlmostEqual(result.observations[0].mean, 3.0301, places=3)

        self.assertAlmostEqual(result.queues[0].average_length, 2.3974,
                               places=3)
        self.assertAlmostEqual(result.queues[1].average_length, 1.5121,
                               places=3)
        self.assertEqual(result.queues[0].balk_count, 235)

        self.assertEqual(result.services[0].completed, 565)
        self.assertEqual(result.services[1].completed, 562)
        self.assertAlmostEqual(result.services[0].average_utilization,
                               0.4603, places=3)
        self.assertAlmostEqual(result.services[1].average_utilization,
                               0.9188, places=3)

        # F9 连续忙碌段是跨多次服务的；必须与旧版一致。
        self.assertAlmostEqual(result.services[0].maximum_busy, 4.8317,
                               places=3)
        self.assertAlmostEqual(result.services[1].maximum_busy, 39.9869,
                               places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
