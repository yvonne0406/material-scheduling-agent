import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from material_agent.cli import main
from material_agent.contracts import validate_request


class ScaffoldTests(unittest.TestCase):
    def test_unimplemented_run_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            output = Path(directory) / "output.json"
            path.write_text(json.dumps({"request_id": "r1", "material_ids": ["M01"]}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--input", str(path), "--output", str(output)])
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "not_implemented")
            self.assertEqual(result["draft_save_status"], "not_attempted")
            self.assertEqual(result["tool_calls"], 0)

    def test_invalid_request_is_rejected(self):
        for value in [[], {}, {"request_id": "r", "material_ids": []}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_request(value)

    def test_missing_input_has_failure_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stderr(io.StringIO()) as error:
                code = main(["--input", str(Path(directory) / "missing.json")])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(error.getvalue())["status"], "failed")
