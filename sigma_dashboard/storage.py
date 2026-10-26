from __future__ import annotations
import json
import sqlite3
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "dashboard.sqlite3"
request_db: ContextVar[Path | None] = ContextVar("sigma_request_db", default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    db = request_db.get() or DB
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def init():
    with connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, name TEXT, kind TEXT, revision INTEGER, created TEXT, updated TEXT, payload TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, scenario_id TEXT, revision INTEGER, created TEXT, payload TEXT)")


def list_scenarios():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT id,name,kind,revision,created,updated FROM scenarios ORDER BY updated DESC")]


def save_scenario(payload, sid=None):
    timestamp = now()
    sid = sid or str(uuid4())
    with connect() as con:
        old = con.execute("SELECT revision,created FROM scenarios WHERE id=?", (sid,)).fetchone()
        revision = old["revision"]+1 if old else 1
        con.execute("INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?,?,?,?)", (sid,payload["name"],payload["kind"],revision,old["created"] if old else timestamp,timestamp,json.dumps(payload,ensure_ascii=False,allow_nan=False)))
    return get_scenario(sid)


def get_scenario(sid):
    with connect() as con:
        row = con.execute("SELECT * FROM scenarios WHERE id=?", (sid,)).fetchone()
    if not row:
        return None
    out = json.loads(row["payload"])
    out.update({k:row[k] for k in ["id","revision","created","updated"]})
    return out


def save_run(scenario, result):
    rid = str(uuid4())
    payload = {"id":rid,"scenario":scenario,"result":result}
    with connect() as con:
        con.execute("INSERT INTO runs VALUES (?,?,?,?,?)",(rid,scenario["id"],scenario["revision"],now(),json.dumps(payload,ensure_ascii=False,allow_nan=False)))
    return payload


def get_run(rid):
    with connect() as con:
        row = con.execute("SELECT payload FROM runs WHERE id=?",(rid,)).fetchone()
    return json.loads(row["payload"]) if row else None


def list_runs():
    with connect() as con:
        rows = con.execute("SELECT id,scenario_id,revision,created,json_extract(payload,'$.scenario.name') AS name,json_extract(payload,'$.scenario.kind') AS kind,json_extract(payload,'$.result.complete') AS complete,json_extract(payload,'$.result.summary.battery_net_kwh') AS energy_kwh FROM runs ORDER BY created DESC LIMIT 80").fetchall()
    return [dict(r) for r in rows]
