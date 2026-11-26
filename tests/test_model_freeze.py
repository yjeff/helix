import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
RESOURCE R(2)
NETWORK
  CREATE(count=1) -> A
  A: ACTIVITY(duration=1) -> DONE
  DONE: EXIT()
END
"""


class ModelFreezeTest(unittest.TestCase):

    def test_compiled_model_is_frozen(self):
        model = helix.Model.from_source(MODEL)
        self.assertTrue(model.is_frozen)
        with self.assertRaises(TypeError):
            model.nodes["A"].args["duration"] = "2"
        with self.assertRaises(AttributeError):
            model.nodes["A"].outgoing = []
        with self.assertRaises(AttributeError):
            model.nodes["A"].label = "B"

    def test_spec_mutation_warns_before_next_run(self):
        model = helix.Model.from_source(MODEL)
        scenario = model.initialize()
        model.resources["R"].capacity = 1
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            scenario.run(end=3, seed=1)
        self.assertTrue(any("freeze" in str(item.message) for item in caught))

    def test_fingerprint_survives_run(self):
        model = helix.Model.from_source(MODEL)
        before = model.structure_fingerprint()
        model.initialize().run(end=3, seed=1)
        self.assertEqual(model.structure_fingerprint(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
