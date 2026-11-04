"""Reproduce complete evidence. real incurs API calls; mock is offline."""
import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from material_agent.agent.runner import run
from material_agent.models.client import HttpModel, MockModel
from material_agent.tools.service import BusinessTools

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["mock", "real"], default="mock")
args = parser.parse_args()
folder = ROOT/"examples"/("delivery-"+args.mode)
folder.mkdir(exist_ok=True)
model = HttpModel() if args.mode == "real" else MockModel()
summary=[]
with tempfile.TemporaryDirectory() as temp:
    for name in ("normal", "duplicate", "missing-info", "risk", "conflict", "save-persistent-failure", "criteria-shifted", "criteria-shifted-repeat"):
        source = "criteria-shifted" if name.endswith("-repeat") else name
        request=json.loads((ROOT/"examples/inputs"/(source+".json")).read_text(encoding="utf-8"))
        (folder/(name+".input.json")).write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding="utf-8")
        data=ROOT/("examples/criteria-data" if name.startswith("criteria") else "data")
        db=Path(temp)/(("normal" if name=="duplicate" else source)+".db")
        tools=BusinessTools(data,db,request,test_mode=True)
        result=run(request,tools,model,folder/(name+".trace.jsonl"))
        result["trace"]="examples/"+folder.name+"/"+name+".trace.jsonl"
        with closing(sqlite3.connect(db)) as con:
            stored=[json.loads(x[0]) for x in con.execute("SELECT payload FROM drafts")]
            reservations=con.execute("SELECT count(*) FROM reservations").fetchone()[0]
        result["verification"]={"stored_drafts":stored,"draft_count":len(stored),"reservation_count":reservations}
        (folder/(name+".output.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        summary.append({"case":name,"status":result["status"],"save_status":result["draft_save_status"],"tool_calls":result["tool_calls"],"draft_count":len(stored)})
        print(summary[-1],flush=True)
    # Explicit user-confirmation simulation, separate from model decisions.
    if result.get("draft"):
        expected={x["material_id"]:x["suggested_time"] for x in result["draft"]["items"]}
        confirmation=tools.confirm_draft(expected)
        with closing(sqlite3.connect(db)) as con:
            confirmation["database_draft_count"]=con.execute("SELECT count(*) FROM drafts").fetchone()[0]
            confirmation["database_reservation_count"]=con.execute("SELECT count(*) FROM reservations").fetchone()[0]
        (folder/"explicit-confirmation.json").write_text(json.dumps({"source":"test_harness_simulated_user_consent_not_model", "input":expected,"result":confirmation},ensure_ascii=False,indent=2),encoding="utf-8")
(folder/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
