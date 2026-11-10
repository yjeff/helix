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


class ContinuousTest(unittest.TestCase):

    def test_dd_ss_rk4(self):
        model = helix.Model.from_source(MODEL)
        result = model.initialize(
            initial={"TEMPERATURE": 10.0}).run(end=1, seed=1)
        self.assertGreater(len(result.continuous), 5)
        final = result.continuous[-1]["values"]["TEMP"]
        self.assertAlmostEqual(final, 10.0 * 2.718281828 ** -1, places=2)

    def test_rkf45(self):
        model = helix.Model.from_source("""
HELIX 1
VAR TEMP AS "TEMPERATURE"
CONTINUOUS METHOD=RKF45, MIN_STEP=0.0001, SAVE_STEP=0.1, MAX_STEP=0.1, TOL=1e-6
EQUATION
  DD(TEMP) = -TEMP
END EQUATION
NETWORK
  CREATE(count=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(
            initial={"TEMPERATURE": 10.0}).run(end=1, seed=1)
        final = result.continuous[-1]["values"]["TEMP"]
        self.assertAlmostEqual(final, 10.0 * 2.718281828 ** -1, places=4)

    def test_sevnt_stops(self):
        model = helix.Model.from_source("""
HELIX 1
VAR TEMP AS "TEMPERATURE"
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
SEVNT code=1, when=TEMP < 5
EQUATION
  DD(TEMP) = -TEMP
END EQUATION
NETWORK
  CREATE(count=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(
            initial={"TEMPERATURE": 10.0}).run(end=5, seed=1)
        self.assertLess(result.now, 5.0)
        # TEMP=10*exp(-t)=5 -> t=ln(2)=0.693147
        self.assertAlmostEqual(result.now, 0.693147, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
