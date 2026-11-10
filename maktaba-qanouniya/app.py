#!/usr/bin/env python3
"""
المكتبة القانونية — Flask + SQLite + OCR Tesseract
cabinet.mwj-lawyers.com — port 5006
"""
# ─── AUDIT LOGGING ───────────────────────────────────────────────
import os as _os
_os.environ.setdefault("AUDIT_URL", "http://audit-app:5010/api/log")
try:
    from audit_client import log_action as _log
except ImportError:
    def _log(*a, **k): pass
# ─────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, jsonify, flash, send_from_directory, abort
import sqlite3, os, json, uuid, threading
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'maktaba-secret-2024')

DB_PATH      = os.environ.get('DB_PATH', '/data/maktaba.db')
UPLOAD_DIR   = os.environ.get('UPLOAD_DIR', '/data/uploads')
BASE_PATH    = os.environ.get('BASE_PATH', '')
NEXTCLOUD_URL= os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')
OCR_LANG     = os.environ.get('OCR_LANG', 'ara')

ALLOWED_EXT  = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'tif', 'bmp'}
MAX_FILE_MB  = 50

CATEGORIES   = ['مدني', 'جزائي']
INSTANCES    = ['ابتدائية', 'استئناف', 'تعقيب']


# ─── PROTECTION NEXTCLOUD ─────────────────────────────────────────────────────
@app.before_request
def require_nextcloud():
    if not NEXTCLOUD_URL:
        return
    if request.path.startswith(('/api/', '/static/', '/file/')):
        return
    ref  = request.headers.get('Referer', '')
    dest = request.headers.get('Sec-Fetch-Dest', '')
    site = request.headers.get('Sec-Fetch-Site', '')
    if dest == 'iframe' or site == 'same-origin':
        return
    if ref and (NEXTCLOUD_URL in ref or request.host in ref):
        return
    if request.content_type and 'json' in request.content_type:
        return
    if any(k.startswith(('nc_', 'oc_')) for k in request.cookies):
        return
    return ('<html><body style="font-family:Arial;display:flex;justify-content:center;'
            'align-items:center;height:100vh;direction:rtl"><div style="text-align:center">'
            '<h1>🔒</h1><p>يرجى الدخول عبر Nextcloud</p></div></body></html>'), 403

@app.after_request
def add_headers(r):
    csp = f"frame-ancestors 'self' {NEXTCLOUD_URL}" if NEXTCLOUD_URL else "frame-ancestors *"
    r.headers['Content-Security-Policy'] = csp
    return r

@app.context_processor
def inject_globals():
    return {'BASE': BASE_PATH, 'CATEGORIES': CATEGORIES, 'INSTANCES': INSTANCES}


# ─── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            titre      TEXT NOT NULL DEFAULT '',
            categorie  TEXT NOT NULL DEFAULT 'مدني',
            instance   TEXT NOT NULL DEFAULT '',
            adad       TEXT NOT NULL DEFAULT '',
            date_doc   TEXT NOT NULL DEFAULT '',
            filename   TEXT NOT NULL DEFAULT '',
            ext        TEXT NOT NULL DEFAULT '',
            ocr_text   TEXT NOT NULL DEFAULT '',
            ocr_done   INTEGER NOT NULL DEFAULT 0,
            nb_pages   INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Migration si table existante sans adad
    cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if 'adad' not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN adad TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()


# ─── OCR ──────────────────────────────────────────────────────────────────────
def run_ocr(article_id, filepath, ext):
    """Lancer l'OCR en arrière-plan."""
    try:
        import pytesseract
        from PIL import Image

        texts = []

        if ext == 'pdf':
            from pdf2image import convert_from_path
            pages = convert_from_path(filepath, dpi=200)
            nb_pages = len(pages)
            for page in pages:
                text = pytesseract.image_to_string(page, lang=OCR_LANG, config='--psm 3')
                texts.append(text)
        else:
            img = Image.open(filepath)
            text = pytesseract.image_to_string(img, lang=OCR_LANG, config='--psm 3')
            texts.append(text)
            nb_pages = 1

        ocr_text = '\n\n--- صفحة ---\n\n'.join(texts)
        conn = get_db()
        conn.execute(
            "UPDATE articles SET ocr_text=?, ocr_done=1, nb_pages=?, updated_at=datetime('now') WHERE id=?",
            (ocr_text, nb_pages, article_id)
        )
        conn.commit()
        conn.close()
        print(f"✅ OCR terminé article {article_id} ({nb_pages} page(s))")
    except Exception as e:
        print(f"❌ OCR erreur article {article_id}: {e}")
        conn = get_db()
        conn.execute("UPDATE articles SET ocr_done=2 WHERE id=?", (article_id,))
        conn.commit()
        conn.close()


# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    cat  = request.args.get('cat', 'مدني')
    q    = request.args.get('q', '').strip()
    conn = get_db()
    if q:
        rows = conn.execute("""
            SELECT * FROM articles
            WHERE categorie=? AND (titre LIKE ? OR instance LIKE ? OR ocr_text LIKE ?)
            ORDER BY date_doc DESC, updated_at DESC
        """, (cat, f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM articles WHERE categorie=? ORDER BY date_doc DESC, updated_at DESC",
            (cat,)
        ).fetchall()
    counts = {c: conn.execute(
        "SELECT COUNT(*) FROM articles WHERE categorie=?", (c,)
    ).fetchone()[0] for c in CATEGORIES}
    conn.close()
    return render_template('index.html', rows=rows, active_cat=cat,
                           counts=counts, q=q)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        f = request.files.get('fichier')
        if not f or f.filename == '':
            flash('يرجى اختيار ملف', 'error')
            return redirect(f"{BASE_PATH}/upload")
        ext = f.filename.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            flash('نوع الملف غير مدعوم (PDF، PNG، JPG، TIFF)', 'error')
            return redirect(f"{BASE_PATH}/upload")

        titre     = request.form.get('titre', '').strip() or secure_filename(f.filename)
        categorie = request.form.get('categorie', 'مدني')
        instance  = request.form.get('instance', '')
        adad      = request.form.get('adad', '').strip()
        date_doc  = request.form.get('date_doc', '')

        uid      = uuid.uuid4().hex[:10]
        filename = f"{uid}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        f.save(filepath)

        conn = get_db()
        cur = conn.execute("""
            INSERT INTO articles (titre, categorie, instance, adad, date_doc, filename, ext)
            VALUES (?,?,?,?,?,?,?)
        """, (titre, categorie, instance, adad, date_doc, filename, ext))
        article_id = cur.lastrowid
        conn.commit()
        conn.close()
        _log(request,'maktaba-qanouniya','upload','article',article_id,
             label=titre+' ('+categorie+')',
             details={'categorie':categorie,'instance':instance,'adad':adad})

        # OCR en arrière-plan
        t = threading.Thread(target=run_ocr, args=(article_id, filepath, ext), daemon=True)
        t.start()

        flash(f'تم رفع الملف بنجاح — جارٍ تحليل OCR في الخلفية', 'success')
        return redirect(f"{BASE_PATH}/?cat={categorie}")

    return render_template('upload.html')


@app.route('/view/<int:aid>')
def view_article(aid):
    conn = get_db()
    art = conn.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not art:
        abort(404)
    return render_template('view.html', art=art)


@app.route('/edit/<int:aid>', methods=['GET', 'POST'])
def edit_article(aid):
    conn = get_db()
    if request.method == 'POST':
        titre    = request.form.get('titre', '').strip()
        categorie= request.form.get('categorie', 'مدني')
        instance = request.form.get('instance', '')
        adad     = request.form.get('adad', '').strip()
        date_doc = request.form.get('date_doc', '')
        conn.execute("""
            UPDATE articles SET titre=?,categorie=?,instance=?,adad=?,date_doc=?,
            updated_at=datetime('now') WHERE id=?
        """, (titre, categorie, instance, adad, date_doc, aid))
        conn.commit()
        conn.close()
        _log(request,'maktaba-qanouniya','update','article',aid,
             label=titre+' ('+categorie+')',
             details={'categorie':categorie,'instance':instance,'adad':adad})
        flash('تم تحديث المقال بنجاح', 'success')
        return redirect(f"{BASE_PATH}/?cat={categorie}")
    art = conn.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not art:
        abort(404)
    return render_template('edit.html', art=art)


@app.route('/delete/<int:aid>', methods=['POST'])
def delete_article(aid):
    conn = get_db()
    art = conn.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    if art:
        try:
            os.remove(os.path.join(UPLOAD_DIR, art['filename']))
        except Exception:
            pass
        conn.execute("DELETE FROM articles WHERE id=?", (aid,))
        conn.commit()
        cat = art['categorie']
        _log(request,'maktaba-qanouniya','delete','article',aid,
             label=art['titre']+' ('+art['categorie']+')',
             details={'categorie':art['categorie'],'instance':art['instance'],'adad':art['adad']})
    else:
        cat = 'مدني'
    conn.close()
    flash('تم حذف المقال', 'warning')
    return redirect(f"{BASE_PATH}/?cat={cat}")


@app.route('/file/<filename>')
def serve_file(filename):
    """Servir le fichier PDF/image directement."""
    safe = secure_filename(filename)
    if not os.path.exists(os.path.join(UPLOAD_DIR, safe)):
        abort(404)
    return send_from_directory(UPLOAD_DIR, safe)


@app.route('/api/ocr-status/<int:aid>')
def api_ocr_status(aid):
    conn = get_db()
    row = conn.execute("SELECT ocr_done, nb_pages FROM articles WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'status': 'not_found'}), 404
    status = {0: 'pending', 1: 'done', 2: 'error'}.get(row['ocr_done'], 'pending')
    return jsonify({'status': status, 'nb_pages': row['nb_pages']})


@app.route('/api/reocr/<int:aid>', methods=['POST'])
def api_reocr(aid):
    """Relancer l'OCR pour un article."""
    conn = get_db()
    art = conn.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not art:
        return jsonify({'error': 'not found'}), 404
    filepath = os.path.join(UPLOAD_DIR, art['filename'])
    t = threading.Thread(target=run_ocr, args=(aid, filepath, art['ext']), daemon=True)
    t.start()
    conn = get_db()
    conn.execute("UPDATE articles SET ocr_done=0 WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5006)), debug=False)

init_db()
