import json
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from material_agent.tools.service import BusinessTools
from material_agent.agent.runner import run
from material_agent.models.client import MockModel
ROOT = Path(__file__).resolve().parents[1]

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.request = {"request_id": "audit", "material_ids": ["M01"], "requested_time": "2026-11-03T18:00:00+08:00"}
        self.tools = BusinessTools(ROOT/"data", Path(self.tmp.name)/"db", self.request)

    def count(self):
        with closing(self.tools.connect()) as db:
            return db.execute("SELECT count(*) FROM drafts").fetchone()[0]

    def test_changed_occupancy_after_save_does_not_reuse_as_valid(self):
        first = self.tools.save_draft({"M01": self.request["requested_time"]})
        self.tools.data["schedule"] = [{"time": self.request["requested_time"]}]
        second = self.tools.save_draft({"M01": "2026-11-03T19:00:00+08:00"})
        self.assertEqual(second["status"], "conflict")
        self.assertEqual(second["existing_draft_id"], first["draft_id"])
        self.assertEqual(self.count(), 1)

    def test_new_risk_invalidates_reuse(self):
        self.tools.save_draft({"M01": self.request["requested_time"]})
        self.tools.data["materials"][0]["rights_confirmed"] = False
        self.assertEqual(self.tools.save_draft({"M01": self.request["requested_time"]})["status"], "blocked")
        self.assertEqual(self.count(), 1)

    def test_alternative_unconfirmed_and_matching_consent(self):
        alt = "2026-11-03T19:00:00+08:00"
        result = self.tools.save_draft({"M01": alt})
        self.assertEqual(result["items"][0]["status"], "needs_confirmation")
        self.assertFalse(result["published"])
        with closing(self.tools.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM reservations").fetchone()[0], 0)
        request = {**self.request, "request_id": "explicit-consent", "confirmed_times": {"M01": alt}}
        tools = BusinessTools(ROOT/"data", Path(self.tmp.name)/"db", request)
        self.assertEqual(tools.save_draft({"M01": alt})["items"][0]["status"], "confirmed")

    def test_model_cannot_publish_or_invent_consent(self):
        class Hostile(MockModel):
            def decide(self, messages):
                if len(messages) == 2:
                    return {"tool": "publish", "arguments": {}}
                if len(messages) == 4:
                    return {"tool": "save_draft", "arguments": {"suggestions": {"M01": "2026-11-03T19:00:00+08:00"}, "confirmed": True}}
                return {"finish": "completed"}
        result = run(self.request, self.tools, Hostile(), Path(self.tmp.name)/"trace")
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["published"])
        self.assertEqual(self.count(), 0)
