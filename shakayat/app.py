#!/usr/bin/env python3
"""
الشكايات — Flask + SQLite
Port 5011
"""
from flask import Flask, render_template, request, redirect, flash, send_from_directory, jsonify, abort
import sqlite3, os, json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'shakayat-2026')
DB_PATH      = os.environ.get('DB_PATH', '/data/shakayat.db')
UPLOAD_FOLDER= os.environ.get('UPLOAD_FOLDER', '/data/uploads')
BASE_PATH    = os.environ.get('BASE_PATH', '')
NC_URL       = os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')

ALLOWED_EXT = {'pdf','doc','docx','jpg','jpeg','png','xls','xlsx','zip','rar'}

def allowed(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXT

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shakayat (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            manoub          TEXT NOT NULL DEFAULT '',
            ded             TEXT NOT NULL DEFAULT '',
            mahkama         TEXT NOT NULL DEFAULT '',
            adad_dabt       TEXT NOT NULL DEFAULT '',
            tarikh_dabt     TEXT NOT NULL DEFAULT '',
            mawdu3          TEXT NOT NULL DEFAULT '',
            jiha            TEXT NOT NULL DEFAULT '',
            mulahazat       TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS fichiers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shakiya_id  INTEGER NOT NULL REFERENCES shakayat(id) ON DELETE CASCADE,
            nom         TEXT NOT NULL,
            filename    TEXT NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit(); conn.close()

def get_user():
    for k in request.cookies:
        if k.startswith('nc_') or k.startswith('oc_'):
            return True
    return request.host in ('localhost', '127.0.0.1')

@app.context_processor
def ctx():
    return {'BASE': BASE_PATH}

# ── LISTE ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if not get_user(): return redirect(f"{NC_URL}/login")
    q = request.args.get('q','').strip()
    conn = get_db()
    if q:
        rows = conn.execute("""
            SELECT * FROM shakayat
            WHERE manoub LIKE ? OR ded LIKE ? OR mahkama LIKE ?
               OR adad_dabt LIKE ? OR mawdu3 LIKE ? OR jiha LIKE ?
            ORDER BY id DESC
        """, tuple([f'%{q}%']*6)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM shakayat ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('index.html', rows=rows, q=q)

# ── CRÉER ─────────────────────────────────────────────────────────────────────
@app.route('/new', methods=['GET','POST'])
def new_shakiya():
    if not get_user(): return redirect(f"{NC_URL}/login")
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        cur = conn.execute("""
            INSERT INTO shakayat (manoub,ded,mahkama,adad_dabt,tarikh_dabt,mawdu3,jiha,mulahazat)
            VALUES (?,?,?,?,?,?,?,?)
        """, (f.get('manoub','').strip(), f.get('ded','').strip(),
              f.get('mahkama','').strip(), f.get('adad_dabt','').strip(),
              f.get('tarikh_dabt','').strip(), f.get('mawdu3','').strip(),
              f.get('jiha','').strip(), f.get('mulahazat','').strip()))
        sid = cur.lastrowid
        # Fichiers
        for file in request.files.getlist('fichiers'):
            if file and file.filename and allowed(file.filename):
                fn = f"{sid}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
                file.save(os.path.join(UPLOAD_FOLDER, fn))
                conn.execute("INSERT INTO fichiers (shakiya_id,nom,filename) VALUES (?,?,?)",
                             (sid, file.filename, fn))
        conn.commit(); conn.close()
        flash('✅ تم إضافة الشكاية', 'success')
        return redirect(f"{BASE_PATH}/")
    return render_template('form.html', s=None, fichiers=[])

# ── DÉTAIL ────────────────────────────────────────────────────────────────────
@app.route('/shakiya/<int:sid>')
def detail(sid):
    if not get_user(): return redirect(f"{NC_URL}/login")
    conn = get_db()
    s = conn.execute("SELECT * FROM shakayat WHERE id=?", (sid,)).fetchone()
    fichiers = conn.execute("SELECT * FROM fichiers WHERE shakiya_id=? ORDER BY id", (sid,)).fetchall()
    conn.close()
    if not s: return redirect(f"{BASE_PATH}/")
    return render_template('detail.html', s=s, fichiers=fichiers)

# ── MODIFIER ──────────────────────────────────────────────────────────────────
@app.route('/shakiya/<int:sid>/edit', methods=['GET','POST'])
def edit_shakiya(sid):
    if not get_user(): return redirect(f"{NC_URL}/login")
    conn = get_db()
    s = conn.execute("SELECT * FROM shakayat WHERE id=?", (sid,)).fetchone()
    fichiers = conn.execute("SELECT * FROM fichiers WHERE shakiya_id=? ORDER BY id", (sid,)).fetchall()
    if not s: conn.close(); return redirect(f"{BASE_PATH}/")
    if request.method == 'POST':
        f = request.form
        conn.execute("""
            UPDATE shakayat SET manoub=?,ded=?,mahkama=?,adad_dabt=?,tarikh_dabt=?,
                mawdu3=?,jiha=?,mulahazat=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (f.get('manoub','').strip(), f.get('ded','').strip(),
              f.get('mahkama','').strip(), f.get('adad_dabt','').strip(),
              f.get('tarikh_dabt','').strip(), f.get('mawdu3','').strip(),
              f.get('jiha','').strip(), f.get('mulahazat','').strip(), sid))
        for file in request.files.getlist('fichiers'):
            if file and file.filename and allowed(file.filename):
                fn = f"{sid}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
                file.save(os.path.join(UPLOAD_FOLDER, fn))
                conn.execute("INSERT INTO fichiers (shakiya_id,nom,filename) VALUES (?,?,?)",
                             (sid, file.filename, fn))
        conn.commit(); conn.close()
        flash('✅ تم تحديث الشكاية', 'success')
        return redirect(f"{BASE_PATH}/shakiya/{sid}")
    conn.close()
    return render_template('form.html', s=s, fichiers=fichiers)

# ── SUPPRIMER FICHIER ─────────────────────────────────────────────────────────
@app.route('/fichier/<int:fid>/delete', methods=['POST'])
def delete_fichier(fid):
    if not get_user(): abort(403)
    conn = get_db()
    f = conn.execute("SELECT * FROM fichiers WHERE id=?", (fid,)).fetchone()
    if f:
        try: os.remove(os.path.join(UPLOAD_FOLDER, f['filename']))
        except: pass
        conn.execute("DELETE FROM fichiers WHERE id=?", (fid,))
        conn.commit()
    sid = f['shakiya_id'] if f else 0
    conn.close()
    return redirect(f"{BASE_PATH}/shakiya/{sid}/edit")

# ── TÉLÉCHARGER FICHIER ───────────────────────────────────────────────────────
@app.route('/fichier/<int:fid>/download')
def download_fichier(fid):
    if not get_user(): abort(403)
    conn = get_db()
    f = conn.execute("SELECT * FROM fichiers WHERE id=?", (fid,)).fetchone()
    conn.close()
    if not f: abort(404)
    return send_from_directory(UPLOAD_FOLDER, f['filename'], as_attachment=True, download_name=f['nom'])

# ── SUPPRIMER SHIKAYA ─────────────────────────────────────────────────────────
@app.route('/shakiya/<int:sid>/delete', methods=['POST'])
def delete_shakiya(sid):
    if not get_user(): abort(403)
    conn = get_db()
    fichiers = conn.execute("SELECT filename FROM fichiers WHERE shakiya_id=?", (sid,)).fetchall()
    for f in fichiers:
        try: os.remove(os.path.join(UPLOAD_FOLDER, f['filename']))
        except: pass
    conn.execute("DELETE FROM shakayat WHERE id=?", (sid,))
    conn.commit(); conn.close()
    flash('تم حذف الشكاية', 'warning')
    return redirect(f"{BASE_PATH}/")

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5011)), debug=False)
