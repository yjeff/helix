import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helix  # noqa: E402


MODEL = """
HELIX 1
PROJECT "TEST"

NETWORK
  CREATE(interval=EXPON(0.4), until=50)
  Q1: QUEUE(capacity=4, on_full=BALK(SUB))
  ACTIVITY(duration=EXPON(0.25))
  TERMINATE()
  SUB: TERMINATE()
END NETWORK
"""


class HelixCoreTest(unittest.TestCase):

    def test_parse_graph(self):
        model = helix.Model.from_source(MODEL)
        self.assertEqual(model.project, "TEST")
        self.assertEqual(model.nodes["Q1"].kind, "QUEUE")
        self.assertEqual(model.nodes["Q1"].args["on_full"], "BALK(SUB)")
        self.assertIn("SUB", model.nodes)

    def test_serial_run(self):
        model = helix.Model.from_source(MODEL)
        result = model.initialize().run(end=50, seed=1)
        self.assertGreater(result.now, 0)
        self.assertEqual(len(result.services), 1)
        self.assertGreater(result.services[0].completed, 0)
        self.assertEqual(len(result.observations), 1)
        self.assertGreater(result.observations[0].count, 0)

    def test_comments_and_continuation(self):
        model = helix.Model.from_source("""
HELIX 1
PROJECT "COMMENT TEST"
; 这是注释
NETWORK
  CREATE(
    interval=1,
    first=0,
  )   ; 行尾注释
  Q1: QUEUE(
    capacity=2,
  )
  ACTIVITY(duration=1)
  TERMINATE()
END NETWORK
""")
        self.assertEqual(model.project, "COMMENT TEST")
        self.assertEqual(model.nodes["Q1"].kind, "QUEUE")
        self.assertEqual(len(model.nodes["Q1"].args), 1)

    def test_initial_by_label(self):
        model = helix.Model.from_source("""
HELIX 1
VAR TEMP GLOBAL AS "TEMPERATURE" RANGE 0..100
NETWORK
  CREATE()
  TERMINATE()
END NETWORK
""")
        scenario = model.initialize(initial={"TEMPERATURE": 12.5})
        self.assertEqual(scenario.initial["TEMP"], 12.5)

    def test_var_scope_inference(self):
        model = helix.Model.from_source("""
HELIX 1
VAR TEMP
VAR STAMP ENTITY
VAR FLAG GLOBAL
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
EQUATION
  DD(TEMP) = -TEMP
END EQUATION
NETWORK
  CREATE(count=1)
  SET: ASSIGN(STAMP=TNOW, FLAG=1)
  TERMINATE()
END NETWORK
""")
        self.assertEqual(model.variables["TEMP"].scope, "GLOBAL")
        self.assertEqual(model.variables["STAMP"].scope, "ENTITY")
        self.assertEqual(model.variables["FLAG"].scope, "GLOBAL")

    def test_array_variables(self):
        model = helix.Model.from_source("""
HELIX 1
VAR TEMP[3]
VAR SUM
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
EQUATION
  DD(TEMP[1]) = 1
  DD(TEMP[2]) = 2
  DD(TEMP[3]) = 3
  SS(SUM) = TEMP[1] + TEMP[2] + TEMP[3]
END EQUATION
NETWORK
  CREATE(count=1)
  SET: ASSIGN(TEMP[2]=10)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"TEMP": [1, 2, 3]}).run(end=1)
        self.assertAlmostEqual(result.continuous_final["TEMP[1]"], 2.0)
        self.assertAlmostEqual(result.continuous_final["TEMP[2]"], 12.0)
        self.assertAlmostEqual(result.continuous_final["TEMP[3]"], 6.0)
        self.assertAlmostEqual(result.continuous_final["SUM"], 20.0)

    def test_shorthand_declarations(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(2)
NETWORK
  CREATE(1) -> Q
  Q: QUEUE(3)
  AWAIT(R)
  ACTIVITY(1)
  FREE(R)
  TERMINATE()
END NETWORK
""")
        self.assertEqual(model.resources["R"].capacity, 2)
        self.assertEqual(model.nodes["Q"].args["capacity"], "3")
        create = next(node for node in model.nodes.values()
                      if node.kind == "CREATE")
        self.assertEqual(create.args["interval"], "1")

    def test_shorthand_activity_await_free(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=1)
