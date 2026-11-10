import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "tv_inspection" / "model.helix"


class TVCaseTest(unittest.TestCase):
    """TV Inspection 全回路：加载 → initialize → run → report → DEBUG。"""

    def test_full_loop(self):
        model = helix.Model.from_file(str(MODEL))
        scenario = model.initialize()

        first = scenario.run(end=480, seed=1)
        second = scenario.run(end=480, seed=1)

        # 同 seed 重放必须完全一致。
        self.assertEqual(first.now, second.now)
        self.assertEqual(first.observations[0].count,
                         second.observations[0].count)
        self.assertAlmostEqual(first.observations[0].mean,
                               second.observations[0].mean)

        # 案例结构：两个服务活动、同一个系统时间观测。
        self.assertEqual(len(first.services), 2)
        inspect = next(s for s in first.services
                       if s.activity == "INSPECT")
        adjust = next(s for s in first.services
                      if s.activity == "ADJUST")
        self.assertGreater(inspect.completed, 0)
        self.assertGreater(adjust.completed, 0)
        self.assertGreater(first.observations[0].count, 0)

        out = ROOT / "tests" / "_tv_case"
        shutil.rmtree(out, ignore_errors=True)
        try:
            out.mkdir(parents=True)
            first.report(
                str(out / "report.md"),
                track={
                    "TIME": "SYSTEM.TIME",
                    "Q1 WAIT": "QUEUE.Q1.WAIT",
                    "INSPECT": "ACTIVITY.INSPECT.UTIL",
                },
                plot=[],
            )
            text = (out / "report.md").read_text(encoding="utf-8")
            self.assertIn("TRACKED METRICS", text)
            self.assertIn("INSPECT", text)

            debugged = scenario.run(
                end=10, seed=1, debug=True,
                debug_path=str(out / "debug"))
            self.assertTrue((out / "debug" / "events.ndjson").exists())
            self.assertEqual(debugged.debug_path, str(out / "debug"))
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
