#!/usr/bin/env python3
"""
نظام الفوترة — Système de Facturation
Facturation — port 5007
"""
from flask import Flask, render_template, request, redirect, jsonify, flash, make_response
import sqlite3, os, json
try:
    from montant_lettres import montant_en_lettres
except ImportError:
    def montant_en_lettres(n): return ''

from datetime import datetime, date

def montant_en_lettres_ar(montant):
    try:
        montant = round(float(montant), 3)
        if montant < 0: return ''
        UNITES = ['','واحد','اثنان','ثلاثة','أربعة','خمسة','ستة','سبعة','ثمانية','تسعة',
                  'عشرة','أحد عشر','اثنا عشر','ثلاثة عشر','أربعة عشر','خمسة عشر',
                  'ستة عشر','سبعة عشر','ثمانية عشر','تسعة عشر']
        DIZAINES = ['','','عشرون','ثلاثون','أربعون','خمسون','ستون','سبعون','ثمانون','تسعون']
        CENTAINES = ['','مئة','مئتان','ثلاثمئة','أربعمئة','خمسمئة','ستمئة','سبعمئة','ثمانمئة','تسعمئة']
        def trois(n):
            if n==0: return ''
            c2=n//100; r=n%100; d=r//10; u=r%10
            p=[]
            if c2: p.append(CENTAINES[c2])
            if r>0:
                if r<20: p.append(UNITES[r])
                else:
                    if d: p.append(DIZAINES[d])
                    if u: p.append(UNITES[u])
            return ' و'.join(p)
        def dinar_str(n):
            if n==0: return 'صفر دينار'
            if n==1: return 'دينار واحد'
            if n==2: return 'ديناران'
            mil=n//1000; r=n%1000; p=[]
            if mil==1: p.append('ألف')
            elif mil==2: p.append('ألفان')
            elif 3<=mil<=10: p.append(UNITES[mil]+' آلاف')
            elif mil>10: p.append(trois(mil)+' ألف')
            if r: p.append(trois(r))
            nb=' و'.join(p)
            if n<3: return nb
            if n<11: return nb+' دنانير'
            return nb+' دينار'
        def mil_str(n):
            if n==0: return ''
            if n==1: return 'ملّيم واحد'
            if n==2: return 'ملّيمان'
            if n<11: return trois(n)+' ملّيمات'
            return trois(n)+' ملّيم'
        d=int(montant); m=round((montant-d)*1000)
        r=dinar_str(d)
        if m: r+=' و'+mil_str(m)
        return r+' تونسي'
    except Exception: return ''



app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'facturation-secret-2026')

DB_PATH      = os.environ.get('DB_PATH', '/data/facturation.db')
BASE_PATH    = os.environ.get('BASE_PATH', '')
NEXTCLOUD_URL= os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')


@app.template_filter('date_fr')
def date_fr(value):
    """Convertir YYYY-MM-DD en DD/MM/YYYY."""
    if not value:
        return ''
    try:
        parts = str(value).split('-')
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return value

DOC_TYPES = {
    'devis':    {'label': 'Devis',    'label_ar': 'عرض السعر', 'icon': '📋', 'color': '#2E75B6'},
    'facture':  {'label': 'Facture',  'label_ar': 'فاتورة',     'icon': '🧾', 'color': '#27ae60'},
    'avoir':    {'label': 'Avoir',    'label_ar': 'إشعار دائن', 'icon': '↩️', 'color': '#e67e22'},
}
STATUTS = {
    'en_cours':  {'label': 'En cours',  'color': '#718096', 'icon': '🕐'},
    'paye':      {'label': 'Payé',      'color': '#27ae60', 'icon': '✅'},
    'annule':    {'label': 'Annulé',    'color': '#e74c3c', 'icon': '❌'},
}
TVA_OPTIONS = [0, 7, 13, 19]  # Valeur par défaut, configurable dans Paramètres

def get_tva_options():
    cab = get_cabinet()
    tva_str = cab.get('tva_rates', '0,7,13,19')
    try:
        return sorted(set(float(x.strip()) for x in tva_str.split(',') if x.strip()))
    except Exception:
        return [0, 7, 13, 19]


# ─── PROTECTION ───────────────────────────────────────────────────────────────
@app.before_request
def require_nextcloud():
    if request.path.startswith(('/api/', '/static/', '/pdf/')):
        return
    if not NEXTCLOUD_URL:
        return
    ref  = request.headers.get('Referer', '')
    dest = request.headers.get('Sec-Fetch-Dest', '')
    site = request.headers.get('Sec-Fetch-Site', '')
    if dest == 'iframe' or site == 'same-origin':
        return
    if ref and (NEXTCLOUD_URL in ref or request.host in ref):
        return
    if any(k.startswith(('nc_', 'oc_')) for k in request.cookies):
        return
    return ('<html><body dir="rtl" style="font-family:Arial;text-align:center;padding:60px">'
            '<h2>🔒 يرجى الدخول عبر Nextcloud</h2></body></html>'), 403

