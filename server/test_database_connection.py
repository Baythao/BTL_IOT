"""Explicitly load .env before testing chosen database."""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
from database import database
import os

with database() as conn:
    n = conn.execute("SELECT 1").fetchone()[0]
    if n != 1:
        raise RuntimeError("Database query failed")
    print("KET NOI THANH CONG:", "PostgreSQL" if os.getenv("DATABASE_URL", "").strip() else "SQLite")
