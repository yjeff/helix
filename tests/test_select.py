import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
NETWORK
  CREATE(interval=0.1, count=2)

  LOAD: QUEUE()
  TRKS: QUEUE()
  LDER: QUEUE()

  BEGN: SELECT(
    queue_rule=ASM,
    server_rule=LIT,
    queues=[LOAD, TRKS, LDER],
    servers=[L1, L2],
  )

  L1: ACTIVITY(duration=1) -> DONE
  L2: ACTIVITY(duration=1) -> DONE
  DONE: TERMINATE()

  LOAD -> BEGN
  TRKS -> BEGN
  LDER -> BEGN
END NETWORK
"""


class SelectTest(unittest.TestCase):

    def test_select_asm(self):
        model = helix.Model.from_source(MODEL)
        self.assertEqual(model.nodes["BEGN"].kind, "SELECT")
        result = model.initialize(entities={
            "TRKS": [{}, {}],
            "LDER": [{}, {}],
        }).run(end=10, seed=1)
        self.assertEqual(result.observations[0].count, 2)
        self.assertEqual(sum(s.completed for s in result.services), 2)
        self.assertEqual(result.services[0].completed, 1)
        self.assertEqual(result.services[1].completed, 1)

    def test_server_rules(self):
        for rule in ("POR", "CYC", "RAN", "LIT", "SIT", "LBT", "SBT"):
            model = helix.Model.from_source(
                MODEL.replace("server_rule=LIT",
                              f"server_rule={rule}"))
            result = model.initialize(entities={
                "TRKS": [{}, {}],
                "LDER": [{}, {}],
            }).run(end=10, seed=7)
            self.assertEqual(
                sum(s.completed for s in result.services), 2,
                f"server_rule={rule}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
