"""Deterministic tools. User request is trusted input, never a model tool argument."""
from contextlib import closing
import copy
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed.astimezone(timezone.utc).isoformat()


class BusinessTools:
    def __init__(self, data_dir, database, request, *, test_mode=False):
        self.request = copy.deepcopy(request)
        self.data = {name: json.loads((Path(data_dir) / (name + ".json")).read_text(encoding="utf-8"))
                     for name in ("materials", "rules", "schedule")}
        self.data_dir = Path(data_dir)
        self.database = str(database)
        self.fail_always = test_mode and request.get("test_faults", {}).get("save_draft") == "fail_always"
        self.fail_once = test_mode and request.get("test_faults", {}).get("save_draft") == "fail_once"
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS drafts (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    draft_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reservations (
                    slot TEXT PRIMARY KEY, request_id TEXT NOT NULL);
            """)

    def connect(self):
        return sqlite3.connect(self.database, timeout=5)

    def read_material(self, material_id):
        material = next((x for x in self.data["materials"] if x["id"] == material_id), None)
        return {"status": "found", "material": copy.deepcopy(material)} if material else {
            "status": "needs_information", "missing": ["material:" + material_id]}

    def check_rules(self, material_id):
        result = self.read_material(material_id)
        if result["status"] != "found":
            return result
        material = result["material"]
        missing, risks = [], []
        for rule in self.data["rules"]:
            if "field" in rule:
                value = material.get(rule["field"])
                if value is None:
                    missing.append(rule["field"])
                elif value != rule["required_value"]:
                    risks.append({"rule_id": rule["id"], "reason": rule["reason"]})
            if "forbidden_claim" in rule and any(rule["forbidden_claim"] in claim for claim in material.get("claims", [])):
                risks.append({"rule_id": rule["id"], "reason": rule["reason"]})
        return {"status": "blocked" if risks else "needs_information" if missing else "approved",
                "missing": missing, "risks": risks}

    def occupied(self, db):
        return {timestamp(x["time"]) for x in self.data["schedule"]} | {
            row[0] for row in db.execute("SELECT slot FROM reservations")}

    def query_slots(self, start, count=3):
        if type(count) is not int or not 1 <= count <= 24:
            raise ValueError("count must be between 1 and 24")
        start = datetime.fromisoformat(timestamp(start))
        with closing(self.connect()) as db:
            occupied = {timestamp(x["time"]) for x in self.data["schedule"]} | {
                row[0] for row in db.execute(
                    "SELECT slot FROM reservations WHERE request_id != ?", (self.request["request_id"],))}
        return {"status": "ok", "slots": [
            {"time": (start + timedelta(hours=i)).isoformat(),
             "available": (start + timedelta(hours=i)).isoformat() not in occupied}
            for i in range(count)]}

    def save_draft(self, suggestions):
        """suggestions: material_id -> proposed time; confirmation only from request."""
        request = self.request
        business = {k: v for k, v in request.items() if k not in ("scenario", "test_faults")}
        fingerprint = hashlib.sha256(json.dumps(business, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT fingerprint,payload FROM drafts WHERE request_id=?", (request["request_id"],)).fetchone()
            if existing:
                if existing[0] != fingerprint:
                    return {"status": "failed", "reason": "idempotency_key_conflict"}
                payload = json.loads(existing[1])
                occupied = {timestamp(x["time"]) for x in self.data["schedule"]} | {
                    row[0] for row in db.execute("SELECT slot FROM reservations WHERE request_id != ?", (request["request_id"],))}
                for item in payload["items"]:
                    review = self.check_rules(item["material_id"])
                    if review["status"] != "approved":
                        return {"status": review["status"], "review": review,
                                "existing_draft_id": payload["draft_id"], "reason": "Existing draft requires review; unchanged"}
                    if timestamp(item["suggested_time"]) in occupied:
                        return {"status": "conflict", "existing_draft_id": payload["draft_id"],
                                "reason": "Existing draft slot is now occupied; draft unchanged, request revision required"}
                db.rollback()
                return {"status": "saved", "reused": True, **payload}
            ids = request["material_ids"]
            if len(ids) != len(set(ids)) or set(suggestions) != set(ids):
                return {"status": "failed", "reason": "material_set_mismatch"}
            if not request.get("requested_time"):
                return {"status": "needs_information", "missing": ["requested_time"]}
            requested = timestamp(request["requested_time"])
            occupied = self.occupied(db)
            items, selected = [], set()
            for material_id in ids:
                review = self.check_rules(material_id)
                if review["status"] != "approved":
                    return {"status": review["status"], "material_id": material_id, "review": review}
                proposed = timestamp(suggestions[material_id])
                if proposed in occupied or proposed in selected:
                    return {"status": "conflict", "material_id": material_id, "time": proposed}
                selected.add(proposed)
                confirmation = request.get("confirmed_times", {}).get(material_id)
                confirmed = proposed == requested or (confirmation is not None and timestamp(confirmation) == proposed)
                items.append({"material_id": material_id, "review_status": "approved", "risks": [],
                              "requested_time": requested, "suggested_time": proposed,
                              "status": "confirmed" if confirmed else "needs_confirmation",
                              "pending": [] if confirmed else ["Confirm alternative time"]})
            if self.fail_once or self.fail_always:
                self.fail_once = False
                raise sqlite3.OperationalError("injected save failure")
            draft_id = "draft-" + hashlib.sha256(request["request_id"].encode()).hexdigest()[:20]
            payload = {"draft_id": draft_id, "items": items, "published": False}
            db.execute("INSERT INTO drafts VALUES (?,?,?,?)", (request["request_id"], fingerprint, draft_id, json.dumps(payload)))
            for item in items:
                if item["status"] == "confirmed":
                    db.execute("INSERT INTO reservations VALUES (?,?)", (item["suggested_time"], request["request_id"]))
            db.commit()
            return {"status": "saved", "reused": False, **payload}
        except (sqlite3.Error, ValueError, TypeError) as exc:
            db.rollback()
            return {"status": "failed", "reason": str(exc)}
        finally:
            db.close()

    def confirm_draft(self, expected_times):
        """Trusted user operation, deliberately NOT exposed to the model."""
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM drafts WHERE request_id=?", (self.request["request_id"],)).fetchone()
            if not row:
                return {"status": "failed", "reason": "draft_not_found"}
            payload = json.loads(row[0])
            actual = {x["material_id"]: x["suggested_time"] for x in payload["items"]}
            if {k: timestamp(v) for k, v in expected_times.items()} != actual:
                return {"status": "failed", "reason": "proposal_changed_or_partial_confirmation"}
            self.data = {name: json.loads((self.data_dir / (name + ".json")).read_text(encoding="utf-8"))
                         for name in ("materials", "rules", "schedule")}
            occupied = {timestamp(x["time"]) for x in self.data["schedule"]} | {
                x[0] for x in db.execute("SELECT slot FROM reservations WHERE request_id != ?", (self.request["request_id"],))}
            for item in payload["items"]:
                review = self.check_rules(item["material_id"])
                if review["status"] != "approved":
                    return {"status": review["status"], "review": review}
                if item["suggested_time"] in occupied:
                    return {"status": "conflict", "reason": "slot_changed_before_confirmation"}
            if self.fail_once or self.fail_always:
                self.fail_once = False
                raise sqlite3.OperationalError("injected confirmation failure")
            reused = all(x["status"] == "confirmed" for x in payload["items"])
            for item in payload["items"]:
                item["status"], item["pending"] = "confirmed", []
                db.execute("INSERT OR IGNORE INTO reservations VALUES (?,?)", (item["suggested_time"], self.request["request_id"]))
            payload["confirmation_source"] = "explicit_user"
            db.execute("UPDATE drafts SET payload=? WHERE request_id=?", (json.dumps(payload), self.request["request_id"]))
            db.commit()
            return {"status": "saved", "reused": reused, **payload}
        except (sqlite3.Error, ValueError, TypeError) as exc:
            db.rollback()
            return {"status": "failed", "reason": str(exc)}
        finally:
            db.close()
