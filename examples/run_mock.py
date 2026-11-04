"""Run from repository root: python examples/run_mock.py. Mock evidence only."""
import json
import tempfile
from pathlib import Path
from material_agent.agent.runner import run
from material_agent.models.client import MockModel
from material_agent.tools.service import BusinessTools

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    for scenario in ("normal", "duplicate", "missing-info", "risk", "conflict", "save-failure"):
        request = json.loads((root / "examples/inputs" / (scenario + ".json")).read_text(encoding="utf-8"))
        database = Path(tmp) / (("normal" if scenario == "duplicate" else scenario) + ".db")
        tool = BusinessTools(root / "data", database, request, test_mode=True)
        result = run(request, tool, MockModel(), root / "examples/traces" / ("mock-" + scenario + ".jsonl"))
        (root / "examples/outputs" / ("mock-" + scenario + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(scenario, result["status"], result["draft_save_status"])
