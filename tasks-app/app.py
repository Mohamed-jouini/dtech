#!/usr/bin/env python3
"""
نظام المهام — Système de Tâches
Port 5008 — Auth via Nextcloud
"""
from flask import Flask, render_template, request, redirect, flash, jsonify, send_from_directory
import warnings
warnings.filterwarnings("ignore")
import sqlite3, os, requests
from datetime import datetime, date
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tasks-mwj-2026')
DB_PATH       = os.environ.get('DB_PATH', '/data/tasks.db')
BASE_PATH     = os.environ.get('BASE_PATH', '')
NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')
NC_ADMIN_USER = os.environ.get('NC_ADMIN_USER', 'admin')  # Admin principal toujours autorisé
# Administrateurs par défaut (voient toutes les tâches) ; surchargeable via la variable DEFAULT_ADMINS (séparés par des virgules)
DEFAULT_ADMINS = [u.strip() for u in os.environ.get('DEFAULT_ADMINS', 'wassef.jlaiel,aziza.kileni').split(',') if u.strip()]
# Seuls ces comptes (+ l'admin principal NC_ADMIN_USER) voient la section « مهام باقي المستخدمين » ;
# surchargeable via la variable VOIR_TOUTES (séparés par des virgules)
VOIR_TOUTES = [u.strip() for u in os.environ.get('VOIR_TOUTES', 'wassef.jlaiel,aziza.kileni').split(',') if u.strip()]


def voit_toutes(uid):
    """Vrai si l'utilisateur voit toutes les tâches de tous les utilisateurs."""
    uid = (uid or '').lower()
    return bool(uid) and uid in [u.lower() for u in [NC_ADMIN_USER] + VOIR_TOUTES]
NC_ADMIN_PASS = os.environ.get('NC_ADMIN_PASS', '')
UPLOAD_DIR    = os.environ.get('UPLOAD_DIR', '/data/uploads')
ALLOWED_EXT   = {'pdf','doc','docx','jpg','jpeg','png','txt','xls','xlsx'}


# SMTP
SMTP_HOST = os.environ.get('SMTP_HOST', 'mail.mwj-lawyers.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
SMTP_FROM = os.environ.get('SMTP_FROM', 'taches@mwj-lawyers.com')

def send_notif_email(to_uids, tache_titre, cree_par, deadline='', description=''):
    """Envoyer notification email aux utilisateurs assignés."""
    if not SMTP_USER or not to_uids:
        return
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    # Récupérer les emails des utilisateurs via occ
    emails = []
    try:
        import docker as docker_sdk
        client = docker_sdk.DockerClient(base_url='unix://var/run/docker.sock')
        container = client.containers.get('nextcloud-nextcloudmwj-wiwcfl-app-1')
        for uid in to_uids:
            uid = uid.strip()
            if not uid: continue
            result = container.exec_run(['php','occ','user:info', uid,'--output=json'], user='www-data')
            if result.exit_code == 0:
                import json
                info = json.loads(result.output.decode())
                email = info.get('email','')
                if email: emails.append(email)
    except Exception as e:
        pass
    if not emails:
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'مهمة جديدة: {tache_titre}'
        msg['From']    = SMTP_FROM
        msg['To']      = ', '.join(emails)
        body = f"""<div dir="rtl" style="font-family:Arial;padding:20px">
<h2 style="color:#1F4E79">📋 مهمة جديدة موجهة إليك</h2>
<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:8px;font-weight:bold;color:#4a5568">العنوان:</td><td style="padding:8px">{tache_titre}</td></tr>
  {'<tr><td style="padding:8px;font-weight:bold;color:#4a5568">الوصف:</td><td style="padding:8px">' + description + '</td></tr>' if description else ''}
  {'<tr><td style="padding:8px;font-weight:bold;color:#4a5568">الموعد:</td><td style="padding:8px">' + deadline + '</td></tr>' if deadline else ''}
  <tr><td style="padding:8px;font-weight:bold;color:#4a5568">أُنشئت بواسطة:</td><td style="padding:8px">{cree_par}</td></tr>
</table>
<p style="margin-top:20px"><a href="http://cabinet.mwj-lawyers.com/mes-taches/" style="background:#2E75B6;color:white;padding:10px 20px;border-radius:6px;text-decoration:none">فتح تطبيق المهام</a></p>
</div>"""
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        import ssl
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=10) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as e:
        pass  # Ne pas bloquer si email échoue

