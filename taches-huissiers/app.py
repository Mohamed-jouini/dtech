#!/usr/bin/env python3
"""
المهام الموكلة للعدول — Tâches des huissiers
Flask + SQLite
"""
from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)

DB_PATH = os.environ.get('DB_PATH', 'taches.db')
HUISSIERS_DB_PATH = os.environ.get('HUISSIERS_DB_PATH', '')
CLIENTS_DB_PATH = os.environ.get('CLIENTS_DB_PATH', '')
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
        CREATE TABLE IF NOT EXISTS taches (
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

@app.route('/tache/new')
def new_tache():
    return render_template('form.html', tache_id=None)

@app.route('/tache/<int:tid>')
def edit_tache(tid):
    return render_template('form.html', tache_id=tid)


# ============================================================
# API
# ============================================================

@app.route('/api/huissiers', methods=['GET'])
def api_huissiers():
    """Liste des huissiers depuis la base huissiers."""
    if not HUISSIERS_DB_PATH or not os.path.exists(HUISSIERS_DB_PATH):
        return jsonify([])
    try:
        conn = sqlite3.connect(HUISSIERS_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM huissiers ORDER BY updated_at DESC").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = json.loads(r['data']) if r['data'] else {}
            d['id'] = r['id']
            results.append(d)
        return jsonify(results)
    except Exception:
        return jsonify([])


@app.route('/api/clients', methods=['GET'])
def api_clients():
    """Liste des dossiers clients depuis la base fiche-client."""
    if not CLIENTS_DB_PATH or not os.path.exists(CLIENTS_DB_PATH):
        return jsonify([])
    try:
        conn = sqlite3.connect(CLIENTS_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM clients ORDER BY updated_at DESC").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = json.loads(r['data']) if r['data'] else {}
            d['id'] = r['id']
            results.append(d)
        return jsonify(results)
    except Exception:
        return jsonify([])


@app.route('/api/taches', methods=['GET'])
def api_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM taches ORDER BY updated_at DESC").fetchall()
    conn.close()
    search = request.args.get('search', '').strip().lower()
    hala = request.args.get('hala', '').strip()

    # Charger les folder_url des clients
    client_folders = {}
    if CLIENTS_DB_PATH and os.path.exists(CLIENTS_DB_PATH):
        try:
            cconn = sqlite3.connect(CLIENTS_DB_PATH)
            cconn.row_factory = sqlite3.Row
            for cr in cconn.execute("SELECT id, data FROM clients").fetchall():
                cd = json.loads(cr['data']) if cr['data'] else {}
                client_folders[cr['id']] = cd.get('folder_url', '')
            cconn.close()
        except Exception:
            pass

    results = []
    for r in rows:
        d = json.loads(r['data']) if r['data'] else {}
        d['id'] = r['id']
        d['created_at'] = r['created_at']
        d['updated_at'] = r['updated_at']
        # Ajouter folder_url si le client a un dossier
        if d.get('client_id') and int(d['client_id']) in client_folders:
            d['folder_url'] = client_folders[int(d['client_id'])]
        if search:
            searchable = json.dumps(d, ensure_ascii=False).lower()
            if search not in searchable:
                continue
        if hala and d.get('hala', '') != hala:
            continue
        results.append(d)
    return jsonify(results)


@app.route('/api/taches', methods=['POST'])
def api_create():
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO taches (data, created_at, updated_at) VALUES (?, ?, ?)",
        (json.dumps(data, ensure_ascii=False), now, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    data['id'] = new_id
    return jsonify(data), 201


@app.route('/api/taches/<int:tid>', methods=['GET'])
def api_get(tid):
    conn = get_db()
    row = conn.execute("SELECT * FROM taches WHERE id = ?", (tid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = json.loads(row['data']) if row['data'] else {}
    d['id'] = row['id']
    return jsonify(d)


@app.route('/api/taches/<int:tid>', methods=['PUT'])
def api_update(tid):
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE taches SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False), now, tid)
    )
    conn.commit()
    conn.close()
    data['id'] = tid
    return jsonify(data)


@app.route('/api/taches/<int:tid>', methods=['DELETE'])
def api_delete(tid):
    conn = get_db()
    conn.execute("DELETE FROM taches WHERE id = ?", (tid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5003))
    app.run(host='0.0.0.0', port=port, debug=False)
