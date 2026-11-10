#!/usr/bin/env python3
"""
طور القضايا — Application de gestion des dossiers judiciaires
Flask + SQLite — cabinet.mwj-lawyers.com
"""
from flask import Flask, render_template, request, redirect, jsonify, flash
import sqlite3, json, os
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
app.secret_key = os.environ.get('SECRET_KEY', 'tawer-qadaya-secret-2024')

DB_PATH         = os.environ.get('DB_PATH', '/data/qadaya.db')
CLIENTS_DB_PATH = os.environ.get('CLIENTS_DB_PATH', '')
BASE_PATH       = os.environ.get('BASE_PATH', '')
NEXTCLOUD_URL   = os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')

TOURS = {'جارية': 'jariya', 'تصريح بالحكم': 'tasrih', 'محكوم فيها': 'mahkum'}
TOURS_LIST = list(TOURS.keys())

MONTHS_AR = {
    '01': 'جانفي', '02': 'فيفري', '03': 'مارس',
    '04': 'أفريل', '05': 'ماي', '06': 'جوان',
    '07': 'جويلية', '08': 'أوت', '09': 'سبتمبر',
    '10': 'أكتوبر', '11': 'نوفمبر', '12': 'ديسمبر'
}
DAYS_AR = {0:'الإثنين', 1:'الثلاثاء', 2:'الأربعاء', 3:'الخميس', 4:'الجمعة', 5:'السبت', 6:'الأحد'}


# ─── PROTECTION ──────────────────────────────────────────────────────────────
@app.before_request
def require_nextcloud():
    if not NEXTCLOUD_URL:
        return
    if request.path.startswith(('/api/', '/static/', '/goto/')):
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
    return (
        '<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">'
        '<style>body{font-family:Arial;display:flex;justify-content:center;'
        'align-items:center;height:100vh;direction:rtl;}'
        '.box{background:white;padding:40px;border-radius:12px;text-align:center;'
        'box-shadow:0 4px 20px rgba(0,0,0,.1);max-width:400px;}'
        'h1{color:#dc3545;font-size:48px;}p{color:#333;font-size:16px;}'
        '.hint{color:#888;font-size:13px;}</style></head><body><div class="box">'
        '<h1>🔒</h1><p>غير مسموح بالوصول المباشر</p>'
        '<p class="hint">يرجى الدخول عبر Nextcloud</p>'
        '</div></body></html>'
    ), 403

@app.after_request
def add_headers(r):
    csp = f"frame-ancestors 'self' {NEXTCLOUD_URL}" if NEXTCLOUD_URL else "frame-ancestors *"
    r.headers['Content-Security-Policy'] = csp
    return r

@app.context_processor
def inject_globals():
    from datetime import datetime, timedelta
    urgent_before = (datetime.now() - timedelta(hours=48)).strftime('%Y-%m-%d')
    today         = datetime.now().strftime('%Y-%m-%d')
    return {'BASE': BASE_PATH, 'TOURS': TOURS_LIST,
            'urgent_before': urgent_before, 'today': today}


