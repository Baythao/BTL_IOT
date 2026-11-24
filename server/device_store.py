"""Validated, timestamped telemetry and observed output-command changes."""
import json
import time

STATE_KEYS = ("fire", "gas", "gas_ready", "fan", "pump", "buzzer")
CONFIG_KEYS = ("gas_on", "gas_off", "gas_warmup_ms", "fire_run_ms", "fire_active_level")


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS device_state (
        device TEXT PRIMARY KEY, payload TEXT NOT NULL, seen REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS device_status (
        device TEXT PRIMARY KEY, status TEXT NOT NULL, seen REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT, received REAL,
        component TEXT, old_value TEXT, new_value TEXT)""")


def validate_state(raw):
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("state must be object")
    for key in STATE_KEYS:
        if type(d.get(key)) is not bool:
            raise ValueError("invalid boolean")
    for key, low, high in [("gas_adc", 0, 4095), ("servo", 0, 180), ("uptime_ms", 0, 4294967295)]:
        if type(d.get(key)) is not int or not low <= d[key] <= high:
            raise ValueError("invalid number")
    clean = {k: d[k] for k in (*STATE_KEYS, "gas_adc", "servo", "uptime_ms")}
    cfg = d.get("config")
    if cfg is not None:
        if not isinstance(cfg, dict) or any(type(cfg.get(k)) is not int for k in CONFIG_KEYS):
            raise ValueError("invalid config")
        if not (0 <= cfg["gas_off"] < cfg["gas_on"] <= 4095
                and 0 <= cfg["gas_warmup_ms"] <= 86400000
                and 0 < cfg["fire_run_ms"] <= 3600000
                and cfg["fire_active_level"] in (0, 1)):
            raise ValueError("invalid config range")
        clean["config"] = {k: cfg[k] for k in CONFIG_KEYS}
    return clean


def save_state(db, device, raw, now=None):
    d = validate_state(raw)
    now = time.time() if now is None else now
    previous = db.execute("SELECT payload,seen FROM device_state WHERE device=?", (device,)).fetchone()
    # After a telemetry gap, record a new baseline, not an invented transition.
    old = json.loads(previous[0]) if previous and now - previous[1] <= 15 else {}
    for key in ("fire", "gas", "fan", "pump", "buzzer", "servo"):
        if key not in old or d[key] != old[key]:
            db.execute("INSERT INTO activity(device,received,component,old_value,new_value) VALUES (?,?,?,?,?)",
                       (device, now, key, json.dumps(old[key]) if key in old else None, json.dumps(d[key])))
    db.execute("""INSERT INTO device_state VALUES (?,?,?) ON CONFLICT(device)
        DO UPDATE SET payload=excluded.payload,seen=excluded.seen""", (device, json.dumps(d), now))


def save_status(db, device, status):
    if status not in ("online", "offline"):
        raise ValueError("invalid status")
    db.execute("""INSERT INTO device_status VALUES (?,?,?) ON CONFLICT(device)
        DO UPDATE SET status=excluded.status,seen=excluded.seen""", (device, status, time.time()))


def read_state(db, device):
    row = db.execute("SELECT payload,seen FROM device_state WHERE device=?", (device,)).fetchone()
    status = db.execute("SELECT status,seen FROM device_status WHERE device=?", (device,)).fetchone()
    age = max(0, time.time() - row[1]) if row else None
    offline = bool(status and status[0] == "offline" and (not row or status[1] >= row[1]))
    return dict(device=device, data=json.loads(row[0]) if row else None,
                last_seen=row[1] if row else None, age_seconds=round(age, 1) if age is not None else None,
                fresh=bool(row and age <= 15 and not offline),
                connection="offline" if offline else ("online" if row and age <= 15 else "stale"))