@app.after_request
def add_headers(r):
    if NEXTCLOUD_URL:
        r.headers['Content-Security-Policy'] = f"frame-ancestors 'self' {NEXTCLOUD_URL}"
    return r

@app.context_processor
def inject_globals():
    return {'BASE': BASE_PATH, 'DOC_TYPES': DOC_TYPES, 'STATUTS': STATUTS,
            'TVA_OPTIONS': get_tva_options(), 'today': date.today().isoformat(),
            'montant_en_lettres': montant_en_lettres}


# ─── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cabinet (
            id            INTEGER PRIMARY KEY DEFAULT 1,
            raison_sociale TEXT NOT NULL DEFAULT '',
            matricule_fiscal TEXT NOT NULL DEFAULT '',
            adresse       TEXT NOT NULL DEFAULT '',
            tel           TEXT NOT NULL DEFAULT '',
            email         TEXT NOT NULL DEFAULT '',
            rib           TEXT NOT NULL DEFAULT '',
            timbre        REAL NOT NULL DEFAULT 1.000,
            mention_legale TEXT NOT NULL DEFAULT '',
            logo_url       TEXT NOT NULL DEFAULT '',
            prefix_devis   TEXT NOT NULL DEFAULT 'D',
            prefix_facture TEXT NOT NULL DEFAULT 'F',
            prefix_avoir   TEXT NOT NULL DEFAULT 'A',
            num_format     TEXT NOT NULL DEFAULT '{prefix}-{year}-{num:04d}',
            tva_rates      TEXT NOT NULL DEFAULT '0,7,13,19',
            exercice_courant TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO cabinet (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS clients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            raison_sociale  TEXT NOT NULL DEFAULT '',
            matricule_fiscal TEXT NOT NULL DEFAULT '',
            adresse         TEXT NOT NULL DEFAULT '',
            tel             TEXT NOT NULL DEFAULT '',
            email           TEXT NOT NULL DEFAULT '',
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL DEFAULT 'facture',
            numero      TEXT NOT NULL DEFAULT '',
            client_id   INTEGER REFERENCES clients(id),
            date_doc    TEXT NOT NULL DEFAULT '',
            date_echeance TEXT NOT NULL DEFAULT '',
            exercice    TEXT NOT NULL DEFAULT '',
            statut      TEXT NOT NULL DEFAULT 'brouillon',
            notes       TEXT NOT NULL DEFAULT '',
            avec_timbre INTEGER NOT NULL DEFAULT 0,
            verrouille  INTEGER NOT NULL DEFAULT 0,
            origine_id  INTEGER,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS exercices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            annee       TEXT NOT NULL,
            libelle     TEXT NOT NULL DEFAULT '',
            date_debut  TEXT NOT NULL DEFAULT '',
            date_fin    TEXT NOT NULL DEFAULT '',
            actif       INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS lignes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            ordre        INTEGER NOT NULL DEFAULT 0,
            description  TEXT NOT NULL DEFAULT '',
            quantite     REAL NOT NULL DEFAULT 1,
            prix_unitaire REAL NOT NULL DEFAULT 0,
            tva          REAL NOT NULL DEFAULT 19,
            remise       REAL NOT NULL DEFAULT 0
        );
    """)
    # Migration colonnes manquantes
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cabinet)").fetchall()]
    doc_cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()]
    if 'langue' not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN langue TEXT NOT NULL DEFAULT 'fr'")
    if 'champs_ar' not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN champs_ar TEXT NOT NULL DEFAULT '{}' ")
    if 'logo_url' not in cols:
        conn.execute("ALTER TABLE cabinet ADD COLUMN logo_url TEXT NOT NULL DEFAULT ''")
    if 'tva_rates' not in cols:
        conn.execute("ALTER TABLE cabinet ADD COLUMN tva_rates TEXT NOT NULL DEFAULT '0,7,13,19'")
    if 'exercice_courant' not in cols:
        conn.execute("ALTER TABLE cabinet ADD COLUMN exercice_courant TEXT NOT NULL DEFAULT ''")
    doc_cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()]
    if 'verrouille' not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN verrouille INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_cabinet():
    conn = get_db()
    cab = dict(conn.execute("SELECT * FROM cabinet WHERE id=1").fetchone())
    conn.close()
    return cab

def get_document_totals(doc_id):
    conn = get_db()
    lignes = conn.execute("SELECT * FROM lignes WHERE document_id=? ORDER BY ordre", (doc_id,)).fetchall()
    conn.close()
    total_ht = 0; total_tva = 0
    for l in lignes:
        ht = round(l['quantite'] * l['prix_unitaire'] * (1 - l['remise']/100), 3)
        tva = round(ht * l['tva'] / 100, 3)
        total_ht += ht; total_tva += tva
    return {'ht': round(total_ht, 3), 'tva': round(total_tva, 3),
            'ttc': round(total_ht + total_tva, 3), 'lignes': [dict(l) for l in lignes]}

def next_numero(doc_type, exercice):
    """MAX de l'exercice courant + 1, respecte debut_num."""
    cab = get_cabinet()
    prefix = cab.get('prefix_' + doc_type, doc_type[0].upper())
    fmt = cab.get('num_format', '{prefix}-{year}-{num:04d}')
    year_short = str(exercice)[-2:] if exercice else str(date.today().year)[-2:]
    if '{num' not in fmt:
        fmt = fmt + '-{num:04d}'
    conn = get_db()
    debut = 0
    try:
        ex_row = conn.execute(
            "SELECT debut_num FROM exercices WHERE annee=?", (str(exercice),)
        ).fetchone()
        if ex_row and ex_row[0]:
            debut = int(ex_row[0]) - 1
    except:
        pass
    rows = conn.execute(
        "SELECT numero FROM documents WHERE type=? AND exercice=?",
        (doc_type, str(exercice))
    ).fetchall()
    conn.close()
    max_num = debut
    for row in rows:
        parts = str(row[0]).replace('-', ' ').replace('/', ' ').split()
        for part in reversed(parts):
            if part.isdigit():
                try: max_num = max(max_num, int(part))
                except: pass
                break
    conn = get_db()
    num = max_num + 1
    for _ in range(9999):
        try:
            cand = fmt.format(
                prefix=prefix, year=str(exercice),
                year_short=year_short, num=num
            )
        except:
            cand = prefix + '-' + str(exercice) + '-' + str(num).zfill(4)
        if not conn.execute(
            'SELECT 1 FROM documents WHERE numero=?', (cand,)
        ).fetchone():
            conn.close()
            return cand
        num += 1
    conn.close()
    return cand


