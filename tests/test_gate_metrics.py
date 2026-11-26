import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
GATE LIGHT1(state=CLOSED)
NETWORK
  CREATE(count=1) -> WAIT
  CREATE(interval=2, count=1, first=2) -> OPEN_NODE
  WAIT: AWAIT(gate=LIGHT1) -> DONE
  OPEN_NODE: OPEN(gate=LIGHT1) -> DONE2
  DONE: EXIT()
  DONE2: EXIT()
END
"""


class GateMetricTest(unittest.TestCase):

    def test_gate_wait_duration_and_metric_namespace(self):
        result = helix.Model.from_source(MODEL).initialize().run(
            end=10, seed=1)
        gate = result.gates[0]
        self.assertEqual(gate.name, "LIGHT1")
        self.assertEqual(gate.state, "OPEN")
        self.assertEqual(gate.wait_count, 1)
        self.assertAlmostEqual(gate.average_wait, 2.0)
        self.assertAlmostEqual(gate.max_wait, 2.0)
        self.assertAlmostEqual(result._metric("GATE.LIGHT1.WAIT"), 2.0)
        self.assertAlmostEqual(result._metric("GATE.WAIT"), 2.0)
        self.assertAlmostEqual(
            result._metric("GATE.LIGHT1.MAX_WAIT"), 2.0)
        self.assertEqual(result._metric("GATE.LIGHT1.WAIT_COUNT"), 1.0)

    def test_gate_report_has_wait_columns(self):
        out = ROOT / "tests" / "_gate_report_tmp"
        out.mkdir(parents=True, exist_ok=True)
        try:
            path = out / "report.md"
            result = helix.Model.from_source(MODEL).initialize().run(
                end=10, seed=1)
            result.report(str(path))
            text = path.read_text(encoding="utf-8")
            self.assertIn("## GATE STATISTICS", text)
            self.assertIn("AVG WAIT", text)
            self.assertIn("MAX WAIT", text)
            self.assertRegex(
                text,
                r"LIGHT1\s+\|\s+OPEN\s+\|\s+1\s+\|\s+2\.0000\s+\|\s+2\.0000")
        finally:
            import shutil
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
