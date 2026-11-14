"""MQTT -> SQLite outbox -> Pushover + Twilio SMS. One instance only.
Run from this folder. DRY_RUN=1 is the default. No inbound device commands.
"""
import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv
import device_store

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DB = ROOT / "alerts.sqlite3"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
DEVICE = os.getenv("DEVICE_ID", "esp32-tang1")
BASE = f"fire-demo/{DEVICE}"
DRY = os.getenv("DRY_RUN", "1") != "0"
CHANNELS = [c for c, var in [("push", "PUSH_ENABLED"), ("sms", "SMS_ENABLED")]
            if os.getenv(var, "1") == "1"]


def connect_db():
    db = sqlite3.connect(DB, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize():
    with connect_db() as db:
        device_store.initialize(db)
        db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, body TEXT, received REAL)")
        db.execute("""CREATE TABLE IF NOT EXISTS outbox (
            id TEXT, channel TEXT, body TEXT, attempts INTEGER DEFAULT 0,
            next_try REAL DEFAULT 0, status TEXT DEFAULT 'pending',
            provider_id TEXT DEFAULT '', PRIMARY KEY(id, channel))""")
        # A crash during HTTP can mean the provider already accepted it.
        # Do not auto resend such ambiguous sends, to avoid duplicate SMS/charges.
        db.execute("UPDATE outbox SET status='uncertain' WHERE status='sending'")


def validate_event(payload):
    d = json.loads(payload)
    if not isinstance(d, dict) or d.get("device") != DEVICE:
        raise ValueError("wrong device")
    if d.get("kind") not in ("FIRE", "GAS"):
        raise ValueError("wrong kind")
    if not isinstance(d.get("id"), str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,72}", d["id"]):
        raise ValueError("wrong id")
    for key, upper in [("gas_adc", 4095), ("uptime_ms", 4294967295), ("age_ms", 4294967295)]:
        if type(d.get(key)) is not int or not 0 <= d[key] <= upper:
            raise ValueError("wrong numeric field")
    return d


def store_event(d):
    kind = "PHAT HIEN LUA" if d["kind"] == "FIRE" else "GAS VUOT NGUONG THU"
    site = os.getenv("SITE_NAME", "Mo hinh")[:60]
    body = f"FireDemo - {site}: {kind}. ADC={d['gas_adc']}."
    if d["age_ms"] >= 15000:
        body += f" CANH BAO GUI TRE {d['age_ms']//1000}s; kiem tra trang thai hien tai."
    body += " Hay kiem tra ngay."
    with connect_db() as db:
        cur = db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?)",
                         (d["id"], json.dumps(d), time.time()))
        if cur.rowcount:
            for channel in CHANNELS:
                db.execute("INSERT INTO outbox(id,channel,body) VALUES (?,?,?)",
                           (d["id"], channel, body))
            logging.warning("NEW %s %s", d["id"], body)
        return cur.rowcount == 1


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logging.error("MQTT connection rejected: %s", reason_code)
    else:
        client.subscribe([(BASE + "/event", 1), (BASE + "/status", 1), (BASE + "/state", 0)])
        logging.info("MQTT connected; DRY_RUN=%s", DRY)


def on_message(client, userdata, message):
    if len(message.payload) > 2048:
        return
    if message.topic in (BASE + "/state", BASE + "/status"):
        try:
            with connect_db() as db:
                if message.topic.endswith("/state"):
                    if message.retain:
                        return  # Old retained data must not appear fresh.
                    device_store.save_state(db, DEVICE, message.payload)
                else:
                    device_store.save_status(db, DEVICE, message.payload.decode())
        except (ValueError, TypeError, UnicodeError, sqlite3.Error) as exc:
            logging.error("Telemetry rejected (%s)", type(exc).__name__)
        return
    if message.topic != BASE + "/event":
        return
    # No notifications from retained event messages.
    if message.retain or len(message.payload) > 1024:
        return
    try:
        d = validate_event(message.payload)
        store_event(d)
        # ACK after durable SQLite transaction, including duplicate events.
        client.publish(BASE + "/ack", d["id"], qos=1, retain=False)
    except (ValueError, TypeError, UnicodeError, sqlite3.Error) as exc:
        logging.error("Event not accepted (%s)", type(exc).__name__)


