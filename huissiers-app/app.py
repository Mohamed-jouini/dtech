#!/usr/bin/env python3
"""
قائمة عدول المنفذين — Liste des huissiers
Flask + SQLite
"""
from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import json
from datetime import datetime

# ─── AUDIT LOGGING ───────────────────────────────────────────────
import os as _os
_os.environ.setdefault("AUDIT_URL", "http://audit-app:5010/api/log")
try:
    from audit_client import log_action as _log
except ImportError:
    def _log(*a, **k): pass
# ─────────────────────────────────────────────────────────────────


app = Flask(__name__)

DB_PATH = os.environ.get('DB_PATH', 'huissiers.db')
NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL', '')
BASE_PATH = os.environ.get('BASE_PATH', '')


@app.context_processor
def inject_base():
    return {'BASE': BASE_PATH}


@app.before_request
def check_access():
    if not NEXTCLOUD_URL:
        return
    if request.path.startswith('/api/'):
        return
    referer = request.headers.get('Referer', '')
    sec_fetch_dest = request.headers.get('Sec-Fetch-Dest', '')
    sec_fetch_site = request.headers.get('Sec-Fetch-Site', '')
    if sec_fetch_dest == 'iframe':
        return
    if sec_fetch_site == 'same-origin':
        return
    if referer and (NEXTCLOUD_URL in referer or request.host in referer):
        return
    if request.content_type and 'json' in request.content_type:
        return
    return '''
    <html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>غير مسموح</title>
    <style>body{font-family:Arial;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;direction:rtl}
    .box{background:white;padding:40px;border-radius:12px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.1)}
    h1{color:#dc3545;font-size:48px}p{color:#333;font-size:16px}.hint{color:#888;font-size:13px}</style></head>
    <body><div class="box"><h1>🔒</h1><p>غير مسموح بالوصول المباشر</p><p class="hint">يرجى الدخول عبر Nextcloud</p></div></body></html>
    ''', 403


@app.after_request
def add_headers(response):
    if NEXTCLOUD_URL:
        response.headers['Content-Security-Policy'] = f"frame-ancestors 'self' {NEXTCLOUD_URL}"
    else:
        response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS huissiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    ''')
    conn.commit()
    conn.close()


# ============================================================
# PAGES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/huissier/new')
def new_huissier():
    return render_template('form.html', huissier_id=None)

@app.route('/huissier/<int:hid>')
def edit_huissier(hid):
    return render_template('form.html', huissier_id=hid)


# ============================================================
# API
# ============================================================

@app.route('/api/huissiers', methods=['GET'])
def api_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM huissiers ORDER BY updated_at DESC").fetchall()
    conn.close()
    search = request.args.get('search', '').strip().lower()
    results = []
    for r in rows:
        d = json.loads(r['data']) if r['data'] else {}
        d['id'] = r['id']
        d['created_at'] = r['created_at']
        d['updated_at'] = r['updated_at']
        if search:
            searchable = json.dumps(d, ensure_ascii=False).lower()
            if search not in searchable:
                continue
        results.append(d)
    return jsonify(results)


@app.route('/api/huissiers', methods=['POST'])
def api_create():
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO huissiers (data, created_at, updated_at) VALUES (?, ?, ?)",
        (json.dumps(data, ensure_ascii=False), now, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    data['id'] = new_id
    _log(request,'huissiers-app','create','huissier',new_id,
         label=data.get('nom',''),details={'nom':data.get('nom','')})
    return jsonify(data), 201


@app.route('/api/huissiers/<int:hid>', methods=['GET'])
def api_get(hid):
    conn = get_db()
    row = conn.execute("SELECT * FROM huissiers WHERE id = ?", (hid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = json.loads(row['data']) if row['data'] else {}
    d['id'] = row['id']
    return jsonify(d)


@app.route('/api/huissiers/<int:hid>', methods=['PUT'])
def api_update(hid):
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    # Lire ancienne valeur pour détecter les changements
    old_row = conn.execute('SELECT data FROM huissiers WHERE id = ?', (hid,)).fetchone()
    old_data = json.loads(old_row['data']) if old_row and old_row['data'] else {}
    # Détecter les champs modifiés
    changes = {k: {'avant': old_data.get(k,''), 'après': data.get(k,'')}
               for k in data if data.get(k) != old_data.get(k)
               and k not in ('created_at','updated_at','id')}
    conn.execute(
        "UPDATE huissiers SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False), now, hid)
    )
    conn.commit()
    conn.close()
    data['id'] = hid
    _log(request,'huissiers-app','update','huissier',hid,
         label=data.get('nom',''),
         details={'modifications': changes})
    return jsonify(data)


@app.route('/api/huissiers/<int:hid>', methods=['DELETE'])
def api_delete(hid):
    conn = get_db()
    # Lire les données AVANT suppression
    row = conn.execute('SELECT data FROM huissiers WHERE id = ?', (hid,)).fetchone()
    hdata = json.loads(row['data']) if row and row['data'] else {}
    conn.execute("DELETE FROM huissiers WHERE id = ?", (hid,))
    conn.commit()
    conn.close()
    _log(request,'huissiers-app','delete','huissier',hid,
         label=hdata.get('nom',''),
         details={'nom':hdata.get('nom',''),'wilaya':hdata.get('wilaya','')})
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
