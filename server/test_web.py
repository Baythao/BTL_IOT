"""RBAC and telemetry tests with temporary SQLite, no external connections."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash
import device_store
from web_app import create_app, database

PASSWORD = "test-only-long-password"


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hash = generate_password_hash(PASSWORD)

    def setUp(self):
        self.env_patch = patch.dict("os.environ", {"DATABASE_URL": ""})
        self.env_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name)/"test.sqlite3")
        self.app = create_app(dict(TESTING=True, DATABASE=self.db, SECRET_KEY="test-secret-"*5))
        with database(self.db) as d:
            for name, role, perms in [("admin", "admin", []), ("viewer", "user", ["view_status"]), ("threshold", "user", ["view_thresholds"])]:
                d.execute("INSERT INTO users(username,full_name,password_hash,role,permissions,created) VALUES (?,?,?,?,?,?)",
                          (name, name, self.hash, role, json.dumps(perms), time.time()))
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()
        self.env_patch.stop()

    def login(self, name="admin", client=None):
        c=client or self.client
        csrf=c.get('/api/session').json['csrf']
        r=c.post('/api/login',json=dict(username=name,password=PASSWORD),headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,200)
        return r.json['csrf']

    def mutate(self, method, url, body=None, client=None):
        c=client or self.client
        token=c.get('/api/session').json['csrf']
        return c.open(url,method=method,json=body,headers={'X-CSRF-Token':token})

    def user_update(self, uid=2, **kw):
        data=dict(full_name='viewer',role='user',permissions=['view_status'],active=True)
        data.update(kw)
        return self.mutate('PATCH',f'/api/admin/users/{uid}',data)

    def sample(self):
        return dict(fire=False,gas=False,gas_ready=True,gas_adc=450,fan=False,pump=False,buzzer=False,servo=0,uptime_ms=5000,
                    config=dict(gas_on=1200,gas_off=900,gas_warmup_ms=5000,fire_run_ms=10000,fire_active_level=1))

    def test_anonymous_denied(self):
        for endpoint in ['/api/device/status','/api/device/thresholds','/api/history','/api/admin/users','/api/admin/audit']:
            self.assertEqual(self.client.get(endpoint).status_code,401)

    def test_viewer_cannot_bypass_admin_or_thresholds(self):
        self.login('viewer')
        self.assertEqual(self.client.get('/api/device/status').status_code,200)
        for endpoint in ['/api/device/thresholds','/api/history','/api/admin/users','/api/admin/audit']:
            self.assertEqual(self.client.get(endpoint).status_code,403)
        self.assertEqual(self.user_update(role='admin').status_code,403)
        self.assertEqual(self.mutate('DELETE','/api/admin/users/1').status_code,403)

    def test_csrf_required(self):
        self.login()
        self.assertEqual(self.client.delete('/api/admin/users/2').status_code,403)

    def test_create_and_force_change(self):
        self.login()
        r=self.mutate('POST','/api/admin/users',dict(username='newuser',full_name='Tên mới',password=PASSWORD,
            role='user',permissions=['view_history'],active=True))
        self.assertEqual(r.status_code,201)
        c=self.app.test_client();self.login('newuser',c)
        self.assertEqual(c.get('/api/history').status_code,403)
        r=self.mutate('POST','/api/password',dict(current=PASSWORD,new='replacement-password-123'),c)
        self.assertEqual(r.status_code,200)
        self.assertEqual(c.get('/api/history').status_code,200)
        self.assertEqual(c.get('/api/device/status').status_code,403)

    def test_revocation_is_immediate(self):
        c=self.app.test_client();self.login('viewer',c);self.login()
        self.assertEqual(self.user_update(permissions=[]).status_code,200)
        self.assertEqual(c.get('/api/device/status').status_code,401)
        self.login('viewer',c)
        self.assertEqual(c.get('/api/device/status').status_code,403)

    def test_lock_and_delete_revoke_sessions(self):
        c=self.app.test_client();self.login('viewer',c);self.login()
        self.assertEqual(self.user_update(active=False).status_code,200)
        self.assertEqual(c.get('/api/device/status').status_code,401)
        self.assertEqual(self.mutate('DELETE','/api/admin/users/2').status_code,200)
        with database(self.db) as d:
            self.assertIsNone(d.execute('SELECT * FROM users WHERE id=2').fetchone())

    def test_self_admin_protection(self):
        self.login()
        self.assertEqual(self.mutate('DELETE','/api/admin/users/1').status_code,400)
        self.assertEqual(self.user_update(uid=1,role='user').status_code,400)
        self.assertEqual(self.user_update(uid=1,active=False).status_code,400)

    def test_no_password_hash_in_users_and_audit(self):
        self.login(); data=self.client.get('/api/admin/users').get_data(as_text=True)
        self.assertNotIn('password_hash',data)
        self.assertNotIn(self.hash,data)
        self.user_update()
        self.assertNotIn(PASSWORD,self.client.get('/api/admin/audit').get_data(as_text=True))

    def test_unknown_permission_rejected(self):
        self.login()
        self.assertEqual(self.user_update(permissions=['manage_users']).status_code,400)

    def test_password_reset_revokes(self):
        c=self.app.test_client();self.login('viewer',c);self.login()
        self.assertEqual(self.mutate('POST','/api/admin/users/2/reset-password',dict(password='temporary-pass-123')).status_code,200)
        self.assertEqual(c.get('/api/device/status').status_code,401)

    def test_thresholds_not_leaked_through_status(self):
        with database(self.db) as d: device_store.save_state(d,'esp32-tang1',json.dumps(self.sample()))
        self.login('viewer')
        self.assertNotIn('config',self.client.get('/api/device/status').json['data'])
        c=self.app.test_client();self.login('threshold',c)
        self.assertEqual(c.get('/api/device/thresholds').json['config']['gas_on'],1200)
        self.assertEqual(c.get('/api/device/status').status_code,403)

    def test_freshness_and_missing_config(self):
        s=self.sample();s.pop('config')
        with database(self.db) as d:
            device_store.save_state(d,'esp32-tang1',json.dumps(s),time.time()-30)
            result=device_store.read_state(d,'esp32-tang1')
            self.assertFalse(result['fresh'])
        self.login()
        self.assertIsNone(self.client.get('/api/device/thresholds').json['config'])

    def test_activity_records_only_changes(self):
        s=self.sample()
        with database(self.db) as d:
            device_store.save_state(d,'esp32-tang1',json.dumps(s))
            device_store.save_state(d,'esp32-tang1',json.dumps(s))
            self.assertEqual(d.execute('SELECT COUNT(*) FROM activity').fetchone()[0],6)
            s['pump']=True;device_store.save_state(d,'esp32-tang1',json.dumps(s))
            self.assertEqual(d.execute('SELECT COUNT(*) FROM activity').fetchone()[0],7)

    def test_invalid_telemetry_and_offline(self):
        s=self.sample();s['gas_adc']=5000
        with self.assertRaises(ValueError):device_store.validate_state(json.dumps(s))
        with database(self.db) as d:
            device_store.save_state(d,'esp32-tang1',json.dumps(self.sample()))
            device_store.save_status(d,'esp32-tang1','offline')
            self.assertFalse(device_store.read_state(d,'esp32-tang1')['fresh'])

    def test_login_rate_limit(self):
        token=self.client.get('/api/session').json['csrf']
        for _ in range(8):
            self.assertEqual(self.client.post('/api/login',json=dict(username='viewer',password='wrong'),headers={'X-CSRF-Token':token}).status_code,401)
        self.assertEqual(self.client.post('/api/login',json=dict(username='viewer',password='wrong'),headers={'X-CSRF-Token':token}).status_code,429)


if __name__ == '__main__':unittest.main()
