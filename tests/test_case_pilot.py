import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = ROOT / "examples" / "pilot_ejection" / "model.helix"

VA = 900.0
VE = 40.0
THE = 15.0 / 57.3
VX = VA - VE * math.sin(THE)
VY = VE * math.cos(THE)


class PilotCaseTest(unittest.TestCase):

    def test_old_new_parity(self):
        model = helix.Model.from_file(str(MODEL))
        result = model.initialize(
            initial={
                "X": 0.0,
                "Y": 0.0,
                "V": math.sqrt(VX * VX + VY * VY),
                "THETA": math.atan2(VY, VX),
                "LEFT_COCKPIT": 0.0,
            },
            constants={
                "VA": VA, "VE": VE, "THE": THE,
                "G": 32.2, "RHO": 0.0023769,
                "CD": 1.0, "XS": 10.0, "XM": 7.0,
            },
        ).run(end=4.0)

        final = result.continuous_final
        self.assertAlmostEqual(result.now, 0.4338647456, places=6)
        self.assertAlmostEqual(final["X"], -60.0, places=5)
        self.assertAlmostEqual(final["Y"], 12.809593, places=5)
        self.assertAlmostEqual(final["V"], 593.620832, places=4)
        self.assertAlmostEqual(final["THETA"], 0.028481, places=5)
        self.assertEqual(final["LEFT_COCKPIT"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
