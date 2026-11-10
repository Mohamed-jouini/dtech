#!/usr/bin/env python3
"""
المعطيات الشخصية للحرفاء
Port 5009 — Auth Nextcloud
"""
from flask import Flask, render_template, request, redirect, flash, jsonify
import sqlite3, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clients-perso-2026')
DB_PATH   = os.environ.get('DB_PATH', '/data/clients_perso.db')
BASE_PATH = os.environ.get('BASE_PATH', '')
NC_URL    = os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')
FICHE_URL = os.environ.get('FICHE_URL', '/fiche-client')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            -- المنوب
            houwiya         TEXT NOT NULL DEFAULT '',
            num_houwiya     TEXT NOT NULL DEFAULT '',
            adresse         TEXT NOT NULL DEFAULT '',
            telephone       TEXT NOT NULL DEFAULT '',
            email           TEXT NOT NULL DEFAULT '',
            -- جهة الاتصال 1
            contact1_nom    TEXT NOT NULL DEFAULT '',
            contact1_tel    TEXT NOT NULL DEFAULT '',
            -- جهة الاتصال 2
            contact2_nom    TEXT NOT NULL DEFAULT '',
            contact2_tel    TEXT NOT NULL DEFAULT '',
            -- جهة الاتصال 3
            contact3_nom    TEXT NOT NULL DEFAULT '',
            contact3_tel    TEXT NOT NULL DEFAULT '',
            -- Liaison fiche-client
            fiche_client_id TEXT NOT NULL DEFAULT '',
            -- Méta
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit(); conn.close()

def get_user():
    for k in request.cookies:
        if k.startswith('nc_') or k.startswith('oc_'):
            return True
    ref = request.headers.get('Referer','')
    if NC_URL in ref or request.host in ('localhost','127.0.0.1'):
        return True
    return False

@app.context_processor
def ctx():
    return {'BASE': BASE_PATH, 'FICHE_URL': FICHE_URL}

# ─── LISTE ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if not get_user(): return redirect(f"{NC_URL}/login")
    q = request.args.get('q','').strip()
    conn = get_db()
    if q:
        rows = conn.execute("""
            SELECT * FROM clients
            WHERE houwiya LIKE ? OR num_houwiya LIKE ? OR telephone LIKE ?
               OR contact1_nom LIKE ? OR contact2_nom LIKE ? OR contact3_nom LIKE ?
            ORDER BY updated_at DESC
        """, tuple([f'%{q}%']*6)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clients ORDER BY updated_at DESC").fetchall()
    conn.close()
    return render_template('index.html', clients=rows, q=q)

# ─── NOUVELLE FICHE ───────────────────────────────────────────────────────────
@app.route('/new', methods=['GET','POST'])
def new_client():
    if not get_user(): return redirect(f"{NC_URL}/login")
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        conn.execute("""
            INSERT INTO clients (
                houwiya, num_houwiya, adresse, telephone, email,
                contact1_nom, contact1_tel,
                contact2_nom, contact2_tel,
                contact3_nom, contact3_tel,
                fiche_client_id, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            f.get('houwiya','').strip(), f.get('num_houwiya','').strip(),
            f.get('adresse','').strip(), f.get('telephone','').strip(),
            f.get('email','').strip(),
            f.get('contact1_nom','').strip(), f.get('contact1_tel','').strip(),
            f.get('contact2_nom','').strip(), f.get('contact2_tel','').strip(),
            f.get('contact3_nom','').strip(), f.get('contact3_tel','').strip(),
            f.get('fiche_client_id','').strip(), f.get('notes','').strip()
        ))
        conn.commit(); conn.close()
        flash('تم إضافة الملف بنجاح ✅', 'success')
        return redirect(f"{BASE_PATH}/")
    return render_template('form.html', client=None)

# ─── FICHE DÉTAIL ─────────────────────────────────────────────────────────────
@app.route('/client/<int:cid>')
def detail(cid):
    if not get_user(): return redirect(f"{NC_URL}/login")
    conn = get_db()
    c = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not c: return redirect(f"{BASE_PATH}/")
    return render_template('detail.html', client=c)

# ─── MODIFIER ─────────────────────────────────────────────────────────────────
@app.route('/client/<int:cid>/edit', methods=['GET','POST'])
def edit_client(cid):
    if not get_user(): return redirect(f"{NC_URL}/login")
    conn = get_db()
    c = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    if not c: conn.close(); return redirect(f"{BASE_PATH}/")
    if request.method == 'POST':
        f = request.form
        conn.execute("""
            UPDATE clients SET
                houwiya=?, num_houwiya=?, adresse=?, telephone=?, email=?,
                contact1_nom=?, contact1_tel=?,
                contact2_nom=?, contact2_tel=?,
                contact3_nom=?, contact3_tel=?,
                fiche_client_id=?, notes=?,
                updated_at=datetime('now','localtime')
            WHERE id=?
        """, (
            f.get('houwiya','').strip(), f.get('num_houwiya','').strip(),
            f.get('adresse','').strip(), f.get('telephone','').strip(),
            f.get('email','').strip(),
            f.get('contact1_nom','').strip(), f.get('contact1_tel','').strip(),
            f.get('contact2_nom','').strip(), f.get('contact2_tel','').strip(),
            f.get('contact3_nom','').strip(), f.get('contact3_tel','').strip(),
            f.get('fiche_client_id','').strip(), f.get('notes','').strip(),
            cid
        ))
        conn.commit(); conn.close()
        flash('تم تحديث الملف ✅', 'success')
        return redirect(f"{BASE_PATH}/client/{cid}")
    conn.close()
    return render_template('form.html', client=c)

# ─── SUPPRIMER ────────────────────────────────────────────────────────────────
@app.route('/client/<int:cid>/delete', methods=['POST'])
def delete_client(cid):
    if not get_user(): return redirect(f"{NC_URL}/login")
    conn = get_db()
    conn.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit(); conn.close()
    flash('تم حذف الملف', 'warning')
    return redirect(f"{BASE_PATH}/")

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5009)), debug=False)

init_db()
