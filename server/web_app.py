"""FireWatch web: server-enforced permissions, no hardware control endpoints."""
import argparse
import getpass
import hmac
import json
import os
import re
import secrets
import time
from datetime import timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash
import device_store

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PERMISSIONS = ("view_status", "view_thresholds", "view_history")


from database import database, integrity_error


def schema(path):
    with database(path) as db:
        device_store.initialize(db)
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL,
            permissions TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            session_version INTEGER NOT NULL DEFAULT 1, must_change INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, occurred REAL, actor TEXT,
            action TEXT, target TEXT, detail TEXT)""")
        db.execute("CREATE TABLE IF NOT EXISTS login_failures (ip TEXT, username TEXT, occurred REAL)")
        db.execute("CREATE INDEX IF NOT EXISTS login_time ON login_failures(occurred)")
        db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, body TEXT, received REAL)")
        db.execute("""CREATE TABLE IF NOT EXISTS outbox (
            id TEXT, channel TEXT, body TEXT, attempts INTEGER DEFAULT 0,
            next_try REAL DEFAULT 0, status TEXT DEFAULT 'pending',
            provider_id TEXT DEFAULT '', PRIMARY KEY(id, channel))""")


def audit(db, actor, action, target, detail=""):
    db.execute("INSERT INTO audit(occurred,actor,action,target,detail) VALUES (?,?,?,?,?)",
               (time.time(), actor, action, target, detail))


def public_user(row):
    return {"id": row["id"], "username": row["username"], "full_name": row["full_name"],
            "role": row["role"], "permissions": list(PERMISSIONS) if row["role"] == "admin" else json.loads(row["permissions"]),
            "active": bool(row["active"]), "must_change": bool(row["must_change"])}


def password_ok(password):
    return isinstance(password, str) and 10 <= len(password) <= 128


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(DATABASE=str(ROOT / "alerts.sqlite3"),
                      SECRET_KEY=os.getenv("WEB_SECRET", ""),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.getenv("WEB_HTTPS", "0") == "1",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      MAX_CONTENT_LENGTH=16 * 1024,
                      DEVICE_ID=os.getenv("DEVICE_ID", "esp32-tang1"))
    if test_config:
        app.config.update(test_config)
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("WEB_SECRET chua du 32 ky tu. Chay: python setup_web.py")
    schema(app.config["DATABASE"])
    dummy_hash = generate_password_hash(secrets.token_hex(20))

    def db():
        return database(app.config["DATABASE"])

    def fail(message, status=400):
        return jsonify(error=message), status

    def has_permission(permission):
        return g.user["role"] == "admin" or permission in json.loads(g.user["permissions"])

    def protected(permission=None, admin=False):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.user:
                    return fail("Vui lòng đăng nhập.", 401)
                if g.user["must_change"]:
                    return fail("Bạn cần đổi mật khẩu tạm trước khi tiếp tục.", 403)
                if admin and g.user["role"] != "admin":
                    return fail("Chỉ Admin được thực hiện thao tác này.", 403)
                if permission and not has_permission(permission):
                    return fail("Bạn chưa được cấp quyền cho chức năng này.", 403)
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    @app.before_request
    def prepare_request():
        g.user = None
        uid = session.get("uid")
        if uid:
            with db() as conn:
                row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if row and row["active"] and session.get("version") == row["session_version"]:
                g.user = row
            else:
                session.clear()
        if request.path.startswith("/api/") and request.method in ("POST", "PATCH", "DELETE", "PUT"):
            expected = session.get("csrf", "")
            given = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected, given):
                return fail("Phiên không hợp lệ. Tải lại trang rồi thử lại.", 403)
            if request.method != "DELETE" and not request.is_json:
                return fail("Yêu cầu phải là JSON.", 415)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(400)
    def bad_request(_):
        return fail("Dữ liệu không hợp lệ.", 400)

    @app.errorhandler(413)
    def too_large(_):
        return fail("Dữ liệu quá lớn.", 413)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/session")
    def session_info():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        return jsonify(user=public_user(g.user) if g.user else None, csrf=session["csrf"],
                       device=app.config["DEVICE_ID"])

    @app.post("/api/login")
    def login():
        body = request.get_json()
        if not isinstance(body, dict): return fail("Dữ liệu không hợp lệ.")
        name, password = body.get("username", ""), body.get("password", "")
        if not isinstance(name, str) or not isinstance(password, str) or len(password) > 128:
            return fail("Thông tin đăng nhập không hợp lệ.")
        name = name.strip().lower()[:64]
        ip = request.remote_addr or "unknown"  # Do not trust arbitrary X-Forwarded-For.
        with db() as conn:
            conn.execute("DELETE FROM login_failures WHERE occurred<?", (time.time()-900,))
            count = conn.execute("SELECT COUNT(*) FROM login_failures WHERE ip=? AND username=?", (ip, name)).fetchone()[0]
            all_count = conn.execute("SELECT COUNT(*) FROM login_failures WHERE ip=?", (ip,)).fetchone()[0]
            if count >= 8 or all_count >= 40:
                return fail("Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút.", 429)
            row = conn.execute("SELECT * FROM users WHERE username=?", (name,)).fetchone()
            valid = check_password_hash(row["password_hash"] if row else dummy_hash, password)
            if not row or not valid or not row["active"]:
                conn.execute("INSERT INTO login_failures VALUES (?,?,?)", (ip, name, time.time()))
                return fail("Tên đăng nhập hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.", 401)
            conn.execute("DELETE FROM login_failures WHERE ip=? AND username=?", (ip, name))
            audit(conn, row["username"], "login", row["username"])
        session.clear()
        session.update(uid=row["id"], version=row["session_version"], csrf=secrets.token_urlsafe(32))
        session.permanent = True
        return jsonify(user=public_user(row), csrf=session["csrf"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.post("/api/password")
    def password():
        if not g.user: return fail("Vui lòng đăng nhập.", 401)
        body = request.get_json()
        if not isinstance(body, dict): return fail("Dữ liệu không hợp lệ.")
        old, new = body.get("current", ""), body.get("new", "")
        if not isinstance(old, str) or len(old) > 128 or not password_ok(new):
            return fail("Mật khẩu mới cần từ 10 đến 128 ký tự.")
        if not check_password_hash(g.user["password_hash"], old):
            return fail("Mật khẩu hiện tại không đúng.")
        if old == new: return fail("Mật khẩu mới phải khác mật khẩu hiện tại.")
        with db() as conn:
            conn.execute("UPDATE users SET password_hash=?,must_change=0,session_version=session_version+1 WHERE id=?",
                         (generate_password_hash(new), g.user["id"]))
            audit(conn, g.user["username"], "change_password", g.user["username"])
            version = conn.execute("SELECT session_version FROM users WHERE id=?", (g.user["id"],)).fetchone()[0]
        session["version"] = version
        return jsonify(ok=True)

    @app.get("/api/device/status")
    @protected("view_status")
    def device_status():
        with db() as conn: result = device_store.read_state(conn, app.config["DEVICE_ID"])
        if result["data"]: result["data"].pop("config", None)
        return jsonify(result)

    @app.get("/api/device/thresholds")
    @protected("view_thresholds")
    def thresholds():
        with db() as conn: state = device_store.read_state(conn, app.config["DEVICE_ID"])
        return jsonify(config=state["data"].get("config") if state["data"] else None,
                       fresh=state["fresh"], last_seen=state["last_seen"], source="ESP32")

    @app.get("/api/history")
    @protected("view_history")
    def history():
        try: before = float(request.args.get("before", time.time()+1))
        except ValueError: return fail("Mốc thời gian không hợp lệ.")
        with db() as conn:
            events = [dict(r) for r in conn.execute("SELECT id,body,received FROM events WHERE received<? ORDER BY received DESC LIMIT 100", (before,))]
            activities = [dict(r) for r in conn.execute("SELECT * FROM activity WHERE device=? AND received<? ORDER BY received DESC,id DESC LIMIT 100", (app.config["DEVICE_ID"], before))]
            for e in events:
                e["payload"] = json.loads(e.pop("body"))
                e["deliveries"] = [dict(r) for r in conn.execute("SELECT channel,status FROM outbox WHERE id=?", (e["id"],))]
        return jsonify(events=events, activities=activities)

    @app.get("/api/admin/users")
    @protected(admin=True)
    def users():
        with db() as conn: rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return jsonify(users=[public_user(r) for r in rows])

    def parse_user(body, creating=False):
        if not isinstance(body, dict): raise ValueError("Dữ liệu không hợp lệ.")
        name = body.get("full_name", "")
        role, permissions, active = body.get("role", "user"), body.get("permissions", []), body.get("active", True)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Họ tên cần từ 1 đến 80 ký tự.")
        if role not in ("admin", "user") or type(active) is not bool:
            raise ValueError("Vai trò hoặc trạng thái không hợp lệ.")
        if not isinstance(permissions, list) or any(p not in PERMISSIONS for p in permissions):
            raise ValueError("Quyền không hợp lệ.")
        result = dict(full_name=name.strip(), role=role, permissions=sorted(set(permissions)), active=active)
        if creating:
            username, pwd = body.get("username", ""), body.get("password", "")
            if not isinstance(username, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,32}", username):
                raise ValueError("Tên đăng nhập: 3–32 chữ không dấu, số, dấu . _ -")
            if not password_ok(pwd): raise ValueError("Mật khẩu tạm cần từ 10 đến 128 ký tự.")
            result.update(username=username.lower(), password_hash=generate_password_hash(pwd))
        return result

    @app.post("/api/admin/users")
    @protected(admin=True)
    def create_user():
        try: data = parse_user(request.get_json(), creating=True)
        except ValueError as exc: return fail(str(exc))
        try:
            with db() as conn:
                cur = conn.execute("""INSERT INTO users(username,full_name,password_hash,role,permissions,active,must_change,created)
                    VALUES (?,?,?,?,?,?,1,?)""", (data["username"], data["full_name"], data["password_hash"], data["role"],
                    json.dumps(data["permissions"]), int(data["active"]), time.time()))
                audit(conn, g.user["username"], "create_user", data["username"], data["role"])
                uid = cur.lastrowid
        except integrity_error(): return fail("Tên đăng nhập đã tồn tại.", 409)
        return jsonify(id=uid), 201

    @app.patch("/api/admin/users/<int:uid>")
    @protected(admin=True)
    def update_user(uid):
        try: data = parse_user(request.get_json())
        except ValueError as exc: return fail(str(exc))
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not row: return fail("Không tìm thấy tài khoản.", 404)
            if uid == g.user["id"] and (not data["active"] or data["role"] != "admin"):
                return fail("Không thể tự khóa hoặc tự hạ quyền Admin đang đăng nhập.")
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if row["role"] == "admin" and row["active"] and admins <= 1 and (not data["active"] or data["role"] != "admin"):
                return fail("Phải giữ ít nhất một Admin đang hoạt động.")
            conn.execute("""UPDATE users SET full_name=?,role=?,permissions=?,active=?,session_version=session_version+1 WHERE id=?""",
                         (data["full_name"], data["role"], json.dumps(data["permissions"]), int(data["active"]), uid))
            audit(conn, g.user["username"], "update_user", row["username"], json.dumps(data, ensure_ascii=False))
            if uid == g.user["id"]: session["version"] = row["session_version"]+1
        return jsonify(ok=True)

    @app.delete("/api/admin/users/<int:uid>")
    @protected(admin=True)
    def delete_user(uid):
        if uid == g.user["id"]: return fail("Không thể xóa tài khoản đang đăng nhập.")
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not row: return fail("Không tìm thấy tài khoản.", 404)
            count = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if row["role"] == "admin" and row["active"] and count <= 1:
                return fail("Không thể xóa Admin hoạt động cuối cùng.")
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            audit(conn, g.user["username"], "delete_user", row["username"])
        return jsonify(ok=True)

    @app.post("/api/admin/users/<int:uid>/reset-password")
    @protected(admin=True)
    def reset_password(uid):
        body = request.get_json()
        pwd = body.get("password") if isinstance(body, dict) else None
        if not password_ok(pwd): return fail("Mật khẩu tạm cần từ 10 đến 128 ký tự.")
        if uid == g.user["id"]: return fail("Dùng mục Đổi mật khẩu cho tài khoản của bạn.")
        with db() as conn:
            row = conn.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
            if not row: return fail("Không tìm thấy tài khoản.", 404)
            conn.execute("UPDATE users SET password_hash=?,must_change=1,session_version=session_version+1 WHERE id=?",
                         (generate_password_hash(pwd), uid))
            audit(conn, g.user["username"], "reset_password", row["username"])
        return jsonify(ok=True)

    @app.get("/api/admin/audit")
    @protected(admin=True)
    def audit_log():
        with db() as conn: rows = [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]
        return jsonify(rows=rows)

    return app


def init_admin():
    path = ROOT / "alerts.sqlite3"
    schema(path)
    username = input("Tên đăng nhập Admin (không dấu): ").strip().lower()
    name = input("Họ tên: ").strip()
    pwd = getpass.getpass("Mật khẩu (10–128 ký tự, không hiện khi gõ): ")
    if pwd != getpass.getpass("Nhập lại mật khẩu: "): raise SystemExit("Mật khẩu không khớp.")
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username) or not 1 <= len(name) <= 80 or not password_ok(pwd):
        raise SystemExit("Thông tin không hợp lệ.")
    with database(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]:
            raise SystemExit("Đã có Admin. Hãy thêm tài khoản trong giao diện quản trị.")
        db.execute("INSERT INTO users(username,full_name,password_hash,role,permissions,created) VALUES (?,?,?,?,?,?)",
                   (username, name, generate_password_hash(pwd), "admin", json.dumps(list(PERMISSIONS)), time.time()))
        audit(db, "local-setup", "create_first_admin", username)
    print("Đã tạo Admin. Chạy: python web_app.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-admin", action="store_true")
    args = parser.parse_args()
    if args.init_admin:
        init_admin()
    else:
        from waitress import serve
        host = os.getenv("WEB_HOST", "0.0.0.0")
        port = int(os.getenv("WEB_PORT", "5000"))
        print(f"FireWatch: http://{host}:{port}")
        serve(create_app(), host=host, port=port, threads=6)
