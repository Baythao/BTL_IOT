"""MQTT -> persistent outbox (PostgreSQL or SQLite) -> SMTP email."""
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import smtplib
import ssl
from email.message import EmailMessage
from database import database
from dotenv import load_dotenv
import device_store

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DB = ROOT / "alerts.sqlite3"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
DEVICE = os.getenv("DEVICE_ID", "esp32-tang1")
BASE = f"fire-demo/{DEVICE}"
DRY = os.getenv("DRY_RUN", "1") != "0"
CHANNELS = ["email"] if os.getenv("EMAIL_ENABLED", "1") == "1" else []
# Wake email worker on new DB commit rather than polling every 500ms.
OUTBOX_WAKE = threading.Event()
# Prevent an ESP32 FIRE /event and a delayed /state fallback from creating two emails.
FIRE_EVENT_LOCK = threading.Lock()
FIRE_FALLBACK_DELAY = 0.5  # Give ESP32's priority /event a brief chance to arrive.
FIRE_DEDUP_WINDOW = 2.4   # A fresh flame episode requires >=3 s of safe state.



def connect_db():
    return database(DB)


def initialize():
    with connect_db() as db:
        device_store.initialize(db)
        db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, body TEXT, received REAL)")
        db.execute("""CREATE TABLE IF NOT EXISTS outbox (
            id TEXT, channel TEXT, body TEXT, attempts INTEGER DEFAULT 0,
            next_try REAL DEFAULT 0, status TEXT DEFAULT 'pending',
            provider_id TEXT DEFAULT '', PRIMARY KEY(id, channel))""")
        # A crash during SMTP can mean the server already accepted the email.
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


def _fire_equivalent(db, d, received_at):
    """Match a fallback FIRE to the same physical onset as the direct ESP32 event.

    Only match when at least one record is a state-based fallback, so normal
    ESP32 FIRE incidents are never silently merged by time alone.
    """
    if d["kind"] != "FIRE":
        return None
    # MQTT can be temporarily offline, hence a somewhat wider history scan.
    rows = db.execute("SELECT id,body,received FROM events WHERE received>=? ORDER BY received DESC LIMIT 200",
                      (received_at - 120,)).fetchall()
    event_at = received_at - d["age_ms"] / 1000.0
    for row in rows:
        try:
            prior = json.loads(row["body"])
        except (TypeError, ValueError, KeyError):
            continue
        if prior.get("kind") != "FIRE" or prior.get("device") != d["device"]:
            continue
        if prior.get("source") != "state_fallback" and d.get("source") != "state_fallback":
            continue
        prior_at = row["received"] - prior.get("age_ms", 0) / 1000.0
        if abs(prior_at - event_at) <= FIRE_DEDUP_WINDOW:
            return row["id"]
    return None


def store_event(d):
    kind = "PHAT HIEN LUA" if d["kind"] == "FIRE" else "GAS VUOT NGUONG THU"
    site = os.getenv("SITE_NAME", "Mo hinh")[:60]
    body = f"FireDemo - {site}: {kind}. ADC={d['gas_adc']}."
    if d["age_ms"] >= 15000:
        body += f" CANH BAO GUI TRE {d['age_ms']//1000}s; kiem tra trang thai hien tai."
    if d.get("source") == "state_fallback":
        body += " Nguon: trang thai cam bien (du phong khi thieu su kien MQTT)."
    body += " Hay kiem tra ngay."
    now = time.time()
    with FIRE_EVENT_LOCK:
        with connect_db() as db:
            equivalent = _fire_equivalent(db, d, now)
            if equivalent:
                logging.info("FIRE already stored from same onset: id=%s equivalent_to=%s",
                             d["id"], equivalent)
                return False
            cur = db.execute("INSERT INTO events VALUES (?,?,?) ON CONFLICT DO NOTHING",
                             (d["id"], json.dumps(d), now))
            inserted = (cur.rowcount == 1)
            if inserted:
                for channel in CHANNELS:
                    db.execute("INSERT INTO outbox(id,channel,body) VALUES (?,?,?)",
                               (d["id"], channel, body))
        # Reaching this line means both the event and its outbox rows committed.
        if inserted:
            logging.warning("DB STORED %s id=%s source=%s age_ms=%s", d["kind"], d["id"],
                            d.get("source", "esp32_event"), d["age_ms"])
        else:
            logging.info("Event duplicated (no new email): %s", d["id"])
        return inserted


def ensure_fire_from_state(snapshot, seen_at):
    """Safety fallback: a real FIRE=true state must not vanish from history.

    If ESP32's event is delivered normally, _fire_equivalent prevents duplication.
    Requires an actual rising edge in state telemetry, not just a value repeated.
    """
    if not snapshot["fire"]:
        return
    event = {
        "device": DEVICE,
        "id": "fire-state-" + str(int(seen_at * 1000)) + "-" + str(snapshot["uptime_ms"]),
        "kind": "FIRE",
        "gas_adc": snapshot["gas_adc"],
        "uptime_ms": snapshot["uptime_ms"],
        "age_ms": 0,
        "source": "state_fallback",
    }
    try:
        if store_event(event) and CHANNELS:
            logging.warning("FIRE FALLBACK stored from /state; ESP32 /event was not seen in time")
            OUTBOX_WAKE.set()
    except Exception:
        logging.exception("Failed to store FIRE fallback from sensor state")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logging.error("MQTT connection rejected: %s", reason_code)
    else:
        result, mid = client.subscribe([(BASE + "/event", 1), (BASE + "/status", 1), (BASE + "/state", 0)])
        logging.info("MQTT connected; DRY_RUN=%s; subscribed=%s; result=%s", DRY, BASE, result)


