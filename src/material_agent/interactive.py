"""Human confirmation lives outside the model's action whitelist."""
import json
from datetime import datetime, timezone
from pathlib import Path
from .contracts import validate_request
from .tools.service import BusinessTools
from .models.client import HttpModel, MockModel
from .agent.runner import run


def interactive(args):
    print("素材审核与排期 | 仅保存草稿 | 模式: " + args.mode)
    if args.input:
        request = validate_request(json.loads(args.input.read_text(encoding="utf-8")))
    else:
        request = validate_request({"request_id": input("请求ID（重复提交使用相同ID）: ").strip(),
            "material_ids": [x.strip() for x in input("素材ID，逗号分隔，例如 M01: ").split(",")],
            "requested_time": input("要求时间，例如 2026-11-06T18:00:00+08:00: ").strip(),
            "time_requirement": "hard"})
    model = HttpModel() if args.mode == "real" else MockModel()
    tools = BusinessTools(args.data_dir, args.database, request, test_mode=args.test_mode)
    result = run(request, tools, model, args.trace, args.max_steps, args.max_calls)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("draft") and any(x["status"] == "needs_confirmation" for x in result["draft"]["items"]):
        print("以上建议尚未获得同意。确认后仍仅为排期草稿，不发布。")
        if input("接受列出的所有建议时段？输入 CONFIRM 确认；其他输入保留待确认: ").strip() == "CONFIRM":
            expected = {x["material_id"]: x["suggested_time"] for x in result["draft"]["items"]}
            confirmation = tools.confirm_draft(expected)
            with Path(args.trace).open("a", encoding="utf-8") as trace:
                trace.write(json.dumps({"event": "user_confirmation", "run_id": result["run_id"],
                    "mode": args.mode, "time": datetime.now(timezone.utc).isoformat(),
                    "arguments": expected, "result": confirmation}, ensure_ascii=False) + "\n")
            result["confirmation_result"] = confirmation
            if confirmation["status"] == "saved":
                result.update(status="completed", draft=confirmation, materials=confirmation["items"], draft_save_status="saved")
            else:
                result.update(status=confirmation["status"], reason="Confirmation was not saved; original pending draft retained")
            print(json.dumps(confirmation, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["status"] == "completed" else 2
