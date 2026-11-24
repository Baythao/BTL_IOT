"""Check real MQTT -> Python server -> durable DB ACK using ESP32 publisher ACL.

Never use firewatch-server to publish to .../event: that account is read-only!
"""
import argparse
import getpass
import json
import os
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

parser = argparse.ArgumentParser(description="Kiem tra canh bao tung loai FIRE/GAS")
parser.add_argument("--kind", choices=["FIRE", "GAS"], default="GAS")
args = parser.parse_args()
load_dotenv(Path(__file__).resolve().parent / ".env")
HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE = os.getenv("DEVICE_ID", "esp32-tang1")
USER = "esp32-device"
PASSWORD = getpass.getpass("Nhap mat khau MQTT cua esp32-device (khong hien thi): ")
EVENT_TOPIC = f"fire-demo/{DEVICE}/event"
ACK_TOPIC = f"fire-demo/{DEVICE}/ack"
EVENT_ID = "test-" + uuid.uuid4().hex
payload = json.dumps({
    "id": EVENT_ID, "device": DEVICE, "kind": args.kind,
    "gas_adc": 1500, "uptime_ms": 10000, "age_ms": 0,
})
connected = threading.Event()
subscribed = threading.Event()
acked = threading.Event()
state = {"connect_ok": False, "subscribe_ok": False}
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id="firewatch-diagnostic-" + uuid.uuid4().hex[:8])
client.username_pw_set(USER, PASSWORD)


def on_connect(c, userdata, flags, reason_code, properties):
    print("MQTT CONNECT:", reason_code)
    state["connect_ok"] = not reason_code.is_failure
    if state["connect_ok"]:
        c.subscribe(ACK_TOPIC, qos=1)
    connected.set()


def on_subscribe(c, userdata, mid, reason_codes, properties):
    state["subscribe_ok"] = all(not code.is_failure for code in reason_codes)
    print("MQTT SUBSCRIBE ACK:", "Success" if state["subscribe_ok"] else "Access denied")
    subscribed.set()


def on_message(c, userdata, message):
    if message.topic == ACK_TOPIC and message.payload.decode(errors="replace") == EVENT_ID:
        print("SERVER ACK:", EVENT_ID)
        acked.set()


client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message

try:
    client.connect(HOST, PORT, keepalive=30)
    client.loop_start()
    if not connected.wait(10) or not state["connect_ok"]:
        raise RuntimeError("Broker unreachable or ESP32 credentials rejected")
    if not subscribed.wait(10) or not state["subscribe_ok"]:
        raise RuntimeError("Cannot subscribe to /ack: check ESP32 ACL")
    info = client.publish(EVENT_TOPIC, payload, qos=1, retain=False)
    info.wait_for_publish(timeout=10)
    if not info.is_published():
        raise RuntimeError("MQTT broker did not acknowledge QoS1 publish")
    print("MQTT broker accepted QoS1 publish:", args.kind, EVENT_ID)
    if not acked.wait(15):
        raise RuntimeError("NO SERVER ACK in 15s. Check notify_server.py log, ACL, and database. MQTT PUBACK alone is insufficient.")
    print("SUCCESS: notify_server.py acknowledged the stored event.")
    print("Now refresh Web > Lich su hoat dong and check Email status.")
finally:
    client.disconnect()
    client.loop_stop()