@app.route('/')
def index():
    conn = get_db()
    stats = {
        'devis':   conn.execute("SELECT COUNT(*) FROM documents WHERE type='devis'").fetchone()[0],
        'factures':conn.execute("SELECT COUNT(*) FROM documents WHERE type='facture'").fetchone()[0],
        'avoirs':  conn.execute("SELECT COUNT(*) FROM documents WHERE type='avoir'").fetchone()[0],
        'clients': conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
    }
    docs_recents = conn.execute("""
        SELECT d.*, c.raison_sociale as client_nom
        FROM documents d LEFT JOIN clients c ON d.client_id=c.id
        ORDER BY d.created_at DESC LIMIT 8
    """).fetchall()
    conn.close()
    return render_template('index.html', stats=stats, docs_recents=docs_recents,
                           cabinet=get_cabinet())

@app.route('/parametres', methods=['GET', 'POST'])
def parametres():
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        conn.execute("""
            UPDATE cabinet SET
                raison_sociale=?, matricule_fiscal=?, adresse=?, tel=?, email=?,
                rib=?, timbre=?, mention_legale=?, logo_url=?,
                prefix_devis=?, prefix_facture=?, prefix_avoir=?, num_format=?
            WHERE id=1
        """, (f.get('raison_sociale',''), f.get('matricule_fiscal',''),
              f.get('adresse',''), f.get('tel',''), f.get('email',''),
              f.get('rib',''), float(f.get('timbre', 1.000) or 1.000),
              f.get('mention_legale',''), f.get('logo_url',''),
              f.get('prefix_devis','D'), f.get('prefix_facture','F'),
              f.get('prefix_avoir','A'), f.get('num_format','{prefix}{num:03d}')))
        conn.commit()
        conn.close()
        flash('تم حفظ بيانات المكتب بنجاح', 'success')
        return redirect(f"{BASE_PATH}/parametres")
    return render_template('parametres.html', cabinet=get_cabinet())