# ─── DB QADAYA ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qadaya (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            mahkama    TEXT NOT NULL DEFAULT '',
            adad       TEXT NOT NULL DEFAULT '',
            daira      TEXT NOT NULL DEFAULT '',
            mandubeen  TEXT NOT NULL DEFAULT '[]',
            addad      TEXT NOT NULL DEFAULT '[]',
            tarikh     TEXT NOT NULL DEFAULT '',
            gharad     TEXT NOT NULL DEFAULT '',
            mulahazat  TEXT NOT NULL DEFAULT '',
            mawdu3     TEXT NOT NULL DEFAULT '',
            tawar      TEXT NOT NULL DEFAULT 'جارية',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Migration colonnes anciennes → JSON
    cols = [r[1] for r in conn.execute("PRAGMA table_info(qadaya)").fetchall()]
    # Ajouter nouvelles colonnes si absentes
    if 'mawdu3' not in cols:
        conn.execute("ALTER TABLE qadaya ADD COLUMN mawdu3 TEXT NOT NULL DEFAULT ''")
    if 'mandubeen' not in cols:
        conn.execute("ALTER TABLE qadaya ADD COLUMN mandubeen TEXT NOT NULL DEFAULT '[]'")
    if 'addad' not in cols:
        conn.execute("ALTER TABLE qadaya ADD COLUMN addad TEXT NOT NULL DEFAULT '[]'")
    # Migrer anciennes données mandub/didd → JSON arrays
    if 'mandub' in cols:
        rows = conn.execute(
            "SELECT id,mandub,sifat_mandub,didd,sifat_didd FROM qadaya WHERE mandubeen='[]'"
        ).fetchall()
        for r in rows:
            if r['mandub'] or r['sifat_mandub']:
                m = json.dumps([{'nom': r['mandub'], 'sifa': r['sifat_mandub']}],
                               ensure_ascii=False)
                conn.execute("UPDATE qadaya SET mandubeen=? WHERE id=?", (m, r['id']))
            if r['didd'] or r['sifat_didd']:
                a = json.dumps([{'nom': r['didd'], 'sifa': r['sifat_didd']}],
                               ensure_ascii=False)
                conn.execute("UPDATE qadaya SET addad=? WHERE id=?", (a, r['id']))
    conn.commit()
    conn.close()


