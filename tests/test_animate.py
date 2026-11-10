import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402
from helix.animate import build_player  # noqa: E402


class AnimateTest(unittest.TestCase):

    def test_build_player(self):
        model = helix.Model.from_file(
            str(ROOT / "examples" / "serial_workstations" / "model.helix"))
        tmp = Path(__file__).resolve().parent / "_anim_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()
        try:
            debug_dir = tmp / "debug"
            model.initialize().run(end=3, seed=1, debug=True,
                                   debug_path=str(debug_dir))
            states = [
                json.loads(line)
                for line in (debug_dir / "states.ndjson").read_text(
                    encoding="utf-8").splitlines() if line.strip()
            ]
            self.assertTrue(states)
            self.assertIn("entities", states[0])
            output = build_player(debug_dir, tmp / "player.html")
            text = output.read_text(encoding="utf-8")
            self.assertIn("Helix Animation", text)
            self.assertIn("const DATA", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