# ─── ROUTES CLIENTS ───────────────────────────────────────────────────────────
@app.route('/clients')
def clients():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*, COUNT(d.id) as nb_docs
        FROM clients c LEFT JOIN documents d ON c.id=d.client_id
        GROUP BY c.id ORDER BY c.raison_sociale
    """).fetchall()
    conn.close()
    return render_template('clients.html', clients=rows)

@app.route('/clients/new', methods=['GET', 'POST'])
def client_new():
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        cur = conn.execute("""
            INSERT INTO clients (raison_sociale, matricule_fiscal, adresse, tel, email, notes)
            VALUES (?,?,?,?,?,?)
        """, (f.get('raison_sociale',''), f.get('matricule_fiscal',''),
              f.get('adresse',''), f.get('tel',''), f.get('email',''), f.get('notes','')))
        conn.commit(); conn.close()
        flash('تم إضافة العميل بنجاح', 'success')
        return redirect(f"{BASE_PATH}/clients")
    return render_template('client_form.html', client=None)

@app.route('/clients/<int:cid>/edit', methods=['GET', 'POST'])
def client_edit(cid):
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        conn.execute("""
            UPDATE clients SET raison_sociale=?, matricule_fiscal=?, adresse=?,
            tel=?, email=?, notes=?, updated_at=datetime('now','localtime') WHERE id=?
        """, (f.get('raison_sociale',''), f.get('matricule_fiscal',''),
              f.get('adresse',''), f.get('tel',''), f.get('email',''),
              f.get('notes',''), cid))
        conn.commit(); conn.close()
        flash('تم تحديث العميل بنجاح', 'success')
        return redirect(f"{BASE_PATH}/clients")
    client = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return render_template('client_form.html', client=client)

@app.route('/clients/<int:cid>/delete', methods=['POST'])
def client_delete(cid):
    conn = get_db()
    conn.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit(); conn.close()
    flash('تم حذف العميل', 'warning')
    return redirect(f"{BASE_PATH}/clients")

@app.route('/api/clients')
def api_clients():
    conn = get_db()
    rows = conn.execute("SELECT id, raison_sociale, matricule_fiscal, adresse, tel, email FROM clients ORDER BY raison_sociale").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─── ROUTES DOCUMENTS ─────────────────────────────────────────────────────────
@app.route('/documents')
def documents():
    doc_type   = request.args.get('type', 'facture')
    statut     = request.args.get('statut', '')
    _ex_def    = get_cabinet().get('exercice_courant') or str(date.today().year)
    exercice   = request.args.get('exercice', _ex_def)
    client_id  = request.args.get('client_id', '')
    date_debut = request.args.get('date_debut', '')
    date_fin   = request.args.get('date_fin', '')
    conn = get_db()
    q = "SELECT d.*, c.raison_sociale as client_nom FROM documents d LEFT JOIN clients c ON d.client_id=c.id WHERE d.type=?"
    params = [doc_type]
    if exercice:   q += " AND d.exercice=?";    params.append(exercice)
    if statut:     q += " AND d.statut=?";      params.append(statut)
    if client_id:  q += " AND d.client_id=?";   params.append(client_id)
    if date_debut: q += " AND d.date_doc>=?";   params.append(date_debut)
    if date_fin:   q += " AND d.date_doc<=?";   params.append(date_fin)
    q += " ORDER BY d.date_doc DESC, d.id DESC"
    rows = conn.execute(q, params).fetchall()
    docs = []
    for r in rows:
        d = dict(r)
        t = get_document_totals(d['id'])
        d['total_ttc'] = t['ttc']
        docs.append(d)
    ex_t = [r[0] for r in conn.execute("SELECT annee FROM exercices ORDER BY annee DESC").fetchall()]
    ex_d = [r[0] for r in conn.execute("SELECT DISTINCT exercice FROM documents ORDER BY exercice DESC").fetchall()]
    exercices = sorted(set(ex_t + ex_d), reverse=True)
    clients = conn.execute("SELECT id, raison_sociale FROM clients ORDER BY raison_sociale").fetchall()
    conn.close()
    return render_template('documents.html', docs=docs, doc_type=doc_type,
                           statut=statut, exercice=exercice, exercices=exercices,
                           clients=clients, client_id=client_id,
                           date_debut=date_debut, date_fin=date_fin)

@app.route('/documents/new', methods=['GET', 'POST'])
def document_new():
    doc_type = request.args.get('type', 'facture')
    cab_ex   = get_cabinet()
    exercice = cab_ex.get('exercice_courant') or str(date.today().year)
    if request.method == 'POST':
        f = request.form
        doc_type = f.get('type', 'facture')
        exercice = f.get('exercice', str(date.today().year))
        numero = next_numero(doc_type, exercice)
        conn = get_db()
        import json as _jins
        _champs = _jins.dumps({
            'aladd': f.get('ar_aladd','').strip(),
            'aladd_show': bool(f.get('ar_aladd_show')),
            'mawdou': f.get('ar_mawdou','').strip(),
            'mawdou_show': bool(f.get('ar_mawdou_show')),
            'aqd': f.get('ar_aqd','').strip(),
            'aqd_show': bool(f.get('ar_aqd_show')),
            'mahkama': f.get('ar_mahkama','').strip(),
            'mahkama_show': bool(f.get('ar_mahkama_show')),
            'qadiya_adad': f.get('ar_qadiya_adad','').strip(),
            'qadiya_adad_show': bool(f.get('ar_qadiya_adad_show')),
            'tarikh_houkm': f.get('ar_tarikh_houkm','').strip(),
            'tarikh_houkm_show': bool(f.get('ar_tarikh_houkm_show')),
        }, ensure_ascii=False)
        cur = conn.execute("""
            INSERT INTO documents (type, numero, client_id, date_doc, date_echeance,
                exercice, statut, notes, avec_timbre, langue, champs_ar)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (doc_type, numero, f.get('client_id') or None,
              f.get('date_doc', date.today().isoformat()),
              f.get('date_echeance',''), exercice,
              f.get('statut','brouillon'), f.get('notes',''),
              1 if f.get('avec_timbre') else 0,
              f.get('langue','fr'), _champs))
        doc_id = cur.lastrowid
        # Lignes
        for i in range(20):
            desc = f.get(f'desc_{i}','').strip()
            if not desc: continue
            conn.execute("""
                INSERT INTO lignes (document_id, ordre, description, quantite, prix_unitaire, tva, remise)
                VALUES (?,?,?,?,?,?,?)
            """, (doc_id, i, desc,
                  float(f.get(f'qte_{i}', 1) or 1),
                  float(f.get(f'pu_{i}', 0) or 0),
                  float(f.get(f'tva_{i}', 19) or 19),
                  float(f.get(f'remise_{i}', 0) or 0)))
        conn.commit(); conn.close()
        flash(f'تم إنشاء {DOC_TYPES[doc_type]["label_ar"]} {numero} بنجاح', 'success')
        return redirect(f"{BASE_PATH}/documents/{doc_id}")
    numero = next_numero(doc_type, exercice)
    conn = get_db()
    clients = conn.execute("SELECT id, raison_sociale FROM clients ORDER BY raison_sociale").fetchall()
    conn.close()
    return render_template('document_form.html', doc=None, lignes=[],
                           champs_ar_dict={},
                           doc_type=doc_type, exercice=exercice, numero=numero,
                           clients=clients, cabinet=get_cabinet())

