"""Read-only FireWatch database diagnosis. Never displays DB passwords."""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
from database import database

if not os.getenv('DATABASE_URL'):
    raise SystemExit('DATABASE_URL not set! App will use SQLite; check server/.env')

with database() as db:
    row = db.execute('SELECT current_database() AS db, current_schema() AS schema').fetchone()
    print('Engine: PostgreSQL')
    print('Database:', row['db'])
    print('Schema:', row['schema'])
    names = [r['table_name'] for r in db.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name")]
    print('Tables:', ', '.join(names) if names else '(none)')
    if 'events' not in names:
        print('Missing table events. Restart notify_server.py to initialize the FireWatch schema.')
    else:
        for r in db.execute('SELECT id,body,received FROM events ORDER BY received DESC LIMIT 10'):
            try:
                d = json.loads(r['body'])
                print('EVENT:', r['id'], 'kind=', d.get('kind'), 'source=',
                      d.get('source', 'esp32_event'))
            except Exception:
                print('EVENT with malformed body:', r['id'])
    if 'outbox' in names:
        for r in db.execute('SELECT id,status FROM outbox ORDER BY next_try DESC LIMIT 10'):
            print('EMAIL:', r['id'], r['status'])
    if 'device_state' in names:
        r = db.execute('SELECT device,payload,seen FROM device_state ORDER BY seen DESC LIMIT 1').fetchone()
        if r:
            try:
                d=json.loads(r['payload'])
                print('SENSOR:', r['device'], 'fire=',d.get('fire'),
                      'gas=',d.get('gas'), 'fire_active_level=',
                      d.get('config',{}).get('fire_active_level'))
            except Exception:
                print('SENSOR: malformed state')