def on_message(client, userdata, message):
    if len(message.payload) > 2048:
        return
    if message.topic in (BASE + "/state", BASE + "/status"):
        if message.retain:
            return  # Never treat historical retained telemetry as a new alarm.
        try:
            if message.topic.endswith("/state"):
                snapshot = device_store.validate_state(message.payload)
                current_time = time.time()
                with connect_db() as db:
                    row = db.execute("SELECT payload,seen FROM device_state WHERE device=?",
                                     (DEVICE,)).fetchone()
                    # Keep the last known FIRE value even after reconnects. Treating
                    # a stale FIRE=true as an unknown baseline would create a new
                    # fallback alarm/email every time the server restarts.
                    previous = json.loads(row["payload"]) if row else None
                    fire_rising = bool(snapshot["fire"] and (previous is None or previous.get("fire") is not True))
                    device_store.save_state(db, DEVICE, message.payload, now=current_time)
                if fire_rising:
                    logging.warning("STATE FIRE ON: device=%s uptime_ms=%s; checking /event",
                                    DEVICE, snapshot["uptime_ms"])
                    # Timer is daemonized and cannot delay handling of MQTT packets.
                    timer = threading.Timer(FIRE_FALLBACK_DELAY, ensure_fire_from_state,
                                            args=(snapshot, current_time))
                    timer.daemon = True
                    timer.start()
            else:
                with connect_db() as db:
                    device_store.save_status(db, DEVICE, message.payload.decode())
        except Exception:
            logging.exception("Telemetry not stored: topic=%s", message.topic)
        return
    if message.topic != BASE + "/event":
        return
    # No notifications from retained event messages.
    if message.retain or len(message.payload) > 1024:
        return
    try:
        d = validate_event(message.payload)
        inserted = store_event(d)
        # ACK only after durable database transaction, including duplicate events.
        if inserted and CHANNELS:
            OUTBOX_WAKE.set()
        client.publish(BASE + "/ack", d["id"], qos=1, retain=False)
        logging.info("ACK %s id=%s: %s", d["kind"], d["id"], "stored" if inserted else "duplicate")
    except Exception:
        logging.exception("Event not accepted; check payload and database")


def send_email(body):
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]
    # Email ro rang theo loai canh bao; FIRE va GAS duoc gui rieng.
    if "PHAT HIEN LUA" in body:
        msg["Subject"] = "[FireWatch] CANH BAO LUA"
    elif "GAS VUOT NGUONG" in body:
        msg["Subject"] = "[FireWatch] CANH BAO KHI GAS"
    else:
        msg["Subject"] = "[FireWatch] Canh bao"
    msg.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    timeout = 15
    if os.getenv("SMTP_SSL", "0") == "1":
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as server:
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"].replace(" ", ""))
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"].replace(" ", ""))
            server.send_message(msg)


def work_once():
    with connect_db() as db:
        row = db.execute("""SELECT id,channel,body,attempts FROM outbox
            WHERE status='pending' AND channel='email' AND next_try<=? ORDER BY next_try LIMIT 1""",
                         (time.time(),)).fetchone()
        if not row:
            return False
        event_id, channel, body, attempts = row
        db.execute("UPDATE outbox SET status='sending',attempts=attempts+1 WHERE id=? AND channel=?",
                   (event_id, channel))
    result, provider_id, next_try = "failed", "", 0
    if DRY:
        logging.info("DRY RUN email: %s", body)
        result = "dry_run"
    else:
        try:
            send_email(body)
            result = "accepted"  # SMTP server accepted, not proof of mailbox delivery.
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            logging.error("Email sending issue: %s", type(exc).__name__)
            result = "uncertain"  # Avoid duplicate emails after ambiguous failure.
    with connect_db() as db:
        db.execute("UPDATE outbox SET status=?,provider_id=?,next_try=? WHERE id=? AND channel=?",
                   (result, provider_id, next_try, event_id, channel))
    logging.info("%s %s => %s %s", event_id, channel, result, provider_id)
    return True


def worker():
    while True:
        try:
            if not work_once():
                OUTBOX_WAKE.wait(timeout=0.5)
                OUTBOX_WAKE.clear()
        except Exception:
            logging.exception("Outbox worker error")
            time.sleep(2)


def require_config():
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", DEVICE):
        raise ValueError("DEVICE_ID invalid")
    required = ["MQTT_HOST", "MQTT_USER", "MQTT_PASS"]
    if not DRY and "email" in CHANNELS:
        required += ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "EMAIL_TO"]
    for key in required:
        value = os.getenv(key, "")
        if not value or "DIEN_" in value or "YOUR_" in value:
            raise ValueError(f"Fill {key} in .env")
    # Dashboard-only operation is valid when email is disabled.


def main():
    require_config()
    initialize()
    if os.getenv("DATABASE_URL", "").strip():
        with connect_db() as db:
            d = db.execute("SELECT current_database(),current_schema()").fetchone()
            logging.info("DB CONNECTED: PostgreSQL database=%s schema=%s", d[0], d[1])
    else:
        logging.warning("DB IS SQLITE, not PostgreSQL: check DATABASE_URL in server/.env")
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