@app.route('/documents/<int:did>')
def document_view(did):
    conn = get_db()
    doc = conn.execute("""
        SELECT d.*, c.raison_sociale as client_nom, c.matricule_fiscal as client_mf,
               c.adresse as client_adresse, c.tel as client_tel, c.email as client_email
        FROM documents d LEFT JOIN clients c ON d.client_id=c.id WHERE d.id=?
    """, (did,)).fetchone()
    conn.close()
    if not doc: return redirect(f"{BASE_PATH}/documents")
    totaux = get_document_totals(did)
    cab = get_cabinet()
    timbre = cab['timbre'] if doc['avec_timbre'] else 0
    totaux['timbre'] = timbre
    totaux['net'] = round(totaux['ttc'] + timbre, 3)
    totaux['net_lettres'] = montant_en_lettres(totaux['net'])
    return render_template('document_view.html', doc=doc, totaux=totaux,
                           cabinet=cab, DOC_TYPES=DOC_TYPES, STATUTS=STATUTS)

@app.route('/documents/<int:did>/edit', methods=['GET', 'POST'])
def document_edit(did):
    conn = get_db()
    doc_check = conn.execute("SELECT verrouille FROM documents WHERE id=?", (did,)).fetchone()
    if doc_check and doc_check['verrouille']:
        flash('🔒 Ce document est verrouillé et ne peut pas être modifié.', 'error')
        return redirect(f"{BASE_PATH}/documents/{did}")
    if request.method == 'POST':
        import json as _jupd
        _champs_upd = _jupd.dumps({
            'aladd': f.get('ar_aladd','').strip(),
            'aladd_show': bool(f.get('ar_aladd_show')),
            'mawdou': f.get('ar_mawdou','').strip(),
            'mawdou_show': bool(f.get('ar_mawdou_show')),
            'aqd': f.get('ar_aqd','').strip(),
            'aqd_show': bool(f.get('ar_aqd_show')),
            'mahkama': f.get('ar_mahkama','').strip(),
            'mahkama_show': bool(f.get('ar_mahkama_show')),
            'qadiya_adad': f.get('ar_qadiya_adad','').strip(),
            'qadiya_adad_show': bool(f.get('ar_qadiya_adad_show')),
            'tarikh_houkm': f.get('ar_tarikh_houkm','').strip(),
            'tarikh_houkm_show': bool(f.get('ar_tarikh_houkm_show')),
        }, ensure_ascii=False)
        conn.execute("""
            UPDATE documents SET client_id=?, date_doc=?, date_echeance=?,
            exercice=?, statut=?, notes=?, avec_timbre=?, numero=?,
            langue=?, champs_ar=?,
            updated_at=datetime('now','localtime') WHERE id=?
        """, (f.get('client_id') or None, f.get('date_doc',''),
              f.get('date_echeance',''), f.get('exercice',''),
              f.get('statut','brouillon'), f.get('notes',''),
              1 if f.get('avec_timbre') else 0,
              f.get('numero',''), f.get('langue','fr'), _champs_upd, did))
        # Réinitialiser les lignes
        conn.execute("DELETE FROM lignes WHERE document_id=?", (did,))
        for i in range(20):
            desc = f.get(f'desc_{i}','').strip()
            if not desc: continue
            conn.execute("""
                INSERT INTO lignes (document_id, ordre, description, quantite, prix_unitaire, tva, remise)
                VALUES (?,?,?,?,?,?,?)
            """, (did, i, desc,
                  float(f.get(f'qte_{i}', 1) or 1),
                  float(f.get(f'pu_{i}', 0) or 0),
                  float(f.get(f'tva_{i}', 19) or 19),
                  float(f.get(f'remise_{i}', 0) or 0)))
        conn.commit(); conn.close()
        flash('تم تحديث الوثيقة بنجاح', 'success')
        return redirect(f"{BASE_PATH}/documents/{did}")
    doc  = conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    lignes = conn.execute("SELECT * FROM lignes WHERE document_id=? ORDER BY ordre", (did,)).fetchall()
    clients = conn.execute("SELECT id, raison_sociale FROM clients ORDER BY raison_sociale").fetchall()
    conn.close()
    if not doc: return redirect(f"{BASE_PATH}/documents")
    import json as _jedit
    try:
        _ca_edit = _jedit.loads(doc['champs_ar'] or '{}')
    except Exception:
        _ca_edit = {}
    return render_template('document_form.html', doc=doc, lignes=lignes,
                           champs_ar_dict=_ca_edit,
                           doc_type=doc['type'], exercice=doc['exercice'],
                           numero=doc['numero'], clients=clients, cabinet=get_cabinet())