def send_http(channel, body):
    if channel == "push":
        return requests.post("https://api.pushover.net/1/messages.json", data={
            "token": os.environ["PUSHOVER_TOKEN"], "user": os.environ["PUSHOVER_USER"],
            "title": "FireDemo - Canh bao", "message": body, "priority": 1,
        }, timeout=(5, 15))
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    return requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                         auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
                         data={"From": os.environ["TWILIO_FROM"],
                               "To": os.environ["SMS_TO"], "Body": body}, timeout=(5, 15))


def work_once():
    with connect_db() as db:
        row = db.execute("""SELECT id,channel,body,attempts FROM outbox
            WHERE status='pending' AND next_try<=? ORDER BY next_try LIMIT 1""",
                         (time.time(),)).fetchone()
        if not row:
            return False
        event_id, channel, body, attempts = row
        db.execute("UPDATE outbox SET status='sending',attempts=attempts+1 WHERE id=? AND channel=?",
                   (event_id, channel))
    result, provider_id, next_try = "failed", "", 0
    if DRY:
        logging.info("DRY RUN %s: %s", channel, body)
        result = "dry_run"
    else:
        try:
            response = send_http(channel, body)
            if response.status_code == 429 and attempts < 2:
                result, next_try = "pending", time.time() + 60
            elif 200 <= response.status_code < 300:
                data = response.json()
                ok = data.get("status") == 1 if channel == "push" else bool(data.get("sid"))
                result = "accepted" if ok else "failed"
                provider_id = str(data.get("sid") or data.get("request") or "")
            elif response.status_code >= 500:
                # Ambiguous whether an upstream service accepted the request.
                result = "uncertain"
            else:
                logging.error("%s HTTP %s; check credentials/sender/recipient in provider console",
                              channel, response.status_code)
        except (requests.RequestException, ValueError):
            result = "uncertain"  # No blind retries that can duplicate paid SMS.
    with connect_db() as db:
        db.execute("UPDATE outbox SET status=?,provider_id=?,next_try=? WHERE id=? AND channel=?",
                   (result, provider_id, next_try, event_id, channel))
    logging.info("%s %s => %s %s", event_id, channel, result, provider_id)
    return True


def worker():
    while True:
        try:
            if not work_once():
                time.sleep(0.5)
        except Exception:
            logging.exception("Outbox worker error")
            time.sleep(2)


def require_config():
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", DEVICE):
        raise ValueError("DEVICE_ID invalid")
    required = ["MQTT_HOST", "MQTT_USER", "MQTT_PASS"]
    if not DRY and "push" in CHANNELS:
        required += ["PUSHOVER_TOKEN", "PUSHOVER_USER"]
    if not DRY and "sms" in CHANNELS:
        required += ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "SMS_TO"]
    for key in required:
        value = os.getenv(key, "")
        if not value or "DIEN_" in value or "YOUR_" in value:
            raise ValueError(f"Fill {key} in .env")
    # Dashboard-only operation is valid when both channels are disabled.


def main():
    require_config()
    initialize()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"notify-{DEVICE}")
    client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
    if os.getenv("MQTT_TLS", "0") == "1":
        client.tls_set(ca_certs=os.getenv("MQTT_CA_FILE") or None)
    client.on_connect, client.on_message = on_connect, on_message
    client.reconnect_delay_set(1, 30)
    threading.Thread(target=worker, daemon=True).start()
    client.connect_async(os.environ["MQTT_HOST"], int(os.getenv("MQTT_PORT", "1883")), 30)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
