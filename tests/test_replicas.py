import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
NETWORK
  CREATE(interval=1, until=5) -> DONE
  DONE: EXIT()
END
"""


class ReplicaTest(unittest.TestCase):

    def test_python_api_replicas(self):
        scenario = helix.Model.from_source(MODEL).initialize()
        replica = scenario.run_replicas(3, seed=7, end=6)
        self.assertEqual(replica.n, 3)
        self.assertEqual(replica.seeds, [7, 8, 9])
        self.assertEqual(replica.manifest()["replications"], 3)
        metric = replica.observations()["TIME IN SYSTEM"]
        self.assertEqual(metric.runs, 3)
        self.assertEqual(metric.half_width, 0.0)

    def test_same_config_manifest_is_reproducible(self):
        scenario = helix.Model.from_source(MODEL).initialize()
        first = scenario.run(end=6, seed=7)
        second = scenario.run(end=6, seed=7)
        self.assertEqual(first.manifest(), second.manifest())
        out = ROOT / "tests" / "_replica_tmp"
        shutil.rmtree(out, ignore_errors=True)
        try:
            path = out / "run.json"
            first.write_manifest(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["seed"], 7)
            self.assertEqual(data["model_hash"], first.model_hash)
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
