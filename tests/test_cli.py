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


if __name__ == "__main__":
    unittest.main(verbosity=2)
