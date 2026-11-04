import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from material_agent.tools.service import BusinessTools
from material_agent.cli import main
ROOT = Path(__file__).resolve().parents[1]

class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/"data", self.root/"data")
        self.request = {"request_id": "confirm", "material_ids": ["M01"], "requested_time": "2026-11-03T18:00:00+08:00"}
        self.tool = BusinessTools(self.root/"data", self.root/"db", self.request)
        self.times = {"M01": "2026-11-03T19:00:00+08:00"}
        self.first = self.tool.save_draft(self.times)

    def test_confirmation_updates_same_draft_idempotently(self):
        a = self.tool.confirm_draft(self.times)
        b = self.tool.confirm_draft(self.times)
        self.assertEqual(a["draft_id"], self.first["draft_id"])
        self.assertEqual(a["items"][0]["status"], "confirmed")
        self.assertTrue(b["reused"])
        self.assertFalse(a["published"])
        with contextlib.closing(self.tool.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM drafts").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM reservations").fetchone()[0], 1)

    def test_confirmation_rechecks_changed_schedule(self):
        (self.root/"data/schedule.json").write_text(json.dumps([{"time": self.times["M01"]}]), encoding="utf-8")
        self.assertEqual(self.tool.confirm_draft(self.times)["status"], "conflict")

    def test_confirmation_rejects_changed_proposal(self):
        self.assertEqual(self.tool.confirm_draft({"M01": "2026-11-03T21:00:00+08:00"})["status"], "failed")

    def test_confirmation_failure_keeps_pending(self):
        self.tool.fail_always = True
        self.assertEqual(self.tool.confirm_draft(self.times)["status"], "failed")
        with contextlib.closing(self.tool.connect()) as db:
            payload=json.loads(db.execute("SELECT payload FROM drafts").fetchone()[0])
            self.assertEqual(payload["items"][0]["status"], "needs_confirmation")
            self.assertEqual(db.execute("SELECT count(*) FROM reservations").fetchone()[0], 0)

    def test_interactive_accept_and_decline(self):
        for response in ("CONFIRM", "no"):
            output = self.root/(response+".json")
            with patch("builtins.input", return_value=response), contextlib.redirect_stdout(io.StringIO()):
                code = main(["--interactive", "--mode", "mock", "--input", str(ROOT/"examples/inputs/conflict.json"),
                    "--data-dir", str(self.root/"data"), "--database", str(self.root/(response+".db")),
                    "--trace", str(self.root/(response+".jsonl")), "--output", str(output)])
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(code, 0 if response == "CONFIRM" else 2)
            self.assertEqual(result["materials"][0]["status"], "confirmed" if response == "CONFIRM" else "needs_confirmation")
