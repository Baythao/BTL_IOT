"""Offline email tests; never connect to MQTT or SMTP."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import notify_server as app

class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.dict(os.environ, {"DATABASE_URL": ""}),
                        patch.object(app, "DB", Path(self.tmp.name)/"test.sqlite3"),
                        patch.object(app, "DRY", False),
                        patch.object(app, "CHANNELS", ["email"])]
        for p in self.patches: p.start()
        app.initialize()
        self.event = dict(device=app.DEVICE, id="boot-1", kind="FIRE", gas_adc=800,
                          uptime_ms=12345, age_ms=100)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def status(self):
        with app.connect_db() as db:
            return [tuple(r) for r in db.execute("SELECT channel,status FROM outbox ORDER BY channel").fetchall()]

    def test_duplicate_stores_one_email(self):
        self.assertTrue(app.store_event(self.event))
        self.assertFalse(app.store_event(self.event))
        self.assertEqual(len(self.status()), 1)

    def test_fire_and_gas_are_independent_events(self):
        fire = dict(self.event, id="fire-001", kind="FIRE")
        gas = dict(self.event, id="gas-001", kind="GAS")
        self.assertTrue(app.store_event(fire))
        self.assertTrue(app.store_event(gas))
        with app.connect_db() as db:
            rows = db.execute("SELECT id,body FROM events ORDER BY id").fetchall()
            self.assertEqual(len(rows), 2)
            kinds = {json.loads(row["body"])["kind"] for row in rows}
            self.assertEqual(kinds, {"FIRE", "GAS"})
        self.assertEqual(len(self.status()), 2)

    def test_ack_after_store_and_duplicate(self):
        c = Mock()
        m = Mock(topic=app.BASE+"/event", retain=False, payload=json.dumps(self.event).encode())
        app.on_message(c,None,m); app.on_message(c,None,m)
        self.assertEqual(c.publish.call_count, 2)

    def test_dry_run_never_sends(self):
        app.store_event(self.event)
        with patch.object(app,"DRY",True), patch.object(app,"send_email") as send:
            app.work_once()
            send.assert_not_called()
        self.assertEqual(self.status(), [("email", "dry_run")])

    def test_smtp_success(self):
        app.store_event(self.event)
        with patch.object(app,"send_email") as send:
            self.assertTrue(app.work_once())
            send.assert_called_once()
        self.assertEqual(self.status(), [("email", "accepted")])

    def test_smtp_timeout_not_automatically_resent(self):
        app.store_event(self.event)
        with patch.object(app,"send_email",side_effect=TimeoutError) as send:
            app.work_once()
            self.assertFalse(app.work_once())
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.status(), [("email", "uncertain")])

    def _state(self, fire):
        return dict(fire=fire, gas=False, gas_ready=True, gas_adc=300,
                    fan=fire, pump=fire, buzzer=fire, servo=90 if fire else 0,
                    uptime_ms=12345,
                    config=dict(gas_on=1200, gas_off=900, gas_warmup_ms=5000,
                                fire_run_ms=10000, fire_active_level=0))

    def _publish_state(self, fire):
        c = Mock()
        m = Mock(topic=app.BASE+"/state", retain=False,
                 payload=json.dumps(self._state(fire)).encode())
        def run_timer(delay, fn, args):
            t=Mock()
            t.start.side_effect=lambda:fn(*args)
            return t
        with patch.object(app.threading, "Timer", side_effect=run_timer):
            app.on_message(c, None, m)

    def _event_rows(self):
        with app.connect_db() as db:
            return [json.loads(r["body"]) for r in db.execute(
                "SELECT body FROM events ORDER BY received").fetchall()]

    def test_fire_state_fallback_when_event_missing(self):
        self._publish_state(False)
        self._publish_state(True)
        self.assertEqual(len(self._event_rows()), 1)
        self.assertEqual(self._event_rows()[0]["kind"], "FIRE")
        self.assertEqual(self._event_rows()[0]["source"], "state_fallback")
        self.assertEqual(len(self.status()), 1)
        self._publish_state(True)
        self.assertEqual(len(self._event_rows()), 1)

    def test_event_then_state_has_one_email(self):
        app.store_event(self.event)
        self._publish_state(True)
        self.assertEqual(len(self._event_rows()), 1)
        self.assertEqual(len(self.status()), 1)

    def test_state_then_direct_event_has_one_email(self):
        self._publish_state(True)
        self.assertFalse(app.store_event(self.event))
        self.assertEqual(len(self._event_rows()), 1)
        self.assertEqual(len(self.status()), 1)

    def test_first_true_state_is_saved_once_even_after_reconnect(self):
        self._publish_state(True)
        with app.connect_db() as db:
            db.execute("UPDATE device_state SET seen=0")
        self._publish_state(True)
        self.assertEqual(len(self._event_rows()), 1)

    def test_gas_not_blocked_by_fire_fallback(self):
        self._publish_state(True)
        gas=dict(self.event, id="gas-after-fire", kind="GAS")
        self.assertTrue(app.store_event(gas))
        self.assertEqual({e["kind"] for e in self._event_rows()}, {"FIRE", "GAS"})
        self.assertEqual(len(self.status()), 2)

    def test_reboot_does_not_resend_inflight(self):
        app.store_event(self.event)
        with app.connect_db() as db:
            db.execute("UPDATE outbox SET status='sending'")
        app.initialize()
        self.assertEqual(self.status(), [("email", "uncertain")])

if __name__ == "__main__":
    unittest.main()