PRIORITIES = {
    'haute':   {'label': 'عالية',   'color': '#e74c3c', 'icon': '🔴'},
    'normale': {'label': 'عادية',   'color': '#2E75B6', 'icon': '🔵'},
    'basse':   {'label': 'منخفضة', 'color': '#27ae60', 'icon': '🟢'},
}
STATUTS = {
    'en_attente': {'label': 'قيد الانتظار', 'color': '#718096', 'icon': '⏳'},
    'en_cours':   {'label': 'جارية',        'color': '#2E75B6', 'icon': '🔄'},
    'terminee':   {'label': 'منجزة',        'color': '#27ae60', 'icon': '✅'},
}


# ─── DB ───────────────────────────────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            cle   TEXT PRIMARY KEY,
            valeur TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO config(cle, valeur) VALUES ('admins', 'admin');
        CREATE TABLE IF NOT EXISTS lectures (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tache_id   INTEGER NOT NULL,
            user_uid   TEXT NOT NULL,
            lu_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(tache_id, user_uid)
        );
        CREATE TABLE IF NOT EXISTS notifs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tache_id   INTEGER NOT NULL,
            user_uid   TEXT NOT NULL,
            vu         INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS commentaires (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tache_id    INTEGER NOT NULL REFERENCES taches(id) ON DELETE CASCADE,
            auteur      TEXT NOT NULL,
            contenu     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS tache_fichiers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tache_id    INTEGER NOT NULL REFERENCES taches(id) ON DELETE CASCADE,
            auteur      TEXT NOT NULL,
            fichier     TEXT NOT NULL,
            fichier_nom TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS taches (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            titre        TEXT NOT NULL,
            description  TEXT NOT NULL DEFAULT '',
            deadline     TEXT NOT NULL DEFAULT '',
            priorite     TEXT NOT NULL DEFAULT 'normale',
            statut       TEXT NOT NULL DEFAULT 'en_attente',
            assigne_a    TEXT NOT NULL,
            cree_par     TEXT NOT NULL,
            fichier      TEXT NOT NULL DEFAULT '',
            fichier_nom  TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    # Migration: colonne contexte
    try:
        conn.execute("ALTER TABLE taches ADD COLUMN contexte TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    conn.close()


# ─── AUTH ─────────────────────────────────────────────────────────────────────
def get_nc_user():
    """Récupérer l'utilisateur connecté via API Nextcloud."""
    # Trouver le cookie Nextcloud
    nc_cookie = None
    nc_cookie_name = None
    for k, v in request.cookies.items():
        if k.startswith('nc_token') or k.startswith('oc_token'):
            nc_cookie = v
            nc_cookie_name = k
            break
    if not nc_cookie:
        for k, v in request.cookies.items():
            if k.startswith('nc_') or k.startswith('oc_'):
                nc_cookie = v
                nc_cookie_name = k
                break
    if not nc_cookie:
        return None
    # Appel API pour récupérer l'utilisateur
    try:
        r = requests.get(
            f"{NEXTCLOUD_URL}/ocs/v2.php/cloud/user",
            cookies={nc_cookie_name: nc_cookie},
            headers={'OCS-APIRequest': 'true', 'Accept': 'application/json'},
            timeout=5, verify=False
        )
        if r.status_code == 200:
            data = r.json()
            uid  = data.get('ocs',{}).get('data',{}).get('id','')
            name = data.get('ocs',{}).get('data',{}).get('displayname', uid)
            if uid:
                return {'uid': uid, 'name': name}
    except Exception:
        pass
    # Fallback: si cookie existe, utiliser le nom du cookie comme uid
    for k in request.cookies:
        if k.startswith('nc_') or k.startswith('oc_'):
            # Cookie présent = utilisateur connecté, récupérer uid depuis cookie sessionid
            uid = request.cookies.get('nc_username', request.cookies.get('oc_username',''))
            if uid:
                return {'uid': uid, 'name': uid}
    return None

def get_admins():
    """Liste des admins : base de données + administrateurs par défaut (toujours présents)."""
    admins = []
    try:
        conn = get_db()
        row = conn.execute("SELECT valeur FROM config WHERE cle='admins'").fetchone()
        conn.close()
        if row:
            admins = [u.strip() for u in row['valeur'].split(',') if u.strip()]
    except Exception:
        pass
    for u in reversed([NC_ADMIN_USER] + DEFAULT_ADMINS):
        if u.lower() not in [a.lower() for a in admins]:
            admins.insert(0, u)
    return admins

def get_nc_user_groups(uid):
    """Récupérer les groupes via Docker SDK (socket)."""
    try:
        import docker as docker_sdk
        client = docker_sdk.DockerClient(base_url='unix://var/run/docker.sock')
        container = client.containers.get('nextcloud-nextcloudmwj-wiwcfl-app-1')
        result = container.exec_run(
            ['php', 'occ', 'user:info', uid, '--output=json'],
            user='www-data'
        )
        if result.exit_code == 0:
            import json
            info = json.loads(result.output.decode())
            return info.get('groups', [])
    except Exception as e:
        pass
    return []

_admin_cache = {}

def is_admin(uid):
    """Admin si: admin principal OU dans la liste admins DB OU dans le groupe Nextcloud 'taches'."""
    if uid == NC_ADMIN_USER:
        return True
    if (uid or '').lower() in [a.lower() for a in get_admins()]:
        return True
    # Cache pour éviter appels Docker répétés
    if uid in _admin_cache:
        return _admin_cache[uid]
    groups = get_nc_user_groups(uid)
    result = 'taches' in groups
    _admin_cache[uid] = result
    return result

def get_nc_users():
    """_ncUsersV2 : utilisateurs Nextcloud (occ via Docker, sinon API OCS)."""
    import json
    # 1) occ dans le conteneur Nextcloud (NC_CONTAINER, sinon detection)
    try:
        import docker as docker_sdk
        client = docker_sdk.DockerClient(base_url='unix://var/run/docker.sock')
        nom = os.environ.get('NC_CONTAINER', '').strip()
        conteneurs = [client.containers.get(nom)] if nom else [
            k for k in client.containers.list()
            if 'nextcloud' in ' '.join(k.image.tags).lower() + k.name.lower()
            and not any(x in k.name.lower() for x in ('cron', 'db', 'redis', 'proxy', 'notify', 'push'))
        ]
        for k in conteneurs:
            r = k.exec_run(['php', 'occ', 'user:list', '--output=json'], user='www-data')
            if r.exit_code == 0:
                return sorted(json.loads(r.output.decode()).keys())
    except Exception:
        pass
    # 2) API OCS avec le compte admin
    try:
        import requests
        if NC_ADMIN_PASS:
            r = requests.get(f"{NEXTCLOUD_URL}/ocs/v1.php/cloud/users?format=json",
                             auth=(NC_ADMIN_USER, NC_ADMIN_PASS),
                             headers={'OCS-APIRequest': 'true'}, timeout=8)
            if r.ok:
                return sorted(r.json().get('ocs', {}).get('data', {}).get('users', []))
    except Exception:
        pass
    return []

def require_auth():
    user = get_nc_user()
    if not user:
        return redirect(f"{NEXTCLOUD_URL}/login?redirect_url={BASE_PATH}/")
    return user

@app.context_processor
def inject_globals():
    return {'BASE': BASE_PATH, 'PRIORITIES': PRIORITIES, 'STATUTS': STATUTS,
            'today': date.today().isoformat(), 'is_admin': is_admin}


# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.template_filter('fromjson')
def _fromjson_filter(s):
    import json
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


@app.template_filter('avc')
def _avatar_color(nom):
    """Couleur stable de la pastille d'un utilisateur (même nom → même couleur)."""
    palette = ['#3E7FD1', '#B5862B', '#2E9E57', '#7A6FB0', '#C25B4A', '#1E8C9A', '#8C6A4E']
    return palette[sum(ord(c) for c in (nom or '')) % len(palette)]


@app.template_filter('ctx_info')
def _ctx_info_filter(s):
    """Résumé du tableau lié à une tâche : titre, nombre de lignes, lignes « منجز », pourcentage."""
    d = _fromjson_filter(s)
    if not isinstance(d, dict) or not d.get('tableau'):
        return None
    champs = d.get('champs') or {}
    tailles = [len(v) if isinstance(v, list) else (1 if v else 0) for v in champs.values()]
    total = max(tailles) if tailles else 0
    manjez = d.get('manjez') or []
    done = sum(1 for i in range(total) if i < len(manjez) and manjez[i])
    return {'titre': d.get('titre', ''), 'extra': d.get('titre_extra', ''),
            'total': total, 'done': done, 'pct': int(round(100.0 * done / total)) if total else 0}


@app.route('/')
def index():
    user = get_nc_user()
    if not user:
        return redirect(f"{NEXTCLOUD_URL}/login?redirect_url={BASE_PATH}/")
    conn = get_db()
    all_taches = conn.execute(
        "SELECT * FROM taches ORDER BY "
        "CASE priorite WHEN 'haute' THEN 1 WHEN 'normale' THEN 2 ELSE 3 END, deadline ASC"
    ).fetchall()
    # Notifs non lues (calculé avant le tri)
    try:
        notifs_map = {r[0]: r[1] for r in conn.execute(
            "SELECT tache_id, MAX(created_at) FROM notifs WHERE user_uid=? AND vu=0 GROUP BY tache_id",
            (user['uid'],)
        ).fetchall()}
    except Exception:
        notifs_map = {}
    from datetime import datetime as _dt
    def sort_key(t):
        # 1. Non lues en premier (0 avant 1)
        has_notif = 1 if t['id'] not in notifs_map else 0
        # 2. Plus récente en premier = timestamp négatif
        try:
            ts = -_dt.strptime(t['created_at'][:19], '%Y-%m-%d %H:%M:%S').timestamp()
        except Exception:
            ts = 0
        return (has_notif, ts)
    mes_taches = sorted([t for t in all_taches if user['uid'] in t['assigne_a'].split(',')], key=sort_key)
    taches_creees = sorted([t for t in all_taches if t['cree_par'] == user['uid'] and user['uid'] not in t['assigne_a'].split(',')], key=sort_key)
    toutes = None
    user_is_admin = is_admin(user['uid'])
    # « مهام باقي المستخدمين » : réservé à la liste VOIR_TOUTES (pas à tous les administrateurs)
    if voit_toutes(user['uid']):
        toutes = conn.execute("SELECT * FROM taches ORDER BY created_at DESC").fetchall()
    # Notifs non lues
    notifs_ids = set(notifs_map.keys())
    conn.close()
    vue      = 'all'
    filtre_statut = request.args.get('statut', '')
    recherche     = request.args.get('q', '').strip().lower()

    def appliquer_filtres(liste):
        if filtre_statut == 'retard':   # tuile « متأخرة » : échéance dépassée et non terminée
            auj = date.today().isoformat()
            liste = [t for t in liste if t['deadline'] and t['deadline'] < auj and t['statut'] != 'terminee']
        elif filtre_statut:
            liste = [t for t in liste if t['statut'] == filtre_statut]
        if recherche:
            liste = [t for t in liste if
                     recherche in t['titre'].lower() or
                     recherche in (t['description'] or '').lower() or
                     recherche in t['assigne_a'].lower() or
                     recherche in t['cree_par'].lower()]
        return liste

    # Compteurs (avant filtres) pour les tuiles du haut
    today_s = date.today().isoformat()
    # Administrateurs : les tuiles portent sur TOUTES les tâches ; sinon sur les tâches qui me sont assignées
    base = list(toutes) if toutes is not None else mes_taches
    stats = {
        'scope':   'all' if toutes is not None else 'mes',
        'mes':     len(base),
        'attente': sum(1 for t in base if t['statut'] == 'en_attente'),
        'cours':   sum(1 for t in base if t['statut'] == 'en_cours'),
        'fini':    sum(1 for t in base if t['statut'] == 'terminee'),
        'retard':  sum(1 for t in base if t['deadline'] and t['deadline'] < today_s and t['statut'] != 'terminee'),
        'creees':  len(taches_creees),
        'nonlues': sum(1 for t in mes_taches + taches_creees if t['id'] in notifs_ids),
    }

    mes_taches    = appliquer_filtres(mes_taches)
    taches_creees = appliquer_filtres(taches_creees)
    if toutes is not None:
        # Administrateurs : TOUTES les tâches de tous les utilisateurs (comme ncadmin)
        toutes = appliquer_filtres(list(toutes))

    return render_template('index.html', user=user, mes_taches=mes_taches,
                           taches_creees=taches_creees, toutes=toutes,
                           notifs_ids=notifs_ids, vue=vue, stats=stats,
                           filtre_statut=filtre_statut, recherche=recherche)

@app.route('/nouvelle', methods=['GET', 'POST'])
def nouvelle():
    user = get_nc_user()
    if not user: return redirect(f"{NEXTCLOUD_URL}/login")

    if request.method == 'POST':
        f = request.form
        titre      = f.get('titre','').strip()
        desc       = f.get('description','').strip()
        contexte   = f.get('contexte','').strip()
        deadline   = f.get('deadline','')
        priorite   = f.get('priorite','normale')
        assigne_a  = f.get('assigne_a','').strip()

        # L'assignation est facultative : sans assigné, la tâche apparaît dans "التي أنشأتها"
        if not titre:
            flash('Le titre est obligatoire', 'error')
            return redirect(f"{BASE_PATH}/nouvelle")

        # Upload fichier
        fichier = ''; fichier_nom = ''
        file = request.files.get('fichier')
        if file and file.filename:
            ext = file.filename.rsplit('.',1)[-1].lower()
            if ext in ALLOWED_EXT:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                fname = secure_filename(f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(UPLOAD_DIR, fname))
                fichier = fname; fichier_nom = file.filename

        conn = get_db()
        cur = conn.execute("""
            INSERT INTO taches (titre, description, contexte, deadline, priorite, assigne_a, cree_par, fichier, fichier_nom)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (titre, desc, contexte, deadline, priorite, assigne_a, user['uid'], fichier, fichier_nom))
        doc_id = cur.lastrowid
        # Notifier les assignés AVANT commit
        notif_uids = [u.strip() for u in assigne_a.split(',') if u.strip() and u.strip() != user['uid']]
        for uid_n in notif_uids:
            conn.execute("INSERT INTO notifs(tache_id, user_uid) VALUES(?,?)", (doc_id, uid_n))
        conn.commit(); conn.close()
        # Envoyer email si demandé
        uids = [u.strip() for u in assigne_a.split(',') if u.strip()]
        if f.get('notif_email') and uids:
            send_notif_email(uids, titre, user['uid'],
                           deadline=f.get('deadline',''),
                           description=desc)
        flash(f'تم إنشاء المهمة وتعيينها لـ {assigne_a}' if uids else 'تم إنشاء المهمة', 'success')
        return redirect(f"{BASE_PATH}/")

    users = get_nc_users()
    return render_template('nouvelle.html', user=user, nc_users=users)

@app.route('/tache/<int:tid>/statut', methods=['POST'])
def update_statut(tid):
    user = get_nc_user()
    if not user: return redirect(f"{NEXTCLOUD_URL}/login")
    statut = request.form.get('statut','en_attente')
    conn = get_db()
    # Seul l'assigné ou l'admin peut changer le statut
    t = conn.execute("SELECT assigne_a, cree_par FROM taches WHERE id=?", (tid,)).fetchone()
    if t and (user['uid'] in t['assigne_a'].split(',') or t['cree_par'] == user['uid'] or is_admin(user['uid'])):
        conn.execute("UPDATE taches SET statut=?, updated_at=datetime('now','localtime') WHERE id=?", (statut, tid))
        uids_all = set(t['assigne_a'].split(',') + [t['cree_par']])
        uids_all.discard(user['uid'])
        for uid in uids_all:
            uid = uid.strip()
            if uid:
                try:
                    conn.execute("INSERT INTO notifs(tache_id, user_uid) VALUES(?,?)", (tid, uid))
                except Exception:
                    pass
        conn.commit()
    conn.close()
    # Depuis la page de détail, on y reste après le changement de statut
    if request.form.get('retour') == 'detail':
        return redirect(f"{BASE_PATH}/tache/{tid}")
    return redirect(f"{BASE_PATH}/")

@app.route('/tache/<int:tid>/delete', methods=['POST'])
def delete_tache(tid):
    user = get_nc_user()
    if not user or not is_admin(user['uid']):
        flash('Accès refusé', 'error')
        return redirect(f"{BASE_PATH}/")
    conn = get_db()
    t = conn.execute("SELECT fichier FROM taches WHERE id=?", (tid,)).fetchone()
    if t and t['fichier']:
        try: os.remove(os.path.join(UPLOAD_DIR, t['fichier']))
        except: pass
    conn.execute("DELETE FROM taches WHERE id=?", (tid,))
    conn.commit(); conn.close()
    flash('تم حذف المهمة', 'warning')
    return redirect(f"{BASE_PATH}/")

@app.route('/fichier/<filename>')
def serve_file(filename):
    user = get_nc_user()
    if not user: return redirect(f"{NEXTCLOUD_URL}/login")
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/api/mes-taches')
def api_mes_taches():
    """API pour le dashboard — tâches non lues uniquement."""
    user = get_nc_user()
    if not user: return jsonify([])
    conn = get_db()
    # Récupérer les tache_ids avec notifs non lues pour cet utilisateur
    try:
        notif_ids = set(r[0] for r in conn.execute(
            "SELECT DISTINCT tache_id FROM notifs WHERE user_uid=? AND vu=0",
            (user['uid'],)
        ).fetchall())
    except Exception:
        notif_ids = set()
    if not notif_ids:
        conn.close()
        return jsonify([])
    placeholders = ','.join('?' * len(notif_ids))
    rows = conn.execute(
        f"SELECT id, titre, priorite, statut, deadline, cree_par FROM taches "
        f"WHERE id IN ({placeholders}) AND statut != 'terminee' "
        f"ORDER BY created_at DESC LIMIT 10",
        list(notif_ids)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/parametres', methods=['GET', 'POST'])
def parametres():
    user = get_nc_user()
    if not user or not is_admin(user['uid']):
        flash('Accès refusé', 'error')
        return redirect(f"{BASE_PATH}/")
    conn = get_db()
    if request.method == 'POST':
        admins = request.form.get('admins', NC_ADMIN_USER).strip()
        # S'assurer que NC_ADMIN_USER est toujours dans la liste
        admins_list = [u.strip() for u in admins.split(',') if u.strip()]
        # Les administrateurs par défaut restent toujours dans la liste
        for u in reversed([NC_ADMIN_USER] + DEFAULT_ADMINS):
            if u.lower() not in [a.lower() for a in admins_list]:
                admins_list.insert(0, u)
        conn.execute("INSERT OR REPLACE INTO config(cle, valeur) VALUES ('admins', ?)",
                     (','.join(admins_list),))
        conn.commit()
        conn.close()
        flash('تم حفظ قائمة المديرين', 'success')
        return redirect(f"{BASE_PATH}/parametres")
    row = conn.execute("SELECT valeur FROM config WHERE cle='admins'").fetchone()
    admins = ','.join(get_admins())   # liste en base + administrateurs par défaut
    nc_users = get_nc_users()
    conn.close()
    return render_template('parametres.html', user=user, admins=admins, nc_users=nc_users)


@app.route('/tache/<int:tid>')
def tache_detail(tid):
    user = get_nc_user()
    if not user: return redirect(f"{NEXTCLOUD_URL}/login")
    conn = get_db()
    t = conn.execute("SELECT * FROM taches WHERE id=?", (tid,)).fetchone()
    if not t or (user['uid'] not in t['assigne_a'].split(',') and t['cree_par'] != user['uid'] and not is_admin(user['uid'])):
        conn.close()
        flash('غير مصرح', 'error')
        return redirect(f"{BASE_PATH}/")
    commentaires = conn.execute(
        "SELECT * FROM commentaires WHERE tache_id=? ORDER BY created_at ASC", (tid,)
    ).fetchall()
    fichiers = conn.execute(
        "SELECT * FROM tache_fichiers WHERE tache_id=? ORDER BY created_at DESC", (tid,)
    ).fetchall()
    conn.close()
    user_is_admin = is_admin(user['uid'])
    can_edit = user_is_admin or t['cree_par'] == user['uid']
    # Marquer comme lu (même connexion)
    try:
        conn.execute("INSERT OR REPLACE INTO lectures(tache_id, user_uid) VALUES(?,?)", (tid, user['uid']))
        conn.execute("UPDATE notifs SET vu=1 WHERE tache_id=? AND user_uid=?", (tid, user['uid']))
        conn.commit()
    except Exception:
        pass
    conn.close()
    return render_template('tache_detail.html', user=user, t=t,
                           commentaires=commentaires, fichiers=fichiers,
                           user_is_admin=user_is_admin, can_edit=can_edit)

@app.route('/tache/<int:tid>/commenter', methods=['POST'])
def commenter(tid):
    user = get_nc_user()
    if not user: return redirect(f"{NEXTCLOUD_URL}/login")
    contenu = request.form.get('contenu','').strip()
    if contenu:
        conn = get_db()
        # Vérifier accès
        t = conn.execute("SELECT assigne_a, cree_par FROM taches WHERE id=?", (tid,)).fetchone()
        if t and (user['uid'] in t['assigne_a'].split(',') or t['cree_par'] == user['uid'] or is_admin(user['uid'])):
            conn.execute(
                "INSERT INTO commentaires (tache_id, auteur, contenu) VALUES (?,?,?)",
                (tid, user['uid'], contenu)
            )
            # Notifier les autres utilisateurs
            t_row = conn.execute("SELECT assigne_a, cree_par FROM taches WHERE id=?", (tid,)).fetchone()
            if t_row:
                uids = set(t_row['assigne_a'].split(',') + [t_row['cree_par']])
                uids.discard(user['uid'])
                for uid in uids:
                    conn.execute("INSERT INTO notifs(tache_id, user_uid) VALUES(?,?)", (tid, uid.strip()))
            conn.commit()
        conn.close()
    return redirect(f"{BASE_PATH}/tache/{tid}")

@app.route('/tache/<int:tid>/upload', methods=['POST'])
def upload_tache(tid):
    user = get_nc_user()
    if not user: return redirect(f"{NEXTCLOUD_URL}/login")
    conn = get_db()
    t = conn.execute("SELECT assigne_a, cree_par FROM taches WHERE id=?", (tid,)).fetchone()
    if t and (user['uid'] in t['assigne_a'].split(',') or t['cree_par'] == user['uid'] or is_admin(user['uid'])):
        file = request.files.get('fichier')
        if file and file.filename:
            ext = file.filename.rsplit('.',1)[-1].lower()
            if ext in ALLOWED_EXT:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                fname = secure_filename(f"task{tid}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(UPLOAD_DIR, fname))
                conn.execute(
                    "INSERT INTO tache_fichiers (tache_id, auteur, fichier, fichier_nom) VALUES (?,?,?,?)",
                    (tid, user['uid'], fname, file.filename)
                )
                t_row2 = conn.execute("SELECT assigne_a, cree_par FROM taches WHERE id=?", (tid,)).fetchone()
                if t_row2:
                    uids2 = set(t_row2['assigne_a'].split(',') + [t_row2['cree_par']])
                    uids2.discard(user['uid'])
                    for uid2 in uids2:
                        conn.execute("INSERT INTO notifs(tache_id, user_uid) VALUES(?,?)", (tid, uid2.strip()))
                conn.commit()
                flash('تم رفع الملف بنجاح', 'success')
    conn.close()
    return redirect(f"{BASE_PATH}/tache/{tid}")


@app.route('/tache/<int:tid>/edit', methods=['GET', 'POST'])
def tache_edit(tid):
    user = get_nc_user()
    conn = get_db()
    t = conn.execute("SELECT * FROM taches WHERE id=?", (tid,)).fetchone()
    if not t:
        conn.close()
        return redirect(f"{BASE_PATH}/")
    if not user or (not is_admin(user['uid']) and t['cree_par'] != user['uid']):
        conn.close()
        flash('غير مصرح', 'error')
        return redirect(f"{BASE_PATH}/")
    if request.method == 'POST':
        f = request.form
        contexte = f.get('contexte','').strip()
        assigne_a = f.get('assigne_a','').strip()   # facultatif
        conn.execute("""
            UPDATE taches SET titre=?, description=?, contexte=?, deadline=?,
            priorite=?, assigne_a=?, updated_at=datetime('now','localtime')
            WHERE id=?
        """, (f.get('titre',''), f.get('description',''), contexte,
              f.get('deadline',''), f.get('priorite','normale'),
              assigne_a, tid))
        conn.commit(); conn.close()
        flash('تم تحديث المهمة', 'success')
        return redirect(f"{BASE_PATH}/tache/{tid}")
    nc_users = get_nc_users()
    conn.close()
    return render_template('tache_edit.html', user=user, t=t, nc_users=nc_users)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5008)), debug=False)

init_db()
