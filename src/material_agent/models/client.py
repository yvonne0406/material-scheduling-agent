"""HTTP adapter for an explicitly configured chat-completions-compatible endpoint."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class HttpModel:
    mode = "real"

    def __init__(self):
        config = Path('.env')
        if config.is_file():
            for line in config.read_text(encoding='utf-8-sig').splitlines():
                key, separator, value = line.partition('=')
                if separator and key.strip() in ('MODEL_ENDPOINT', 'MODEL_NAME', 'MODEL_API_KEY'):
                    os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))
        self.url = os.environ.get("MODEL_ENDPOINT")
        self.name = os.environ.get("MODEL_NAME")
        self.key = os.environ.get("MODEL_API_KEY")
        if not all((self.url, self.name, self.key)):
            raise ValueError("Set MODEL_ENDPOINT, MODEL_NAME and MODEL_API_KEY")
        if not self.url.startswith("https://"):
            raise ValueError("MODEL_ENDPOINT must use HTTPS")

    def decide(self, messages):
        body = json.dumps({"model": self.name, "messages": messages, "temperature": 0}).encode()
        request = Request(self.url, body, {"Content-Type": "application/json", "Authorization": "Bearer " + self.key})
        try:
            with urlopen(request, timeout=45) as response:
                result = json.load(response)
            return json.loads(result["choices"][0]["message"]["content"])
        except HTTPError as exc:
            raise ValueError("Model HTTP error: " + str(exc.code)) from None
        except (URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError):
            raise ValueError("Model connection or response format error") from None


class MockModel:
    mode = "mock"
    name = "deterministic-flow-fixture-v1"

    def decide(self, messages):
        request = json.loads(messages[1]["content"])
        observations = [json.loads(m["content"]) for m in messages[2:] if m["role"] == "user"]
        def action(tool, arguments, reason):
            return {"tool": tool, "arguments": arguments, "reason": reason}
        def finish(status, reason):
            return {"finish": status, "reason": reason}
        if not request.get("requested_time"):
            return finish("needs_information", "Missing requested_time")
        if observations:
            last = observations[-1]
            status = last["result"]["status"]
            if status in ("needs_information", "blocked", "failed"):
                return finish(status, "Stop based on tool result: " + status)
            if status == "saved":
                return finish("completed", "Draft tool confirmed save")
        for mid in request["material_ids"]:
            for tool in ("read_material", "check_rules"):
                if not any(x["tool"] == tool and x["arguments"].get("material_id") == mid for x in observations):
                    return action(tool, {"material_id": mid}, "Read and validate material")
        queries = [x for x in observations if x["tool"] == "query_slots"]
        if not queries:
            return action("query_slots", {"start": request["requested_time"], "count": 3}, "Check requested and alternative slots")
        slots = [x["time"] for x in queries[-1]["result"].get("slots", []) if x["available"]]
        if len(slots) < len(request["material_ids"]):
            return finish("incomplete", "Insufficient available slots")
        if any(x["result"]["status"] == "conflict" for x in observations):
            return finish("incomplete", "Schedule changed; request another run")
        return action("save_draft", {"suggestions": dict(zip(request["material_ids"], slots))}, "Save available suggestion; tool enforces confirmation")
