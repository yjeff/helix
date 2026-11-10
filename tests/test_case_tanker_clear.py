import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "tanker_fleet" / "model.helix"
INITIAL = {
    "TANKER_LEVEL": 0,
    "STORAGE_LEVEL": 1000,
    "LOAD_AVAIL": 1,
    "UNLOAD_AVAIL": 1,
    "REFINERY_AVAIL": 1,
}


class TankerClearTest(unittest.TestCase):

    def test_clear_time_matches_old_window(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(initial=INITIAL).run(
            end=365, seed=1, clear_time=65)

        services = {service.activity: service for service in result.services}
        # 旧版 MONTR,CLEAR,65 后 TRIP TIME count=303。
        # 新版用 RET 完成次数对应完整循环。
        self.assertGreaterEqual(services["RET"].completed, 290)
        self.assertLessEqual(services["RET"].completed, 320)

        # 旧版 WAITING TIME count=303；新版对应 DOCK 等待次数。
        dock = result.resources[0]
        self.assertGreaterEqual(dock.wait_count, 260)
        self.assertLessEqual(dock.wait_count, 320)

        # 期末班次相位应与旧版一致。
        self.assertEqual(result.continuous_final["LOAD_AVAIL"], 0.0)

        observations = {item.label: item for item in result.observations}
        self.assertGreaterEqual(observations["WAITING TIME"].count, 290)
        self.assertLessEqual(observations["WAITING TIME"].count, 330)
        self.assertGreaterEqual(observations["WAITING TIME"].mean, 1.2)
        self.assertLessEqual(observations["WAITING TIME"].mean, 2.2)

        self.assertGreaterEqual(observations["TRIP TIME"].count, 290)
        self.assertLessEqual(observations["TRIP TIME"].count, 330)
        self.assertGreaterEqual(observations["TRIP TIME"].mean, 13.5)
        self.assertLessEqual(observations["TRIP TIME"].mean, 15.2)

    def test_clear_time_reduces_statistics(self):
        model = helix.Model.from_file(str(MODEL))
        full = model.initialize(initial=INITIAL).run(end=100, seed=1)
        window = model.initialize(initial=INITIAL).run(
            end=100, seed=1, clear_time=65)
        full_ret = {s.activity: s.completed for s in full.services}["RET"]
        window_ret = {s.activity: s.completed for s in window.services}["RET"]
        self.assertLess(window_ret, full_ret)


if __name__ == "__main__":
    unittest.main(verbosity=2)
