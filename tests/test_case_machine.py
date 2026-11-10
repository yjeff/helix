import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "machine_breakdown" / "model.helix"


class MachineBreakdownCaseTest(unittest.TestCase):

    def test_five_run_averages(self):
        model = helix.Model.from_file(str(MODEL))
        times = []
        uses = []
        repairs = []
        for seed in range(5):
            result = model.initialize().run(end=1000.0, seed=seed)
            services = {s.activity: s for s in result.services}
            times.append(result.observations[0].mean)
            uses.append(
                services["ACTIVITY_1"].average_utilization
                + services["ACTIVITY_2"].average_utilization)
            repairs.append(
                services["ACTIVITY_3"].average_utilization)

        # 书中 Table 6-1 五运行平均：
        # time≈9.59, tool use≈0.844, repair≈0.11。
        self.assertGreaterEqual(sum(times) / 5, 8.0)
        self.assertLessEqual(sum(times) / 5, 10.5)
        self.assertGreaterEqual(sum(uses) / 5, 0.80)
        self.assertLessEqual(sum(uses) / 5, 0.90)
        self.assertGreaterEqual(sum(repairs) / 5, 0.08)
        self.assertLessEqual(sum(repairs) / 5, 0.13)


if __name__ == "__main__":
    unittest.main(verbosity=2)