@app.route('/documents/<int:did>/delete', methods=['POST'])
def document_delete(did):
    conn = get_db()
    doc = conn.execute("SELECT type, verrouille FROM documents WHERE id=?", (did,)).fetchone()
    if doc and doc['verrouille']:
        conn.close()
        flash('🔒 Ce document est verrouillé et ne peut pas être supprimé.', 'error')
        return redirect(f"{BASE_PATH}/documents?type={doc['type']}")
    conn.execute("DELETE FROM documents WHERE id=?", (did,))
    conn.commit(); conn.close()
    flash('تم حذف الوثيقة', 'warning')
    return redirect(f"{BASE_PATH}/documents?type={doc['type'] if doc else 'facture'}")

@app.route('/documents/<int:did>/verrouiller', methods=['POST'])
def document_verrouiller(did):
    etat = 1 if request.form.get('verrouille') == '1' else 0
    conn = get_db()
    conn.execute("UPDATE documents SET verrouille=?, updated_at=datetime('now','localtime') WHERE id=?", (etat, did))
    conn.commit(); conn.close()
    msg = '🔒 Document verrouillé — plus de modification possible.' if etat else '🔓 Document déverrouillé.'
    flash(msg, 'success' if etat else 'warning')
    return redirect(f"{BASE_PATH}/documents/{did}")

@app.route('/documents/<int:did>/statut', methods=['POST'])
def document_statut(did):
    statut = request.form.get('statut','brouillon')
    conn = get_db()
    conn.execute("UPDATE documents SET statut=?, updated_at=datetime('now','localtime') WHERE id=?",
                 (statut, did))
    conn.commit(); conn.close()
    return redirect(f"{BASE_PATH}/documents/{did}")

@app.route('/documents/<int:did>/convert', methods=['POST'])
def document_convert(did):
    """Convertir Devis → Facture."""
    conn = get_db()
    doc = dict(conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone())
    lignes = conn.execute("SELECT * FROM lignes WHERE document_id=? ORDER BY ordre", (did,)).fetchall()
    exercice = doc['exercice'] or str(date.today().year)
    numero = next_numero('facture', exercice)
    cur = conn.execute("""
        INSERT INTO documents (type, numero, client_id, date_doc, date_echeance,
            exercice, statut, notes, avec_timbre, origine_id)
        VALUES ('facture',?,?,?,?,?,'brouillon',?,?,?)
    """, (numero, doc['client_id'], date.today().isoformat(),
          doc['date_echeance'], exercice, doc['notes'],
          doc['avec_timbre'], did))
    new_id = cur.lastrowid
    for l in lignes:
        conn.execute("""
            INSERT INTO lignes (document_id, ordre, description, quantite, prix_unitaire, tva, remise)
            VALUES (?,?,?,?,?,?,?)
        """, (new_id, l['ordre'], l['description'], l['quantite'],
              l['prix_unitaire'], l['tva'], l['remise']))
    # Marquer le devis comme validé
    conn.execute("UPDATE documents SET statut='valide' WHERE id=?", (did,))
    conn.commit(); conn.close()
    flash(f'Devis converti en Facture {numero}', 'success')
    return redirect(f"{BASE_PATH}/documents/{new_id}")