NETWORK
  CREATE(count=1)
  AWAIT(R)
  ACTIVITY(2)
  FREE(R)
  TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=5)
        self.assertEqual(result.observations[0].count, 1)

    def test_old_if_syntax_rejected(self):
        from helix.errors import HelixSyntaxError
        with self.assertRaises(HelixSyntaxError):
            helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  B: IF
    WHEN RANDOM() < 0.5 -> A
    ELSE -> A
  END IF
  A: TERMINATE()
END NETWORK
""")

    def test_else_if_chain(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  B: IF RANDOM() < 0.2 -> A
  ELSE IF RANDOM() < 0.5 -> C
  ELSE -> D

  A: TERMINATE()
  C: TERMINATE()
  D: TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=1, seed=3)
        self.assertEqual(result.observations[0].count, 1)

    def test_scan_observe_shorthand(self):
        model = helix.Model.from_source("""
HELIX 1
VAR A[2] GLOBAL
NETWORK
  CREATE(count=1)
  SCAN I IN 1..2
    WHERE A[I] == 0
    DO OBSERVE("POS", I)
    STOP
  END SCAN
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"A": [0, 0]}).run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["POS"].mean, 1.0)

    def test_numeric_equation_rejected(self):
        from helix.errors import HelixCompileError
        with self.assertRaises(HelixCompileError):
            helix.Model.from_source("""
HELIX 1
VAR X
EQUATION
  DD(1) = 1
END
NETWORK
  EXIT()
END
""")

    def test_lowercase_header_and_bom(self):
        model = helix.Model.from_source("\ufeffhelix 1\n"
                                        "network\n"
                                        "  create(count=1)\n"
                                        "  exit()\n"
                                        "end\n")
        self.assertTrue(model.nodes)

    def test_lowercase_var_declaration(self):
        model = helix.Model.from_source("""
helix 1
var		id entity
network
  create(count=1)
  assign(id=7)
  observe("ID", id)
  exit
end
""")
        result = model.initialize().run(end=1)
        self.assertEqual(result.observations[0].values, [7])

    def test_balk_preserves_lowercase_label(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(interval=0, count=5)
  q1: QUEUE(capacity=1, on_full=BALK(sub))
  ACTIVITY(duration=10)
  sub: EXIT()
END
""")
        result = model.initialize().run(end=2)
        self.assertEqual(result.queues[0].balk_count, 3)

    def test_continuous_options(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
CONTINUOUS METHOD=RK4, MIN_STEP=0.1, SAVE_STEP=0.1, MAX_STEP=0.1
EQUATION
  DD(X) = 1
END
NETWORK
  EXIT()
END
""")
        scenario = model.initialize(
            initial={"X": 0},
            continuous={
                "method": "RKF45",
                "min_step": 1e-4,
                "save_step": 0.01,
                "max_step": 0.01,
                "tol": 1e-6,
            },
        )
        result = scenario.run(end=1)
        self.assertAlmostEqual(result.continuous_final["X"], 1.0, places=3)

    def test_unknown_continuous_option(self):
        from helix.errors import HelixCompileError
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  EXIT()
END
""")
        with self.assertRaises(HelixCompileError):
            model.initialize(continuous={"bogus": 1})

    def test_create_count_without_interval_is_batch(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=4)
  EXIT()
END
""")
        result = model.initialize().run(end=1)
        self.assertEqual(result.observations[0].count, 4)

    def test_create_batch_attributes(self):
        model = helix.Model.from_source("""
HELIX 1
VAR ID ENTITY
VAR VALUE ENTITY
NETWORK
  CREATE(count=5, ID=[1, 2, 3, 4, 5],
         VALUE=[10, 20, 30, 40, 50])
  OBSERVE("ID", ID)
  OBSERVE("VALUE", VALUE)
  EXIT()
END
""")
        result = model.initialize().run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["ID"].values, [1, 2, 3, 4, 5])
        self.assertEqual(
            observations["VALUE"].values, [10, 20, 30, 40, 50])

    def test_create_batch_attributes_interval_zero(self):
        model = helix.Model.from_source("""
HELIX 1
VAR ID ENTITY
VAR VALUE ENTITY
NETWORK
  CREATE(count=5, interval=0,
         ID=[1, 2, 3, 4, 5],
         VALUE=[10, 20, 30, 40, 50])
  OBSERVE("ID", ID)
  OBSERVE("VALUE", VALUE)
  EXIT()
END
""")
        result = model.initialize().run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["ID"].values, [1, 2, 3, 4, 5])
        self.assertEqual(
            observations["VALUE"].values, [10, 20, 30, 40, 50])

    def test_create_batch_attributes_infer_count(self):
        model = helix.Model.from_source("""
HELIX 1
VAR ID ENTITY
NETWORK
  CREATE(ID=[7, 8, 9])
  OBSERVE("ID", ID)
  EXIT()
END
""")
        result = model.initialize().run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["ID"].values, [7, 8, 9])

    def test_create_attribute_length_mismatch(self):
        from helix.errors import HelixCompileError
        with self.assertRaises(HelixCompileError):
            helix.Model.from_source("""
HELIX 1
VAR ID ENTITY
NETWORK
  CREATE(count=2, ID=[1, 2, 3])
  EXIT()
END
""")

    def test_alter_resource_capacity(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=1)
