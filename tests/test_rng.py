import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402
from helix.kernel import Kernel  # noqa: E402


MODEL = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  EXIT()
END
""")


class RngTest(unittest.TestCase):

    def _runtime(self):
        scenario = MODEL.initialize()
        kernel = Kernel(scenario=scenario, start=0.0, end=1.0, seed=7)
        return kernel.runtime

    def test_substreams_are_independent(self):
        first = self._runtime()._rng("NODE_A", "duration").random()
        runtime = self._runtime()
        runtime._rng("NODE_B", "duration").random()
        second = runtime._rng("NODE_A", "duration").random()
        self.assertEqual(first, second)

    def test_global_mode_keeps_legacy_stream(self):
        runtime = self._runtime()
        runtime.rng_mode = "global"
        first = runtime._rng("A", "x").random()
        second = runtime._rng("B", "y").random()
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