@app.route('/documents/<int:did>/avoir', methods=['POST'])
def document_avoir(did):
    """Créer un avoir depuis une facture."""
    conn = get_db()
    doc = dict(conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone())
    lignes = conn.execute("SELECT * FROM lignes WHERE document_id=? ORDER BY ordre", (did,)).fetchall()
    exercice = doc['exercice'] or str(date.today().year)
    numero = next_numero('avoir', exercice)
    cur = conn.execute("""
        INSERT INTO documents (type, numero, client_id, date_doc,
            exercice, statut, notes, avec_timbre, origine_id)
        VALUES ('avoir',?,?,?,?,'valide',?,?,?)
    """, (numero, doc['client_id'], date.today().isoformat(),
          exercice, f"Avoir sur {doc['numero']}", doc['avec_timbre'], did))
    new_id = cur.lastrowid
    for l in lignes:
        conn.execute("""
            INSERT INTO lignes (document_id, ordre, description, quantite, prix_unitaire, tva, remise)
            VALUES (?,?,?,?,?,?,?)
        """, (new_id, l['ordre'], l['description'], l['quantite'],
              l['prix_unitaire'], l['tva'], l['remise']))
    conn.commit(); conn.close()
    flash(f'Avoir {numero} créé', 'success')
    return redirect(f"{BASE_PATH}/documents/{new_id}")

@app.route('/documents/<int:did>/pdf/ar')
def document_pdf_ar(did):
    conn = get_db()
    doc = conn.execute("""
        SELECT d.*, c.raison_sociale as client_nom, c.matricule_fiscal as client_mf,
               c.adresse as client_adresse, c.tel as client_tel, c.email as client_email
        FROM documents d LEFT JOIN clients c ON d.client_id=c.id WHERE d.id=?
    """, (did,)).fetchone()
    conn.close()
    if not doc or doc['type'] != 'facture':
        return redirect(f"{BASE_PATH}/documents/{did}")
    totaux = get_document_totals(did)
    cab = get_cabinet()
    timbre = cab['timbre'] if doc['avec_timbre'] else 0
    totaux['timbre'] = timbre
    totaux['net'] = round(totaux['ttc'] + timbre, 3)
    totaux['net_lettres'] = montant_en_lettres_ar(totaux['net'])
    import json as _jpdf
    try:
        champs_ar_data = _jpdf.loads(doc['champs_ar'] or '{}')
    except Exception:
        champs_ar_data = {}
    html = render_template('document_pdf_ar.html', doc=doc, totaux=totaux,
                           cabinet=cab, DOC_TYPES=DOC_TYPES, STATUTS=STATUTS,
                           champs_ar=champs_ar_data)
    from flask import make_response
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@app.route('/documents/<int:did>/pdf')
def document_pdf(did):
    # Rediriger vers PDF arabe si langue=ar
    import json as _jlang
    conn_l = get_db()
    doc_l = conn_l.execute("SELECT langue FROM documents WHERE id=?", (did,)).fetchone()
    conn_l.close()
    if doc_l and doc_l['langue'] == 'ar':
        return redirect(f"{BASE_PATH}/documents/{did}/pdf/ar")
    """Afficher le PDF imprimable."""
    conn = get_db()
    doc = conn.execute("""
        SELECT d.*, c.raison_sociale as client_nom, c.matricule_fiscal as client_mf,
               c.adresse as client_adresse, c.tel as client_tel, c.email as client_email
        FROM documents d LEFT JOIN clients c ON d.client_id=c.id WHERE d.id=?
    """, (did,)).fetchone()
    conn.close()
    if not doc: return "Document introuvable", 404
    totaux = get_document_totals(did)
    cab = get_cabinet()
    timbre = cab['timbre'] if doc['avec_timbre'] else 0
    totaux['timbre'] = timbre
    totaux['net'] = round(totaux['ttc'] + timbre, 3)
    totaux['net_lettres'] = montant_en_lettres(totaux['net'])
    return render_template('document_pdf.html', doc=doc, totaux=totaux,
                           cabinet=cab, DOC_TYPES=DOC_TYPES)

@app.route('/api/next-numero')
def api_next_numero():
    doc_type = request.args.get('type', 'facture')
    exercice = request.args.get('exercice', str(date.today().year))
    return jsonify({'numero': next_numero(doc_type, exercice)})