NETWORK
  CREATE(count=1)
  ALTER(resource=R, capacity=2)
  EXIT()
END
""")
        result = model.initialize().run(end=1)
        self.assertEqual(result.resources[0].capacity, 2)

    def test_alter_activity_duration(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  SET: ALTER(activity=SERVICE, duration=1)
  SERVICE: ACTIVITY(duration=5)
  EXIT()
END
""")
        result = model.initialize().run(end=10)
        self.assertAlmostEqual(result.observations[0].mean, 1.0)
        self.assertEqual(model.nodes["SERVICE"].args["duration"], "1")

    def test_alter_create_interval(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  C: CREATE(interval=10, count=2) -> SET
  SET: ALTER(create=C, interval=1)
  EXIT()
END
""")
        model.initialize().run(end=2)
        self.assertEqual(model.nodes["C"].args["interval"], "1")

    def test_end_closes_blocks(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
EQUATION
  DD(X) = 1
END
NETWORK
  CREATE(count=1)
  EXIT()
END
""")
        result = model.initialize(initial={"X": 0}).run(end=1)
        self.assertEqual(result.observations[0].count, 1)

    def test_exit_alias(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  EXIT()
END NETWORK
""")
        result = model.initialize().run(end=1)
        self.assertEqual(result.observations[0].count, 1)

    def test_shorthand_gate_observe(self):
        model = helix.Model.from_source("""
HELIX 1
GATE L(OPEN)
NETWORK
  CREATE(count=1)
  OBSERVE("DOUBLE", 1 + 1)
  TERMINATE()
END NETWORK
""")
        self.assertEqual(model.gates["L"].state, "OPEN")
        result = model.initialize().run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["DOUBLE"].mean, 2.0)

    def test_goto_alias(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1) GOTO A

  A: ACTIVITY(duration=1)
     GOTO B

  B: IF RANDOM() < 2.0 -> C
  ELSE GOTO C

  C: TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=1)
        self.assertEqual(result.observations[0].count, 1)

    def test_goto_in_parallel(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(count=1)
  PARALLEL
    PATH GOTO A
    PATH GOTO B
  END PARALLEL

  A: TERMINATE()
  B: TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=1)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0].count, 2)

    def test_continuous_statistics_dt(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X
CONTINUOUS METHOD=RK4, MIN_STEP=0.01, SAVE_STEP=0.1, MAX_STEP=0.1
EQUATION
  DD(X) = 1
END EQUATION
RESOURCE R(capacity=1)
NETWORK
  CREATE(count=1)
  AWAIT(resource=R)
  ACTIVITY(duration=2)
  FREE(resource=R)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0}).run(end=10)
        self.assertGreater(result.resources[0].average_held, 0.0)
        self.assertGreater(result.services[0].average_utilization, 0.0)

    def test_initial_entity_at_node(self):
        model = helix.Model.from_source("""
HELIX 1
RESOURCE R(capacity=1)
NETWORK
  AWAIT_PIT: AWAIT(resource=R)
  ACTIVITY(duration=1)
  FREE(resource=R)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(entities={
            "AWAIT_PIT": [{"LOAD_START": 0.0}],
        }).run(end=5)
        self.assertEqual(result.observations[0].count, 1)

    def test_observe_node(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X GLOBAL
NETWORK
  CREATE(count=1)
  ASSIGN(X=5)
  OBSERVE(name="SAMPLE", value=X)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0}).run(end=1)
        self.assertEqual(result.observations[0].count, 1)
        self.assertEqual(result.observations[0].mean, 5.0)

    def test_array_sum_function(self):
        model = helix.Model.from_source("""
HELIX 1
VAR A[3] GLOBAL
VAR S
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
EQUATION
  SS(S) = SUM(A)
END EQUATION
NETWORK
  CREATE(count=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"A": [1, 2, 3]}).run(end=1)
        self.assertEqual(result.continuous_final["S"], 6.0)

    def test_assign_distribution(self):
        model = helix.Model.from_source("""
HELIX 1
VAR X GLOBAL
NETWORK
  CREATE(count=1)
  ASSIGN(X=UNFRM(10, 20))
  TERMINATE()
END NETWORK
""")
        result = model.initialize(initial={"X": 0}).run(end=1, seed=7)
        self.assertGreaterEqual(result.global_values["X"], 10.0)
        self.assertLessEqual(result.global_values["X"], 20.0)

    def test_scan_array(self):
        model = helix.Model.from_source("""
HELIX 1
VAR ACTIVE[3] GLOBAL
VAR PIT_INDEX GLOBAL
NETWORK
  CREATE(count=1)
  SCAN PIT IN 1..3
    WHERE ACTIVE[PIT] == 0
    DO ASSIGN(PIT_INDEX=PIT, ACTIVE[PIT]=1)
    STOP
  END SCAN
  TERMINATE()
END NETWORK
""")
        result = model.initialize(
            initial={"ACTIVE": [1, 0, 0], "PIT_INDEX": 0}).run(end=1)
        self.assertEqual(result.global_values["PIT_INDEX"], 2.0)
        self.assertEqual(result.global_values["ACTIVE[2]"], 1.0)

    def test_clear_time(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(interval=1, count=20)
  TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=10, seed=1, clear_time=5)
        # 统计清零后只应保留 5 之后完成的实体。
        self.assertGreater(result.observations[0].count, 0)
        self.assertLessEqual(result.observations[0].count, 6)

    def test_unknown_initial(self):
        model = helix.Model.from_source("""
HELIX 1
VAR TEMP AS "TEMPERATURE"
NETWORK
  CREATE()
  TERMINATE()
END NETWORK
""")
        with self.assertRaises(helix.HelixCompileError):
            model.initialize(initial={"NO SUCH": 1})

    def test_balk_not_system_time(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(interval=0.1, until=3)
  Q: QUEUE(capacity=1, on_full=BALK(SUB))
  A: ACTIVITY(duration=10)
  TERMINATE()
  SUB: TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=15, seed=1)
        self.assertEqual(result.observations[0].count, 1)
        self.assertGreater(result.queues[0].balk_count, 0)

    def test_if_branch(self):
        model = helix.Model.from_source("""
HELIX 1
NETWORK
  CREATE(interval=0.1, count=20)
  CHECK: IF RANDOM() < 0.5 -> A
  ELSE -> B
  A: ACTIVITY(duration=1)
  TERMINATE()
  B: ACTIVITY(duration=1)
  TERMINATE()
END NETWORK
""")
        result = model.initialize().run(end=10, seed=3)
        self.assertEqual(len(result.services), 2)
        self.assertGreater(result.services[0].completed, 0)
        self.assertGreater(result.services[1].completed, 0)

    def test_activity_distribution_attribute(self):
        model = helix.Model.from_source("""
HELIX 1
VAR SVLTIME ENTITY
NETWORK
  CREATE(count=2, SVLTIME=[5, 7])
  ACTIVITY(duration=UNFRM(SVLTIME, SVLTIME), servers=2)
  EXIT()
END
""")
        result = model.initialize().run(end=20)
        self.assertEqual(result.observations[0].count, 2)
        self.assertAlmostEqual(result.observations[0].mean, 6.0)

    def test_activity_duration_from_attribute(self):
        model = helix.Model.from_source("""
HELIX 1
VAR SVLTIME ENTITY
NETWORK
  CREATE(count=2, SVLTIME=[5, 7])
  ACTIVITY(duration=SVLTIME, servers=2)
  EXIT()
END
""")
        result = model.initialize().run(end=20)
        self.assertEqual(result.observations[0].count, 2)
        self.assertAlmostEqual(result.observations[0].mean, 6.0)

    def test_if_or_and_not_equal(self):
        model = helix.Model.from_source("""
HELIX 1
VAR ID ENTITY
NETWORK
  CREATE(count=3, ID=[1, 2, 3])
  CHECK: IF ID = 1 OR ID <> 2 -> A
  ELSE -> B
  A: OBSERVE("A", 1) -> DONE
  B: OBSERVE("B", 1) -> DONE
  DONE: EXIT()
END
""")
        result = model.initialize().run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["A"].count, 2)
        self.assertEqual(observations["B"].count, 1)

    def test_if_attribute_branch(self):
        model = helix.Model.from_source("""
HELIX 1
VAR ID ENTITY
NETWORK
  CREATE(count=3, ID=[1, 2, 3])
  CHECK: IF ID = 1 -> A
  ELSE IF ID = 2 -> B
  ELSE -> C
  A: OBSERVE("ONE", 1) -> DONE
  B: OBSERVE("TWO", 1) -> DONE
  C: OBSERVE("THREE", 1) -> DONE
  DONE: EXIT()
END
""")
        result = model.initialize().run(end=1)
        observations = {item.label: item for item in result.observations}
        self.assertEqual(observations["ONE"].count, 1)
        self.assertEqual(observations["TWO"].count, 1)
        self.assertEqual(observations["THREE"].count, 1)

    def test_debug_parse_writes_tokens(self):
        directory = ROOT / "tests" / "_parse_debug"
        shutil.rmtree(directory, ignore_errors=True)
        try:
            helix.Model.from_source(
                MODEL, debug_parse=True, debug_path=str(directory))
            self.assertTrue((directory / "tokens.ndjson").exists())
            self.assertTrue((directory / "parse.ndjson").exists())
            self.assertTrue((directory / "ast.json").exists())
            tokens = (directory / "tokens.ndjson").read_text(
                encoding="utf-8")
            self.assertIn("HELIX", tokens)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_debug_writes_events(self):
        model = helix.Model.from_source(MODEL)
        directory = ROOT / "tests" / "_debug_tmp"
        shutil.rmtree(directory, ignore_errors=True)
        try:
            result = model.initialize().run(
                end=20, seed=1, debug=True, debug_path=str(directory))
            self.assertTrue((directory / "run.json").exists())
            self.assertTrue((directory / "model.json").exists())
            events = (directory / "events.ndjson").read_text(
                encoding="utf-8")
            self.assertIn("CREATE", events)
            self.assertEqual(result.debug_path, str(directory))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
