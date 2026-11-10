#!/usr/bin/env python3
"""
أرشيف — Archive des dossiers
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

DB_PATH = os.environ.get('DB_PATH', 'archive.db')
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
        CREATE TABLE IF NOT EXISTS archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    ''')
    conn.commit()
    conn.close()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dossier/new')
def new_dossier():
    return render_template('form.html', dossier_id=None)

@app.route('/dossier/<int:did>')
def edit_dossier(did):
    return render_template('form.html', dossier_id=did)


@app.route('/api/archive', methods=['GET'])
def api_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM archive ORDER BY updated_at DESC").fetchall()
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


@app.route('/api/archive', methods=['POST'])
def api_create():
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO archive (data, created_at, updated_at) VALUES (?, ?, ?)",
        (json.dumps(data, ensure_ascii=False), now, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    data['id'] = new_id
    _log(request,'archive-app','create','dossier',new_id,
         label=data.get('mahkama','')+' — عدد: '+str(data.get('adad_qadiya','—'))+' — '+data.get('manoub',''),
         details={'adad_qadiya':data.get('adad_qadiya',''),'mahkama':data.get('mahkama',''),'manoub':data.get('manoub','')})
    return jsonify(data), 201


@app.route('/api/archive/<int:did>', methods=['GET'])
def api_get(did):
    conn = get_db()
    row = conn.execute("SELECT * FROM archive WHERE id = ?", (did,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = json.loads(row['data']) if row['data'] else {}
    d['id'] = row['id']
    return jsonify(d)


@app.route('/api/archive/<int:did>', methods=['PUT'])
def api_update(did):
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    old_row = conn.execute('SELECT data FROM archive WHERE id = ?', (did,)).fetchone()
    old_data = json.loads(old_row['data']) if old_row and old_row['data'] else {}
    skip = {'created_at','updated_at','id'}
    changes = {}
    for k in data:
        if k in skip: continue
        v_old = str(old_data.get(k,'') or '').strip()
        v_new = str(data.get(k,'') or '').strip()
        if v_old != v_new and (v_old or v_new):
            changes[k] = {'avant': old_data.get(k,''), 'après': data.get(k,'')}
    conn.execute(
        "UPDATE archive SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False), now, did)
    )
    conn.commit()
    conn.close()
    data['id'] = did
    _log(request,'archive-app','update','dossier',did,
         label=data.get('mahkama','')+' — عدد: '+str(data.get('adad_qadiya','—'))+' — '+data.get('manoub',''),
         details={'modifications': changes})
    return jsonify(data)


@app.route('/api/archive/<int:did>', methods=['DELETE'])
def api_delete(did):
    conn = get_db()
    row = conn.execute('SELECT data FROM archive WHERE id = ?', (did,)).fetchone()
    ddata = json.loads(row['data']) if row and row['data'] else {}
    conn.execute("DELETE FROM archive WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    _log(request,'archive-app','delete','dossier',did,
         label=ddata.get('mahkama','')+' — عدد: '+str(ddata.get('adad_qadiya','—'))+' — '+ddata.get('manoub',''),
         details={'adad_qadiya':ddata.get('adad_qadiya',''),'mahkama':ddata.get('mahkama','')})
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5004))
    app.run(host='0.0.0.0', port=port, debug=False)
