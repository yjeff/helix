import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from helix.cli import main  # noqa: E402

MODEL = ROOT / "examples" / "serial_workstations" / "model.helix"


class CliTest(unittest.TestCase):

    def test_check(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["check", str(MODEL)])
        self.assertEqual(code, 0)
        self.assertIn("ok:", output.getvalue())

    def test_run(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["run", str(MODEL), "--end", "2", "--seed", "1"])
        self.assertEqual(code, 0)
        self.assertIn("time:", output.getvalue())


    def test_run_replicas(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "run", str(MODEL), "--end", "2", "--seed", "1",
                "--replicas", "3",
            ])
        self.assertEqual(code, 0)
        self.assertIn("replicas: 3", output.getvalue())
        self.assertIn("HALF-WIDTH", output.getvalue())

    def test_compare(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "compare", str(MODEL), str(MODEL),
                "--end", "2", "--seed", "1", "--replicas", "2",
            ])
        self.assertEqual(code, 0)
        self.assertIn("compare:", output.getvalue())
        self.assertIn("OBSERVATIONS", output.getvalue())
        self.assertIn("paired by seed", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
