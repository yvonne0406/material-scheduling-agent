from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from material_agent.tools.service import BusinessTools

ROOT = Path(__file__).resolve().parents[1]


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "drafts.db"

    def tools(self, name="normal", **kwargs):
        request = json.loads((ROOT / "examples/inputs" / (name + ".json")).read_text(encoding="utf-8"))
        return BusinessTools(ROOT / "data", self.database, request, **kwargs)

    def test_normal_and_duplicate(self):
        tool = self.tools()
        first = tool.save_draft({"M01": tool.request["requested_time"]})
        second = tool.save_draft({"M01": tool.request["requested_time"]})
        self.assertEqual(first["status"], "saved")
        self.assertFalse(first["published"])
        self.assertEqual(first["draft_id"], second["draft_id"])
        self.assertTrue(second["reused"])
        self.assertTrue(tool.query_slots(tool.request["requested_time"], 1)["slots"][0]["available"])
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM drafts").fetchone()[0], 1)

    def test_missing_and_risk(self):
        for scenario, mid, status in [("missing-info", "M02", "needs_information"), ("risk", "M03", "blocked")]:
            tool = self.tools(scenario)
            self.assertEqual(tool.save_draft({mid: tool.request["requested_time"]})["status"], status)

    def test_conflict_and_alternative_confirmation_boundary(self):
        tool = self.tools("conflict")
        self.assertEqual(tool.save_draft({"M01": tool.request["requested_time"]})["status"], "conflict")
        slots = tool.query_slots(tool.request["requested_time"])["slots"]
        self.assertFalse(slots[0]["available"])
        result = tool.save_draft({"M01": slots[1]["time"]})
        self.assertEqual(result["items"][0]["status"], "needs_confirmation")
        self.assertTrue(tool.query_slots(slots[1]["time"], 1)["slots"][0]["available"])

    def test_failure_rolls_back_and_retry_succeeds(self):
        tool = self.tools("save-failure", test_mode=True)
        suggestion = {"M01": tool.request["requested_time"]}
        self.assertEqual(tool.save_draft(suggestion)["status"], "failed")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM drafts").fetchone()[0], 0)
        self.assertEqual(tool.save_draft(suggestion)["status"], "saved")

    def test_changed_request_id_content_rejected(self):
        tool = self.tools()
        tool.save_draft({"M01": tool.request["requested_time"]})
        tool.request["requested_time"] = "2026-11-03T19:00:00+08:00"
        self.assertEqual(tool.save_draft({"M01": tool.request["requested_time"]})["reason"], "idempotency_key_conflict")

    def test_reservation_rechecked_on_save(self):
        a, b = self.tools(), self.tools()
        b.request["request_id"] = "another-request"
        slot = a.request["requested_time"]
        self.assertTrue(b.query_slots(slot, 1)["slots"][0]["available"])
        a.save_draft({"M01": slot})
        self.assertEqual(b.save_draft({"M01": slot})["status"], "conflict")

    def test_timezone_equivalence(self):
        tool = self.tools("conflict")
        self.assertFalse(tool.query_slots("2026-11-03T12:00:00+00:00", 1)["slots"][0]["available"])
