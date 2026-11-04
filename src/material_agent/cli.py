import argparse
import json
import sys
from pathlib import Path

from .contracts import TaskStatus, validate_request


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draft scheduling agent scaffold")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=["scaffold", "mock", "real"], default="scaffold")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--database", type=Path, default=Path("runtime/drafts.db"))
    parser.add_argument("--trace", type=Path, default=Path("runtime/trace.jsonl"))
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.interactive:
            if args.mode == "scaffold":
                args.mode = "mock"
            from .interactive import interactive
            return interactive(args)
        if args.input is None:
            parser.error("--input is required unless --interactive is used")
        request = validate_request(json.loads(args.input.read_text(encoding="utf-8")))
        result = {
            "request_id": request["request_id"],
            "mode": args.mode,
            "status": TaskStatus.NOT_IMPLEMENTED.value,
            "reason": "Scaffold only: model loop and business tools are not implemented.",
            "materials": [],
            "draft_save_status": "not_attempted",
            "tool_calls": 0,
        }
        if args.mode != "scaffold":
            from .agent.runner import run
            from .models.client import HttpModel, MockModel
            from .tools.service import BusinessTools
            model = HttpModel() if args.mode == "real" else MockModel()
            tools = BusinessTools(args.data_dir, args.database, request, test_mode=args.test_mode)
            result = run(request, tools, model, args.trace, args.max_steps, args.max_calls)
        output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        sys.stdout.write(output)
        return 0 if result["status"] == "completed" else 2
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
