#!/usr/bin/env python3
"""
أجندة الجلسات — Agenda des audiences
Flask + SQLite
"""
from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import json
from datetime import datetime, date


# ─── AUDIT LOGGING ───────────────────────────────────────────────
import os as _os
_os.environ.setdefault("AUDIT_URL", "http://audit-app:5010/api/log")
try:
    from audit_client import log_action as _log
except ImportError:
    def _log(*a, **k): pass
# ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

DB_PATH = os.environ.get('DB_PATH', 'jalsat.db')
CLIENTS_DB_PATH = os.environ.get('CLIENTS_DB_PATH', '')
TAWER_DB_PATH = os.environ.get('TAWER_DB_PATH', '')
NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL', '')
BASE_PATH = os.environ.get('BASE_PATH', '')
FICHE_CLIENT_BASE = os.environ.get('FICHE_CLIENT_BASE', '/fiche-client')

TAWER_MAP = {'جارية': 'جارية', 'تصريح': 'تصريح', 'محكوم فيها': 'محكوم فيها'}


def sync_to_tawer(values):
    """Sync jalsa to tawer-qadaya. Prend toujours le طور de la ligne avec la date الجلسة la plus récente."""
    if not TAWER_DB_PATH or not os.path.exists(TAWER_DB_PATH):
        return
    adad = values.get('adad_qadiya', '')
    if not adad:
        return
    try:
        # Trouver le طور de la ligne avec la date la plus récente pour cette affaire
        jalsat_conn = get_db()
        latest = jalsat_conn.execute(
            "SELECT tawer, mahkama, daira, manoub, ded, jalsa, gharad FROM jalsat WHERE adad_qadiya = ? AND tawer != '' ORDER BY jalsa DESC LIMIT 1",
            (adad,)
        ).fetchone()
        jalsat_conn.close()

        if not latest or not latest['tawer']:
            return

        tawer = latest['tawer']
        if tawer not in TAWER_MAP:
            return

        # Build mandubeen/addad as JSON arrays
        manoub = latest['manoub'] or values.get('manoub', '')
        ded = latest['ded'] or values.get('ded', '')
        mandubeen = json.dumps([{'nom': manoub, 'sifa': ''}], ensure_ascii=False) if manoub else '[]'
        addad_json = json.dumps([{'nom': ded, 'sifa': ''}], ensure_ascii=False) if ded else '[]'

        conn = sqlite3.connect(TAWER_DB_PATH)
        conn.row_factory = sqlite3.Row

        existing = conn.execute("SELECT id FROM qadaya WHERE adad = ?", (adad,)).fetchone()

        if existing:
            conn.execute("""UPDATE qadaya SET mahkama=?, daira=?, mandubeen=?, addad=?,
                tarikh=?, gharad=?, tawar=?, updated_at=datetime('now') WHERE id=?""",
                (latest['mahkama'] or '', latest['daira'] or '', mandubeen, addad_json,
                 latest['jalsa'] or '', latest['gharad'] or '', tawer, existing['id']))
        else:
            conn.execute("""INSERT INTO qadaya (mahkama, adad, daira, mandubeen, addad, tarikh, mawdu3, gharad, mulahazat, tawar)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (latest['mahkama'] or '', adad, latest['daira'] or '', mandubeen, addad_json,
                 latest['jalsa'] or '', '', latest['gharad'] or '', '', tawer))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Sync to tawer error: {e}")


@app.context_processor
def inject_base():
    return {'BASE': BASE_PATH, 'FICHE_BASE': FICHE_CLIENT_BASE}


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
        CREATE TABLE IF NOT EXISTS jalsat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER DEFAULT 0,
            mahkama TEXT DEFAULT '',
            adad_qadiya TEXT DEFAULT '',
            daira TEXT DEFAULT '',
            manoub TEXT DEFAULT '',
            mustafid TEXT DEFAULT '',
            ded TEXT DEFAULT '',
            jalsa TEXT DEFAULT '',
            gharad TEXT DEFAULT '',
            jalsa_moqbila TEXT DEFAULT '',
            gharad_jalsa_moqbila TEXT DEFAULT '',
            tawer TEXT DEFAULT '',
            tarikh_akhir_ajal TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    ''')
    # Migration colonne mustafid
    cols = [r[1] for r in conn.execute('PRAGMA table_info(jalsat)').fetchall()]
    for col in ('mustafid', 'tawer', 'tarikh_akhir_ajal'):
        if col not in cols:
            conn.execute("ALTER TABLE jalsat ADD COLUMN %s TEXT DEFAULT ''" % col)
    conn.commit()
    conn.close()


FIELDS = ['client_id', 'mahkama', 'adad_qadiya', 'daira', 'manoub', 'mustafid', 'ded', 'jalsa', 'gharad', 'jalsa_moqbila', 'gharad_jalsa_moqbila', 'tawer', 'tarikh_akhir_ajal']


# ============================================================
# PAGES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/jalsa/new')
def new_jalsa():
    return render_template('form.html', jalsa_id=None)

@app.route('/jalsa/<int:jalsa_id>')
def edit_jalsa(jalsa_id):
    return render_template('form.html', jalsa_id=jalsa_id)


# ============================================================
# API
# ============================================================

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

@app.route('/api/jalsat', methods=['GET'])
def api_list():
    conn = get_db()
    search = request.args.get('search', '').strip()
    month = request.args.get('month', '').strip()  # format: 2026-04

    rows = conn.execute("SELECT * FROM jalsat ORDER BY jalsa ASC").fetchall()
    conn.close()

    # Charger les folder_url des clients
    client_folders = {}
    if CLIENTS_DB_PATH and os.path.exists(CLIENTS_DB_PATH):
        try:
            cconn = sqlite3.connect(CLIENTS_DB_PATH)
            cconn.row_factory = sqlite3.Row
            for cr in cconn.execute("SELECT id, data FROM clients").fetchall():
                cd = json.loads(cr['data']) if cr['data'] else {}
                if cd.get('folder_url'):
                    client_folders[cr['id']] = cd['folder_url']
            cconn.close()
        except Exception:
            pass

    results = []
    for r in rows:
        d = dict(r)
        # Ajouter folder_url si le client a un dossier Nextcloud
        if d.get('client_id') and int(d['client_id']) in client_folders:
            d['folder_url'] = client_folders[int(d['client_id'])]
        if search:
            searchable = json.dumps(d, ensure_ascii=False).lower()
            if search.lower() not in searchable:
                continue
        if month:
            tj = d.get('jalsa', '')
            tjm = d.get('jalsa_moqbila', '')
            if not (tj.startswith(month) or tjm.startswith(month)):
                continue
        results.append(d)
    return jsonify(results)


@app.route('/api/jalsat', methods=['POST'])
def api_create():
    data = request.get_json()
    now = datetime.now().isoformat()
    values = {f: data.get(f, '') for f in FIELDS}
    values['created_at'] = now
    values['updated_at'] = now

    conn = get_db()
    cols = ', '.join(values.keys())
    placeholders = ', '.join(['?'] * len(values))
    cursor = conn.execute(f"INSERT INTO jalsat ({cols}) VALUES ({placeholders})", list(values.values()))
    new_id = cursor.lastrowid

    # Auto-duplication : si الجلسة المقبلة est renseignée, créer une copie
    if values.get('jalsa_moqbila'):
        copy = {
            'client_id': values.get('client_id', ''),
            'mahkama': values.get('mahkama', ''),
            'adad_qadiya': values.get('adad_qadiya', ''),
            'daira': values.get('daira', ''),
            'manoub': values.get('manoub', ''),
            'mustafid': values.get('mustafid', ''),
            'ded': values.get('ded', ''),
            'jalsa': values.get('jalsa_moqbila', ''),
            'gharad': values.get('gharad_jalsa_moqbila', ''),
            'jalsa_moqbila': '',
            'gharad_jalsa_moqbila': '',
            'tawer': values.get('tawer', ''),
            'tarikh_akhir_ajal': values.get('tarikh_akhir_ajal', ''),
            'created_at': now,
            'updated_at': now,
        }
        copy_cols = ', '.join(copy.keys())
        copy_ph = ', '.join(['?'] * len(copy))
        conn.execute(f"INSERT INTO jalsat ({copy_cols}) VALUES ({copy_ph})", list(copy.values()))

    conn.commit()
    conn.close()
    values['id'] = new_id
    _log(request, 'agenda-jalsat', 'create', 'jalsa', new_id,
         label=values.get('mahkama','') + ' — ' + values.get('adad_qadiya',''),
         details={'jalsa': values.get('jalsa',''), 'mahkama': values.get('mahkama','')})
    sync_to_tawer(values)
    return jsonify(values), 201


@app.route('/api/jalsat/<int:jid>', methods=['GET'])
def api_get(jid):
    conn = get_db()
    row = conn.execute("SELECT * FROM jalsat WHERE id = ?", (jid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))


@app.route('/api/jalsat/<int:jid>', methods=['PUT'])
def api_update(jid):
    data = request.get_json()
    now = datetime.now().isoformat()
    values = {f: data.get(f, '') for f in FIELDS}
    values['updated_at'] = now

    conn = get_db()

    # Lire TOUTE l'ancienne valeur pour diff
    old_row = conn.execute('SELECT * FROM jalsat WHERE id = ?', (jid,)).fetchone()
    old_moqbila = old_row['jalsa_moqbila'] if old_row else ''
    # Champs à comparer
    diff_fields = ['mahkama','adad_qadiya','daira','manoub','mustafid','ded','jalsa','gharad','jalsa_moqbila','gharad_jalsa_moqbila','tawer','tarikh_akhir_ajal']
    changes = {}
    if old_row:
        for f in diff_fields:
            v_old = old_row[f] or ''
            v_new = values.get(f,'') or ''
            if str(v_old).strip() != str(v_new).strip() and (v_old or v_new):
                changes[f] = {'avant': v_old, 'après': v_new}

    # Mettre à jour la ligne actuelle
    sets = ', '.join(f"{k} = ?" for k in values)
    conn.execute(f"UPDATE jalsat SET {sets} WHERE id = ?", list(values.values()) + [jid])

    # Auto-duplication : si الجلسة المقبلة a changé (nouvelle valeur non vide)
    new_moqbila = values.get('jalsa_moqbila', '')
    if new_moqbila and new_moqbila != old_moqbila:
        # Vérifier qu'une copie n'existe pas déjà pour cette date + cette affaire
        existing = conn.execute(
            "SELECT id FROM jalsat WHERE adad_qadiya = ? AND jalsa = ? AND id != ?",
            (values.get('adad_qadiya', ''), new_moqbila, jid)
        ).fetchone()

        if not existing:
            copy = {
                'client_id': values.get('client_id', ''),
                'mahkama': values.get('mahkama', ''),
                'adad_qadiya': values.get('adad_qadiya', ''),
                'daira': values.get('daira', ''),
                'manoub': values.get('manoub', ''),
                'mustafid': values.get('mustafid', ''),
                'ded': values.get('ded', ''),
                'jalsa': new_moqbila,
                'gharad': values.get('gharad_jalsa_moqbila', ''),
                'jalsa_moqbila': '',
                'gharad_jalsa_moqbila': '',
                'tawer': values.get('tawer', ''),
                'tarikh_akhir_ajal': values.get('tarikh_akhir_ajal', ''),
                'created_at': now,
                'updated_at': now,
            }
            copy_cols = ', '.join(copy.keys())
            copy_ph = ', '.join(['?'] * len(copy))
            conn.execute(f"INSERT INTO jalsat ({copy_cols}) VALUES ({copy_ph})", list(copy.values()))

    # Propagation المنوب et المستفيد vers toutes les lignes du même عدد القضية
    new_manoub = values.get('manoub', '')
    new_mustafid = values.get('mustafid', '')
    adad = values.get('adad_qadiya', '')
    if adad and old_row:
        old_row_dict = dict(old_row)
        if old_row_dict.get('manoub','') != new_manoub or old_row_dict.get('mustafid','') != new_mustafid:
            # Meme connexion/transaction : une 2e connexion bloquerait sur le verrou
            # d'ecriture de la 1re ("database is locked") et la modification serait perdue.
            conn.execute(
                "UPDATE jalsat SET manoub=?, mustafid=?, updated_at=? WHERE adad_qadiya=? AND id!=?",
                (new_manoub, new_mustafid, now, adad, jid)
            )

    conn.commit()
    conn.close()
    values['id'] = jid
    _log(request, 'agenda-jalsat', 'update', 'jalsa', jid,
         label=values.get('mahkama','') + ' — ' + values.get('adad_qadiya',''),
         details={'modifications': changes})
    sync_to_tawer(values)
    return jsonify(values)


@app.route('/api/jalsat/<int:jid>', methods=['DELETE'])
def api_delete(jid):
    conn = get_db()
    row = conn.execute('SELECT * FROM jalsat WHERE id = ?', (jid,)).fetchone()
    mahkama = row['mahkama'] if row else ''
    adad    = row['adad_qadiya'] if row else ''
    manoub  = row['manoub'] if row else ''
    jalsa   = row['jalsa'] if row else ''
    conn.execute("DELETE FROM jalsat WHERE id = ?", (jid,))
    conn.commit()
    conn.close()
    _log(request, 'agenda-jalsat', 'delete', 'jalsa', jid,
         label=mahkama+' — '+adad,
         details={'mahkama':mahkama,'adad_qadiya':adad,'manoub':manoub,'jalsa':jalsa})
    return jsonify({'ok': True})


@app.route('/api/jalsat/upcoming', methods=['GET'])
def api_upcoming():
    """الجلسات القادمة"""
    today = date.today().isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM jalsat WHERE jalsa >= ? OR jalsa_moqbila >= ? ORDER BY jalsa ASC",
        (today, today)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])



@app.route('/akhir-ajal')
def akhir_ajal():
    """Page آخر آجال — affiche la dernière ligne par عدد القضية avec تاريخ آخر آجال rempli"""
    conn = get_db()
    rows = conn.execute("""
        SELECT j.id, j.adad_qadiya, j.mahkama, j.daira, j.manoub, j.mustafid,
               j.ded, j.jalsa, j.gharad, j.tawer, j.tarikh_akhir_ajal
        FROM jalsat j
        INNER JOIN (
            SELECT adad_qadiya, MAX(jalsa) as max_jalsa
            FROM jalsat
            WHERE tarikh_akhir_ajal != ''
              AND tarikh_akhir_ajal IS NOT NULL
              AND adad_qadiya != ''
            GROUP BY adad_qadiya
        ) latest ON j.adad_qadiya = latest.adad_qadiya
                 AND j.jalsa = latest.max_jalsa
        WHERE j.tarikh_akhir_ajal != ''
          AND j.tarikh_akhir_ajal IS NOT NULL
        ORDER BY j.tarikh_akhir_ajal ASC
    """).fetchall()
    conn.close()
    return render_template('akhir_ajal.html', rows=rows)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
