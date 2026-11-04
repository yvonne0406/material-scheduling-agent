from enum import Enum


class TaskStatus(str, Enum):
    COMPLETED = "completed"
    NEEDS_INFORMATION = "needs_information"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED = "blocked"
    FAILED = "failed"
    LIMIT_REACHED = "limit_reached"
    NOT_IMPLEMENTED = "not_implemented"


def validate_request(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    if not isinstance(value.get("request_id"), str) or not value["request_id"].strip():
        raise ValueError("request_id must be a non-empty string")
    ids = value.get("material_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x.strip() for x in ids):
        raise ValueError("material_ids must be a non-empty list of strings")
    return value
