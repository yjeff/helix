import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1

VAR LEVEL AS "LEVEL"

CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1

EQUATION
  DD(LEVEL) = 1.0
END EQUATION

NETWORK
  CREATE(count=1)

  HOLD: ACTIVITY(until=GO)
  TERMINATE()

  GO: DETECT(when=LEVEL > 1.0) -> SIGNAL
  SIGNAL: TERMINATE()
END NETWORK
"""


class AssignDetectTest(unittest.TestCase):

    def test_until_detect_event(self):
        model = helix.Model.from_source(MODEL)
        result = model.initialize(initial={"LEVEL": 0.0}).run(end=5)
        self.assertAlmostEqual(result.observations[0].mean, 1.0, places=2)

    def test_assign_variable(self):
        model = helix.Model.from_source("""
HELIX 1
VAR STAMP ENTITY
VAR X GLOBAL
NETWORK
  CREATE(count=1)
  SET: ASSIGN(STAMP=TNOW, X=3)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0}).run(end=1)
        self.assertEqual(result.observations[0].count, 1)

    def test_top_level_detect_event(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
DETECT name=LEVEL_UP, when=X > 1
EQUATION
  DD(X) = 1
END EQUATION
NETWORK
  CREATE(count=1)
  HOLD: ACTIVITY(until=LEVEL_UP)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0}).run(end=5)
        self.assertAlmostEqual(result.observations[0].mean, 1.0, places=2)

    def test_dynamic_event_name(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
VAR IDX GLOBAL
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
SEVNT name=GO, code=2, when=X > 1, action=FIRE
EQUATION
  DD(X) = 1
END EQUATION
NETWORK
  CREATE(count=1)
  ASSIGN(IDX=2)
  HOLD: ACTIVITY(until=DONE[IDX])
  TERMINATE()

  FIRE: EVENT(name=DONE[IDX])
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0, "IDX": 0}).run(end=5)
        self.assertEqual(result.observations[0].count, 1)

    def test_event_action(self):
        model = helix.Model.from_source("""
HELIX 1
VAR FLAG GLOBAL
NETWORK
  CREATE(count=1)
  EVENT(name=SET_FLAG, action=SET)
  TERMINATE()

  SET: ASSIGN(FLAG=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"FLAG": 0}).run(end=1)
        self.assertEqual(result.global_values["FLAG"], 1.0)

    def test_sevnt_action(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
VAR FLAG GLOBAL
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
SEVNT name=READY, code=2, when=X > 1, action=SET
EQUATION
  DD(X) = 1
END EQUATION
NETWORK
  CREATE(count=1)
  HOLD: ACTIVITY(until=READY)
  TERMINATE()

  SET: ASSIGN(FLAG=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0, "FLAG": 0}).run(end=5)
        self.assertEqual(result.continuous_final["FLAG"], 1.0)

    def test_sevnt_until_event(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
SEVNT name=HOLD_DONE, code=2, when=X > 1
EQUATION
  DD(X) = 1
END EQUATION
NETWORK
  CREATE(count=1)
  HOLD: ACTIVITY(until=HOLD_DONE)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0}).run(end=5)
        self.assertEqual(result.observations[0].count, 1)
        self.assertAlmostEqual(result.observations[0].mean, 1.0, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
