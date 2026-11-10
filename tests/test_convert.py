import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402
from helix.convert import convert_file  # noqa: E402

SLAM_ROOT = ROOT.parent / "slam_v2"


@unittest.skipUnless((SLAM_ROOT / "SLAM" / "parser.py").exists(),
                     "slam_v2 parser not present")
class ConvertTest(unittest.TestCase):

    def test_serial_conversion_compiles(self):
        source, warnings = convert_file(
            SLAM_ROOT / "examples" / "discrete" /
            "serial_workstations.slam")
        self.assertIn("HELIX 1", source)
        model = helix.Model.from_source(source)
        self.assertTrue(model.nodes)
        self.assertTrue(any(node.kind == "QUEUE"
                            for node in model.nodes.values()))

    def test_cedar_conversion_names(self):
        source, warnings = convert_file(
            SLAM_ROOT / "examples" / "continuous" /
            "cedar_bog_lake.slam")
        self.assertIn("DD(P)", source)
        self.assertIn("VAR P GLOBAL", source)
        helix.Model.from_source(source)

    def test_tanker_conversion_names(self):
        source, warnings = convert_file(
            SLAM_ROOT / "examples" / "mixed" /
            "tanker_fleet.slam")
        self.assertIn("DD(T)", source)
        self.assertIn("DD(S)", source)
        self.assertIn("ACTIVITY(until=ENDU)", source)
        helix.Model.from_source(source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
