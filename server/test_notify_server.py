"""Offline tests: never connect MQTT and never call notification providers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import requests
import notify_server as app


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, "DB", Path(self.tmp.name)/"test.sqlite3"),
                        patch.object(app, "DRY", False),
                        patch.object(app, "CHANNELS", ["push", "sms"])]
        for p in self.patches: p.start()
        app.initialize()
        self.event = dict(device=app.DEVICE, id="boot-1", kind="FIRE", gas_adc=800,
                          uptime_ms=12345, age_ms=100)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def status(self):
        with app.connect_db() as db:
            return db.execute("SELECT channel,status FROM outbox ORDER BY channel").fetchall()

    def test_duplicate_only_creates_two_channels_once(self):
        self.assertTrue(app.store_event(self.event))
        self.assertFalse(app.store_event(self.event))
        self.assertEqual(len(self.status()), 2)

    def test_ack_after_store_and_duplicate(self):
        c = Mock()
        m = Mock(topic=app.BASE+"/event", retain=False, payload=json.dumps(self.event).encode())
        app.on_message(c,None,m); app.on_message(c,None,m)
        self.assertEqual(c.publish.call_count, 2)
        self.assertEqual(len(self.status()), 2)

    def test_invalid_and_retained_do_not_ack(self):
        c = Mock()
        m = Mock(topic=app.BASE+"/event", retain=True, payload=json.dumps(self.event).encode())
        app.on_message(c,None,m)
        m.retain=False; m.payload=b'{"kind":"INVALID"}'
        app.on_message(c,None,m)
        c.publish.assert_not_called()

    def test_dry_run_never_sends(self):
        app.store_event(self.event)
        with patch.object(app,"DRY",True), patch.object(app,"send_http") as send:
            app.work_once();app.work_once()
            send.assert_not_called()
        self.assertTrue(all(s=="dry_run" for _,s in self.status()))

    def test_channels_independent_timeout_not_resent(self):
        app.store_event(self.event)
        good=Mock(status_code=201);good.json.return_value={"sid":"SM_TEST"}
        with patch.object(app,"send_http",side_effect=[requests.Timeout(),good]) as send:
            app.work_once();app.work_once()
            self.assertFalse(app.work_once())
            self.assertEqual(send.call_count,2)
        self.assertEqual(self.status(),[("push","uncertain"),("sms","accepted")])

    def test_reboot_does_not_resend_inflight(self):
        app.store_event(self.event)
        with app.connect_db() as db:
            db.execute("UPDATE outbox SET status='sending'")
        app.initialize()
        self.assertTrue(all(s=="uncertain" for _,s in self.status()))
        self.assertFalse(app.work_once())

    def test_delayed_notice(self):
        self.event['age_ms']=60000
        app.store_event(self.event)
        with app.connect_db() as db:
            text=db.execute("SELECT body FROM outbox LIMIT 1").fetchone()[0]
        self.assertIn("GUI TRE 60s",text)


if __name__ == "__main__":
    unittest.main()