# ─── ROUTES EXERCICES ────────────────────────────────────────────────────────
@app.route('/exercices')
def exercices():
    conn = get_db()
    # Auto-importer années avec documents mais absentes de la table exercices
    years_doc = [r[0] for r in conn.execute(
        "SELECT DISTINCT exercice FROM documents WHERE exercice != '' AND exercice IS NOT NULL"
    ).fetchall()]
    years_tbl = [r[0] for r in conn.execute("SELECT annee FROM exercices").fetchall()]
    for y in years_doc:
        if y and y not in years_tbl:
            conn.execute(
                "INSERT INTO exercices (annee, libelle, actif, debut_num) VALUES (?,?,0,1)",
                (y, 'Exercice ' + str(y))
            )
    conn.commit()
    rows = conn.execute(
        "SELECT e.*, COUNT(d.id) as nb_docs FROM exercices e "
        "LEFT JOIN documents d ON d.exercice=e.annee "
        "GROUP BY e.id ORDER BY e.annee DESC"
    ).fetchall()
    conn.close()
    return render_template('exercices.html', exercices=rows)

@app.route('/exercices/new', methods=['POST'])
def exercice_new():
    f = request.form
    annee    = f.get('annee','').strip()
    libelle  = f.get('libelle','').strip()
    date_deb = f.get('date_debut','')
    date_fin = f.get('date_fin','')
    if not annee:
        flash("L'année est obligatoire", 'error')
        return redirect(f"{BASE_PATH}/exercices")
    conn = get_db()
    # Si marqué actif → désactiver les autres
    actif = 1 if f.get('actif') else 0
    if actif:
        conn.execute("UPDATE exercices SET actif=0")
        conn.execute("UPDATE cabinet SET exercice_courant=? WHERE id=1", (annee,))
    debut_num = int(f.get("debut_num", 1) or 1)
    conn.execute(
        "INSERT INTO exercices (annee, libelle, date_debut, date_fin, actif, debut_num) VALUES (?,?,?,?,?,?)",
        (annee, libelle or annee, date_deb, date_fin, actif, debut_num)
    )
    conn.commit(); conn.close()
    flash(f'Exercice {annee} créé', 'success')
    return redirect(f"{BASE_PATH}/exercices")

@app.route('/exercices/<int:eid>/activer', methods=['POST'])
def exercice_activer(eid):
    conn = get_db()
    ex = conn.execute("SELECT annee FROM exercices WHERE id=?", (eid,)).fetchone()
    if ex:
        conn.execute("UPDATE exercices SET actif=0")
        conn.execute("UPDATE exercices SET actif=1 WHERE id=?", (eid,))
        conn.execute("UPDATE cabinet SET exercice_courant=? WHERE id=1", (ex['annee'],))
        conn.commit()
        flash(f'Exercice {ex["annee"]} activé comme exercice courant', 'success')
    conn.close()
    return redirect(f"{BASE_PATH}/exercices")

@app.route('/exercices/<int:eid>/delete', methods=['POST'])
def exercice_delete(eid):
    conn = get_db()
    ex = conn.execute("SELECT annee, nb_docs FROM (SELECT e.*, COUNT(d.id) as nb_docs FROM exercices e LEFT JOIN documents d ON d.exercice=e.annee WHERE e.id=?)", (eid,)).fetchone()
    conn.execute("DELETE FROM exercices WHERE id=?", (eid,))
    conn.commit(); conn.close()
    flash('Exercice supprimé', 'warning')
    return redirect(f"{BASE_PATH}/exercices")

@app.route('/exercices/<int:eid>/edit', methods=['POST'])
def exercice_edit(eid):
    f = request.form
    conn = get_db()
    conn.execute(
        "UPDATE exercices SET libelle=?, date_debut=?, date_fin=?, debut_num=? WHERE id=?",
        (f.get('libelle',''), f.get('date_debut',''), f.get('date_fin',''), int(f.get('debut_num',1) or 1), eid)
    )
    conn.commit(); conn.close()
    flash('Exercice mis à jour', 'success')
    return redirect(f"{BASE_PATH}/exercices")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5007)), debug=False)

init_db()

# ─── UPLOAD LOGO ──────────────────────────────────────────────────────────────
import werkzeug.utils
LOGO_DIR = os.environ.get('LOGO_DIR', '/data/logos')

@app.route('/upload-logo', methods=['POST'])
def upload_logo():
    f = request.files.get('logo_file')
    if not f or f.filename == '':
        return jsonify({'error': 'Aucun fichier'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'):
        return jsonify({'error': 'Format non supporté'}), 400
    os.makedirs(LOGO_DIR, exist_ok=True)
    fname = werkzeug.utils.secure_filename(f'logo_cabinet.{ext}')
    fpath = os.path.join(LOGO_DIR, fname)
    f.save(fpath)
    # Mettre à jour logo_url dans cabinet
    logo_url = f"{BASE_PATH}/logo/{fname}"
    conn = get_db()
    conn.execute("UPDATE cabinet SET logo_url=? WHERE id=1", (logo_url,))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'url': logo_url})

@app.route('/logo/<filename>')
def serve_logo(filename):
    from flask import send_from_directory
    return send_from_directory(LOGO_DIR, filename)

