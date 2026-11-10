#!/usr/bin/env python3
"""
ملف المنوب والقضية — Flask + SQLite
Supporte plusieurs طرف ضد et plusieurs محامي مسؤول
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

DB_PATH = os.environ.get('DB_PATH', 'clients.db')
JALSAT_DB_PATH = os.environ.get('JALSAT_DB_PATH', '')
NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL', '')
BASE_PATH = os.environ.get('BASE_PATH', '')
AGENDA_BASE = os.environ.get('AGENDA_BASE', '/agenda-jalsat')


@app.context_processor
def inject_base():
    return {'BASE': BASE_PATH, 'AGENDA_BASE': AGENDA_BASE}


@app.before_request
def check_access():
    """Bloquer l'accès direct — autoriser depuis Nextcloud et navigation interne."""
    if not NEXTCLOUD_URL:
        return

    # Toujours autoriser les appels API
    if request.path.startswith('/api/'):
        return

    referer = request.headers.get('Referer', '')
    sec_fetch_dest = request.headers.get('Sec-Fetch-Dest', '')
    sec_fetch_site = request.headers.get('Sec-Fetch-Site', '')

    # iframe → OK
    if sec_fetch_dest == 'iframe':
        return

    # Navigation interne dans l'iframe (same-origin ou cross-site avec referer)
    if sec_fetch_site == 'same-origin':
        return

    # Referer contient le domaine Nextcloud ou l'app elle-même → OK
    if referer and (NEXTCLOUD_URL in referer or request.host in referer):
        return

    # Requête avec content-type JSON → OK
    if request.content_type and 'json' in request.content_type:
        return

    # Sinon → accès refusé
    return '''
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head><meta charset="UTF-8"><title>غير مسموح</title>
    <style>
      body { font-family: Arial, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; direction: rtl; }
      .box { background: white; padding: 40px; border-radius: 12px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.1); max-width: 400px; }
      h1 { color: #dc3545; font-size: 48px; margin-bottom: 10px; }
      p { color: #333; font-size: 16px; margin-bottom: 8px; }
      .hint { color: #888; font-size: 13px; }
    </style></head>
    <body><div class="box">
      <h1>🔒</h1>
      <p>غير مسموح بالوصول المباشر</p>
      <p class="hint">يرجى الدخول عبر Nextcloud</p>
    </div></body></html>
    ''', 403


@app.after_request
def add_headers(response):
    """Autoriser l'affichage dans un iframe Nextcloud."""
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
        CREATE TABLE IF NOT EXISTS clients (
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

@app.route('/client/new')
def new_client():
    return render_template('form.html', client_id=None)

@app.route('/client/<int:client_id>')
def edit_client(client_id):
    return render_template('form.html', client_id=client_id)

@app.route('/client/<int:client_id>/print')
def print_client(client_id):
    return render_template('print.html', client_id=client_id)


# ============================================================
# API
# ============================================================

@app.route('/api/clients', methods=['GET'])
def api_list():
    conn = get_db()
    search = request.args.get('search', '').strip()
    rows = conn.execute("SELECT * FROM clients ORDER BY updated_at DESC").fetchall()
    conn.close()

    results = []
    for r in rows:
        d = json.loads(r['data']) if r['data'] else {}
        d['id'] = r['id']
        d['created_at'] = r['created_at']
        d['updated_at'] = r['updated_at']
        if search:
            searchable = json.dumps(d, ensure_ascii=False).lower()
            if search.lower() not in searchable:
                continue
        results.append(d)
    return jsonify(results)


@app.route('/api/clients', methods=['POST'])
def api_create():
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO clients (data, created_at, updated_at) VALUES (?, ?, ?)",
        (json.dumps(data, ensure_ascii=False), now, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    data['id'] = new_id
    _log(request, 'fiche-client', 'create', 'client', new_id,
         label=data.get('client_nom','')+' — عدد: '+str(data.get('raqm_qadiya','—')),
         details={'raqm_qadiya': data.get('raqm_qadiya',''), 'client_nom': data.get('client_nom','')})
    return jsonify(data), 201


@app.route('/api/clients/<int:cid>', methods=['GET'])
def api_get(cid):
    conn = get_db()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = json.loads(row['data']) if row['data'] else {}
    d['id'] = row['id']
    return jsonify(d)


@app.route('/api/clients/<int:cid>', methods=['PUT'])
def api_update(cid):
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    # Lire ancienne valeur
    old_row = conn.execute('SELECT data FROM clients WHERE id = ?', (cid,)).fetchone()
    old_data = json.loads(old_row['data']) if old_row and old_row['data'] else {}
    # Détecter les champs modifiés
    skip = {'created_at','updated_at','id','extra_clients','extra_adverses','amal_list'}
    changes = {k: {'avant': old_data.get(k,''), 'après': data.get(k,'')}
               for k in data
               if str(data.get(k,'')) != str(old_data.get(k,'')) and k not in skip}
    conn.execute(
        "UPDATE clients SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False), now, cid)
    )
    conn.commit()
    conn.close()
    data['id'] = cid
    _log(request, 'fiche-client', 'update', 'client', cid,
         label=data.get('client_nom','')+' — عدد: '+str(data.get('raqm_qadiya','—')),
         details={'modifications': changes})
    return jsonify(data)


@app.route('/api/clients/<int:cid>', methods=['DELETE'])
def api_delete(cid):
    conn = get_db()
    # Lire les données avant suppression
    row = conn.execute("SELECT data FROM clients WHERE id = ?", (cid,)).fetchone()
    cdata = json.loads(row['data']) if row and row['data'] else {}
    conn.execute("DELETE FROM clients WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    _log(request, 'fiche-client', 'delete', 'client', cid,
         label=cdata.get('client_nom','')+' — عدد: '+str(cdata.get('raqm_qadiya','—')),
         details={'raqm_qadiya':cdata.get('raqm_qadiya',''),'client_nom':cdata.get('client_nom','')})
    return jsonify({'ok': True})


@app.route('/api/clients/<int:cid>/jalsat', methods=['GET'])
def api_client_jalsat(cid):
    """الجلسات المرتبطة بهذا الملف"""
    if not JALSAT_DB_PATH or not os.path.exists(JALSAT_DB_PATH):
        return jsonify([])
    try:
        conn = sqlite3.connect(JALSAT_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM jalsat WHERE client_id = ? ORDER BY jalsa ASC", (cid,)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
