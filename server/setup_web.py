"""Prepare a local .env with a random signing secret. Never print the secret."""
from pathlib import Path
import secrets
from dotenv import dotenv_values

root = Path(__file__).resolve().parent
path = root / ".env"
if not path.exists():
    path.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
values = dotenv_values(path)
if not values.get("WEB_SECRET"):
    with path.open("a", encoding="utf-8") as f:
        f.write("\nWEB_SECRET=" + secrets.token_hex(32) + "\n")
    print("Da tao khoa phien dang nhap trong .env.")
else:
    print("Da co WEB_SECRET, giu nguyen.")
print("Tiep theo: python web_app.py --init-admin")