# ─── HELPERS FICHE-CLIENT ────────────────────────────────────────────────────
def get_clients_db():
    if not CLIENTS_DB_PATH or not os.path.exists(CLIENTS_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(CLIENTS_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None

def _clean(v):
    return str(v).replace('\u200f','').replace('\u200e','').replace('\u200b','').strip() if v else ''

def _parse_client_row(row):
    try:
        d = json.loads(row['data']) if row['data'] else {}
    except Exception:
        d = {}

    # المنوب الأول + extra_clients
    mandubeen = []
    if d.get('client_nom') or d.get('client_sifa'):
        mandubeen.append({'nom': _clean(d.get('client_nom', '')),
                          'sifa': _clean(d.get('client_sifa', ''))})
    for ec in d.get('extra_clients', []):
        nom  = _clean(ec.get('nom', ''))
        sifa = _clean(ec.get('sifa', ''))
        if nom or sifa:
            mandubeen.append({'nom': nom, 'sifa': sifa})

    # الضد الأول + extra_adverses
    addad = []
    if d.get('adverse_nom') or d.get('adverse_sifa'):
        addad.append({'nom': _clean(d.get('adverse_nom', '')),
                      'sifa': _clean(d.get('adverse_sifa', ''))})
    for ea in d.get('extra_adverses', []):
        nom  = _clean(ea.get('nom', ''))
        sifa = _clean(ea.get('sifa', ''))
        if nom or sifa:
            addad.append({'nom': nom, 'sifa': sifa})

    return {
        'raqm_qadiya': _clean(d.get('raqm_qadiya', '')),
        'folder_url':  _clean(d.get('folder_url', '')),
        'client_nom':  _clean(d.get('client_nom', '')),
        'mustafid':    _clean(d.get('client_mustafid', '')),
        'mandubeen':   mandubeen,
        'addad':       addad,
    }

def lookup_client_by_adad(adad):
    conn = get_clients_db()
    if not conn:
        return None
    try:
        rows = conn.execute("SELECT * FROM clients").fetchall()
        adad_c = _clean(adad)
        for row in rows:
            c = _parse_client_row(row)
            if c['raqm_qadiya'] == adad_c:
                return c
        for row in rows:
            c = _parse_client_row(row)
            if c['raqm_qadiya'] and adad_c in c['raqm_qadiya']:
                return c
    except Exception:
        pass
    finally:
        conn.close()
    return None

def get_mustafid_map():
    """{raqm_qadiya: nom du المستفيد} lu dans la base fiche-client (une seule lecture)."""
    conn = get_clients_db()
    if not conn:
        return {}
    m = {}
    try:
        for row in conn.execute("SELECT * FROM clients").fetchall():
            c = _parse_client_row(row)
            if c['raqm_qadiya'] and c['mustafid']:
                m.setdefault(c['raqm_qadiya'], c['mustafid'])
    except Exception:
        pass
    finally:
        conn.close()
    return m

def _with_mustafid(rows, mmap):
    for r in rows:
        adad = _clean(r.get('adad', ''))
        must = mmap.get(adad, '')
        if not must and len(adad) >= 3:
            # meme tolerance que lookup_client_by_adad : le عدد peut etre contenu dans le رقم القضية
            must = next((v for k, v in mmap.items() if adad in k), '')
        r['mustafid'] = must
    return rows

def get_all_clients():
    conn = get_clients_db()
    if not conn:
        return []
    result = []
    try:
        for row in conn.execute("SELECT * FROM clients ORDER BY updated_at DESC").fetchall():
            c = _parse_client_row(row)
            if c['raqm_qadiya'] or c['client_nom']:
                result.append({k: v for k, v in c.items() if k not in ('mandubeen','addad')})
    except Exception:
        pass
    finally:
        conn.close()
    return result


# ─── HELPERS FORM ─────────────────────────────────────────────────────────────
def _parse_parties(json_str):
    """Parse JSON parties array, toujours retourner une liste valide."""
    try:
        data = json.loads(json_str or '[]')
        return [{'nom': _clean(p.get('nom','')), 'sifa': _clean(p.get('sifa',''))}
                for p in data if p.get('nom') or p.get('sifa')]
    except Exception:
        return []

def _form_data():
    f = request.form
    mandubeen = _parse_parties(f.get('mandubeen_json', '[]'))
    addad     = _parse_parties(f.get('addad_json', '[]'))
    return (
        f.get('mahkama','').strip(),
        f.get('adad','').strip(),
        f.get('daira','').strip(),
        json.dumps(mandubeen, ensure_ascii=False),
        json.dumps(addad, ensure_ascii=False),
        f.get('tarikh','').strip(),
        f.get('mawdu3','').strip(),
        f.get('gharad','').strip(),
        f.get('mulahazat','').strip(),
        f.get('tawar','جارية').strip(),
    )

def _enrich_row(row):
    """Convertir une Row en dict avec parties parsées."""
    d = dict(row)
    d['mandubeen_list'] = _parse_parties(d.get('mandubeen','[]'))
    d['addad_list']     = _parse_parties(d.get('addad','[]'))
    return d


# ─── ROUTES ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    tab = request.args.get('tab', 'jariya')
    tf  = {v: k for k, v in TOURS.items()}.get(tab, 'جارية')
    conn = get_db()
    rows   = conn.execute("SELECT * FROM qadaya WHERE tawar=? ORDER BY tarikh ASC, updated_at DESC", (tf,)).fetchall()
    counts = {t: conn.execute("SELECT COUNT(*) FROM qadaya WHERE tawar=?", (t,)).fetchone()[0]
              for t in TOURS_LIST}
    conn.close()
    enriched = _with_mustafid([_enrich_row(r) for r in rows], get_mustafid_map())

    # Séparer : sans date (rouge) et avec date (groupées par mois)
    no_date = [r for r in enriched if not r.get('tarikh')]
    dated   = [r for r in enriched if r.get('tarikh')]

    # Grouper par mois puis par jour
    from itertools import groupby
    from datetime import datetime as dt
    def month_key(r):
        t = r.get('tarikh', '')
        return t[:7] if len(t) >= 7 else ''
    groups = []
    for mkey, mgrp in groupby(dated, key=month_key):
        if mkey and len(mkey) >= 7:
            y, m = mkey[:4], mkey[5:7]
            mlabel = f"{MONTHS_AR.get(m, m)} {y}"
        else:
            mlabel = mkey
        month_rows = list(mgrp)
        # Grouper par jour YYYY-MM-DD
        day_groups = []
        for dkey, dgrp in groupby(month_rows, key=lambda r: r.get('tarikh','')[:10]):
            # Nom du jour
            day_label = dkey
            try:
                d = dt.strptime(dkey, '%Y-%m-%d')
                day_num  = d.day
                day_name = DAYS_AR[d.weekday()]
                month_name = MONTHS_AR.get(f"{d.month:02d}", '')
                day_label = f"{day_name} {day_num} {month_name}"
            except Exception:
                pass
            day_groups.append({'day_label': day_label, 'rows': list(dgrp)})
        groups.append({'label': mlabel, 'mkey': mkey, 'day_groups': day_groups, 'count': len(month_rows)})

    return render_template('index.html',
                           no_date=no_date,
                           groups=groups,
                           active_tab=tab, active_tawar=tf,
                           counts=counts, TOURS_MAP=TOURS)

@app.route('/new', methods=['GET', 'POST'])
def new_qadiya():
    if request.method == 'POST':
        data = _form_data()
        conn = get_db()
        conn.execute("""INSERT INTO qadaya
            (mahkama,adad,daira,mandubeen,addad,tarikh,mawdu3,gharad,mulahazat,tawar)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", data)
        conn.commit(); conn.close()
        _log(request,'tawer-qadaya','create','qadiya','',
             label=str(data[0])+' — '+str(data[1]),details={'tawar':data[-1],'adad':data[1]})
        flash('تمت إضافة القضية بنجاح', 'success')
        return redirect(f"{BASE_PATH}/?tab={TOURS.get(data[-1],'jariya')}")
    return render_template('form.html', qadiya=None, title='إضافة قضية جديدة')

@app.route('/edit/<int:qid>', methods=['GET', 'POST'])
def edit_qadiya(qid):
    conn = get_db()
    if request.method == 'POST':
        data = _form_data()
        # Lire ancienne valeur avant update
        old = conn.execute('SELECT * FROM qadaya WHERE id=?', (qid,)).fetchone()
        fields = ['mahkama','adad','daira','tarikh','mawdu3','gharad','mulahazat','tawar','mandubeen','addad']
        changes = {}
        if old:
            new_vals = dict(zip(['mahkama','adad','daira','mandubeen','addad','tarikh','mawdu3','gharad','mulahazat','tawar'], data))
            for f in fields:
                v_old = old[f] or ''
                v_new = new_vals.get(f,'') or ''
                if str(v_old).strip() != str(v_new).strip() and (v_old or v_new):
                    changes[f] = {'avant': v_old, 'après': v_new}
        conn.execute("""UPDATE qadaya SET mahkama=?,adad=?,daira=?,mandubeen=?,addad=?,
            tarikh=?,mawdu3=?,gharad=?,mulahazat=?,tawar=?,updated_at=datetime('now') WHERE id=?""",
            data + (qid,))
        conn.commit(); conn.close()
        _log(request,'tawer-qadaya','update','qadiya',qid,
             label=str(data[0])+' — '+str(data[1]),
             details={'modifications': changes})
        flash('تم تحديث القضية بنجاح', 'success')
        return redirect(f"{BASE_PATH}/?tab={TOURS.get(data[-1],'jariya')}")
    row = conn.execute("SELECT * FROM qadaya WHERE id=?", (qid,)).fetchone()
    conn.close()
    if not row:
        return redirect(f"{BASE_PATH}/")
    return render_template('form.html', qadiya=_enrich_row(row), title='تعديل القضية')

@app.route('/delete/<int:qid>', methods=['POST'])
def delete_qadiya(qid):
    conn = get_db()
    q = conn.execute("SELECT * FROM qadaya WHERE id=?", (qid,)).fetchone()
    mahkama = q['mahkama'] if q else ''
    adad    = q['adad'] if q else ''
    tawar   = q['tawar'] if q else ''
    conn.execute("DELETE FROM qadaya WHERE id=?", (qid,))
    conn.commit(); conn.close()
    _log(request,'tawer-qadaya','delete','qadiya',qid,
         label=mahkama+' — '+adad,
         details={'mahkama':mahkama,'adad':adad,'tawar':tawar})
    flash('تم حذف القضية', 'warning')
    return redirect(f"{BASE_PATH}/?tab={TOURS.get(q['tawar'],'jariya') if q else 'jariya'}")

@app.route('/goto/<path:adad>')
def goto_folder(adad):
    c = lookup_client_by_adad(adad)
    if c and c.get('folder_url'):
        return redirect(c['folder_url'])
    return (f'<html><body dir="rtl" style="font-family:Arial;text-align:center;padding:60px">'
            f'<h2>📂 لم يتم إيجاد الملف</h2>'
            f'<p>العدد <strong>{adad}</strong> غير موجود في ملف المنوب أو لا يحتوي على رابط.</p>'
            f'<a href="{BASE_PATH}/">← رجوع</a></body></html>'), 404


# ─── API ─────────────────────────────────────────────────────────────────────
@app.route('/api/tawar/<int:qid>', methods=['POST'])
def api_change_tawar(qid):
    tawar = request.json.get('tawar','')
    if tawar not in TOURS_LIST:
        return jsonify({'error': 'طور غير صحيح'}), 400
    conn = get_db()
    conn.execute("UPDATE qadaya SET tawar=?,updated_at=datetime('now') WHERE id=?", (tawar,qid))
    conn.commit(); conn.close()
    _log(request,'tawer-qadaya','update','qadiya',qid,
         label=f'تغيير الطور → {tawar}',details={'tawar':tawar})
    return jsonify({'ok': True, 'tab': TOURS[tawar]})

@app.route('/api/qadaya')
def api_list():
    tab  = request.args.get('tab','jariya')
    conn = get_db()
    if tab == 'all':
        rows = conn.execute("SELECT * FROM qadaya ORDER BY tawar,updated_at DESC").fetchall()
    else:
        tf = {v: k for k, v in TOURS.items()}.get(tab,'جارية')
        rows = conn.execute("SELECT * FROM qadaya WHERE tawar=? ORDER BY updated_at DESC",(tf,)).fetchall()
    counts = {t: conn.execute("SELECT COUNT(*) FROM qadaya WHERE tawar=?",(t,)).fetchone()[0]
              for t in TOURS_LIST}
    conn.close()
    return jsonify({'rows': _with_mustafid([_enrich_row(r) for r in rows], get_mustafid_map()),
                    'counts': counts})

@app.route('/api/client-lookup')
def api_client_lookup():
    adad = request.args.get('adad','').strip()
    if not adad:
        return jsonify({'found': False})
    c = lookup_client_by_adad(adad)
    return jsonify({'found': True, **c}) if c else jsonify({'found': False})

@app.route('/api/clients-list')
def api_clients_list():
    return jsonify(get_all_clients())

@app.route('/api/debug-client')
def api_debug_client():
    if not CLIENTS_DB_PATH:
        return jsonify({'error': 'CLIENTS_DB_PATH non défini'})
    if not os.path.exists(CLIENTS_DB_PATH):
        return jsonify({'error': f'Fichier inexistant: {CLIENTS_DB_PATH}'})
    conn = get_clients_db()
    if not conn:
        return jsonify({'error': 'Connexion impossible'})
    try:
        cols  = [r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
        count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        sample = conn.execute("SELECT * FROM clients LIMIT 2").fetchall()
        return jsonify({'columns': cols, 'total': count,
                        'sample': [_parse_client_row(r) for r in sample]})
    finally:
        conn.close()


# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5005)), debug=False)

init_db()
