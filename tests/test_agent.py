import json
import tempfile
import unittest
from pathlib import Path
from material_agent.agent.runner import run
from material_agent.models.client import MockModel
from material_agent.tools.service import BusinessTools
ROOT = Path(__file__).resolve().parents[1]

class AgentTests(unittest.TestCase):
    def execute(self, scenario, model=None, **limits):
        request = json.loads((ROOT / "examples/inputs" / (scenario + ".json")).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            tools = BusinessTools(ROOT / "data", Path(tmp)/"db", request, test_mode=True)
            result = run(request, tools, model or MockModel(), Path(tmp)/"trace", **limits)
            events = [json.loads(line) for line in (Path(tmp)/"trace").read_text(encoding="utf-8").splitlines()]
        return result, events

    def test_scenarios(self):
        for scenario, expected in [("normal", "completed"), ("conflict", "needs_confirmation"),
                                   ("missing-info", "needs_information"), ("risk", "blocked"), ("save-failure", "failed")]:
            with self.subTest(scenario=scenario):
                result, events = self.execute(scenario)
                self.assertEqual(result["status"], expected)
                self.assertEqual(events[-1]["status"], expected)
                self.assertEqual(result["mode"], "mock")

    def test_limit(self):
        result, events = self.execute("normal", max_calls=1)
        self.assertEqual(result["status"], "limit_reached")
        self.assertEqual(result["tool_calls"], 1)

    def test_false_completion_rejected(self):
        class Liar(MockModel):
            def decide(self, messages):
                return {"finish": "completed", "reason": "saved"}
        result, _ = self.execute("normal", Liar())
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["draft"])

    def test_model_observes_tool_result(self):
        class Observer(MockModel):
            def decide(self, messages):
                if len(messages) > 2:
                    assert "result" in json.loads(messages[-1]["content"])
                return super().decide(messages)
        result, _ = self.execute("normal", Observer())
        self.assertEqual(result["status"], "completed")

    def test_malformed_tool_arguments_are_observed_without_crash(self):
        class Bad(MockModel):
            def decide(self, messages):
                if len(messages) == 2:
                    return {"tool": "check_rules", "arguments": None}
                return {"finish": "failed"}
        result, events = self.execute("normal", Bad())
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(e["event"] == "tool_result" and e["result"]["status"] == "failed" for e in events))

    def test_persistent_save_failure_never_completes(self):
        request = {"request_id": "persistent", "material_ids": ["M01"], "requested_time": "2026-11-03T18:00:00+08:00"}
        with tempfile.TemporaryDirectory() as tmp:
            tools = BusinessTools(ROOT / "data", Path(tmp)/"db", request)
            tools.save_draft = lambda **kwargs: {"status": "failed", "reason": "Persistent storage outage"}
            result = run(request, tools, MockModel(), Path(tmp)/"trace")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["draft_save_status"], "failed")
        self.assertIsNone(result["draft"])

    def test_changed_occupancy_changes_suggestion(self):
        request = {"request_id": "changed", "material_ids": ["M01"], "requested_time": "2026-11-03T18:00:00+08:00"}
        with tempfile.TemporaryDirectory() as tmp:
            tools = BusinessTools(ROOT / "data", Path(tmp)/"db", request)
            tools.data["schedule"] = [{"time": request["requested_time"]}]
            result = run(request, tools, MockModel(), Path(tmp)/"trace")
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["materials"][0]["suggested_time"], "2026-11-03T11:00:00+00:00")
