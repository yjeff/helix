import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
VAR TEMP AS "TEMPERATURE"
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
EQUATION
  DD(TEMP) = -TEMP
END EQUATION
NETWORK
  CREATE(count=1)
  TERMINATE()
END NETWORK
"""


class ReportTest(unittest.TestCase):

    def test_default_report_tables(self):
        result = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=2)
  Q1: QUEUE()
  A1: ACTIVITY(duration=1)
  EXIT()
END
""").initialize().run(end=3, seed=1)
        out = ROOT / "tests" / "_default_report_tmp"
        shutil.rmtree(out, ignore_errors=True)
        try:
            path = out / "report.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            result.report(str(path))
            text = path.read_text(encoding="utf-8")
            self.assertIn("# Helix SUMMARY REPORT", text)
            self.assertIn("## QUEUE STATISTICS", text)
            self.assertIn("AVG LENGTH", text)
            self.assertIn("## SERVICE ACTIVITY STATISTICS", text)
            self.assertIn("AVG UTIL.", text)
            self.assertIn("SERVERS", text)
            self.assertIn("## ABBREVIATIONS", text)
            lines = text.splitlines()
            start = lines.index("## QUEUE STATISTICS") + 2
            table = []
            for line in lines[start:]:
                if not line.startswith("|"):
                    break
                table.append(line)
            self.assertGreaterEqual(len(table), 3)
            self.assertEqual(len({len(line) for line in table}), 1)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_queue_and_activity_metrics(self):
        result = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(interval=0, count=5)
  Q1: QUEUE(capacity=10)
  A1: ACTIVITY(duration=1)
  EXIT()
END
""").initialize().run(end=3, seed=1)
        out = ROOT / "tests" / "_metric_tmp"
        shutil.rmtree(out, ignore_errors=True)
        try:
            path = out / "report.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            result.report(str(path), track={
                "Q1 LENGTH": "QUEUE.Q1.LENGTH",
                "Q1 STD": "QUEUE.Q1.STD_LENGTH",
                "Q1 MAX": "QUEUE.Q1.MAX_LENGTH",
                "A1 UTIL": "ACTIVITY.A1.UTIL",
                "A1 STD": "ACTIVITY.A1.STD_UTIL",
                "A1 MAX": "ACTIVITY.A1.MAX_UTIL",
                "A1 BLOCK": "ACTIVITY.A1.BLOCK",
                "A1 IDLE": "ACTIVITY.A1.MAX_IDLE",
            })
            text = path.read_text(encoding="utf-8")
            self.assertIn("Q1 STD", text)
            self.assertIn("A1 MAX", text)
            self.assertIn("A1 IDLE", text)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_track_and_plot(self):
        result = helix.Model.from_source(MODEL).initialize(
            initial={"TEMPERATURE": 10.0}).run(end=1, seed=1)
        out = ROOT / "tests" / "_report_tmp"
        shutil.rmtree(out, ignore_errors=True)
        try:
            path = out / "report.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            result.report(
                str(path),
                project="TEST PROJECT",
                track={"TEMP LAST": "TEMP", "TEMP MEAN": "TEMP.MEAN"},
                plot=["TEMP"],
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("TEST PROJECT", text)
            self.assertIn("TRACKED METRICS", text)
            self.assertIn("TEMP LAST", text)
            svg = out / "report.svg"
            self.assertTrue(svg.exists())
            self.assertIn("<polyline", svg.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
